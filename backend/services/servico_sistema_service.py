"""Serviço do Sistema > aba "Atualização" — configuração + orquestração da
atualização automática de Backend/Frontend nesta instalação de cliente.

Substitui, como MECANISMO DE DISPARO, a Tarefa Agendada Windows
independente (`updater/install-updater-task.ps1`, pausada por decisão do
usuário 2026-08-26) — o disparo periódico agora é uma tarefa de fundo
DENTRO do próprio processo do backend (ver `server.py`'s `lifespan` +
`loop_verificacao_atualizacao` abaixo), configurável por esta tela. A
etapa de baixar/trocar/reverter versão continua sendo o script
`updater/apply_update.ps1` já escrito e testado (parse-check) — este
service só grava a configuração, escreve um `config.json` fresco pro
script ler, e o invoca como subprocesso.

**Restrição real de arquitetura** (todo o resto deste backend é
parametrizado por `servidor`+`banco` por requisição — não existe uma
"conexão padrão" do processo): ao gravar a configuração via
`save_config`, também escrevemos `backend/updater_conn.json`
(`{servidor, banco}`) — é assim que a tarefa de fundo, que roda sem
nenhuma requisição HTTP, sabe contra qual banco checar a cada ciclo. Ver
PENDENCIAS.md > "Serviço do Sistema — Atualização" pro desenho completo.

**Aplicar nunca é automático** — o ciclo de fundo só CHECA e BAIXA
(`-Mode DownloadOnly`, nunca troca a versão em produção sozinho); trocar
(`aplicar_atualizacao`) e reverter (`reverter_atualizacao`) são sempre
ação explícita do usuário master pela tela, avisado via o badge no menu
lateral quando há algo pendente.
"""
import asyncio
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from db.connection import _open_conn

# Achado real (Adriana/suporte, 2026-08-28, instalação real "KONTACTO
# APP"): `.resolve()` aqui RESOLVE a junction `current-backend` pro seu
# alvo real (`releases\<commit>\backend`) — em qualquer instalação real
# (ver `bootstrap-install.ps1`/"Guia de Instalacao.md"), o backend roda
# de DENTRO da junction `<InstallDir>\current-backend`, cujo pai é
# `<InstallDir>` (onde `updater\` mora de verdade, ao lado de
# `current-backend`/`current-frontend` — nunca dentro de `releases\`).
# Resolver a junction troca `<InstallDir>` por `<InstallDir>\releases\
# <commit>`, e a conta de `_UPDATER_DIR` abaixo erra o caminho de
# `apply_update.ps1` (erro real reportado: "F:\BackOn\releases\updater\
# apply_update.ps1" não existe — o real seria "F:\BackOn\updater\...").
# `bootstrap-install.ps1` registra a Tarefa Agendada rodando DE DENTRO da
# junction exatamente pra manter esse caminho ESTÁVEL entre atualizações
# — nunca resolver essa junction é o comportamento correto, não um
# detalhe incidental. Só funcionava sem bug no repositório de
# desenvolvimento porque lá não existe junction nenhuma (backend/ e
# updater/ já são pastas irmãs de verdade).
_BACKEND_ROOT = Path(__file__).parent.parent
_UPDATER_DIR = _BACKEND_ROOT.parent / "updater"
_APPLY_SCRIPT = _UPDATER_DIR / "apply_update.ps1"
_UPDATER_CONFIG_PATH = _UPDATER_DIR / "config.json"
_UPDATER_STATE_PATH = _UPDATER_DIR / "state.json"
_CONN_FILE = _BACKEND_ROOT / "updater_conn.json"

_INTERVALO_CICLO_SEGUNDOS = 60  # granularidade do "relógio" do loop de fundo — não é o intervalo configurado pelo usuário, ver loop_verificacao_atualizacao

_CONFIG_PADRAO = {
    "manifest_url": "",
    "pasta_backend": "",
    "pasta_frontend": "",
    "intervalo_minutos": 30,
    "canal": "H",
    "cel_suporte": "",
    "commit_atual": None,
    "commit_anterior": None,
    "commit_pendente": None,
    "pendente_desde": None,
    "ultima_verificacao": None,
    "ultimo_erro": None,
    "manutencao_indices_ativo": True,
    "manutencao_indices_dias_semana": "0,1,2,3,4,5,6",
    "manutencao_indices_hora": "03:00",
    "manutencao_indices_ultima_execucao": None,
    "manutencao_indices_ultimo_resultado": None,
    # Extensão 2026-08-31 (Áureo, análise DBA de RJPNEUS-TESTE) — ver
    # services/manutencao_indices_service.py pro racional completo de
    # cada campo novo.
    "manutencao_indices_orcamento_minutos": 120,
    "checkdb_ativo": True,
    "checkdb_dias_semana": "0",
    "checkdb_hora": "04:00",
    "checkdb_ultima_execucao": None,
    "checkdb_ultimo_resultado": None,
    "espaco_pct_usado": None,
    "espaco_verificado_em": None,
}


def _row_to_dict(r: dict) -> dict:
    return dict(r)


def _ensure_servico_sistema_atualizacao_table(cur) -> None:
    """Migração idempotente (mesmo padrão de
    `balanca_service._ensure_balancas_table`) — tabela nova, linha única
    (config global desta instalação, sem chave por empresa)."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'servico_sistema_atualizacao') "
        "CREATE TABLE servico_sistema_atualizacao ("
        "codigo INT IDENTITY(1,1) PRIMARY KEY, "
        "manifest_url NVARCHAR(1000) NULL, "
        "pasta_backend NVARCHAR(400) NULL, "
        "pasta_frontend NVARCHAR(400) NULL, "
        "intervalo_minutos INT NOT NULL DEFAULT 30, "
        "canal NVARCHAR(1) NOT NULL DEFAULT 'H', "
        "cel_suporte NVARCHAR(20) NULL, "
        "commit_atual NVARCHAR(40) NULL, "
        "commit_anterior NVARCHAR(40) NULL, "
        "commit_pendente NVARCHAR(40) NULL, "
        "pendente_desde DATETIME NULL, "
        "ultima_verificacao DATETIME NULL, "
        "ultimo_erro NVARCHAR(500) NULL, "
        "manutencao_indices_ativo BIT NOT NULL DEFAULT 1, "
        "manutencao_indices_dias_semana NVARCHAR(20) NOT NULL DEFAULT '0,1,2,3,4,5,6', "
        "manutencao_indices_hora NVARCHAR(5) NOT NULL DEFAULT '03:00', "
        "manutencao_indices_ultima_execucao DATETIME NULL, "
        "manutencao_indices_ultimo_resultado NVARCHAR(500) NULL)"
    )
    # `canal` adicionado 2026-08-28 (Homologação/Produção) — instalação já
    # existente (ex.: a máquina real do Juan/Kontacto) pode ter a tabela
    # sem essa coluna; ADD separado cobre esse caso, além do CREATE acima
    # cobrir instalação nova. Default 'H' (Homologação) — seguro por
    # padrão, nenhuma instalação passa a aplicar em Produção sem
    # configuração explícita.
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'canal') "
        "ALTER TABLE servico_sistema_atualizacao ADD canal NVARCHAR(1) NOT NULL DEFAULT 'H'"
    )
    # `cel_suporte` adicionado 2026-08-28 (Apoio Fiscal BackOn) — número de
    # WhatsApp do SUPORTE (Kontacto), não do cliente/lojista. Destino das
    # notificações automáticas de rejeição fiscal quando o cliente já tem
    # o serviço de WhatsApp configurado (ver apoio_fiscal_service.py).
    # Opcional, em branco por padrão — cada instalação configura a dela.
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'cel_suporte') "
        "ALTER TABLE servico_sistema_atualizacao ADD cel_suporte NVARCHAR(20) NULL"
    )
    # Manutenção automática de índices/estatística (2026-08-28) — ver
    # services/manutencao_indices_service.py. Config mora aqui porque é a
    # mesma ideia de "config de serviço em background desta instalação"
    # que a Atualização já é, não uma tabela nova. `dias_semana` segue a
    # mesma convenção 0=domingo..6=sábado já usada em `Web_DiasSemana`
    # (produto_completo_service.py). `ativo` liga por padrão (decisão do
    # usuário: roda automático em todo banco) — existe só como "desliga
    # de emergência" por instalação, sem precisar mexer em código.
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'manutencao_indices_ativo') "
        "ALTER TABLE servico_sistema_atualizacao ADD manutencao_indices_ativo BIT NOT NULL DEFAULT 1"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'manutencao_indices_dias_semana') "
        "ALTER TABLE servico_sistema_atualizacao ADD manutencao_indices_dias_semana NVARCHAR(20) NOT NULL DEFAULT '0,1,2,3,4,5,6'"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'manutencao_indices_hora') "
        "ALTER TABLE servico_sistema_atualizacao ADD manutencao_indices_hora NVARCHAR(5) NOT NULL DEFAULT '03:00'"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'manutencao_indices_ultima_execucao') "
        "ALTER TABLE servico_sistema_atualizacao ADD manutencao_indices_ultima_execucao DATETIME NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'manutencao_indices_ultimo_resultado') "
        "ALTER TABLE servico_sistema_atualizacao ADD manutencao_indices_ultimo_resultado NVARCHAR(500) NULL"
    )
    # Extensão 2026-08-31 (Áureo, análise DBA de RJPNEUS-TESTE — ver
    # PENDENCIAS.md) — 4 recursos novos de manutenção, ver
    # services/manutencao_indices_service.py pro racional completo:
    # orçamento de tempo/circuit breaker pro REBUILD, agenda própria de
    # `DBCC CHECKDB`, e cache da última checagem de espaço vs. teto do
    # SQL Server Express (10GB).
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'manutencao_indices_orcamento_minutos') "
        "ALTER TABLE servico_sistema_atualizacao ADD manutencao_indices_orcamento_minutos INT NOT NULL DEFAULT 120"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'checkdb_ativo') "
        "ALTER TABLE servico_sistema_atualizacao ADD checkdb_ativo BIT NOT NULL DEFAULT 1"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'checkdb_dias_semana') "
        "ALTER TABLE servico_sistema_atualizacao ADD checkdb_dias_semana NVARCHAR(20) NOT NULL DEFAULT '0'"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'checkdb_hora') "
        "ALTER TABLE servico_sistema_atualizacao ADD checkdb_hora NVARCHAR(5) NOT NULL DEFAULT '04:00'"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'checkdb_ultima_execucao') "
        "ALTER TABLE servico_sistema_atualizacao ADD checkdb_ultima_execucao DATETIME NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'checkdb_ultimo_resultado') "
        "ALTER TABLE servico_sistema_atualizacao ADD checkdb_ultimo_resultado NVARCHAR(500) NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'espaco_pct_usado') "
        "ALTER TABLE servico_sistema_atualizacao ADD espaco_pct_usado FLOAT NULL"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('servico_sistema_atualizacao') "
        "AND name = 'espaco_verificado_em') "
        "ALTER TABLE servico_sistema_atualizacao ADD espaco_verificado_em DATETIME NULL"
    )


def _get_config_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_servico_sistema_atualizacao_table(cur)
        conn.commit()
        cur.execute(
            "SELECT TOP 1 codigo, manifest_url, pasta_backend, pasta_frontend, intervalo_minutos, canal, cel_suporte, "
            "commit_atual, commit_anterior, commit_pendente, pendente_desde, ultima_verificacao, ultimo_erro, "
            "manutencao_indices_ativo, manutencao_indices_dias_semana, manutencao_indices_hora, "
            "manutencao_indices_ultima_execucao, manutencao_indices_ultimo_resultado, "
            "manutencao_indices_orcamento_minutos, checkdb_ativo, checkdb_dias_semana, checkdb_hora, "
            "checkdb_ultima_execucao, checkdb_ultimo_resultado, espaco_pct_usado, espaco_verificado_em "
            "FROM servico_sistema_atualizacao ORDER BY codigo DESC"
        )
        row = cur.fetchone()
        dados = _row_to_dict(row) if row else dict(_CONFIG_PADRAO)
        dados.pop("codigo", None)

        # Reconciliação com `state.json` — achado real 2026-09-01 (máquina
        # "SUPORTE"/Adriana): `commit_atual`/`commit_anterior` eram colunas
        # da tabela, expostas na tela ("Versão atual"), mas NUNCA gravadas
        # em lugar nenhum do código — `-Mode ApplyPending`/`Rollback`
        # rodam como subprocesso DETACHED (ver `_disparar_ps1_detached`),
        # o Python nunca fica sabendo quando terminam pra atualizar o
        # banco. "Versão atual" ficava sempre em branco, mesmo depois de
        # uma atualização aplicada com sucesso (inclusive aplicada
        # manualmente via `apply_update.ps1 -Mode Full` direto no
        # PowerShell, sem passar pela tela). Corrigido lendo o valor real
        # (`state.json`'s campo `commit`, a mesma fonte de verdade que
        # `apply_update.ps1` já usa) toda vez que a config é carregada —
        # sincroniza o banco se estiver desatualizado, sem depender de
        # capturar o momento exato em que o subprocesso termina.
        commit_local = _ler_commit_atual()
        if row and commit_local and commit_local != dados.get("commit_atual"):
            commit_anterior = dados.get("commit_atual")
            cur.execute(
                "UPDATE servico_sistema_atualizacao SET commit_atual=%s, commit_anterior=%s WHERE codigo=%s",
                (commit_local, commit_anterior, row["codigo"]),
            )
            conn.commit()
            dados["commit_atual"] = commit_local
            dados["commit_anterior"] = commit_anterior

        cur.close()
        conn.close()
        return {"success": True, "dados": dados}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_config_sync(servidor: str, banco: str, dados: dict) -> dict:
    manifest_url = (dados.get("manifest_url") or "").strip()
    pasta_backend = (dados.get("pasta_backend") or "").strip()
    pasta_frontend = (dados.get("pasta_frontend") or "").strip()
    raw_intervalo = dados.get("intervalo_minutos")
    try:
        intervalo_minutos = int(raw_intervalo) if raw_intervalo not in (None, "") else 30
    except (TypeError, ValueError):
        return {"success": False, "message": "Intervalo de verificação inválido."}
    # 0 = verificação automática DESLIGADA (só manual, via "Verificar agora")
    # — pedido explícito do usuário, 2026-08-26. Qualquer valor entre 1 e 4
    # continua recusado (mesmo mínimo de sempre), pra não virar um polling
    # agressivo sem querer.
    if intervalo_minutos < 0 or (0 < intervalo_minutos < 5):
        return {"success": False, "message": "O intervalo deve ser 0 (desliga a verificação automática) ou no mínimo 5 minutos."}

    # Canal — 'H' (Homologação, equipe) ou 'P' (Produção, clientes).
    # Adicionado 2026-08-28, ver docstring do módulo/CLAUDE.md > "Padrões
    # de UI" pro desenho completo (Homologação só aplica pela tela cheia;
    # Produção só aplica pelo botão "Atualizar Sistema" do Sidebar).
    canal = (dados.get("canal") or "H").strip().upper()
    if canal not in ("H", "P"):
        return {"success": False, "message": "Canal inválido — use Homologação ou Produção."}

    # "Cel Suporte" (Apoio Fiscal BackOn, 2026-08-28) — só dígitos/+,
    # nenhuma validação forte de formato (normalizado na hora de usar via
    # services/whatsapp/service.py::normalize_phone, ver
    # apoio_fiscal_service.py::notificar_rejeicao_sync).
    cel_suporte = (dados.get("cel_suporte") or "").strip()

    # Manutenção automática de índices (2026-08-28) — ver
    # services/manutencao_indices_service.py pro que essas 3 colunas
    # controlam. Validação frouxa de propósito (mesmo espírito de
    # `cel_suporte` acima): formato errado cai no default seguro em vez
    # de bloquear o Gravar por um campo que não é crítico.
    manutencao_ativo = bool(dados.get("manutencao_indices_ativo", True))
    dias_raw = (dados.get("manutencao_indices_dias_semana") or "").strip()
    dias_validos = {p.strip() for p in dias_raw.split(",") if p.strip().isdigit() and 0 <= int(p.strip()) <= 6}
    manutencao_dias = ",".join(sorted(dias_validos, key=int)) if dias_validos else "0,1,2,3,4,5,6"
    hora_raw = (dados.get("manutencao_indices_hora") or "").strip()
    manutencao_hora = "03:00"
    if len(hora_raw) == 5 and hora_raw[2] == ":" and hora_raw[:2].isdigit() and hora_raw[3:].isdigit():
        h, m = int(hora_raw[:2]), int(hora_raw[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            manutencao_hora = hora_raw

    # Extensão 2026-08-31 (Áureo) — orçamento de tempo (circuit breaker
    # do REBUILD) + agenda própria de CHECKDB. Mesma validação frouxa dos
    # campos de manutenção acima: formato errado cai no default seguro,
    # nunca bloqueia o Gravar por um campo não-crítico.
    raw_orcamento = dados.get("manutencao_indices_orcamento_minutos")
    try:
        orcamento_minutos = int(raw_orcamento) if raw_orcamento not in (None, "") else 120
        if orcamento_minutos < 1:
            orcamento_minutos = 120
    except (TypeError, ValueError):
        orcamento_minutos = 120

    checkdb_ativo = bool(dados.get("checkdb_ativo", True))
    checkdb_dias_raw = (dados.get("checkdb_dias_semana") or "").strip()
    checkdb_dias_validos = {p.strip() for p in checkdb_dias_raw.split(",") if p.strip().isdigit() and 0 <= int(p.strip()) <= 6}
    checkdb_dias = ",".join(sorted(checkdb_dias_validos, key=int)) if checkdb_dias_validos else "0"
    checkdb_hora_raw = (dados.get("checkdb_hora") or "").strip()
    checkdb_hora = "04:00"
    if len(checkdb_hora_raw) == 5 and checkdb_hora_raw[2] == ":" and checkdb_hora_raw[:2].isdigit() and checkdb_hora_raw[3:].isdigit():
        h, m = int(checkdb_hora_raw[:2]), int(checkdb_hora_raw[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            checkdb_hora = checkdb_hora_raw

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_servico_sistema_atualizacao_table(cur)
        conn.commit()
        cur.execute("SELECT TOP 1 codigo FROM servico_sistema_atualizacao ORDER BY codigo DESC")
        existente = cur.fetchone()
        if existente:
            cur.execute(
                "UPDATE servico_sistema_atualizacao SET manifest_url=%s, pasta_backend=%s, "
                "pasta_frontend=%s, intervalo_minutos=%s, canal=%s, cel_suporte=%s, "
                "manutencao_indices_ativo=%s, manutencao_indices_dias_semana=%s, manutencao_indices_hora=%s, "
                "manutencao_indices_orcamento_minutos=%s, checkdb_ativo=%s, checkdb_dias_semana=%s, checkdb_hora=%s "
                "WHERE codigo=%s",
                (manifest_url, pasta_backend, pasta_frontend, intervalo_minutos, canal, cel_suporte,
                 manutencao_ativo, manutencao_dias, manutencao_hora,
                 orcamento_minutos, checkdb_ativo, checkdb_dias, checkdb_hora, existente["codigo"]),
            )
        else:
            cur.execute(
                "INSERT INTO servico_sistema_atualizacao (manifest_url, pasta_backend, pasta_frontend, intervalo_minutos, canal, cel_suporte, "
                "manutencao_indices_ativo, manutencao_indices_dias_semana, manutencao_indices_hora, "
                "manutencao_indices_orcamento_minutos, checkdb_ativo, checkdb_dias_semana, checkdb_hora) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (manifest_url, pasta_backend, pasta_frontend, intervalo_minutos, canal, cel_suporte,
                 manutencao_ativo, manutencao_dias, manutencao_hora,
                 orcamento_minutos, checkdb_ativo, checkdb_dias, checkdb_hora),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}

    try:
        _CONN_FILE.write_text(json.dumps({"servidor": servidor, "banco": banco}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logging.getLogger(__name__).warning(
            "Falha ao gravar updater_conn.json — a tarefa de fundo não vai saber qual banco checar.",
            exc_info=True,
        )

    return {"success": True, "message": "Configuração de atualização gravada."}


def _get_status_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "pendente": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_servico_sistema_atualizacao_table(cur)
        conn.commit()
        cur.execute("SELECT TOP 1 commit_pendente, canal FROM servico_sistema_atualizacao ORDER BY codigo DESC")
        row = cur.fetchone()
        cur.close()
        conn.close()
        pendente = bool(row and row.get("commit_pendente"))
        canal = (row.get("canal") if row else None) or "H"
        return {"success": True, "pendente": pendente, "canal": canal}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "pendente": False, "message": f"Erro: {e}"}


def _escrever_config_ps1(dados: dict) -> None:
    """Traduz a config gravada no banco pro `config.json` que
    `apply_update.ps1` já sabe ler (ver a extensão do script — campos
    `currentBackendDir`/`currentFrontendDir` novos, opcionais)."""
    pasta_backend = dados.get("pasta_backend") or ""
    # Mesmo achado do módulo (ver comentário em `_BACKEND_ROOT` acima) —
    # `pasta_backend` é a junction `current-backend`; `.resolve()` a
    # trocaria pelo alvo real (`releases\<commit>\backend`), errando o
    # `installDir` gravado em `config.json`.
    install_dir = str(Path(pasta_backend).parent) if pasta_backend else str(_UPDATER_DIR)
    # `canal` traduzido pro texto que `apply_update.ps1` espera
    # (`Homologacao`/`Producao`) — ver `Invoke-Download` nesse script pro
    # ponto que lê isso e decide se respeita `manifest.estavel`.
    canal_ps1 = "Producao" if (dados.get("canal") or "H").strip().upper() == "P" else "Homologacao"
    payload = {
        "manifestUrl": dados.get("manifest_url") or "",
        "installDir": install_dir,
        "currentBackendDir": pasta_backend,
        "currentFrontendDir": dados.get("pasta_frontend") or "",
        "backendPort": 8081,
        "healthCheckTimeoutSeconds": 30,
        "healthCheckRetries": 10,
        "keepReleases": 2,
        "canal": canal_ps1,
    }
    _UPDATER_DIR.mkdir(parents=True, exist_ok=True)
    _UPDATER_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _disparar_ps1_detached(modo: str) -> None:
    """Dispara `apply_update.ps1 -Mode <modo>` como subprocesso DETACHED —
    precisa sobreviver à morte do processo Python que o chamou (ApplyPending/
    Rollback reiniciam o backend de propósito)."""
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(_APPLY_SCRIPT), "-Mode", modo],
        creationflags=flags,
        close_fds=True,
    )


def _aplicar_atualizacao_sync(servidor: str, banco: str) -> dict:
    cfg = _get_config_sync(servidor, banco)
    if not cfg.get("success"):
        return cfg
    dados = cfg["dados"]
    if not dados.get("commit_pendente"):
        return {"success": False, "message": "Não há atualização pendente para aplicar."}
    try:
        _escrever_config_ps1(dados)
        _disparar_ps1_detached("ApplyPending")
    except Exception as e:
        return {"success": False, "message": f"Falha ao iniciar a atualização: {e}"}
    return {"success": True, "message": "Atualização iniciada — o sistema vai reiniciar em instantes."}


def _reverter_atualizacao_sync(servidor: str, banco: str) -> dict:
    cfg = _get_config_sync(servidor, banco)
    if not cfg.get("success"):
        return cfg
    dados = cfg["dados"]
    if not dados.get("commit_anterior"):
        return {"success": False, "message": "Não há versão anterior para reverter."}
    try:
        _escrever_config_ps1(dados)
        _disparar_ps1_detached("Rollback")
    except Exception as e:
        return {"success": False, "message": f"Falha ao iniciar a reversão: {e}"}
    return {"success": True, "message": "Reversão iniciada — o sistema vai reiniciar em instantes."}


def _ler_updater_state() -> Optional[dict]:
    if not _UPDATER_STATE_PATH.is_file():
        return None
    try:
        # "utf-8-sig", não "utf-8" — achado real 2026-08-26: `apply_update.
        # ps1` grava `state.json` via `Set-Content -Encoding UTF8`, que no
        # Windows PowerShell 5.1 (o interpretador real usado aqui, não o
        # pwsh 7) sempre inclui um BOM. Lendo com "utf-8" puro, o BOM sobra
        # como caractere ﻿ antes do "{", `json.loads` falha, e a
        # exceção era engolida em silêncio — o commit pendente nunca era
        # visto pelo lado Python mesmo com o download tendo funcionado.
        # "utf-8-sig" remove o BOM se presente e funciona igual sem ele.
        return json.loads(_UPDATER_STATE_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _ler_pending_commit() -> Optional[str]:
    state = _ler_updater_state()
    return state.get("pendingCommit") if state else None


def _ler_commit_atual() -> Optional[str]:
    """Commit REALMENTE aplicado e rodando nesta instalação — campo
    `commit` de `state.json` (`apply_update.ps1` é quem grava, ver
    `$State.commit` no script). Achado real 2026-09-01 (máquina
    "SUPORTE"/Adriana): esse valor nunca era sincronizado pro banco —
    "Versão atual" na tela ficava sempre em branco. Ver reconciliação em
    `_get_config_sync`."""
    state = _ler_updater_state()
    return state.get("commit") if state else None


def _atualizar_status_pos_verificacao_sync(servidor: str, banco: str, commit_pendente: Optional[str], erro: Optional[str]) -> None:
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 codigo, commit_pendente FROM servico_sistema_atualizacao ORDER BY codigo DESC")
        row = cur.fetchone()
        if not row:
            conn.close()
            return
        if commit_pendente and commit_pendente != row.get("commit_pendente"):
            cur.execute(
                "UPDATE servico_sistema_atualizacao SET commit_pendente=%s, pendente_desde=GETDATE(), "
                "ultima_verificacao=GETDATE(), ultimo_erro=%s WHERE codigo=%s",
                (commit_pendente, erro, row["codigo"]),
            )
        else:
            cur.execute(
                "UPDATE servico_sistema_atualizacao SET ultima_verificacao=GETDATE(), ultimo_erro=%s WHERE codigo=%s",
                (erro, row["codigo"]),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def _executar_verificacao_download_sync(servidor: str, banco: str, dados: dict) -> dict:
    """Roda de fato `apply_update.ps1 -Mode DownloadOnly` e grava o
    resultado (commit_pendente/ultimo_erro/ultima_verificacao) — chamado
    tanto pelo ciclo automático (`_ciclo_verificacao_sync`, respeitando o
    intervalo configurado) quanto pelo botão manual "Verificar agora"
    (`_verificar_agora_sync`, ignora o intervalo/última verificação)."""
    _escrever_config_ps1(dados)
    erro = None
    commit_novo = None
    try:
        resultado = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(_APPLY_SCRIPT), "-Mode", "DownloadOnly"],
            capture_output=True, text=True, timeout=600,
        )
        if resultado.returncode != 0:
            erro = (resultado.stderr or resultado.stdout or "Falha desconhecida ao verificar atualização.").strip()[-500:]
        else:
            commit_novo = _ler_pending_commit()
    except Exception as e:
        erro = str(e)[:500]

    _atualizar_status_pos_verificacao_sync(servidor, banco, commit_pendente=commit_novo, erro=erro)
    if erro:
        return {"success": False, "message": f"Falha ao verificar atualização: {erro}"}
    if commit_novo:
        return {"success": True, "message": f"Atualização encontrada (commit {commit_novo}) — baixada e pronta para aplicar.", "pendente": True}
    return {"success": True, "message": "Nenhuma atualização nova encontrada.", "pendente": False}


def _ciclo_verificacao_sync() -> None:
    """Um ciclo do loop de fundo — chamado a cada `_INTERVALO_CICLO_
    SEGUNDOS`, mas só de fato verifica/baixa quando o `intervalo_minutos`
    configurado pelo usuário já decorreu desde `ultima_verificacao`.
    `intervalo_minutos == 0` desliga a verificação automática por
    completo (só via "Verificar agora"/`_verificar_agora_sync`)."""
    if not _CONN_FILE.is_file():
        return
    try:
        conn_info = json.loads(_CONN_FILE.read_text(encoding="utf-8"))
        servidor, banco = conn_info.get("servidor"), conn_info.get("banco")
    except Exception:
        return
    if not servidor or not banco:
        return

    cfg = _get_config_sync(servidor, banco)
    if not cfg.get("success"):
        return
    dados = cfg["dados"]
    if not dados.get("manifest_url") or not dados.get("pasta_backend") or not dados.get("pasta_frontend"):
        return  # ainda não configurado nesta instalação

    intervalo = int(dados.get("intervalo_minutos") or 0)
    if intervalo <= 0:
        return  # verificação automática desligada nesta instalação

    ultima = dados.get("ultima_verificacao")
    if isinstance(ultima, str):
        try:
            ultima = datetime.fromisoformat(ultima)
        except ValueError:
            ultima = None
    if ultima and (datetime.now() - ultima) < timedelta(minutes=intervalo):
        return  # ainda não está na hora

    _executar_verificacao_download_sync(servidor, banco, dados)


def _verificar_agora_sync(servidor: str, banco: str) -> dict:
    """Botão "Verificar agora" — dispara a mesma checagem/download do
    ciclo automático, mas na hora, ignorando `intervalo_minutos`/última
    verificação. Funciona mesmo com a verificação automática desligada
    (`intervalo_minutos == 0`)."""
    cfg = _get_config_sync(servidor, banco)
    if not cfg.get("success"):
        return cfg
    dados = cfg["dados"]
    if not dados.get("manifest_url") or not dados.get("pasta_backend") or not dados.get("pasta_frontend"):
        return {"success": False, "message": "Configure a URL do manifest e as pastas de Backend/Frontend antes de verificar."}
    return _executar_verificacao_download_sync(servidor, banco, dados)


async def loop_verificacao_atualizacao() -> None:
    """Tarefa de fundo ÚNICA deste backend (primeira do projeto, ver
    `server.py`'s `lifespan`) — nunca derruba o processo se um ciclo
    falhar (erro isolado por ciclo, mesmo princípio de `schema_ensure.
    ensure_all_schema`)."""
    while True:
        try:
            await asyncio.sleep(_INTERVALO_CICLO_SEGUNDOS)
            await asyncio.to_thread(_ciclo_verificacao_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).warning("Ciclo de verificação de atualização falhou.", exc_info=True)


async def get_config(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_config_sync, servidor, banco)


async def save_config(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_save_config_sync, servidor, banco, dados)


async def get_status(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_status_sync, servidor, banco)


async def aplicar_atualizacao(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_aplicar_atualizacao_sync, servidor, banco)


async def reverter_atualizacao(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_reverter_atualizacao_sync, servidor, banco)


async def verificar_agora(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_verificar_agora_sync, servidor, banco)
