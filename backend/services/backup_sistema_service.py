"""Rotina de backup programado (dias da semana + hora de início +
intervalo de repetição) — mesma arquitetura de fundo de
`manutencao_indices_service.py`/`servico_sistema_service.py` (ver
`server.py`'s `lifespan`). Motivada pelo mesmo diagnóstico real
(2026-08-28) que originou a Manutenção de Índices — o BackOn VB6 já tem
seu próprio serviço de backup (`Kontacto_Bkp.vb`, Windows Service em
VB.NET, `BACKUP DATABASE ... TO DISK`, de hora em hora, sem controle de
dia) — o pedido aqui foi trazer a MESMA capacidade pro app novo, com
destino também podendo ser Blob (não só disco local) e com controle de
dia/hora/intervalo em vez de "sempre de hora em hora, sem escolha".

Config em tabela própria `backup_sistema_config` — não reaproveita
`servico_sistema_atualizacao` (que já acumula Atualização + Manutenção
de Índices; virar um "balde" único demais passou a valer separar).

**Composição do agendamento** (decidido com o usuário via
`AskUserQuestion`, 2026-08-28): dias da semana filtram QUANDO é
permitido rodar; `hora_inicio` é o horário mais cedo do dia em que o
1º backup pode disparar; `intervalo_horas` é o mínimo de tempo desde a
ÚLTIMA execução pra liberar a próxima. Nunca dispara antes de
`hora_inicio` no dia, e a partir daí repete a cada `intervalo_horas` —
não tenta alinhar em slots fixos de relógio (06h/12h/18h), o que evitaria
toda a complexidade de borda de virada de dia; "no mínimo N horas desde
a última vez, nunca antes do horário X" já cobre o caso de uso real sem
ambiguidade de fuso/DST/dia seguinte.

**Destino** (`SelectField`, 1 por vez — decidido com o usuário):
- `LOCAL`: `BACKUP DATABASE ... TO DISK` — a pasta é resolvida e
  gravada pelo SERVIDOR SQL, não pela máquina que roda este backend
  (podem ser máquinas diferentes — confirmado neste mesmo projeto:
  o backend de teste roda em `GERDELL`, o SQL Server de teste em
  `minimachine`). Retenção via `xp_delete_file` (mesmo mecanismo que a
  "Maintenance Cleanup Task" do SSMS usa por trás dos panos) — roda NO
  SERVIDOR, não depende do backend enxergar a pasta.
- `BLOB`: `BACKUP DATABASE ... TO URL`, com uma `CREDENTIAL` de SQL
  Server gerada a partir de um SAS token de curta duração (1h,
  suficiente pra cobrir a duração do próprio backup — regenerado a cada
  execução, nunca fica um SAS de longa duração salvo no SQL Server).
  Reaproveita `controle_aux.Azure_ConnectionString` (mesma credencial já
  usada por Gestor de Documentos/Fotos de Produto — não pede segredo
  novo). Retenção via `BlobServiceClient` (lista + apaga blobs mais
  velhos que `retencao_dias`).

**Retenção automática** — extra não pedido explicitamente, mas
necessário: sem limpeza, o backup acumula pra sempre e enche o disco/
Blob (o próprio `Kontacto_Bkp.vb` evita isso reusando sempre os mesmos 4
nomes de arquivo por turno — aqui, com intervalo configurável, o nome
do arquivo é sempre único, então a limpeza precisa ser um passo
explícito, não um acidente de sobrescrita).

**Compatibilidade**: nunca usa `WITH COMPRESSION` — não suportado em
SQL Server Express antes da versão 2016 SP1 (a base real que motivou
esta rodada de features é 2014 Express) — trade-off consciente: backup
Blob sai maior/mais lento sem compressão, mas funciona em qualquer
edição/versão que este projeto já encontrou pela frente."""
import asyncio
import json
import logging
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Optional

from azure.core.exceptions import AzureError
from azure.storage.blob import AccountSasPermissions, BlobServiceClient, ResourceTypes, generate_account_sas

from db.connection import _open_conn
from services.servico_sistema_service import _CONN_FILE

logger = logging.getLogger(__name__)

_INTERVALO_CICLO_SEGUNDOS = 300  # granularidade do "relógio" do loop de fundo — 5 min
_TIMEOUT_BACKUP_SEGUNDOS = 3600  # backup de banco grande pode demorar
_SAS_VALIDADE_MINUTOS = 90  # cobre folga o suficiente pra qualquer backup terminar
_EMPRESA_AUX = 0

_CONFIG_PADRAO = {
    "ativo": False,  # desligado por padrão — backup precisa de configuração explícita antes de rodar sozinho
    "dias_semana": "0,1,2,3,4,5,6",
    "hora_inicio": "02:00",
    "intervalo_horas": 24,
    "destino": "LOCAL",
    "pasta_local": "",
    "blob_container": "backups-sql",
    "retencao_dias": 30,
    "ultima_execucao": None,
    "ultimo_resultado": None,
}


def _ensure_backup_sistema_table(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'backup_sistema_config') "
        "CREATE TABLE backup_sistema_config ("
        "codigo INT IDENTITY(1,1) PRIMARY KEY, "
        "ativo BIT NOT NULL DEFAULT 0, "
        "dias_semana NVARCHAR(20) NOT NULL DEFAULT '0,1,2,3,4,5,6', "
        "hora_inicio NVARCHAR(5) NOT NULL DEFAULT '02:00', "
        "intervalo_horas INT NOT NULL DEFAULT 24, "
        "destino NVARCHAR(10) NOT NULL DEFAULT 'LOCAL', "
        "pasta_local NVARCHAR(400) NULL, "
        "blob_container NVARCHAR(100) NOT NULL DEFAULT 'backups-sql', "
        "retencao_dias INT NOT NULL DEFAULT 30, "
        "ultima_execucao DATETIME NULL, "
        "ultimo_resultado NVARCHAR(500) NULL)"
    )
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'backup_sistema_log') "
        "CREATE TABLE backup_sistema_log ("
        "codigo INT IDENTITY(1,1) PRIMARY KEY, "
        "data_hora DATETIME NOT NULL DEFAULT GETDATE(), "
        "sucesso BIT NOT NULL, "
        "destino NVARCHAR(10) NOT NULL, "
        "caminho_ou_url NVARCHAR(500) NULL, "
        "tamanho_mb DECIMAL(12,2) NULL, "
        "duracao_segundos INT NULL, "
        "mensagem NVARCHAR(500) NULL)"
    )


def _row_to_dict(r: dict) -> dict:
    return dict(r)


def _get_config_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_backup_sistema_table(cur)
        conn.commit()
        cur.execute(
            "SELECT TOP 1 ativo, dias_semana, hora_inicio, intervalo_horas, destino, pasta_local, "
            "blob_container, retencao_dias, ultima_execucao, ultimo_resultado "
            "FROM backup_sistema_config ORDER BY codigo DESC"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        dados = _row_to_dict(row) if row else dict(_CONFIG_PADRAO)
        return {"success": True, "dados": dados}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_config_sync(servidor: str, banco: str, dados: dict) -> dict:
    ativo = bool(dados.get("ativo", False))
    dias_raw = (dados.get("dias_semana") or "").strip()
    dias_validos = {p.strip() for p in dias_raw.split(",") if p.strip().isdigit() and 0 <= int(p.strip()) <= 6}
    dias_semana = ",".join(sorted(dias_validos, key=int)) if dias_validos else "0,1,2,3,4,5,6"

    hora_raw = (dados.get("hora_inicio") or "").strip()
    hora_inicio = "02:00"
    if len(hora_raw) == 5 and hora_raw[2] == ":" and hora_raw[:2].isdigit() and hora_raw[3:].isdigit():
        h, m = int(hora_raw[:2]), int(hora_raw[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            hora_inicio = hora_raw

    try:
        intervalo_horas = int(dados.get("intervalo_horas") or 24)
    except (TypeError, ValueError):
        return {"success": False, "message": "Intervalo (horas) inválido."}
    if intervalo_horas < 1 or intervalo_horas > 168:
        return {"success": False, "message": "O intervalo deve ser entre 1 e 168 horas (7 dias)."}

    destino = (dados.get("destino") or "LOCAL").strip().upper()
    if destino not in ("LOCAL", "BLOB"):
        return {"success": False, "message": "Destino inválido — use Local ou Blob."}

    pasta_local = (dados.get("pasta_local") or "").strip()
    if ativo and destino == "LOCAL" and not pasta_local:
        return {"success": False, "message": "Informe a pasta de destino local antes de ativar o backup."}

    blob_container = (dados.get("blob_container") or "backups-sql").strip() or "backups-sql"

    try:
        retencao_dias = int(dados.get("retencao_dias") or 30)
    except (TypeError, ValueError):
        return {"success": False, "message": "Retenção (dias) inválida."}
    if retencao_dias < 1 or retencao_dias > 3650:
        return {"success": False, "message": "A retenção deve ser entre 1 e 3650 dias."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_backup_sistema_table(cur)
        conn.commit()
        cur.execute("SELECT TOP 1 codigo FROM backup_sistema_config ORDER BY codigo DESC")
        existente = cur.fetchone()
        campos = (ativo, dias_semana, hora_inicio, intervalo_horas, destino, pasta_local, blob_container, retencao_dias)
        if existente:
            cur.execute(
                "UPDATE backup_sistema_config SET ativo=%s, dias_semana=%s, hora_inicio=%s, intervalo_horas=%s, "
                "destino=%s, pasta_local=%s, blob_container=%s, retencao_dias=%s WHERE codigo=%s",
                campos + (existente["codigo"],),
            )
        else:
            cur.execute(
                "INSERT INTO backup_sistema_config (ativo, dias_semana, hora_inicio, intervalo_horas, destino, "
                "pasta_local, blob_container, retencao_dias) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                campos,
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Configuração de backup gravada."}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _listar_logs_sync(servidor: str, banco: str, limite: int = 50) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        _ensure_backup_sistema_table(cur)
        conn.commit()
        cur.execute(
            "SELECT TOP (%s) codigo, data_hora, sucesso, destino, caminho_ou_url, tamanho_mb, "
            "duracao_segundos, mensagem FROM backup_sistema_log ORDER BY data_hora DESC",
            (limite,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"success": True, "itens": [_row_to_dict(r) for r in rows]}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _registrar_log_sync(
    servidor: str, banco: str, *, sucesso: bool, destino: str, caminho_ou_url: str,
    tamanho_mb: Optional[float], duracao_segundos: int, mensagem: str,
) -> None:
    try:
        conn = _open_conn(servidor, banco)
        cur = conn.cursor(as_dict=True)
        _ensure_backup_sistema_table(cur)
        conn.commit()
        cur.execute(
            "INSERT INTO backup_sistema_log (sucesso, destino, caminho_ou_url, tamanho_mb, duracao_segundos, mensagem) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (sucesso, destino, caminho_ou_url[:500], tamanho_mb, duracao_segundos, mensagem[:500]),
        )
        cur.execute("SELECT TOP 1 codigo FROM backup_sistema_config ORDER BY codigo DESC")
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE backup_sistema_config SET ultima_execucao=%s, ultimo_resultado=%s WHERE codigo=%s",
                (datetime.now(), mensagem[:500], row["codigo"]),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        logger.warning("Falha ao registrar log de backup em %s/%s", servidor, banco, exc_info=True)


def _hora_valida(txt: str) -> Optional[dt_time]:
    try:
        h, m = (txt or "").strip().split(":")
        return dt_time(int(h), int(m))
    except Exception:
        return None


def _deve_rodar_agora_sync(servidor: str, banco: str, agora: Optional[datetime] = None) -> bool:
    """`agora` injetável só pra teste — mesmo motivo de
    `manutencao_indices_service._deve_rodar_agora_sync`."""
    if agora is None:
        agora = datetime.now()
    cfg = _get_config_sync(servidor, banco)
    if not cfg.get("success"):
        return False
    d = cfg["dados"]
    if not d.get("ativo"):
        return False

    dias_raw = d.get("dias_semana") or ""
    dias = {int(p.strip()) for p in dias_raw.split(",") if p.strip().isdigit() and 0 <= int(p.strip()) <= 6}
    dia_projeto = (agora.weekday() + 1) % 7  # convenção do projeto: domingo=0..sábado=6
    if dia_projeto not in dias:
        return False

    hora_cfg = _hora_valida(d.get("hora_inicio") or "")
    if hora_cfg is None:
        return False
    inicio_do_dia = agora.replace(hour=hora_cfg.hour, minute=hora_cfg.minute, second=0, microsecond=0)
    if agora < inicio_do_dia:
        return False  # ainda não chegou no horário de início de hoje

    ultima = d.get("ultima_execucao")
    if not isinstance(ultima, datetime):
        return True  # nunca rodou — e já passamos do horário de início

    intervalo_horas = int(d.get("intervalo_horas") or 24)
    return (agora - ultima) >= timedelta(hours=intervalo_horas)


def _sas_da_connection_string(azure_conn_str: str) -> tuple[str, str]:
    """Extrai `AccountName`/`AccountKey` da connection string (mesmo
    formato `chave=valor;chave=valor` que `BlobServiceClient.from_
    connection_string` já aceita — aqui é parseado manualmente só porque
    `generate_account_sas` pede os dois valores separados, não a
    connection string inteira)."""
    partes = dict(
        p.split("=", 1) for p in azure_conn_str.split(";") if "=" in p
    )
    nome = partes.get("AccountName", "").strip()
    chave = partes.get("AccountKey", "").strip()
    if not nome or not chave:
        raise ValueError("Azure_ConnectionString não tem AccountName/AccountKey reconhecíveis.")
    return nome, chave


def _preparar_backup_blob_sync(cur, azure_conn_str: str, container: str) -> tuple[str, str]:
    """Garante o container, gera um SAS de curta duração e cria/atualiza a
    `CREDENTIAL` do SQL Server usada pelo `BACKUP ... TO URL`. Devolve
    (nome_da_credential, url_do_container) — o nome da credential PRECISA
    ser exatamente a URL do container, é assim que `BACKUP TO URL`
    resolve qual credential usar."""
    account_name, account_key = _sas_da_connection_string(azure_conn_str)

    service = BlobServiceClient.from_connection_string(azure_conn_str)
    try:
        service.create_container(container)
    except AzureError:
        pass  # já existe — ok

    sas = generate_account_sas(
        account_name=account_name,
        account_key=account_key,
        resource_types=ResourceTypes(container=True, object=True),
        permission=AccountSasPermissions(read=True, write=True, create=True, list=True, delete=True),
        expiry=datetime.utcnow() + timedelta(minutes=_SAS_VALIDADE_MINUTOS),
    )

    container_url = f"https://{account_name}.blob.core.windows.net/{container}"
    cred_esc = container_url.replace("]", "]]")
    cur.execute("SELECT 1 FROM sys.credentials WHERE name = %s", (container_url,))
    if cur.fetchone():
        cur.execute(f"ALTER CREDENTIAL [{cred_esc}] WITH IDENTITY = 'SHARED ACCESS SIGNATURE', SECRET = %s", (sas,))
    else:
        cur.execute(
            f"CREATE CREDENTIAL [{cred_esc}] WITH IDENTITY = 'SHARED ACCESS SIGNATURE', SECRET = %s", (sas,)
        )
    return container_url, container_url


def _limpar_backups_antigos_local_sync(cur, pasta: str, retencao_dias: int) -> None:
    """`xp_delete_file` roda NO PRÓPRIO SERVIDOR SQL — mesmo mecanismo
    usado por trás da "Maintenance Cleanup Task" do SSMS. Não depende do
    backend enxergar a pasta (pode estar numa máquina diferente)."""
    data_corte = datetime.now() - timedelta(days=retencao_dias)
    cur.execute(
        "EXEC master.dbo.xp_delete_file 0, %s, N'bak', %s, 0",
        (pasta, data_corte),
    )


def _limpar_backups_antigos_blob_sync(azure_conn_str: str, container: str, retencao_dias: int) -> None:
    service = BlobServiceClient.from_connection_string(azure_conn_str)
    container_client = service.get_container_client(container)
    corte = datetime.now(timezone.utc) - timedelta(days=retencao_dias)
    for blob in container_client.list_blobs():
        if blob.last_modified and blob.last_modified < corte:
            try:
                container_client.delete_blob(blob.name)
            except AzureError:
                pass


def _rodar_backup_sync(servidor: str, banco: str) -> dict:
    t0 = datetime.now()
    cfg = _get_config_sync(servidor, banco)
    if not cfg.get("success"):
        msg = f"Falha ao ler configuração: {cfg.get('message')}"
        _registrar_log_sync(servidor, banco, sucesso=False, destino="?", caminho_ou_url="", tamanho_mb=None, duracao_segundos=0, mensagem=msg)
        return {"success": False, "message": msg}
    d = cfg["dados"]
    destino = d.get("destino") or "LOCAL"
    banco_esc = banco.replace("]", "]]")
    nome_arquivo = f"{banco}_{t0:%Y%m%d_%H%M%S}.bak"

    try:
        conn = _open_conn(servidor, banco, timeout=_TIMEOUT_BACKUP_SEGUNDOS)
    except Exception as e:
        msg = f"Falha ao conectar: {e}"
        _registrar_log_sync(servidor, banco, sucesso=False, destino=destino, caminho_ou_url="", tamanho_mb=None, duracao_segundos=0, mensagem=msg)
        return {"success": False, "message": msg}

    caminho_ou_url = ""
    try:
        cur = conn.cursor(as_dict=True)
        conn.autocommit(True)  # BACKUP/CREATE CREDENTIAL não podem rodar dentro de transação de usuário

        if destino == "BLOB":
            cur.execute("SELECT Azure_ConnectionString FROM controle_aux")
            row = cur.fetchone()
            azure_conn_str = (row.get("Azure_ConnectionString") or "").strip() if row else ""
            if not azure_conn_str:
                raise ValueError("Azure_ConnectionString não configurada em Controle do Sistema.")
            container = d.get("blob_container") or "backups-sql"
            _, container_url = _preparar_backup_blob_sync(cur, azure_conn_str, container)
            caminho_ou_url = f"{container_url}/{nome_arquivo}"
            url_esc = caminho_ou_url.replace("'", "''")
            credential_esc = container_url.replace("'", "''")
            cur.execute(f"BACKUP DATABASE [{banco_esc}] TO URL = '{url_esc}' WITH CREDENTIAL = '{credential_esc}'")
            _limpar_backups_antigos_blob_sync(azure_conn_str, container, int(d.get("retencao_dias") or 30))
        else:
            pasta = (d.get("pasta_local") or "").rstrip("\\/")
            if not pasta:
                raise ValueError("Pasta de destino local não configurada.")
            caminho_ou_url = f"{pasta}\\{nome_arquivo}"
            caminho_esc = caminho_ou_url.replace("'", "''")
            cur.execute(f"BACKUP DATABASE [{banco_esc}] TO DISK = '{caminho_esc}'")
            _limpar_backups_antigos_local_sync(cur, pasta, int(d.get("retencao_dias") or 30))

        tamanho_mb = None
        try:
            cur.execute(
                "SELECT TOP 1 backup_size/1024.0/1024.0 AS mb FROM msdb.dbo.backupset "
                "WHERE database_name = %s ORDER BY backup_finish_date DESC",
                (banco,),
            )
            row = cur.fetchone()
            if row and row.get("mb") is not None:
                tamanho_mb = round(float(row["mb"]), 2)
        except Exception:
            pass  # tamanho é informativo — nunca falha o backup por causa disso

        conn.autocommit(False)
        cur.close()
    except Exception as e:
        try:
            conn.autocommit(False)
        except Exception:
            pass
        duracao = int((datetime.now() - t0).total_seconds())
        msg = f"Falha no backup ({destino}): {e}"
        _registrar_log_sync(servidor, banco, sucesso=False, destino=destino, caminho_ou_url=caminho_ou_url, tamanho_mb=None, duracao_segundos=duracao, mensagem=msg)
        return {"success": False, "message": msg}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    duracao = int((datetime.now() - t0).total_seconds())
    msg = f"Backup concluído em {duracao}s" + (f" ({tamanho_mb} MB)" if tamanho_mb is not None else "")
    _registrar_log_sync(servidor, banco, sucesso=True, destino=destino, caminho_ou_url=caminho_ou_url, tamanho_mb=tamanho_mb, duracao_segundos=duracao, mensagem=msg)
    return {"success": True, "message": msg}


def _ciclo_backup_sync() -> None:
    if not _CONN_FILE.is_file():
        return
    try:
        conn_info = json.loads(_CONN_FILE.read_text(encoding="utf-8"))
        servidor, banco = conn_info.get("servidor"), conn_info.get("banco")
    except Exception:
        return
    if not servidor or not banco:
        return
    if not _deve_rodar_agora_sync(servidor, banco):
        return
    _rodar_backup_sync(servidor, banco)


async def get_config(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_config_sync, servidor, banco)


async def save_config(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_save_config_sync, servidor, banco, dados)


async def listar_logs(servidor: str, banco: str, limite: int = 50) -> dict:
    return await asyncio.to_thread(_listar_logs_sync, servidor, banco, limite)


async def executar_agora(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_rodar_backup_sync, servidor, banco)


async def loop_backup_sistema() -> None:
    """Tarefa de fundo — nunca derruba o processo se um ciclo falhar
    (mesmo princípio de `manutencao_indices_service.loop_manutencao_
    indices`/`servico_sistema_service.loop_verificacao_atualizacao`)."""
    while True:
        try:
            await asyncio.sleep(_INTERVALO_CICLO_SEGUNDOS)
            await asyncio.to_thread(_ciclo_backup_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Ciclo de backup programado falhou.", exc_info=True)
