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
