"""Conexão SQL Server (pymssql) e helpers de serialização.

Regra de negócio das credenciais:
  • Bancos hospedados no Azure SQL (host *.database.windows.net) usam a conta "suporte".
  • Bancos locais / on-premises (qualquer outro host) usam a conta "sa".
As credenciais ficam preferencialmente em variáveis de ambiente; os valores
abaixo são apenas fallback para desenvolvimento local.
"""
import os
import traceback
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

import pymssql

SQL_AZURE_USER = os.environ.get("SQL_AZURE_USER", "suporte")
SQL_AZURE_PASSWORD = os.environ.get("SQL_AZURE_PASSWORD", "Cmslrav@155")
SQL_LOCAL_USER = os.environ.get("SQL_LOCAL_USER", "sa")
SQL_LOCAL_PASSWORD = os.environ.get("SQL_LOCAL_PASSWORD", "Cmslrav@155")
SQL_TDS_VERSION = os.environ.get("SQL_TDS_VERSION", "7.4")


def _is_azure_server(servidor: str) -> bool:
    """Heurística simples: tudo que termina em .database.windows.net é Azure."""
    return ".database.windows.net" in (servidor or "").strip().lower()


def _pick_sql_credentials(servidor: str) -> tuple[str, str]:
    """Retorna (user, password) conforme o tipo do host (Azure vs local)."""
    if _is_azure_server(servidor):
        return SQL_AZURE_USER, SQL_AZURE_PASSWORD
    return SQL_LOCAL_USER, SQL_LOCAL_PASSWORD


# Mantidos por retro-compatibilidade — apontam para o conjunto padrão (Azure).
# Código novo deve usar _pick_sql_credentials(servidor).
SQL_ADMIN_USER = SQL_AZURE_USER
SQL_ADMIN_PASSWORD = SQL_AZURE_PASSWORD


def _open_conn(servidor: str, banco: str, timeout: int = 10):
    """Abre conexão SQL Server com a credencial adequada ao host.

    • Hosts *.database.windows.net → conta Azure ("suporte").
    • Demais hosts (SQL Server local/on-prem) → conta "sa".
    """
    server = (servidor or "").strip()
    user, password = _pick_sql_credentials(server)
    return pymssql.connect(
        server=server,
        user=user,
        password=password,
        database=banco,
        login_timeout=timeout, timeout=timeout,
        tds_version=SQL_TDS_VERSION,
    )


def _to_json_safe(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, bytes):
            try:
                out[k] = v.decode("utf-8", errors="replace")
            except Exception:
                out[k] = None
        else:
            out[k] = v
    return out


def friendly_db_error(e: Exception) -> str:
    """Traduz uma exceção de conexão/consulta ao SQL Server (pymssql/FreeTDS/
    DB-Lib) numa mensagem em português sem jargão técnico, pra mostrar direto
    ao usuário final (ex.: tela de login) em vez do texto cru do driver
    ("DB-Lib error message 20003, severity 6:\\nAdaptive Server connection
    timed out..."). O texto técnico original continua disponível pra quem
    precisa depurar via os campos error_line/error_code_line/error_query
    (ver auth_service.py) — esta função só troca a mensagem PRINCIPAL."""
    raw = str(e)
    low = raw.lower()
    # Nota: pymssql/FreeTDS embrulha vários tipos de falha de conexão sob o
    # mesmo código numérico (18456) — não dá pra confiar só no número, só no
    # texto da mensagem (ex.: um timeout de conexão também chega com "18456"
    # no início, sem ter nada a ver com usuário/senha errados).
    if "login failed" in low:
        return "Usuário ou senha do banco de dados incorretos."
    if "cannot open database" in low:
        return "O banco de dados configurado não foi encontrado no servidor."
    if "timed out" in low or "timeout" in low:
        return ("Não foi possível conectar ao servidor — o tempo de conexão "
                "esgotou. Verifique se o servidor está ligado e acessível pela rede.")
    if ("unable to connect" in low or "getaddrinfo" in low or "no such host" in low
            or "name or service not known" in low or "could not open a connection" in low):
        return "Não foi possível encontrar o servidor. Verifique o endereço configurado na conexão."
    if "adaptive server connection failed" in low or "net-lib error" in low:
        return "Não foi possível conectar ao servidor de banco de dados. Verifique se ele está ligado e acessível."
    return "Não foi possível conectar ao banco de dados no momento. Tente novamente em instantes."


def _err_origin() -> tuple[Optional[str], Optional[str]]:
    """Retorna (arquivo:linha, código_fonte_da_linha) do frame onde a exceção atual ocorreu."""
    import sys
    tb = traceback.extract_tb(sys.exc_info()[2])
    if not tb:
        return None, None
    last = tb[-1]
    filename = os.path.basename(last.filename or "")
    line = f"{filename}:{last.lineno}"
    code = (last.line or "").strip() if hasattr(last, "line") else None
    return line, code


# ---------- Descobre tamanhos máximos das colunas dinamicamente ----------
_COLUMN_SIZES_CACHE: dict[tuple[str, str], dict[str, int]] = {}


def _get_col_sizes(conn, banco: str, table: str) -> dict[str, int]:
    """Retorna {coluna: tamanho_máximo} para colunas char/varchar/nchar/nvarchar.
    Resultado em cache por (banco, tabela). -1 indica nvarchar(MAX)."""
    key = (banco.lower(), table.lower())
    if key in _COLUMN_SIZES_CACHE:
        return _COLUMN_SIZES_CACHE[key]
    sizes: dict[str, int] = {}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = %s AND DATA_TYPE IN ('varchar','nvarchar','char','nchar')",
            (table,),
        )
        for r in cur.fetchall():
            cname = (r.get("COLUMN_NAME") or "").lower()
            mlen = r.get("CHARACTER_MAXIMUM_LENGTH")
            if cname:
                sizes[cname] = int(mlen) if mlen is not None else -1
        cur.close()
    except Exception:
        pass
    _COLUMN_SIZES_CACHE[key] = sizes
    return sizes


def _trunc(value, sizes: dict[str, int], col: str, fallback: int = 60):
    """Trunca valor para o tamanho máximo da coluna (ou fallback se desconhecida)."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    s = value
    maxlen = sizes.get(col.lower())
    if maxlen is None:
        maxlen = fallback
    elif maxlen < 0:
        return s  # nvarchar(MAX) — sem limite
    return s[:maxlen]
