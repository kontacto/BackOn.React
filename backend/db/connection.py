"""Conexão SQL Server (pymssql) e helpers de serialização.

Regra de negócio das credenciais:
  • Bancos hospedados no Azure SQL (host *.database.windows.net) usam a conta "suporte".
  • Bancos locais / on-premises (qualquer outro host) usam a conta "sa".
As credenciais ficam preferencialmente em variáveis de ambiente; os valores
abaixo são apenas fallback para desenvolvimento local.
"""
import logging
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
# Achado real, 2026-08-11: TDS 7.4 (padrão original) falha com
# "(20002) Adaptive Server connection failed" contra alguns SQL Server 2014
# mais antigos/menos atualizados (ex.: DESKTOP-TDK482U, build 12.0.2000) —
# mesma credencial e mesma rede, só a versão do protocolo TDS é diferente.
# Um 1º fix baixou o padrão pra 7.0 (a versão mais retrocompatível) — isso
# CAUSOU UMA REGRESSÃO REAL, achada ao vivo no mesmo dia contra "Baixo
# Brisa Real" (Pedido Bar web): TDS 7.0 é ANTERIOR ao tipo DATE do SQL
# Server (introduzido só a partir de TDS 7.3/SQL Server 2008) — negociando
# em 7.0, o FreeTDS/pymssql não reconhece colunas DATE como tipo temporal e
# devolve `str` cru em vez de `datetime.date`, quebrando TODO `.isoformat()`
# do backend (`'str' object has no attribute 'isoformat'`) pra qualquer
# conexão que negocie em 7.0 — e como 7.0 é a mais permissiva, isso passou
# a acontecer em TODA conexão, não só na que motivou o fix original.
# Corrigido tentando a versão MAIS MODERNA primeiro (7.4, maior fidelidade
# de tipo) e só degradando pra uma mais antiga quando a negociação
# realmente falhar (`_TDS_VERSION_FALLBACKS` abaixo, agora em ordem
# decrescente) — preserva a recuperação automática pro caso
# DESKTOP-TDK482U sem sacrificar tipos de data pra todo o resto da frota.


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


# Ordem de fallback de versão TDS — usada quando a versão configurada
# (SQL_TDS_VERSION) falha por INCOMPATIBILIDADE DE PROTOCOLO (não por
# senha/host/timeout errado). Achado real, 2026-08-11: um SQL Server 2014
# menos atualizado (DESKTOP-TDK482U, build 12.0.2000) rejeita TDS 7.1+ com
# "(20002) Adaptive Server connection failed", mesma credencial/rede que
# funciona perfeitamente contra outro servidor (GERDELL, build 12.0.5000)
# só que com uma versão de protocolo mais baixa. Como este backend atende
# várias instalações de cliente com versões de SQL Server variadas (e
# imprevisíveis com antecedência), a defesa não é só usar um padrão fixo —
# é tentar em cascata, pra qualquer servidor futuro com uma incompatibilidade
# ainda não vista se recuperar sozinho, sem precisar de uma nova rodada de
# investigação manual como esta. ORDEM DECRESCENTE (mais moderna primeiro) —
# ver correção acima (2026-08-11, mesmo dia): tentar a versão mais antiga
# primeiro dava tipagem de DATE incorreta (str em vez de date) pra toda
# conexão que negociasse com sucesso em 7.0, não só pra quem genuinamente
# precisava da versão antiga.
_TDS_VERSION_FALLBACKS = ("7.4", "7.3", "7.2", "7.1", "7.0")


def _e_falha_negociacao_tds(e: Exception) -> bool:
    """True só para o padrão específico de falha de NEGOCIAÇÃO DE PROTOCOLO
    (onde trocar a versão TDS genuinamente pode resolver) — nunca pra senha
    errada, host inexistente ou timeout de rede, onde tentar de novo com
    outra versão só perde tempo repetindo o mesmo erro."""
    low = str(e).lower()
    return "adaptive server connection failed" in low or "net-lib error" in low


def _connect_with_tds_fallback(server: str, user: str, password: str, banco: str, timeout: int):
    """Abre uma conexão `pymssql` tentando a versão TDS configurada
    (`SQL_TDS_VERSION`) primeiro e, se a falha for especificamente de
    negociação de protocolo (`_e_falha_negociacao_tds`), tenta em cascata
    as demais versões conhecidas (`_TDS_VERSION_FALLBACKS`) antes de
    desistir — outros tipos de falha (senha errada, host fora do ar,
    timeout) não acionam a cascata, já que trocar a versão TDS não
    resolveria e só atrasaria o erro real.

    Extraído de `_open_conn` em 2026-08-11 pra ser reaproveitado também
    por `auth_service._sql_login_sync` — achado ao vivo no mesmo dia: o
    login abre sua PRÓPRIA conexão fora de `_open_conn` (roda antes de
    qualquer sessão existir), então tinha ficado de fora da cascata
    quando ela foi criada só dentro de `_open_conn` — reproduzindo, só na
    tela de Login, o MESMO "Adaptive Server connection failed" que a
    cascata inteira existe pra evitar. Levanta a última exceção capturada
    (sem traduzir) se todas as versões falharem — quem chama decide como
    traduzir/embrulhar."""
    versoes = [SQL_TDS_VERSION] + [v for v in _TDS_VERSION_FALLBACKS if v != SQL_TDS_VERSION]
    ultimo_erro: Optional[Exception] = None
    for tds in versoes:
        try:
            return pymssql.connect(
                server=server,
                user=user,
                password=password,
                database=banco,
                login_timeout=timeout, timeout=timeout,
                tds_version=tds,
            )
        except Exception as e:
            ultimo_erro = e
            if not _e_falha_negociacao_tds(e):
                raise  # não é problema de versão de protocolo — tentar outra não ajuda
    raise ultimo_erro  # type: ignore[misc]


def _open_conn(servidor: str, banco: str, timeout: int = 10):
    """Abre conexão SQL Server com a credencial adequada ao host.

    • Hosts *.database.windows.net → conta Azure ("suporte").
    • Demais hosts (SQL Server local/on-prem) → conta "sa".

    Delega a abertura em si (com cascata de versão TDS) pra
    `_connect_with_tds_fallback`. Qualquer falha aqui é traduzida por
    `friendly_db_error` antes de propagar — este é o ÚNICO ponto de
    abertura de conexão usado por todo o resto do backend (~70 services),
    então traduzir aqui cobre toda mensagem de "Falha conexão: ..." do
    sistema de uma vez, sem precisar tocar em cada call site (`except
    Exception as e: message=f"Falha conexão: {e}"` continua igual em todo
    canto, só que `{e}` agora já vem com o texto amigável em vez do erro
    cru do driver). A tela de Login (`auth_service.py`) abre sua própria
    conexão fora deste helper (roda antes de qualquer sessão existir) mas
    reaproveita `_connect_with_tds_fallback` pra ter a mesma cascata —
    regra [GLOBAL] "mensagens do sistema devem usar linguagem menos
    técnica pro usuário final", pedido explícito do usuário, 2026-07-18.
    """
    server = (servidor or "").strip()
    user, password = _pick_sql_credentials(server)

    try:
        conn = _connect_with_tds_fallback(server, user, password, banco, timeout)
    except Exception as e:
        raise ConnectionError(friendly_db_error(e)) from e

    _ensure_schema_integral(conn, server, banco)
    return conn


def _ensure_schema_integral(conn, servidor: str, banco: str) -> None:
    """Aplica de forma INTEGRAL (não pontual) toda migração de schema
    pendente pra este banco, numa única chamada — pedido explícito do
    usuário, 2026-08-11 ("a persistência não pode ser de forma pontual.
    tem que ser integral"), ver CLAUDE.md > "Cada app precisa se
    auto-atualizar no banco" e `services/schema_ensure.py` (registro
    central de todas as migrações).

    Import TARDIO (não no topo do arquivo) — `schema_ensure` importa de
    vários services, que por sua vez importam `_open_conn` deste módulo
    no topo dos arquivos deles; um import no topo daqui criaria um ciclo.
    Falha aqui NUNCA derruba a conexão em si — só registra e segue (cada
    `_ensure_*` individual continua existindo como rede de segurança no
    próprio ponto de uso original, então uma falha pontual aqui não
    significa que a feature específica vai quebrar)."""
    try:
        from services.schema_ensure import ensure_all_schema, ensure_auto_close_off
        # as_dict=True — todo `_ensure_*` original foi escrito assumindo
        # esse formato de cursor (mesmo padrão usado em todo o resto do
        # backend), não o tuple padrão do pymssql.
        cur = conn.cursor(as_dict=True)
        ensure_all_schema(cur, servidor, banco)
        conn.commit()
        cur.close()
        # Roda DEPOIS do commit acima, nunca dentro do mesmo lote — ver
        # docstring de `ensure_auto_close_off` (ALTER DATABASE não pode
        # rodar dentro de transação de usuário).
        ensure_auto_close_off(conn, servidor, banco)
    except Exception:
        logging.getLogger(__name__).warning(
            "Falha ao garantir schema integral em %s/%s", servidor, banco, exc_info=True
        )
        try:
            conn.rollback()
        except Exception:
            pass


def iso(value: Any) -> Optional[str]:
    """Converte um valor de data/hora pra string ISO, tolerando os dois
    formatos que o driver pode devolver pra uma coluna DATE/DATETIME:
    `datetime.date`/`datetime.datetime` (caso normal) OU `str` já crua —
    achado ao vivo 2026-08-11 contra "Baixo Brisa Real"
    (`DESKTOP-TDK482U`/`BD_BAIXOBRISA`, SQL Server 2014 SP1 build
    12.0.2000): esse servidor só negocia TDS 7.0 (ver `_TDS_VERSION_
    FALLBACKS` acima), versão anterior ao tipo DATE do protocolo — o
    FreeTDS/pymssql devolve a coluna como string crua nesse caso, e todo
    `campo.isoformat()` direto (sem passar por este helper) quebra com
    `'str' object has no attribute 'isoformat'`. Reordenar a cascata TDS
    (ver acima) resolve pra servidores que suportam uma versão mais nova,
    mas não pra este caso específico, que só tem TDS 7.0 disponível —
    daí a necessidade de tolerar ambos os tipos aqui. Ponto único de
    correção pra qualquer service que formatar data — usar em vez de
    `campo.isoformat() if campo else None` cru."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


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


_CONNECTION_ERROR_PATTERNS = (
    "login failed", "cannot open database", "timed out", "timeout",
    "unable to connect", "getaddrinfo", "no such host",
    "name or service not known", "could not open a connection",
    "adaptive server connection failed", "net-lib error",
    # Padrões de conexão que CAI NO MEIO de uma query já em andamento (não
    # na abertura inicial) — ex.: "DBPROCESS is dead or not enabled" visto
    # ao vivo no KPDV (2026-08-11, abrir venda contra GERDELL/BARESTELA).
    "dbprocess is dead", "server connection lost", "connection is closed",
    "read from the server failed", "not connected to any mssql server",
)


def is_connection_error(e: Exception) -> bool:
    """True quando o texto da exceção bate com um dos padrões conhecidos de
    falha de CONEXÃO (driver/rede/servidor fora do ar) — inclusive quando a
    conexão caiu NO MEIO de uma query já em andamento, não só na abertura
    inicial. Usado pelos call sites que capturam exceção depois de já ter
    aberto a conexão (ver `friendly_db_error`) pra decidir se aplicam a
    tradução amigável ou preservam a mensagem original — nunca aplicar a
    tradução "sem querer" em cima de um erro de negócio genuíno (chave
    duplicada, violação de constraint, etc.), que deve continuar mostrando
    o texto real da query pra não confundir com um problema de rede."""
    low = str(e).lower()
    return any(p in low for p in _CONNECTION_ERROR_PATTERNS)


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
    if ("dbprocess is dead" in low or "server connection lost" in low or "connection is closed" in low
            or "read from the server failed" in low or "not connected to any mssql server" in low):
        return ("A conexão com o banco de dados caiu no meio da operação. "
                "Tente novamente — se persistir, verifique a estabilidade da rede/servidor.")
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
