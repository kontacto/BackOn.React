"""Manutenção automática de índices/estatística — roda em background,
dentro do próprio processo do backend (mesma arquitetura de
`servico_sistema_service.loop_verificacao_atualizacao`, ver
`server.py`'s `lifespan`).

Motivada por diagnóstico real (2026-08-28) de timeout intermitente no
BackOn VB6 de um cliente real (réplica de teste `RJPNEUS-TESTE`) —
`pedido_venda` tinha 36 índices, vários fragmentados até 98%, estatística
do otimizador nunca atualizada desde a criação. Ver PENDENCIAS.md/memória
de projeto pro diagnóstico completo. Essa mesma manutenção protege o
app novo (que compartilha o banco com o BackOn VB6 durante a migração),
sem depender de SQL Server Agent (Express não suporta) nem de Tarefa
Agendada do Windows configurada manualmente por instalação.

Config mora em `servico_sistema_atualizacao` (ver
`servico_sistema_service._ensure_servico_sistema_atualizacao_table`) —
não é uma tabela própria, é mais uma responsabilidade da mesma "config de
serviço em background desta instalação" que a Atualização já é.

**Limiar de fragmentação** segue a recomendação padrão da Microsoft:
< 5% não mexe, 5–30% `REORGANIZE` (leve, não bloqueia leitura/escrita),
>= 30% `REBUILD` (mais pesado — SQL Server Express não suporta
`REBUILD WITH (ONLINE=ON)`, então BLOQUEIA a tabela durante a execução;
por isso só roda dentro da janela de dias/hora configurada, pensada pra
madrugada/baixo uso — nunca dispara fora dela).

**Extensão 2026-08-31, user-directed** — depois de uma análise de DBA
real feita nesta mesma sessão contra `RJPNEUS-TESTE` (Áureo, ver
PENDENCIAS.md), 4 recursos novos foram adicionados a este arquivo, todos
ligados a achados concretos daquela análise:

1. **Verificação de integridade (`DBCC CHECKDB WITH PHYSICAL_ONLY`)** —
   nenhuma das rotinas existentes (esta, nem `backup_sistema_service.py`)
   detecta corrupção de página. É o 3º pilar clássico de manutenção de
   SQL Server (Backup + Integridade + Índice) que faltava. Agenda própria
   (`checkdb_*`, mesmo mecanismo de dia/hora/janela da manutenção de
   índices, mas tipicamente semanal — é mais pesado). `PHYSICAL_ONLY` é o
   padrão de mercado pra banco grande (mais rápido que o CHECKDB
   completo, ainda cobre corrupção de página física, só não valida
   regras lógicas avançadas). Não tenta interpretar o conteúdo das
   mensagens do DBCC (formato varia por versão) — só registra se a
   chamada lançou exceção (indício real de problema) ou não.
2. **Orçamento de tempo / circuit breaker** — achado real: um banco com
   centenas de índices fragmentados (como o `RJPNEUS-TESTE` analisado)
   pode fazer o ciclo de manutenção ultrapassar a janela noturna
   configurada e ainda estar rodando REBUILD (que bloqueia tabela, sem
   `ONLINE=ON` no Express) quando o expediente já começou.
   `manutencao_indices_orcamento_minutos` (padrão 120min) limita quanto
   tempo o ciclo pode gastar iniciando REBUILD/REORGANIZE novos — o que
   sobra fica pra reavaliar no próximo ciclo agendado (a fragmentação
   persiste, não se perde).
3. **Alerta de espaço vs. teto do SQL Server Express (10GB)** — achado
   direto da análise: `RJPNEUS-TESTE` já estava em ~50% do teto rígido
   de 10GB de dados que a Express Edition impõe por banco. Roda a cada
   ciclo (é uma leitura leve de `sys.database_files`, sem custo real),
   só grava/alerta quando a instância é Express (`SERVERPROPERTY
   ('EngineEdition') = 4` — outras edições não têm esse teto simples).
4. **Relatório (nunca ação automática) de índices nunca usados** — achado
   real: dezenas de índices com nome sequencial genérico (`os_1`...
   `os_22`, etc.) sem nenhum uso registrado desde o boot da instância.
   Dropar automaticamente é arriscado (relatório mensal que só roda 1x/
   mês pode não aparecer numa janela de poucos dias de uptime) — esta
   função só LISTA candidatos pra revisão manual, nunca dropa sozinha.

Um 5º item (botão "Rodar agora" manual, bypassando a janela agendada)
também foi pedido — é só um wrapper fino sobre `_rodar_manutencao_sync`
já existente (`rodar_manutencao_agora`), sem lógica nova de fato."""
import asyncio
import json
import logging
import time as time_module
from datetime import datetime, time as dt_time, timedelta
from typing import Callable, Optional

from db.connection import _open_conn
from services.servico_sistema_service import _CONN_FILE

logger = logging.getLogger(__name__)

_INTERVALO_CICLO_SEGUNDOS = 300  # granularidade do "relógio" do loop de fundo — 5 min
_FRAG_MIN_REORGANIZE = 5.0
_FRAG_MIN_REBUILD = 30.0
_PAGE_COUNT_MINIMO = 100  # ignora índice pequeno demais pra fragmentação importar
_PAGE_COUNT_MINIMO_RELATORIO = 200  # idem, pro relatório de índices não usados
_JANELA_TOLERANCIA_MINUTOS = 59  # dispara se o ciclo passar do horário configurado por até esse tanto
_TIMEOUT_MANUTENCAO_SEGUNDOS = 1800  # operação pode ser longa — bem maior que o timeout padrão de query
_ORCAMENTO_PADRAO_MINUTOS = 120  # circuit breaker padrão quando a instalação não configurou o próprio
_TETO_EXPRESS_MB = 10240.0  # 10GB — limite real de dados por banco na SQL Server Express Edition
_ESPACO_ALERTA_PCT = 80.0  # a partir de quanto do teto Express soa o alerta


def _ler_conn_file() -> Optional[tuple[str, str]]:
    """Mesmo arquivo que `servico_sistema_service._ciclo_verificacao_sync`
    já lê — reaproveitado aqui em vez de duplicado."""
    if not _CONN_FILE.is_file():
        return None
    try:
        conn_info = json.loads(_CONN_FILE.read_text(encoding="utf-8"))
        servidor, banco = conn_info.get("servidor"), conn_info.get("banco")
    except Exception:
        return None
    if not servidor or not banco:
        return None
    return servidor, banco


def _hora_valida(txt: str) -> Optional[dt_time]:
    try:
        h, m = (txt or "").strip().split(":")
        return dt_time(int(h), int(m))
    except Exception:
        return None


def _avaliar_janela(ativo: bool, dias_raw: str, hora_raw: str, ultima_execucao, agora: datetime) -> bool:
    """Motor de janela compartilhado — mesma regra pra Manutenção de
    Índices e pra CHECKDB, só muda de onde os 4 valores vêm (colunas
    `manutencao_indices_*` ou `checkdb_*`). Convenção do projeto
    (`Web_DiasSemana`): domingo=0..sábado=6; Python usa Monday=0..
    Sunday=6, por isso a conversão `(weekday()+1) % 7`."""
    if not ativo:
        return False
    dias = {int(p.strip()) for p in (dias_raw or "").split(",") if p.strip().isdigit() and 0 <= int(p.strip()) <= 6}
    dia_projeto = (agora.weekday() + 1) % 7
    if dia_projeto not in dias:
        return False
    hora_cfg = _hora_valida(hora_raw or "")
    if hora_cfg is None:
        return False
    inicio = agora.replace(hour=hora_cfg.hour, minute=hora_cfg.minute, second=0, microsecond=0)
    fim = inicio + timedelta(minutes=_JANELA_TOLERANCIA_MINUTOS)
    if not (inicio <= agora <= fim):
        return False
    if isinstance(ultima_execucao, datetime) and ultima_execucao.date() == agora.date():
        return False  # já rodou hoje
    return True


def _get_config_manutencao_sync(cur) -> Optional[dict]:
    cur.execute(
        "SELECT TOP 1 manutencao_indices_ativo, manutencao_indices_dias_semana, "
        "manutencao_indices_hora, manutencao_indices_ultima_execucao "
        "FROM servico_sistema_atualizacao ORDER BY codigo DESC"
    )
    return cur.fetchone()


def _deve_rodar_agora_sync(servidor: str, banco: str, agora: Optional[datetime] = None) -> bool:
    """`agora` é injetável (default `datetime.now()`) só pra teste — evita
    ter que fazer monkeypatch do módulo `datetime` em si (frágil: é um
    tipo C imutável, e `isinstance(x, datetime)` dentro da função quebra
    se `datetime` for substituído por um objeto que não é a classe)."""
    if agora is None:
        agora = datetime.now()
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return False
    try:
        cur = conn.cursor(as_dict=True)
        cfg = _get_config_manutencao_sync(cur)
    finally:
        conn.close()

    if not cfg:
        return False
    return _avaliar_janela(
        bool(cfg.get("manutencao_indices_ativo")),
        cfg.get("manutencao_indices_dias_semana") or "",
        cfg.get("manutencao_indices_hora") or "",
        cfg.get("manutencao_indices_ultima_execucao"),
        agora,
    )


def _get_config_checkdb_sync(cur) -> Optional[dict]:
    cur.execute(
        "SELECT TOP 1 checkdb_ativo, checkdb_dias_semana, checkdb_hora, checkdb_ultima_execucao "
        "FROM servico_sistema_atualizacao ORDER BY codigo DESC"
    )
    return cur.fetchone()


def _deve_rodar_checkdb_agora_sync(servidor: str, banco: str, agora: Optional[datetime] = None) -> bool:
    """Mesma janela de `_deve_rodar_agora_sync`, config própria
    (`checkdb_*`) — tipicamente 1x/semana (mais pesado que reorganize/
    rebuild), nunca precisa estar no mesmo dia/hora da manutenção de
    índices."""
    if agora is None:
        agora = datetime.now()
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return False
    try:
        cur = conn.cursor(as_dict=True)
        cfg = _get_config_checkdb_sync(cur)
    finally:
        conn.close()

    if not cfg:
        return False
    return _avaliar_janela(
        bool(cfg.get("checkdb_ativo")),
        cfg.get("checkdb_dias_semana") or "",
        cfg.get("checkdb_hora") or "",
        cfg.get("checkdb_ultima_execucao"),
        agora,
    )


def _ler_orcamento_minutos_sync(servidor: str, banco: str) -> int:
    try:
        conn = _open_conn(servidor, banco)
    except Exception:
        return _ORCAMENTO_PADRAO_MINUTOS
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 manutencao_indices_orcamento_minutos FROM servico_sistema_atualizacao "
            "ORDER BY codigo DESC"
        )
        row = cur.fetchone()
        conn.close()
        valor = row.get("manutencao_indices_orcamento_minutos") if row else None
        return int(valor) if valor else _ORCAMENTO_PADRAO_MINUTOS
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return _ORCAMENTO_PADRAO_MINUTOS


def _analisar_fragmentacao_sync(cur) -> list[dict]:
    """Modo 'LIMITED' — mais leve (varre só o IAM, não os dados) — de
    propósito: uma checagem de fragmentação sem filtro de objeto/mais
    pesada ('DETAILED'/'SAMPLED' sem WHERE) já travou uma conexão de
    verdade durante a investigação que motivou esta feature; nunca
    repetir esse erro numa rotina que roda sozinha, sem supervisão."""
    cur.execute(
        "SELECT OBJECT_NAME(ips.object_id) AS tabela, i.name AS indice, "
        "ips.avg_fragmentation_in_percent AS frag, ips.page_count "
        "FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips "
        "JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id "
        "WHERE i.index_id > 0 AND i.name IS NOT NULL AND ips.page_count > %s "
        "AND OBJECTPROPERTY(ips.object_id, 'IsMSShipped') = 0",
        (_PAGE_COUNT_MINIMO,),
    )
    return cur.fetchall()


def _gravar_com_retry(servidor: str, banco: str, coluna_execucao: str, coluna_resultado: str, resumo: str, contexto: str) -> None:
    """Reaproveitado por `_gravar_resultado_sync`/`_gravar_resultado_
    checkdb_sync`. Achado ao vivo (2026-08-31, teste real contra
    `BD_PAJE`, banco genuinamente fragmentado): logo depois de um lote
    pesado de REBUILD, a conexão original às vezes morre no meio
    ("Adaptive Server connection timed out") — e a PRÓPRIA conexão NOVA
    aberta aqui pra gravar o resultado às vezes falha também, no mesmo
    instante (SQL Server ainda absorvendo o lote anterior). Sem retry, um
    ciclo que genuinamente rodou (e ajudou) ficava sem NENHUM registro
    visível na tela — parecia que nada tinha acontecido. 1 nova tentativa
    curta (3s de espera) já cobriu esse hiccup nos testes ao vivo desta
    sessão."""
    ultimo_erro: Optional[Exception] = None
    for tentativa in range(2):
        try:
            conn = _open_conn(servidor, banco)
            cur = conn.cursor(as_dict=True)
            cur.execute("SELECT TOP 1 codigo FROM servico_sistema_atualizacao ORDER BY codigo DESC")
            row = cur.fetchone()
            if row:
                cur.execute(
                    f"UPDATE servico_sistema_atualizacao SET {coluna_execucao}=%s, {coluna_resultado}=%s WHERE codigo=%s",
                    (datetime.now(), resumo[:500], row["codigo"]),
                )
                conn.commit()
            cur.close()
            conn.close()
            return
        except Exception as e:
            ultimo_erro = e
            if tentativa == 0:
                time_module.sleep(3)
    logger.warning("Falha ao gravar resultado (%s) em %s/%s, após retry: %s", contexto, servidor, banco, ultimo_erro)


def _gravar_resultado_sync(servidor: str, banco: str, resumo: str) -> None:
    _gravar_com_retry(
        servidor, banco, "manutencao_indices_ultima_execucao", "manutencao_indices_ultimo_resultado",
        resumo, "manutenção de índices",
    )


def _rodar_manutencao_sync(
    servidor: str, banco: str, orcamento_minutos: int = _ORCAMENTO_PADRAO_MINUTOS,
    _clock: Callable[[], datetime] = datetime.now,
) -> dict:
    """`_clock` é injetável só pra teste do circuit breaker (item 2 da
    extensão 2026-08-31) — sem isso não dá pra simular "o tempo passou"
    de forma determinística numa suíte de teste que não dorme de
    verdade."""
    t0 = _clock()
    reconstruidos = 0
    reorganizados = 0
    pulados_por_orcamento = 0
    erros: list[str] = []
    tabelas_tocadas: set[str] = set()

    try:
        conn = _open_conn(servidor, banco, timeout=_TIMEOUT_MANUTENCAO_SEGUNDOS)
    except Exception as e:
        resumo = f"Falha ao conectar: {e}"
        _gravar_resultado_sync(servidor, banco, resumo)
        return {"success": False, "resumo": resumo}

    try:
        # Autocommit — cada índice roda e comita isolado; uma falha num
        # índice específico não derruba nem desfaz as outras já
        # concluídas nesta mesma rodada.
        conn.autocommit(True)
        cur = conn.cursor(as_dict=True)
        try:
            linhas = _analisar_fragmentacao_sync(cur)
        except Exception as e:
            erros.append(f"análise de fragmentação: {e}")
            linhas = []

        candidatos = [
            linha for linha in linhas
            if linha.get("tabela") and linha.get("indice") and float(linha.get("frag") or 0) >= _FRAG_MIN_REORGANIZE
        ]
        orcamento_segundos = max(1, int(orcamento_minutos)) * 60

        for i, linha in enumerate(candidatos):
            if (_clock() - t0).total_seconds() > orcamento_segundos:
                pulados_por_orcamento = len(candidatos) - i
                break
            tabela = linha["tabela"]
            indice = linha["indice"]
            frag = float(linha.get("frag") or 0)
            tabela_esc = tabela.replace("]", "]]")
            indice_esc = indice.replace("]", "]]")
            try:
                if frag >= _FRAG_MIN_REBUILD:
                    cur.execute(f"ALTER INDEX [{indice_esc}] ON [{tabela_esc}] REBUILD")
                    reconstruidos += 1
                else:
                    cur.execute(f"ALTER INDEX [{indice_esc}] ON [{tabela_esc}] REORGANIZE")
                    reorganizados += 1
                tabelas_tocadas.add(tabela)
            except Exception as e:
                erros.append(f"{tabela}.{indice}: {e}")

        # REBUILD já atualiza estatística sozinho (equivalente a FULLSCAN);
        # REORGANIZE não — atualiza de novo pra cobrir os dois casos sem
        # precisar distinguir qual índice de cada tabela recebeu qual.
        for tabela in tabelas_tocadas:
            try:
                cur.execute(f"UPDATE STATISTICS [{tabela.replace(']', ']]')}] WITH FULLSCAN")
            except Exception as e:
                erros.append(f"UPDATE STATISTICS {tabela}: {e}")

        conn.autocommit(False)
        cur.close()
    except Exception as e:
        erros.append(str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    duracao_s = (_clock() - t0).total_seconds()
    resumo = (
        f"{reconstruidos} índice(s) reconstruído(s), {reorganizados} reorganizado(s), "
        f"{len(tabelas_tocadas)} tabela(s) com estatística atualizada, em {duracao_s:.0f}s"
    )
    if pulados_por_orcamento:
        resumo += f" — {pulados_por_orcamento} índice(s) adiado(s) por orçamento de tempo (retoma no próximo ciclo)"
    if erros:
        resumo += f" — {len(erros)} erro(s): " + "; ".join(erros[:3])
    _gravar_resultado_sync(servidor, banco, resumo)
    return {"success": not erros, "resumo": resumo}


def _gravar_resultado_checkdb_sync(servidor: str, banco: str, resumo: str) -> None:
    _gravar_com_retry(servidor, banco, "checkdb_ultima_execucao", "checkdb_ultimo_resultado", resumo, "CHECKDB")


def _rodar_checkdb_sync(servidor: str, banco: str) -> dict:
    """`WITH PHYSICAL_ONLY` — padrão de mercado pra banco grande: mais
    rápido que o CHECKDB completo, ainda cobre corrupção de página física
    (o tipo de problema real que justifica rodar isso), só não valida
    regras lógicas avançadas de tipos complexos que este projeto não usa.
    Não interpreta o conteúdo das mensagens do DBCC (formato varia por
    versão do SQL Server) — só distingue sucesso/falha pela exceção."""
    t0 = datetime.now()
    try:
        conn = _open_conn(servidor, banco, timeout=_TIMEOUT_MANUTENCAO_SEGUNDOS)
    except Exception as e:
        resumo = f"Falha ao conectar: {e}"
        _gravar_resultado_checkdb_sync(servidor, banco, resumo)
        return {"success": False, "resumo": resumo}
    try:
        conn.autocommit(True)
        cur = conn.cursor(as_dict=True)
        cur.execute("DBCC CHECKDB WITH PHYSICAL_ONLY, NO_INFOMSGS")
        try:
            while cur.nextset():
                pass
        except Exception:
            pass
        conn.autocommit(False)
        cur.close()
        conn.close()
        duracao_s = (datetime.now() - t0).total_seconds()
        resumo = f"Nenhum erro de integridade detectado, em {duracao_s:.0f}s"
        _gravar_resultado_checkdb_sync(servidor, banco, resumo)
        return {"success": True, "resumo": resumo}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        duracao_s = (datetime.now() - t0).total_seconds()
        resumo = f"CHECKDB encontrou possível problema de integridade ({duracao_s:.0f}s): {e}"[:500]
        _gravar_resultado_checkdb_sync(servidor, banco, resumo)
        return {"success": False, "resumo": resumo}


def _listar_indices_nao_usados_sync(servidor: str, banco: str) -> dict:
    """Só relatório — nunca dropa nada sozinha. `index_id > 1` exclui
    heap/clustered (revisar/dropar um PK é uma decisão estrutural
    diferente, fora de escopo desta lista). "Nunca usado" é medido desde
    o boot da instância (`sys.dm_db_index_usage_stats`) — uma janela
    curta de uptime pode não cobrir uma rotina mensal/trimestral real;
    por isso isto é sempre um candidato pra REVISÃO HUMANA, nunca uma
    ação automática."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT t.name AS tabela, i.name AS indice, SUM(a.used_pages) AS paginas "
            "FROM sys.indexes i "
            "JOIN sys.tables t ON i.object_id = t.object_id "
            "JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id "
            "JOIN sys.allocation_units a ON p.partition_id = a.container_id "
            "WHERE i.index_id > 1 AND i.name IS NOT NULL "
            "AND OBJECTPROPERTY(i.object_id, 'IsMSShipped') = 0 "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM sys.dm_db_index_usage_stats us "
            "  WHERE us.object_id = i.object_id AND us.index_id = i.index_id "
            "  AND (us.user_seeks + us.user_scans + us.user_lookups) > 0"
            ") "
            "GROUP BY t.name, i.name "
            "HAVING SUM(a.used_pages) > %s "
            "ORDER BY SUM(a.used_pages) DESC",
            (_PAGE_COUNT_MINIMO_RELATORIO,),
        )
        linhas = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "indices": linhas}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _verificar_espaco_sync(servidor: str, banco: str) -> dict:
    """Roda a cada ciclo (5 min) — leitura leve de `sys.database_files`,
    sem custo real. Só calcula percentual/alerta quando a instância é
    Express (`EngineEdition = 4`); outras edições não têm esse teto
    simples de 10GB por banco. `type = 0` = arquivos de DADOS (ROWS) —
    log não conta pro teto Express."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT CAST(SERVERPROPERTY('EngineEdition') AS INT) AS edicao")
        edicao_row = cur.fetchone() or {}
        express = edicao_row.get("edicao") == 4
        cur.execute("SELECT SUM(size) * 8.0 / 1024 AS mb FROM sys.database_files WHERE type = 0")
        mb_row = cur.fetchone() or {}
        mb = float(mb_row.get("mb") or 0)
        pct = round((mb / _TETO_EXPRESS_MB) * 100, 1) if express else None

        if express:
            cur.execute("SELECT TOP 1 codigo FROM servico_sistema_atualizacao ORDER BY codigo DESC")
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE servico_sistema_atualizacao SET espaco_pct_usado=%s, espaco_verificado_em=%s "
                    "WHERE codigo=%s",
                    (pct, datetime.now(), row["codigo"]),
                )
                conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "express": express, "pct_usado": pct,
            "alerta": bool(express and pct is not None and pct >= _ESPACO_ALERTA_PCT),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _ciclo_manutencao_sync() -> None:
    conn_info = _ler_conn_file()
    if not conn_info:
        return
    servidor, banco = conn_info
    if _deve_rodar_agora_sync(servidor, banco):
        orcamento = _ler_orcamento_minutos_sync(servidor, banco)
        _rodar_manutencao_sync(servidor, banco, orcamento_minutos=orcamento)
    if _deve_rodar_checkdb_agora_sync(servidor, banco):
        _rodar_checkdb_sync(servidor, banco)
    _verificar_espaco_sync(servidor, banco)


async def loop_manutencao_indices() -> None:
    """Tarefa de fundo — nunca derruba o processo se um ciclo falhar
    (mesmo princípio de `servico_sistema_service.loop_verificacao_
    atualizacao`/`schema_ensure.ensure_all_schema`)."""
    while True:
        try:
            await asyncio.sleep(_INTERVALO_CICLO_SEGUNDOS)
            await asyncio.to_thread(_ciclo_manutencao_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Ciclo de manutenção de índices falhou.", exc_info=True)


async def rodar_manutencao_agora(servidor: str, banco: str) -> dict:
    """Botão "Rodar agora" — dispara a mesma manutenção do ciclo
    automático, na hora, ignorando dia/hora/janela configurados (mesmo
    padrão de `servico_sistema_service.verificar_agora`)."""
    orcamento = await asyncio.to_thread(_ler_orcamento_minutos_sync, servidor, banco)
    return await asyncio.to_thread(_rodar_manutencao_sync, servidor, banco, orcamento)


async def listar_indices_nao_usados(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_listar_indices_nao_usados_sync, servidor, banco)


async def verificar_espaco(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_verificar_espaco_sync, servidor, banco)
