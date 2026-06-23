from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any, List, Optional
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
import asyncio
import traceback
import pymssql

# MongoDB é opcional — usado só pelos endpoints legados /status.
# Se motor não estiver instalado OU MONGO_URL não estiver no .env,
# esses endpoints ficam desabilitados (não quebra o app).
try:
    from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
    _MOTOR_AVAILABLE = True
except Exception:
    _MOTOR_AVAILABLE = False


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection (opcional)
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
if _MOTOR_AVAILABLE and mongo_url and db_name:
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    _MONGO_ENABLED = True
else:
    client = None
    db = None
    _MONGO_ENABLED = False

# =====================================================================
# CREDENCIAIS SQL SERVER — selecionadas por tipo de servidor
# =====================================================================
# Regra de negócio:
#   • Bancos hospedados no Azure SQL (host *.database.windows.net) usam
#     a conta "suporte".
#   • Bancos locais / on-premises (qualquer outro host) usam a conta "sa".
# As credenciais ficam preferencialmente em variáveis de ambiente; os
# valores abaixo são apenas fallback para desenvolvimento local.
# =====================================================================
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

app = FastAPI()
api_router = APIRouter(prefix="/api")


class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class LoginRequest(BaseModel):
    empresa: str
    servidor: str
    banco: str
    usuario: str
    senha: str
    timeout: Optional[int] = 8


class LoginResponse(BaseModel):
    success: bool
    message: str
    empresa: Optional[str] = None
    server: Optional[str] = None
    database: Optional[str] = None
    usuario: Optional[dict] = None
    funcionario: Optional[dict] = None
    # Diagnóstico de erro
    error_step: Optional[str] = None          # connect | query_usuarios | query_funcionarios
    error_line: Optional[str] = None          # arquivo:linha
    error_code_line: Optional[str] = None     # trecho de código que falhou
    error_query: Optional[str] = None         # SQL executado (parâmetros omitidos)
    attempted: Optional[dict] = None          # dados da conexão tentada


@api_router.get("/")
async def root():
    return {"message": "Back-On API ativo"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.dict())
    if _MONGO_ENABLED:
        await db.status_checks.insert_one(status_obj.dict())
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    if not _MONGO_ENABLED:
        return []
    docs = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**d) for d in docs]


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


GENERIC_AUTH_ERROR = "Usuário ou senha inválidos."


def criptografa_frase(senha: str) -> str:
    """Equivalente Python à função C# Criptografa_Frase do sistema BackOn.
    Aplica cifra de César +3 (cada caractere + 3 no código Unicode).
    Mesma lógica usada para gravar a senha em usuarios.senha."""
    if not senha:
        return ""
    senha = senha.strip()
    return "".join(chr(ord(c) + 3) for c in senha)


# Usuário master do sistema BackOn — acesso total, sem depender da tabela usuarios.
# Equivalente ao bloco C#:
#   if (SenhaUsuario == "$KONT2011" & NomeUsuario.ToUpper() == "KONTACTO") { ... }
MASTER_USER_NAME = "KONTACTO"
MASTER_USER_PASSWORD = "$KONT2011"


def _build_master_session(empresa: str, servidor: str, banco: str) -> LoginResponse:
    return LoginResponse(
        success=True,
        message="Login realizado com sucesso (usuário master).",
        empresa=empresa,
        server=servidor,
        database=banco,
        usuario={
            "usuario": MASTER_USER_NAME,
            "nome": "KONTACTO Sistemas",
            "administrador": 1,
            "administrador_label": "Sim",
            "classe": 0,
            "classe_descricao": "Master",
            "classe_label": "0 - Master",
            "controla_carteira": False,
            "situacao": "A",
            "situacao_label": "Ativo",
            "master": True,
        },
        funcionario={
            "nome_guerra": MASTER_USER_NAME,
            "nome": "KONTACTO Sistemas",
            "cod_funcao": "ADM",
            "situacao": "A",
            "situacao_label": "Ativo",
            "tipo_prof": "M",
            "empresa": 0,
            "master": True,
        },
    )

# Colunas relevantes da tabela 'funcionarios' (a tabela tem 80+ colunas,
# selecionamos só o que o app exibe ou pode usar futuramente).
FUNCIONARIO_COLUMNS = [
    "codigo_int", "nome_guerra", "nome", "cod_funcao", "codcargo",
    "email", "tel_prof", "ddd_prof", "tel_cel_prof", "ddd_cel_prof",
    "data_nasc", "admissao", "desligamento", "situacao",
    "endereco", "bairr_prof", "cid_prof", "est_prof", "cep_prof",
    "tipo_prof", "empresa", "turno", "sexo_prof",
]
FUNCIONARIO_SELECT = ", ".join(FUNCIONARIO_COLUMNS)


def _enrich_usuario(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    out = dict(row)
    if "administrador" in out and out["administrador"] is not None:
        out["administrador_label"] = "Sim" if int(out["administrador"]) == 1 else "Não"
    # Descrição do grupo vem do JOIN classes_usuarios (campo classe_descricao).
    # Monta classe_label no formato "código - descrição" (ex: "3 - SÓCIO").
    descr = (out.get("classe_descricao") or "").strip() if out.get("classe_descricao") else ""
    classe_num = out.get("classe")
    if descr:
        out["classe_descricao"] = descr  # normaliza (strip)
        if classe_num is not None:
            out["classe_label"] = f"{classe_num} - {descr}"
        else:
            out["classe_label"] = descr
    elif classe_num is not None:
        out["classe_label"] = f"Classe {classe_num}"
    return out


def _enrich_funcionario(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    out = dict(row)
    sit_map = {"A": "Ativo", "I": "Inativo", "F": "Férias", "D": "Desligado"}
    if out.get("situacao"):
        out["situacao_label"] = sit_map.get(str(out["situacao"]).strip().upper(),
                                            str(out["situacao"]).strip())
    # Telefones combinados (DDD + número)
    if out.get("ddd_cel_prof") and out.get("tel_cel_prof"):
        out["celular"] = f"({out['ddd_cel_prof']}) {out['tel_cel_prof']}"
    elif out.get("tel_cel_prof"):
        out["celular"] = str(out["tel_cel_prof"])
    if out.get("ddd_prof") and out.get("tel_prof"):
        out["telefone"] = f"({out['ddd_prof']}) {out['tel_prof']}"
    elif out.get("tel_prof"):
        out["telefone"] = str(out["tel_prof"])
    return out


def _err_origin() -> tuple[Optional[str], Optional[str]]:
    """Retorna (arquivo:linha, código_fonte_da_linha) do frame onde a exceção atual ocorreu."""
    tb = traceback.extract_tb(__import__("sys").exc_info()[2])
    if not tb:
        return None, None
    last = tb[-1]
    filename = os.path.basename(last.filename or "")
    line = f"{filename}:{last.lineno}"
    code = (last.line or "").strip() if hasattr(last, "line") else None
    return line, code


def _sql_login_sync(payload: LoginRequest) -> LoginResponse:
    # IMPORTANTE: o servidor é usado EXATAMENTE como o app enviou (sem parsing).
    # Aceita qualquer formato suportado pelo pymssql/FreeTDS:
    #   "localhost"
    #   "192.168.0.10"
    #   "SRV-KONTACTO\\SQLEXPRESS"
    #   "192.168.0.10,1433"
    #   "erp.empresa.com.br"
    servidor = (payload.servidor or "").strip()

    # ------- Checagem do usuário master (bypass total do SQL) -------
    if (payload.usuario or "").strip().upper() == MASTER_USER_NAME and payload.senha == MASTER_USER_PASSWORD:
        return _build_master_session(payload.empresa, servidor, payload.banco)

    sql_user, sql_password = _pick_sql_credentials(servidor)

    attempted = {
        "empresa": payload.empresa,
        "server": servidor,
        "database": payload.banco,
        "sql_user": sql_user,
        "login_user": payload.usuario,
        "login_timeout": payload.timeout or 8,
    }

    # ------- Etapa 1: abrir conexão -------
    try:
        conn = pymssql.connect(
            server=servidor,                        # ← do app, sem alteração
            user=sql_user,                          # ← suporte (Azure) | sa (local)
            password=sql_password,
            database=payload.banco,                 # ← do app
            login_timeout=payload.timeout or 8,
            timeout=payload.timeout or 8,
            tds_version=SQL_TDS_VERSION,
        )
    except pymssql.OperationalError as e:
        line, code = _err_origin()
        return LoginResponse(
            success=False,
            message=f"Falha na conexão: {e}",
            error_step="connect",
            error_line=line,
            error_code_line=code,
            attempted=attempted,
        )
    except Exception as e:  # noqa: BLE001
        line, code = _err_origin()
        return LoginResponse(
            success=False,
            message=f"Erro inesperado: {e}",
            error_step="connect",
            error_line=line,
            error_code_line=code,
            attempted=attempted,
        )

    # ------- Etapa 2: consultar usuarios -------
    query_usuarios = (
        "SELECT u.usuario, u.classe, u.administrador, "
        "       c.classe AS classe_descricao "
        "FROM usuarios u "
        "LEFT JOIN classes_usuarios c ON c.codigo = u.classe "
        "WHERE u.usuario = %s AND u.senha = %s"
    )
    query_funcionarios = f"SELECT {FUNCIONARIO_SELECT} FROM funcionarios WHERE nome_guerra = %s"
    try:
        cur = conn.cursor(as_dict=True)
        # Aplica a mesma cifra que o sistema BackOn original usa para gravar a senha
        senha_cripto = criptografa_frase(payload.senha)
        cur.execute(query_usuarios, (payload.usuario, senha_cripto))
        usuario_row = cur.fetchone()
        if not usuario_row:
            cur.close()
            conn.close()
            return LoginResponse(
                success=False,
                message=GENERIC_AUTH_ERROR,
                error_step="query_usuarios",
                attempted=attempted,
            )

        usuario_obj = _enrich_usuario(_to_json_safe(usuario_row))
        if usuario_obj:
            for k in list(usuario_obj.keys()):
                if k.lower() in {"senha", "password", "pwd", "hash_senha", "senha_hash"}:
                    usuario_obj.pop(k, None)

        # ------- Etapa 3: consultar funcionarios -------
        cur2 = conn.cursor(as_dict=True)
        cur2.execute(query_funcionarios, (payload.usuario,))
        funcionario_row = cur2.fetchone()
        funcionario_obj = _enrich_funcionario(_to_json_safe(funcionario_row))

        cur.close()
        cur2.close()
        conn.close()

        return LoginResponse(
            success=True,
            message="Login realizado com sucesso.",
            empresa=payload.empresa,
            server=servidor,
            database=payload.banco,
            usuario=usuario_obj,
            funcionario=funcionario_obj,
        )
    except pymssql.OperationalError as e:
        try:
            conn.close()
        except Exception:
            pass
        line, code = _err_origin()
        # Determinar qual query falhou olhando o code-line capturado
        step = "query_funcionarios" if code and "funcionarios" in code else "query_usuarios"
        failed_query = query_funcionarios if step == "query_funcionarios" else query_usuarios
        return LoginResponse(
            success=False,
            message=f"Erro de banco: {e}",
            error_step=step,
            error_line=line,
            error_code_line=code,
            error_query=failed_query,
            attempted=attempted,
        )
    except Exception as e:  # noqa: BLE001
        try:
            conn.close()
        except Exception:
            pass
        line, code = _err_origin()
        step = "query_funcionarios" if code and "funcionarios" in code else "query_usuarios"
        failed_query = query_funcionarios if step == "query_funcionarios" else query_usuarios
        return LoginResponse(
            success=False,
            message=f"Erro ao consultar usuário: {e}",
            error_step=step,
            error_line=line,
            error_code_line=code,
            error_query=failed_query,
            attempted=attempted,
        )


@api_router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    if not payload.servidor.strip() or not payload.banco.strip():
        raise HTTPException(status_code=400, detail="Servidor e Banco são obrigatórios.")
    if not payload.usuario.strip() or not payload.senha:
        raise HTTPException(status_code=400, detail="Usuário e senha são obrigatórios.")
    result = await asyncio.to_thread(_sql_login_sync, payload)
    return result


class ClientesRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    page: int = 1
    size: int = 20


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


# =====================================================================
# Validação CPF / CNPJ (incluindo CNPJ alfanumérico — RFB 2026)
# =====================================================================
def _only_alnum_upper(s: str) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def _valid_cpf(s: str) -> bool:
    s = "".join(ch for ch in (s or "") if ch.isdigit())
    if len(s) != 11 or s == s[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(s[j]) * (i + 1 - j) for j in range(i))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(s[i]):
            return False
    return True


def _valid_cnpj(s: str) -> bool:
    """Valida CNPJ numérico OU alfanumérico (2026).
    Regra alfanumérica: primeiras 12 posições aceitam A-Z e 0-9;
    duas últimas (DV) permanecem numéricas. Valor de cada caractere
    é (ord(c) - ord('0')), ou seja A=17, B=18, ..., Z=42.
    Pesos: 5,4,3,2,9,8,7,6,5,4,3,2 (DV1) e 6,5,4,3,2,9,8,7,6,5,4,3,2 (DV2).
    """
    s = _only_alnum_upper(s)
    if len(s) != 14:
        return False
    for c in s[:12]:
        if not (c.isdigit() or ("A" <= c <= "Z")):
            return False
    if not (s[12].isdigit() and s[13].isdigit()):
        return False
    # rejeita sequências repetidas (00000000000000)
    if len(set(s)) == 1:
        return False

    def val(c: str) -> int:
        return ord(c) - ord("0")

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma1 = sum(val(s[i]) * pesos1[i] for i in range(12))
    dv1 = soma1 % 11
    dv1 = 0 if dv1 < 2 else 11 - dv1
    if dv1 != int(s[12]):
        return False

    soma2 = sum(val(s[i]) * pesos2[i] for i in range(13))
    dv2 = soma2 % 11
    dv2 = 0 if dv2 < 2 else 11 - dv2
    if dv2 != int(s[13]):
        return False
    return True


def _validate_cgc_cpf(value: str) -> tuple[bool, str]:
    """Retorna (ok, msg). Vazio é considerado OK (campo opcional)."""
    raw = _only_alnum_upper(value)
    if not raw:
        return True, ""
    if len(raw) == 11:
        return (_valid_cpf(raw), "CPF inválido.")
    if len(raw) == 14:
        return (_valid_cnpj(raw), "CNPJ inválido.")
    return False, "CGC/CPF deve ter 11 (CPF) ou 14 (CNPJ) caracteres."


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


def _list_clientes_sync(req: ClientesRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}

    try:
        size = max(1, min(100, req.size))
        offset = max(0, (req.page - 1) * size)
        search = (req.search or "").strip()

        where = ""
        params: tuple = ()
        if search:
            where = "WHERE c.nome LIKE %s OR c.cgc_cpf LIKE %s OR c.telefone_cli LIKE %s"
            like = f"%{search}%"
            params = (like, like, like)

        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT COUNT(*) AS total FROM cliente c {where}", params)
        total = cur.fetchone()["total"]

        cur.execute(
            f"SELECT c.codigo, c.nome, c.cgc_cpf, "
            f"       COALESCE(ct.ddd, CAST(c.ddd_cli AS NVARCHAR(4))) AS ddd_cli, "
            f"       COALESCE(ct.tel, c.telefone_cli) AS telefone_cli, "
            f"       c.e_mail, c.situacao, "
            f"       t.descricao AS tipo_descricao "
            f"FROM cliente c "
            f"OUTER APPLY (SELECT TOP 1 ddd, tel FROM cliente_tel WHERE codigo = c.codigo ORDER BY sequencia) ct "
            f"LEFT JOIN tipo_cliente t ON t.codigo = TRY_CAST(c.cliente_forn AS INT) "
            f"{where} "
            f"ORDER BY c.nome OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY",
            params
        )
        rows = [_to_json_safe(r) for r in cur.fetchall()]
        # Telefone formatado
        for r in rows:
            ddd = r.get("ddd_cli") or ""
            tel = (r.get("telefone_cli") or "").strip()
            r["telefone"] = f"({ddd}) {tel}" if ddd and tel else tel
        cur.close()
        conn.close()
        return {"success": True, "items": rows, "total": total, "page": req.page, "size": size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


@api_router.post("/clientes")
async def list_clientes(req: ClientesRequest):
    return await asyncio.to_thread(_list_clientes_sync, req)


# =====================================================================
# Tipo Cliente — dropdown
# =====================================================================
def _list_tipo_cliente_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, descricao FROM tipo_cliente ORDER BY descricao")
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


@api_router.get("/tipo-cliente")
async def list_tipo_cliente(servidor: str, banco: str):
    return await asyncio.to_thread(_list_tipo_cliente_sync, servidor, banco)


# =====================================================================
# GET cliente por código (com endereço primário + telefones)
# =====================================================================
def _get_cliente_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.codigo, c.cgc_cpf, c.nome, c.e_mail, c.inscr_est AS inscre, c.cliente_forn AS tipo, "
            "       c.aceita_email, c.vendedor, c.situacao, "
            "       c.ddd_cli, c.telefone_cli, "
            "       t.descricao AS tipo_descricao "
            "FROM cliente c "
            "LEFT JOIN tipo_cliente t ON t.codigo = TRY_CAST(c.cliente_forn AS INT) "
            "WHERE c.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"success": False, "message": "Cliente não encontrado."}
        cliente = _to_json_safe(row)

        # Endereço (pega o primeiro registro de cliente_end)
        cur.execute(
            "SELECT TOP 1 sequencia, tipo, endereco, numero, complemento, bairro, cidade, uf, cep "
            "FROM cliente_end WHERE codigo = %s ORDER BY sequencia",
            (codigo,),
        )
        end_row = cur.fetchone()
        endereco = _to_json_safe(end_row) if end_row else None

        # Telefones (até 3)
        cur.execute(
            "SELECT TOP 3 sequencia, ddd, tel, descricao "
            "FROM cliente_tel WHERE codigo = %s ORDER BY sequencia",
            (codigo,),
        )
        tel_rows = [_to_json_safe(r) for r in cur.fetchall()]

        cur.close()
        conn.close()
        return {
            "success": True,
            "cliente": cliente,
            "endereco": endereco,
            "telefones": tel_rows,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


@api_router.get("/clientes/{codigo}")
async def get_cliente(codigo: int, servidor: str, banco: str):
    return await asyncio.to_thread(_get_cliente_sync, servidor, banco, codigo)


# Busca cliente por CGC/CPF (alfanumérico, sem máscara). Retorna codigo se achar.
def _find_by_cgc_sync(servidor: str, banco: str, cgc: str) -> dict:
    raw = _only_alnum_upper(cgc)
    if not raw:
        return {"success": False, "message": "CGC/CPF vazio."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 codigo, nome FROM cliente WHERE cgc_cpf = %s",
            (raw,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": True, "found": False}
        return {
            "success": True,
            "found": True,
            "codigo": int(row["codigo"]),
            "nome": (row.get("nome") or "").strip(),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


@api_router.get("/clientes/find/by-cgc")
async def find_cliente_by_cgc(servidor: str, banco: str, cgc: str):
    return await asyncio.to_thread(_find_by_cgc_sync, servidor, banco, cgc)


# =====================================================================
# Produtos (pecas) + Serviços — lista unificada para uso futuro em pedidos.
# =====================================================================
def _list_produtos_servicos_sync(
    servidor: str, banco: str, search: str, page: int, size: int, tipo: str
) -> dict:
    """tipo: 'all' | 'P' (produto/pecas) | 'S' (servico)"""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        items: list[dict] = []
        total = 0
        like = f"%{search.strip()}%" if search else None
        offset = max(0, (page - 1) * size)

        if tipo in ("all", "P"):
            # PRODUTOS (pecas)
            where_p = ""
            params_p: tuple = ()
            if like:
                where_p = "WHERE p.descricao LIKE %s OR CAST(p.codigo_int AS NVARCHAR(20)) LIKE %s"
                params_p = (like, like)
            cur.execute(
                f"SELECT 'P' AS tipo, p.codigo_int AS codigo, p.descricao, "
                f"       p.p_venda AS valor, p.estoque, p.codigo_fab, p.uni "
                f"FROM pecas p {where_p} "
                f"ORDER BY p.descricao",
                params_p,
            )
            for r in cur.fetchall():
                items.append({
                    "tipo": "P",
                    "codigo": (r.get("codigo") or "").strip() if isinstance(r.get("codigo"), str) else str(r.get("codigo") or ""),
                    "descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "estoque": float(r.get("estoque") or 0),
                    "cod_fab": (r.get("codigo_fab") or "").strip(),
                    "unidade": (r.get("uni") or "").strip(),
                })

        if tipo in ("all", "S"):
            # SERVIÇOS
            where_s = ""
            params_s: tuple = ()
            if like:
                where_s = "WHERE s.descricao LIKE %s OR CAST(s.codigo AS NVARCHAR(20)) LIKE %s"
                params_s = (like, like)
            cur.execute(
                f"SELECT 'S' AS tipo, s.codigo, s.descricao, s.valor_hora AS valor "
                f"FROM servicos s {where_s} "
                f"ORDER BY s.descricao",
                params_s,
            )
            for r in cur.fetchall():
                items.append({
                    "tipo": "S",
                    "codigo": (r.get("codigo") or "").strip() if isinstance(r.get("codigo"), str) else str(r.get("codigo") or ""),
                    "descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "estoque": None,
                })

        total = len(items)
        # Paginação em memória (BARESTEL fica abaixo de alguns milhares, ok p/ MVP).
        items_page = items[offset:offset + size]

        cur.close()
        conn.close()
        return {"success": True, "items": items_page, "total": total, "page": page, "size": size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


@api_router.get("/produtos-servicos")
async def list_produtos_servicos(
    servidor: str,
    banco: str,
    search: str = "",
    page: int = 1,
    size: int = 40,
    tipo: str = "all",
):
    return await asyncio.to_thread(
        _list_produtos_servicos_sync, servidor, banco, search, page, size, tipo
    )


# Foto do produto — procura em pasta configurável (env FOTOS_PRODUTOS_DIR).
# Default: /app/fotos_produtos (Linux) ou C:\desenv\fotos_produtos (Windows).
# Aceita extensões: .jpg, .jpeg, .png, .webp. Nome do arquivo = codigo_int.
import os as _os  # noqa: E402

_FOTOS_DIR = _os.environ.get("FOTOS_PRODUTOS_DIR", "/app/fotos_produtos")


@api_router.get("/produtos/foto/{codigo}")
async def get_produto_foto(codigo: str):
    from fastapi.responses import FileResponse, Response  # noqa: E402
    # Sanitiza pra evitar path traversal
    safe = "".join(c for c in codigo if c.isalnum() or c in "-_")
    if not safe:
        return Response(status_code=204)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = _os.path.join(_FOTOS_DIR, f"{safe}{ext}")
        if _os.path.exists(path):
            return FileResponse(path)
    # 204 No Content quando não tem foto (frontend mostra placeholder)
    return Response(status_code=204)


# =====================================================================
# Pedidos (pedido_venda) — CRUD básico
# =====================================================================
SITUACAO_LABEL = {"A": "Aberto", "F": "Fechado", "C": "Cancelado", "PG": "Faturado"}


class PedidosListRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    situacao: Optional[str] = ""  # vazio = todos
    data_ini: Optional[str] = None  # ISO YYYY-MM-DD
    data_fim: Optional[str] = None  # ISO YYYY-MM-DD
    page: int = 1
    size: int = 20


def _list_pedidos_sync(req: PedidosListRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        where_parts: list[str] = []
        params: list = []
        term = (req.search or "").strip()
        if term:
            like = f"%{term}%"
            where_parts.append(
                "(c.nome LIKE %s OR c.cgc_cpf LIKE %s OR p.NOME_CLIENTE LIKE %s "
                "OR p.TELEFONE_CLIENTE LIKE %s OR CAST(p.pedido AS NVARCHAR(20)) LIKE %s)"
            )
            params.extend([like, like, like, like, like])
        if req.situacao:
            where_parts.append("p.situacao = %s")
            params.append(req.situacao)
        if req.data_ini:
            where_parts.append("p.data >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where_parts.append("p.data <= %s")
            params.append(req.data_fim)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # Total
        cur.execute(
            f"SELECT COUNT(*) c FROM pedido_venda p "
            f"LEFT JOIN cliente c ON c.codigo = p.cliente {where}",
            params,
        )
        total = int(cur.fetchone()["c"] or 0)

        offset = max(0, (req.page - 1) * req.size)
        cur.execute(
            f"SELECT p.pedido, p.data, p.validade, p.situacao, p.total, p.cliente, "
            f"       COALESCE(c.nome, p.NOME_CLIENTE) AS cliente_nome, "
            f"       p.vendedor, f.nome AS vendedor_nome, p.hora_aberto "
            f"FROM pedido_venda p "
            f"LEFT JOIN cliente c ON c.codigo = p.cliente "
            f"LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            f"{where} "
            f"ORDER BY p.pedido DESC OFFSET {offset} ROWS FETCH NEXT {req.size} ROWS ONLY",
            params,
        )
        items: list[dict] = []
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip()
            items.append({
                "pedido": int(r["pedido"] or 0),
                "data": r["data"].isoformat() if r.get("data") else None,
                "validade": r["validade"].isoformat() if r.get("validade") else None,
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(r.get("total") or 0),
                "cliente": int(r["cliente"] or 0) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "vendedor": int(r["vendedor"] or 0) if r.get("vendedor") else None,
                "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
                "hora_aberto": (r.get("hora_aberto") or "").strip(),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": total, "page": req.page, "size": req.size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


@api_router.post("/pedidos")
async def list_pedidos(req: PedidosListRequest):
    return await asyncio.to_thread(_list_pedidos_sync, req)


def _get_pedido_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.pedido, p.cliente, p.data, p.validade, p.vendedor, p.hora_aberto, "
            "       p.obs, p.situacao, p.total, p.NOME_CLIENTE, p.TELEFONE_CLIENTE, p.area_atuacao, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       f.nome AS vendedor_nome, a.descricao AS area_descricao "
            "FROM pedido_venda p "
            "LEFT JOIN cliente c ON c.codigo = p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            "LEFT JOIN area_atuacao a ON a.area = p.area_atuacao "
            "WHERE p.pedido = %s",
            (pedido,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (row.get("situacao") or "").strip()
        return {
            "success": True,
            "pedido": {
                "pedido": int(row["pedido"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or row.get("NOME_CLIENTE") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data"].isoformat() if row.get("data") else None,
                "validade": row["validade"].isoformat() if row.get("validade") else None,
                "vendedor": int(row["vendedor"] or 0) if row.get("vendedor") else None,
                "vendedor_nome": (row.get("vendedor_nome") or "").strip(),
                "hora_aberto": (row.get("hora_aberto") or "").strip(),
                "obs": row.get("obs") or "",
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(row.get("total") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


@api_router.get("/pedidos/{pedido}")
async def get_pedido(pedido: int, servidor: str, banco: str):
    return await asyncio.to_thread(_get_pedido_sync, servidor, banco, pedido)


class PedidoSaveRequest(BaseModel):
    servidor: str
    banco: str
    cliente: int                       # cliente.codigo
    vendedor: int                      # funcionarios.codigo_int
    validade: Optional[str] = None     # ISO date YYYY-MM-DD
    obs: Optional[str] = ""
    area_atuacao: Optional[int] = None # area_atuacao.area (FK)


def _save_pedido_sync(req: PedidoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        # Se for update, verifica situação — só pedido em 'A' (Aberto) pode ser editado.
        if pedido_codigo is not None:
            cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido_codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            if sit_atual != "A":
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"Pedido com situação '{label}' não pode ser alterado."}
        # Busca o nome e telefone do cliente para denormalizar em NOME_CLIENTE / TELEFONE_CLIENTE
        cur.execute(
            "SELECT TOP 1 c.nome, "
            "  COALESCE((SELECT TOP 1 LTRIM(RTRIM(CAST(ddd AS NVARCHAR(4))) + tel) "
            "            FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia), "
            "           LTRIM(RTRIM(CAST(c.ddd_cli AS NVARCHAR(4))) + ISNULL(c.telefone_cli,''))) AS tel "
            "FROM cliente c WHERE c.codigo = %s",
            (req.cliente,),
        )
        cli_row = cur.fetchone() or {}
        nome_cli = (cli_row.get("nome") or "").strip()[:60]
        tel_cli = (cli_row.get("tel") or "").strip()[:60]

        validade = req.validade or None
        obs = req.obs or ""

        if pedido_codigo is None:
            # pedido é IDENTITY — deixar o SQL gerar e retornar via OUTPUT INSERTED.pedido
            cur.execute(
                "INSERT INTO pedido_venda "
                "(cliente, data, validade, vendedor, hora_aberto, obs, situacao, "
                " NOME_CLIENTE, TELEFONE_CLIENTE, abertopor, total, tipo, area_atuacao) "
                "OUTPUT INSERTED.pedido "
                "VALUES (%s, CAST(GETDATE() AS DATE), %s, %s, "
                "        CONVERT(NVARCHAR(8), GETDATE(), 108), %s, 'A', %s, %s, %s, 0, 0, %s)",
                (req.cliente, validade, req.vendedor, obs, nome_cli, tel_cli, req.vendedor, req.area_atuacao),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter número do pedido."}
            pedido_id = int(row["pedido"] if isinstance(row, dict) else row[0])
        else:
            # Update apenas dos campos editáveis (não mexe em situacao aqui).
            cur.execute(
                "UPDATE pedido_venda SET "
                " cliente=%s, validade=%s, vendedor=%s, obs=%s, "
                " NOME_CLIENTE=%s, TELEFONE_CLIENTE=%s, area_atuacao=%s "
                "WHERE pedido=%s",
                (req.cliente, validade, req.vendedor, obs, nome_cli, tel_cli, req.area_atuacao, pedido_codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            pedido_id = pedido_codigo
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "pedido": pedido_id}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


@api_router.post("/pedidos/create")
async def create_pedido(req: PedidoSaveRequest):
    return await asyncio.to_thread(_save_pedido_sync, req, None)


@api_router.put("/pedidos/{pedido}")
async def update_pedido(pedido: int, req: PedidoSaveRequest):
    return await asyncio.to_thread(_save_pedido_sync, req, pedido)


# =====================================================================
# Itens do Pedido (pedido_venda_prod)
# Relacionamentos:
#   pedido_venda.pedido = pedido_venda_prod.pedido
#   pedido_venda_prod.produto = pecas.codigo_int  (produto)  -> tipo 'P'
#   pedido_venda_prod.produto = servicos.codigo    (serviço)  -> tipo 'S'
# Política: só pedido com situacao='A' (Aberto) permite CRUD de itens.
# Total do item = qtd_pedida * p_venda - desconto + acrescimo
# pedido_venda.total = SUM dos itens não cancelados.
# =====================================================================
def _item_total(qtd, pv) -> float:
    # p_venda já é o preço líquido unitário (= p_normal - desconto + acrescimo)
    return round(float(qtd or 0) * float(pv or 0), 2)


def _recalc_pedido_total(cur, pedido: int) -> float:
    cur.execute(
        "UPDATE pedido_venda SET total = ISNULL(("
        "  SELECT SUM(qtd_pedida * p_venda) "
        "  FROM pedido_venda_prod WHERE pedido=%s AND ISNULL(item_cancelado,0)=0"
        "), 0) WHERE pedido=%s",
        (pedido, pedido),
    )
    cur.execute("SELECT total FROM pedido_venda WHERE pedido=%s", (pedido,))
    r = cur.fetchone()
    return float((r.get("total") if isinstance(r, dict) else (r[0] if r else 0)) or 0)


def _check_pedido_aberto(cur, pedido: int) -> tuple[bool, str]:
    """Retorna (existe, situacao). Não levanta exceção."""
    cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
    row = cur.fetchone()
    if not row:
        return (False, "")
    return (True, (row.get("situacao") or "").strip().upper())


def _resolve_produto(cur, codigo: str) -> Optional[dict]:
    """Procura primeiro em pecas, depois em servicos. Retorna dados padrão do item."""
    cur.execute(
        "SELECT codigo_int AS codigo, descricao, codigo_fab, p_venda AS valor, uni, "
        "       custo_reposicao FROM pecas WHERE codigo_int=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        return {
            "tipo": "P",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo_fab") or "").strip(),
            "valor": float(r.get("valor") or 0),
            "unidade": (r.get("uni") or "").strip()[:2] or "UN",
            "custo": float(r.get("custo_reposicao") or 0),
        }
    cur.execute(
        "SELECT codigo, descricao, valor_hora AS valor FROM servicos WHERE codigo=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        return {
            "tipo": "S",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo") or "").strip(),
            "valor": float(r.get("valor") or 0),
            "unidade": "HR",
            "custo": 0.0,
        }
    return None


def _list_itens_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "subtotal": 0}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado.", "items": [], "subtotal": 0}
        cur.execute(
            "SELECT i.codauto, i.produto, i.qtd_pedida, i.p_venda, i.p_normal, i.desconto, i.acrescimo, "
            "       i.descricao_produto, i.unidade_pedido, "
            "       pe.descricao AS peca_desc, pe.codigo_fab AS peca_fab, "
            "       sv.descricao AS serv_desc "
            "FROM pedido_venda_prod i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "WHERE i.pedido = %s AND ISNULL(i.item_cancelado,0) = 0 "
            "ORDER BY i.codauto",
            (pedido,),
        )
        items = []
        subtotal = 0.0
        for r in cur.fetchall():
            is_peca = r.get("peca_desc") is not None
            tipo = "P" if is_peca else ("S" if r.get("serv_desc") is not None else "?")
            base_desc = (r.get("peca_desc") if is_peca else r.get("serv_desc")) or ""
            complemento = (r.get("descricao_produto") or "").strip()
            qtd = float(r.get("qtd_pedida") or 0)
            pv = float(r.get("p_venda") or 0)
            pnorm = float(r.get("p_normal") or 0)
            desc = float(r.get("desconto") or 0)
            acr = float(r.get("acrescimo") or 0)
            tot = _item_total(qtd, pv)
            subtotal += tot
            items.append({
                "codauto": int(r["codauto"]),
                "produto": (r.get("produto") or "").strip(),
                "tipo": tipo,
                "descricao": base_desc.strip(),
                "complemento": complemento,
                "cod_fab": (r.get("peca_fab") or r.get("produto") or "").strip(),
                "unidade": (r.get("unidade_pedido") or "").strip(),
                "qtd": qtd,
                "p_normal": pnorm,
                "valor_unitario": pv,
                "desconto": desc,
                "acrescimo": acr,
                "total": tot,
            })
        cur.close()
        conn.close()
        return {
            "success": True,
            "items": items,
            "subtotal": round(subtotal, 2),
            "situacao": sit,
            "editavel": sit == "A",
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "subtotal": 0}


@api_router.get("/pedidos/{pedido}/itens")
async def list_itens(pedido: int, servidor: str, banco: str):
    return await asyncio.to_thread(_list_itens_sync, servidor, banco, pedido)


class ItemSaveRequest(BaseModel):
    servidor: str
    banco: str
    produto: Optional[str] = None          # obrigatório no create
    qtd: float = 1
    valor_unitario: Optional[float] = None # se None, usa preço padrão do produto
    complemento: Optional[str] = ""
    desconto: Optional[float] = 0          # desconto UNITÁRIO em R$
    desconto_pct: Optional[float] = 0      # % informado (0 se foi em R$) — só para o log
    acrescimo: Optional[float] = 0         # acréscimo UNITÁRIO em R$
    usuario_codigo: Optional[int] = -2     # -2 = KONTACTO (master)
    funcao: Optional[int] = None           # 1=gerente,2=supervisor,3=vendedor (p/ validar limite)


def _validar_limite_desconto(cur, funcao: Optional[int], usuario_codigo: Optional[int],
                             p_normal: float, desc: float, desc_pct: float) -> Optional[str]:
    """Valida o desconto contra o limite da função (tabela controle). Retorna mensagem de erro
    se exceder, ou None se OK. Master (usuario_codigo == -2) sempre passa."""
    if (usuario_codigo if usuario_codigo is not None else -2) == -2:
        return None  # master ignora limite
    pct = float(desc_pct or 0)
    if pct <= 0 and p_normal > 0 and desc > 0:
        pct = desc / p_normal * 100
    if pct <= 0 or not funcao:
        return None
    cur.execute(
        "SELECT TOP 1 desconto_pdv_gerente, desconto_pdv_supervisor, desconto_pdv_vendedor FROM controle"
    )
    r = cur.fetchone() or {}
    col = {1: "desconto_pdv_gerente", 2: "desconto_pdv_supervisor", 3: "desconto_pdv_vendedor"}.get(int(funcao))
    if not col:
        return None
    lim = float(r.get(col) or 100)
    if pct > lim + 0.001:
        return f"Desconto {pct:.2f}% acima do limite permitido para a função ({lim:.0f}%)."
    return None


def _log_desconto_item(cur, pedido: int, codauto: int, perc: float, valor_unit: float, usuario: int):
    """Registra/atualiza o desconto de um item em descontos_concedidos.
    Política: só removo ou adiciono (delete + insert). TIPO='PED', TIPO_DESCONTO='I'."""
    cur.execute(
        "DELETE FROM descontos_concedidos "
        "WHERE TIPO='PED' AND CODIGO=%s AND CODIGO_PRODUTO=%s AND TIPO_DESCONTO='I'",
        (pedido, codauto),
    )
    if float(valor_unit or 0) > 0:
        cur.execute(
            "INSERT INTO descontos_concedidos "
            "(TIPO, CODIGO, CODIGO_PRODUTO, PERCENTUAL, VALOR, USUARIO, TIPO_DESCONTO) "
            "VALUES ('PED', %s, %s, %s, %s, %s, 'I')",
            (pedido, codauto, float(perc or 0), float(valor_unit or 0), int(usuario if usuario is not None else -2)),
        )


def _add_item_sync(req: ItemSaveRequest, pedido: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        codigo = (req.produto or "").strip()
        if not codigo:
            conn.close()
            return {"success": False, "message": "Produto/serviço obrigatório."}
        prod = _resolve_produto(cur, codigo)
        if not prod:
            conn.close()
            return {"success": False, "message": f"Produto/serviço '{codigo}' não encontrado."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        # valor_unitario = p_normal (preço base/tabela no momento). desconto/acrescimo são UNITÁRIOS.
        p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
        p_normal = float(p_normal or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)  # preço líquido unitário
        complemento = (req.complemento or "").strip()
        unidade = prod["unidade"]
        custo = float(prod.get("custo") or 0)  # pecas.custo_reposicao no momento da venda
        # Defesa em profundidade: valida limite de desconto por função (master ignora)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}

        cur.execute(
            "INSERT INTO pedido_venda_prod "
            "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
            " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item) "
            "OUTPUT INSERTED.codauto "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE))",
            (pedido, codigo, qtd, p_venda, p_normal, desc, acr, custo, complemento, unidade),
        )
        row = cur.fetchone()
        codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codauto": codauto, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _update_item_sync(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        # valor_unitario = p_normal (preço base). desconto/acrescimo são UNITÁRIOS.
        p_normal = float(req.valor_unitario or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        # Defesa em profundidade: valida limite de desconto por função (master ignora)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}
        p_venda = round(p_normal - desc + acr, 4)  # preço líquido unitário
        complemento = (req.complemento or "").strip()

        cur.execute(
            "UPDATE pedido_venda_prod SET "
            " qtd_pedida=%s, p_normal=%s, p_venda=%s, desconto=%s, acrescimo=%s, "
            " descricao_produto=%s, data_alteracao_item=CAST(GETDATE() AS DATE) "
            "WHERE codauto=%s AND pedido=%s",
            (qtd, p_normal, p_venda, desc, acr, complemento, codauto, pedido),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar item: {e}"}


def _delete_item_sync(servidor: str, banco: str, pedido: int, codauto: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}
        cur.execute("DELETE FROM pedido_venda_prod WHERE codauto=%s AND pedido=%s", (codauto, pedido))
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        cur.execute(
            "DELETE FROM descontos_concedidos "
            "WHERE TIPO='PED' AND CODIGO=%s AND CODIGO_PRODUTO=%s AND TIPO_DESCONTO='I'",
            (pedido, codauto),
        )
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover item: {e}"}


@api_router.post("/pedidos/{pedido}/itens")
async def add_item(pedido: int, req: ItemSaveRequest):
    return await asyncio.to_thread(_add_item_sync, req, pedido)


@api_router.put("/pedidos/{pedido}/itens/{codauto}")
async def update_item(pedido: int, codauto: int, req: ItemSaveRequest):
    return await asyncio.to_thread(_update_item_sync, req, pedido, codauto)


@api_router.delete("/pedidos/{pedido}/itens/{codauto}")
async def delete_item(pedido: int, codauto: int, servidor: str, banco: str):
    return await asyncio.to_thread(_delete_item_sync, servidor, banco, pedido, codauto)


def _list_descontos_sync(servidor: str, banco: str, pedido: int) -> dict:
    """Relatório de descontos concedidos do pedido (descontos_concedidos).
    Junta com pedido_venda_prod (via CODIGO_PRODUTO = codauto) para descrição/qtd."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.codauto, i.produto, i.qtd_pedida, i.p_normal, i.desconto, "
            "       pe.descricao AS peca_desc, sv.descricao AS serv_desc, "
            "       d.PERCENTUAL, d.USUARIO, d.TIPO_DESCONTO "
            "FROM pedido_venda_prod i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "LEFT JOIN descontos_concedidos d ON d.TIPO='PED' AND d.CODIGO=i.pedido AND d.CODIGO_PRODUTO=i.codauto "
            "WHERE i.pedido=%s AND ISNULL(i.item_cancelado,0)=0 AND ISNULL(i.desconto,0) > 0 "
            "ORDER BY i.codauto",
            (pedido,),
        )
        items = []
        total = 0.0
        for r in cur.fetchall():
            tipo_d = (r.get("TIPO_DESCONTO") or "I").strip().upper() or "I"
            qtd = float(r.get("qtd_pedida") or 0)
            valor_unit = float(r.get("desconto") or 0)
            p_normal = float(r.get("p_normal") or 0)
            valor_total = round(valor_unit * qtd, 2)
            total += valor_total
            # % do log, ou calcula a partir do valor/p_normal
            pct = float(r.get("PERCENTUAL") or 0)
            if pct <= 0 and p_normal > 0:
                pct = round(valor_unit / p_normal * 100, 2)
            desc = (r.get("peca_desc") or r.get("serv_desc") or r.get("produto") or "Item")
            items.append({
                "cod": int(r["codauto"]),
                "tipo_desconto": tipo_d,
                "tipo_label": "Geral" if tipo_d == "G" else "Item",
                "descricao": (desc or "").strip(),
                "percentual": pct,
                "valor_unitario": valor_unit,
                "qtd": qtd,
                "valor_total": valor_total,
                "usuario": int(r.get("USUARIO") or 0),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": round(total, 2)}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


@api_router.get("/pedidos/{pedido}/descontos")
async def list_descontos(pedido: int, servidor: str, banco: str):
    return await asyncio.to_thread(_list_descontos_sync, servidor, banco, pedido)


def _get_limites_sync(servidor: str, banco: str) -> dict:
    """Lê os limites de desconto por função na tabela controle (registro único)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 desconto_pdv_gerente, desconto_pdv_supervisor, desconto_pdv_vendedor "
            "FROM controle"
        )
        r = cur.fetchone()
        cur.close(); conn.close()
        if not r:
            # sem registro de configuração → sem restrição
            return {"success": True, "gerente": 100.0, "supervisor": 100.0, "vendedor": 100.0, "configurado": False}
        return {
            "success": True,
            "gerente": float(r.get("desconto_pdv_gerente") or 0),
            "supervisor": float(r.get("desconto_pdv_supervisor") or 0),
            "vendedor": float(r.get("desconto_pdv_vendedor") or 0),
            "configurado": True,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


@api_router.get("/controle/desconto-limites")
async def desconto_limites(servidor: str, banco: str):
    return await asyncio.to_thread(_get_limites_sync, servidor, banco)


def _get_empresa_sync(servidor: str, banco: str) -> dict:
    """Dados da empresa (tabela controle, registro único): fantasia/razão social."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 empresa, fantasia, rz_social FROM controle")
        r = cur.fetchone() or {}
        cur.close(); conn.close()
        return {
            "success": True,
            "empresa": (r.get("empresa") or "").strip() or None,
            "fantasia": (r.get("fantasia") or "").strip() or None,
            "rz_social": (r.get("rz_social") or "").strip() or None,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


@api_router.get("/controle/empresa")
async def controle_empresa(servidor: str, banco: str):
    return await asyncio.to_thread(_get_empresa_sync, servidor, banco)


_SIT_LABELS = {"A": "Aberto", "F": "Fechado", "PG": "Faturado", "C": "Cancelado"}


def _relatorio_pedidos_sync(servidor: str, banco: str, data_ini: str, data_fim: str,
                            vendedor: Optional[str], situacao: Optional[str]) -> dict:
    """Lista de pedidos por período + filtros (vendedor/situação) para o Relatório de Pedidos.
    Campos: pedido, cliente, data, vendedor (nome), situacao. A análise (descontos/margem)
    é carregada sob demanda pelos endpoints já existentes ao expandir cada registro."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "pedidos": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["CAST(pv.data AS DATE) BETWEEN %s AND %s"]
        params: list = [data_ini, data_fim]
        if vendedor not in (None, "", "all"):
            where.append("pv.vendedor = %s")
            params.append(vendedor)
        if situacao not in (None, "", "all"):
            where.append("pv.situacao = %s")
            params.append(situacao)
        cur.execute(
            "SELECT TOP 300 pv.pedido, pv.data, pv.situacao, ISNULL(pv.total,0) AS total, "
            "       c.nome AS cliente, pv.vendedor AS vendedor_cod, f.nome AS vendedor_nome "
            "FROM pedido_venda pv "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY pv.data DESC, pv.pedido DESC",
            tuple(params),
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        pedidos = []
        for r in rows:
            d = r.get("data")
            pedidos.append({
                "pedido": r.get("pedido"),
                "data": d.isoformat() if hasattr(d, "isoformat") else (str(d) if d else None),
                "situacao": (r.get("situacao") or "").strip(),
                "situacao_label": _SIT_LABELS.get((r.get("situacao") or "").strip(), r.get("situacao") or "—"),
                "total": float(r.get("total") or 0),
                "cliente": (r.get("cliente") or "").strip() or "—",
                "vendedor_cod": r.get("vendedor_cod"),
                "vendedor_nome": (r.get("vendedor_nome") or "").strip() or "—",
            })
        return {"success": True, "pedidos": pedidos}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "pedidos": []}


@api_router.get("/relatorios/pedidos")
async def relatorio_pedidos(servidor: str, banco: str, data_ini: str, data_fim: str,
                            vendedor: Optional[str] = None, situacao: Optional[str] = None):
    return await asyncio.to_thread(_relatorio_pedidos_sync, servidor, banco, data_ini, data_fim, vendedor, situacao)


def _limite_por_funcao(lim: dict, funcao: int) -> float:
    # funcao: 1=gerente, 2=supervisor, 3=vendedor (master = gerente)
    if funcao == 2:
        return float(lim.get("supervisor") or 0)
    if funcao == 3:
        return float(lim.get("vendedor") or 0)
    return float(lim.get("gerente") or 0)


class DescontoGeralRequest(BaseModel):
    servidor: str
    banco: str
    valor: float = 0               # valor TOTAL do desconto geral em R$ (0 = remover)
    usuario_codigo: Optional[int] = -2
    funcao: Optional[int] = 1       # 1=gerente, 2=supervisor, 3=vendedor


def _aplicar_desconto_geral_sync(req: DescontoGeralRequest, pedido: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        valor = float(req.valor or 0)
        if valor < 0:
            conn.close()
            return {"success": False, "message": "Valor inválido."}

        # busca todos os itens do pedido
        cur.execute(
            "SELECT codauto, p_normal, acrescimo, qtd_pedida FROM pedido_venda_prod "
            "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
            (pedido,),
        )
        itens = cur.fetchall()
        if not itens:
            conn.close()
            return {"success": False, "message": "Pedido sem itens para aplicar desconto."}

        # base = soma dos itens a preço cheio (p_normal * qtd)
        base = sum(float(it.get("p_normal") or 0) * float(it.get("qtd_pedida") or 0) for it in itens)
        if valor > 0 and base <= 0:
            conn.close()
            return {"success": False, "message": "Itens sem valor para distribuir o desconto."}

        # valida limite por função pelo % equivalente
        pct_efetivo = round(valor / base * 100, 4) if base > 0 else 0
        if valor > 0:
            lim = _get_limites_sync(req.servidor, req.banco)
            limite = _limite_por_funcao(lim, int(req.funcao or 1))
            if limite > 0 and pct_efetivo > limite + 1e-6:
                conn.close()
                return {"success": False, "message": f"Desconto ({pct_efetivo:g}%) acima do limite ({limite:g}%) para sua função."}
            if valor > base + 1e-6:
                conn.close()
                return {"success": False, "message": "Desconto maior que o total dos itens."}

        usuario = int(req.usuario_codigo if req.usuario_codigo is not None else -2)
        for it in itens:
            codauto = int(it["codauto"])
            p_normal = float(it.get("p_normal") or 0)
            acr = float(it.get("acrescimo") or 0)
            # distribui proporcionalmente ao peso do item (p_normal) → desconto UNITÁRIO
            desconto_unit = round(valor * p_normal / base, 2) if (valor > 0 and base > 0) else 0.0
            p_venda = round(p_normal - desconto_unit + acr, 4)
            cur.execute(
                "UPDATE pedido_venda_prod SET desconto=%s, p_venda=%s, "
                "data_alteracao_item=CAST(GETDATE() AS DATE) WHERE codauto=%s AND pedido=%s",
                (desconto_unit, p_venda, codauto, pedido),
            )
            # desconto geral SOBREPÕE os descontos de item: remove qualquer log do item (I e G)
            cur.execute(
                "DELETE FROM descontos_concedidos WHERE TIPO='PED' AND CODIGO=%s AND CODIGO_PRODUTO=%s",
                (pedido, codauto),
            )
            if valor > 0 and desconto_unit > 0:
                pct_item = round(desconto_unit / p_normal * 100, 2) if p_normal > 0 else 0
                cur.execute(
                    "INSERT INTO descontos_concedidos "
                    "(TIPO, CODIGO, CODIGO_PRODUTO, PERCENTUAL, VALOR, USUARIO, TIPO_DESCONTO) "
                    "VALUES ('PED', %s, %s, %s, %s, %s, 'G')",
                    (pedido, codauto, pct_item, desconto_unit, usuario),
                )
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total, "valor": valor, "percentual": pct_efetivo}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao aplicar desconto geral: {e}"}


@api_router.post("/pedidos/{pedido}/desconto-geral")
async def aplicar_desconto_geral(pedido: int, req: DescontoGeralRequest):
    return await asyncio.to_thread(_aplicar_desconto_geral_sync, req, pedido)


def _relatorio_desc_margem_sync(servidor: str, banco: str, data_ini: str, data_fim: str,
                                vendedor: Optional[str], pedido: Optional[int],
                                cliente_nome: Optional[str] = None) -> dict:
    """Relatório consolidado: por pedido (agrupado por vendedor) com venda, desconto,
    custo e margem. O CUSTO usa o custo de reposição do cadastro (pecas.custo_reposicao /
    servicos.custo_hora), com fallback para pedido_venda_prod.custo_ped. A venda é líquida
    (p_venda já é descontado), então desconto E custo influenciam a margem.
    Filtros: período + vendedor + pedido + nome do cliente (todos opcionais)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "vendedores": [], "totais": {}}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["CAST(pv.data AS DATE) BETWEEN %s AND %s"]
        params: list = [data_ini, data_fim]
        if vendedor:
            where.append("pv.vendedor = %s")
            params.append(vendedor)
        if pedido:
            where.append("pv.pedido = %s")
            params.append(pedido)
        if cliente_nome and cliente_nome.strip():
            where.append("c.nome LIKE %s")
            params.append(f"%{cliente_nome.strip()}%")
        cur.execute(
            "SELECT pv.pedido, pv.data, pv.vendedor, pv.situacao, "
            "       f.nome AS vendedor_nome, c.nome AS cliente_nome, "
            "       ISNULL(ag.venda,0) AS venda, ISNULL(ag.desconto,0) AS desconto, ISNULL(ag.custo,0) AS custo "
            "FROM pedido_venda pv "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "OUTER APPLY (SELECT "
            "    SUM(i.p_venda * i.qtd_pedida) AS venda, "
            "    SUM(ISNULL(i.desconto,0) * i.qtd_pedida) AS desconto, "
            "    SUM(COALESCE(NULLIF(pe.custo_reposicao,0), NULLIF(sv.custo_hora,0), NULLIF(i.custo_ped,0), 0) * i.qtd_pedida) AS custo "
            "  FROM pedido_venda_prod i "
            "  LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "  LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "  WHERE i.pedido = pv.pedido AND ISNULL(i.item_cancelado,0)=0) ag "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY pv.vendedor, pv.pedido",
            tuple(params),
        )
        grupos: dict = {}
        tot_venda = tot_desc = tot_custo = 0.0
        for r in cur.fetchall():
            vcod = str(r.get("vendedor") or "").strip()
            vnome = (r.get("vendedor_nome") or "").strip() or (f"Vendedor {vcod}" if vcod else "Sem vendedor")
            venda = float(r.get("venda") or 0)
            desc = float(r.get("desconto") or 0)
            custo = float(r.get("custo") or 0)
            margem = round(venda - custo, 2)
            margem_pct = round((margem / venda * 100), 2) if venda > 0 else 0.0
            data_val = r.get("data")
            data_str = data_val.strftime("%Y-%m-%d") if hasattr(data_val, "strftime") else (str(data_val)[:10] if data_val else "")
            ped_obj = {
                "pedido": int(r["pedido"]),
                "data": data_str,
                "situacao": (r.get("situacao") or "").strip(),
                "cliente": (r.get("cliente_nome") or "").strip(),
                "venda": round(venda, 2),
                "desconto": round(desc, 2),
                "custo": round(custo, 2),
                "margem": margem,
                "margem_pct": margem_pct,
            }
            g = grupos.setdefault(vcod, {
                "vendedor": vcod, "vendedor_nome": vnome, "pedidos": [],
                "sub_venda": 0.0, "sub_desconto": 0.0, "sub_custo": 0.0, "sub_margem": 0.0,
            })
            g["pedidos"].append(ped_obj)
            g["sub_venda"] += venda
            g["sub_desconto"] += desc
            g["sub_custo"] += custo
            g["sub_margem"] += margem
            tot_venda += venda; tot_desc += desc; tot_custo += custo
        cur.close(); conn.close()
        vendedores = []
        for g in grupos.values():
            g["sub_venda"] = round(g["sub_venda"], 2)
            g["sub_desconto"] = round(g["sub_desconto"], 2)
            g["sub_custo"] = round(g["sub_custo"], 2)
            g["sub_margem"] = round(g["sub_margem"], 2)
            g["sub_margem_pct"] = round((g["sub_margem"] / g["sub_venda"] * 100), 2) if g["sub_venda"] > 0 else 0.0
            vendedores.append(g)
        margem_geral = round(tot_venda - tot_custo, 2)
        totais = {
            "venda": round(tot_venda, 2),
            "desconto": round(tot_desc, 2),
            "custo": round(tot_custo, 2),
            "margem": margem_geral,
            "margem_pct": round((margem_geral / tot_venda * 100), 2) if tot_venda > 0 else 0.0,
            "qtd_pedidos": sum(len(g["pedidos"]) for g in vendedores),
        }
        return {"success": True, "vendedores": vendedores, "totais": totais}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "vendedores": [], "totais": {}}


@api_router.get("/relatorios/descontos-margem")
async def relatorio_descontos_margem(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[str] = None, pedido: Optional[int] = None,
    cliente_nome: Optional[str] = None,
):
    return await asyncio.to_thread(
        _relatorio_desc_margem_sync, servidor, banco, data_ini, data_fim, vendedor, pedido, cliente_nome
    )




# Busca de cliente para o pedido — por nome, cgc/cpf ou telefone.
def _find_clientes_for_pedido_sync(servidor: str, banco: str, term: str, limit: int = 15) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        like = f"%{(term or '').strip()}%"
        cur.execute(
            f"SELECT TOP {int(limit)} c.codigo, c.nome, c.cgc_cpf, "
            f"       COALESCE(ct.tel, c.telefone_cli) AS telefone "
            f"FROM cliente c "
            f"OUTER APPLY (SELECT TOP 1 tel FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia) ct "
            f"WHERE c.nome LIKE %s OR c.cgc_cpf LIKE %s OR c.telefone_cli LIKE %s OR ct.tel LIKE %s "
            f"ORDER BY c.nome",
            (like, like, like, like),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "cgc_cpf": (r.get("cgc_cpf") or "").strip(),
            "telefone": (r.get("telefone") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


@api_router.get("/clientes/find/search")
async def find_clientes_search(servidor: str, banco: str, term: str = ""):
    return await asyncio.to_thread(_find_clientes_for_pedido_sync, servidor, banco, term)


# Cliente — resumo com telefone + endereço (para exibir no form de pedido)
def _cliente_resumo_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.codigo, c.nome, c.cgc_cpf, c.e_mail, "
            "  COALESCE((SELECT TOP 1 LTRIM(RTRIM(CAST(ddd AS NVARCHAR(4))) + ' ' + tel) FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia), '') AS telefone, "
            "  (SELECT TOP 1 LTRIM(RTRIM(ISNULL(endereco,'')+', '+ISNULL(CAST(numero AS NVARCHAR(10)),'') + ' - ' + ISNULL(bairro,'') + ' - ' + ISNULL(cidade,'') + '/' + ISNULL(uf,''))) "
            "    FROM cliente_end WHERE codigo=c.codigo ORDER BY sequencia) AS endereco "
            "FROM cliente c WHERE c.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "Cliente não encontrado."}
        return {
            "success": True,
            "cliente": {
                "codigo": int(row["codigo"]),
                "nome": (row.get("nome") or "").strip(),
                "cgc_cpf": (row.get("cgc_cpf") or "").strip(),
                "e_mail": (row.get("e_mail") or "").strip(),
                "telefone": (row.get("telefone") or "").strip(),
                "endereco": (row.get("endereco") or "").strip(),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


@api_router.get("/clientes/{codigo}/resumo")
async def get_cliente_resumo(codigo: int, servidor: str, banco: str):
    return await asyncio.to_thread(_cliente_resumo_sync, servidor, banco, codigo)


# Área de atuação — dropdown
def _list_area_atuacao_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT area AS codigo, descricao FROM area_atuacao ORDER BY descricao")
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


@api_router.get("/area-atuacao")
async def list_area_atuacao(servidor: str, banco: str):
    return await asyncio.to_thread(_list_area_atuacao_sync, servidor, banco)


# Funcionários — dropdown de vendedores
def _list_funcionarios_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int AS codigo, nome, nome_guerra, cod_funcao "
            "FROM funcionarios WHERE ISNULL(situacao,'A') <> 'I' ORDER BY nome"
        )
        items = [{
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "nome_guerra": (r.get("nome_guerra") or "").strip(),
            "cod_funcao": (r.get("cod_funcao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


@api_router.get("/funcionarios")
async def list_funcionarios(servidor: str, banco: str):
    return await asyncio.to_thread(_list_funcionarios_sync, servidor, banco)


# DOWNLOAD TEMP — remover após sync
from fastapi.responses import PlainTextResponse as _PTR  # noqa: E402

_DEV_FILES_2 = {
    "server.py": "/app/backend/server.py",
    "clientes.tsx": "/app/frontend/app/clientes.tsx",
    "pedido-form.tsx": "/app/frontend/app/pedido-form.tsx",
    "pedidos.tsx": "/app/frontend/app/pedidos.tsx",
}


@api_router.get("/dev/file2")
async def dev_file2(name: str):
    path = _DEV_FILES_2.get(name)
    if not path:
        return _PTR(f"# nao encontrado: {name}", status_code=404)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _PTR(f.read())
    except Exception as e:
        return _PTR(f"# erro: {e}", status_code=500)


# =====================================================================
# CREATE / UPDATE cliente (cliente + cliente_end + cliente_tel)
# =====================================================================
class TelefoneInput(BaseModel):
    ddd: Optional[str] = ""
    tel: Optional[str] = ""
    descricao: Optional[str] = ""


class EnderecoInput(BaseModel):
    tipo: int = 0  # 0=Comercial, 1=Cobrança, 2=Entrega
    cep: Optional[str] = ""
    endereco: Optional[str] = ""
    numero: Optional[int] = None
    complemento: Optional[str] = ""
    bairro: Optional[str] = ""
    cidade: Optional[str] = ""
    uf: Optional[str] = ""


class ClienteSaveRequest(BaseModel):
    servidor: str
    banco: str
    cgc_cpf: Optional[str] = ""
    nome: str
    e_mail: Optional[str] = ""
    inscre: Optional[str] = ""
    tipo: Optional[str] = ""           # FK string para tipo_cliente.codigo
    aceita_email: bool = False
    vendedor: Optional[int] = None     # funcionarios.codigo_int do usuário logado
    usuario_cadastro: Optional[int] = None
    usuario_alteracao: Optional[int] = None


def _normalize_cgc(s: Optional[str]) -> str:
    return _only_alnum_upper(s or "")


def _save_cliente_sync(
    req: ClienteSaveRequest,
    endereco: Optional[EnderecoInput],
    telefones: List[TelefoneInput],
    codigo: Optional[int],
) -> dict:
    # Validações de domínio
    nome = (req.nome or "").strip()
    if not nome:
        return {"success": False, "message": "Nome é obrigatório."}
    if len(nome) > 60:
        return {"success": False, "message": "Nome excede 60 caracteres."}

    cgc = _normalize_cgc(req.cgc_cpf)
    ok, msg = _validate_cgc_cpf(cgc)
    if not ok:
        return {"success": False, "message": msg}

    if len(telefones) > 3:
        return {"success": False, "message": "Máximo de 3 telefones."}

    # cliente.cliente_forn é SMALLINT no banco (FK p/ tipo_cliente.codigo)
    tipo_int: Optional[int] = None
    if req.tipo and str(req.tipo).strip():
        try:
            tipo_int = int(str(req.tipo).strip())
        except ValueError:
            tipo_int = None

    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}

    try:
        cur = conn.cursor()

        # Descobre tamanhos reais das colunas (cache por (banco, tabela)).
        sz_cli = _get_col_sizes(conn, req.banco, "cliente")
        sz_end = _get_col_sizes(conn, req.banco, "cliente_end")
        sz_tel = _get_col_sizes(conn, req.banco, "cliente_tel")

        # Telefone primário — gravado nos campos inline (compat com legacy).
        # cliente.ddd_cli é SMALLINT, cliente.telefone_cli é nvarchar(8).
        primary = telefones[0] if telefones else None
        ddd_int: Optional[int] = None
        tel_inline: Optional[str] = None
        if primary:
            try:
                ddd_int = int((primary.ddd or "").strip()) if (primary.ddd or "").strip().isdigit() else None
            except ValueError:
                ddd_int = None
            tel_raw = (primary.tel or "").strip()
            if tel_raw:
                tel_inline = _trunc(tel_raw, sz_cli, "telefone_cli", 8)

        usuario_cad = req.usuario_cadastro if req.usuario_cadastro is not None else req.vendedor
        usuario_alt = req.usuario_alteracao if req.usuario_alteracao is not None else req.vendedor

        if codigo is None:
            # INSERT cliente
            cur.execute(
                "INSERT INTO cliente "
                "(cgc_cpf, nome, e_mail, inscr_est, cliente_forn, aceita_email, vendedor, "
                " usuario_cadastro, data, situacao, ddd_cli, telefone_cli) "
                "OUTPUT INSERTED.codigo "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CAST(GETDATE() AS DATE), 'A', %s, %s)",
                (
                    _trunc(cgc, sz_cli, "cgc_cpf", 14) or None,
                    _trunc(nome, sz_cli, "nome", 60),
                    _trunc((req.e_mail or "").strip(), sz_cli, "e_mail", 60) or None,
                    _trunc((req.inscre or "").strip(), sz_cli, "inscr_est", 18) or None,
                    tipo_int,
                    1 if req.aceita_email else 0,
                    req.vendedor,
                    usuario_cad,
                    ddd_int,
                    tel_inline,
                ),
            )
            new_id_row = cur.fetchone()
            if not new_id_row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter código do novo cliente."}
            cliente_codigo = int(new_id_row[0])
        else:
            # UPDATE cliente
            cur.execute(
                "UPDATE cliente SET "
                " cgc_cpf=%s, nome=%s, e_mail=%s, inscr_est=%s, cliente_forn=%s, "
                " aceita_email=%s, vendedor=%s, usuario_alteracao=%s, "
                " data_alteracao=CAST(GETDATE() AS DATE), "
                " ddd_cli=%s, telefone_cli=%s "
                "WHERE codigo=%s",
                (
                    _trunc(cgc, sz_cli, "cgc_cpf", 14) or None,
                    _trunc(nome, sz_cli, "nome", 60),
                    _trunc((req.e_mail or "").strip(), sz_cli, "e_mail", 60) or None,
                    _trunc((req.inscre or "").strip(), sz_cli, "inscr_est", 18) or None,
                    tipo_int,
                    1 if req.aceita_email else 0,
                    req.vendedor,
                    usuario_alt,
                    ddd_int,
                    tel_inline,
                    codigo,
                ),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Cliente não encontrado para atualização."}
            cliente_codigo = codigo

            # Limpa endereço e telefones existentes para regravar
            cur.execute("DELETE FROM cliente_end WHERE codigo=%s", (cliente_codigo,))
            cur.execute("DELETE FROM cliente_tel WHERE codigo=%s", (cliente_codigo,))

        # INSERT endereço (apenas 1)
        if endereco:
            cep = "".join(ch for ch in (endereco.cep or "") if ch.isdigit())[:8]
            uf = (endereco.uf or "").strip()[:2].upper()
            cur.execute(
                "INSERT INTO cliente_end "
                "(codigo, tipo, endereco, numero, complemento, bairro, cidade, uf, cep) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    cliente_codigo,
                    int(endereco.tipo or 0),
                    _trunc((endereco.endereco or "").strip(), sz_end, "endereco", 60) or None,
                    endereco.numero,
                    _trunc((endereco.complemento or "").strip(), sz_end, "complemento", 30) or None,
                    _trunc((endereco.bairro or "").strip(), sz_end, "bairro", 35) or None,
                    _trunc((endereco.cidade or "").strip(), sz_end, "cidade", 35) or None,
                    uf or None,
                    cep or None,
                ),
            )

        # INSERT telefones (até 3)
        for tel in telefones[:3]:
            ddd_n = _trunc((tel.ddd or "").strip(), sz_tel, "ddd", 4)
            tel_n = _trunc((tel.tel or "").strip(), sz_tel, "tel", 10)
            if not tel_n:
                continue
            cur.execute(
                "INSERT INTO cliente_tel (codigo, ddd, tel, descricao) "
                "VALUES (%s, %s, %s, %s)",
                (
                    cliente_codigo,
                    ddd_n or "21",
                    tel_n,
                    _trunc((tel.descricao or "").strip(), sz_tel, "descricao", 15) or None,
                ),
            )

        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": cliente_codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


class ClienteCreateRequest(ClienteSaveRequest):
    endereco: Optional[EnderecoInput] = None
    telefones: List[TelefoneInput] = Field(default_factory=list)


@api_router.post("/clientes/create")
async def create_cliente(req: ClienteCreateRequest):
    base = ClienteSaveRequest(**req.dict(exclude={"endereco", "telefones"}))
    return await asyncio.to_thread(
        _save_cliente_sync, base, req.endereco, req.telefones, None
    )


@api_router.put("/clientes/{codigo}")
async def update_cliente(codigo: int, req: ClienteCreateRequest):
    base = ClienteSaveRequest(**req.dict(exclude={"endereco", "telefones"}))
    return await asyncio.to_thread(
        _save_cliente_sync, base, req.endereco, req.telefones, codigo
    )


# =====================================================================
# Dashboard — totais do dia + lista de pedidos do vendedor
# =====================================================================
def _dashboard_sync(servidor: str, banco: str, vendedor: Optional[str], data_iso: str,
                    situacao: Optional[str] = None) -> dict:
    """Totais e pedidos do dia (pedido_venda/pedido_venda_prod).
    vendedor None/'' = todos; situacao None/'' = todas; produtos/servicos = soma p_venda*qtd
    por tipo (pecas/servicos). Inclui margem média do dia (venda líquida - custo)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}",
                "totais": {"pedidos": 0, "produtos": 0, "servicos": 0, "margem": 0, "margem_pct": 0}, "pedidos": []}
    try:
        cur = conn.cursor(as_dict=True)
        vfilter = ""
        vparams: list = []
        if vendedor not in (None, "", "all"):
            vfilter += " AND pv.vendedor = %s"
            vparams.append(vendedor)
        if situacao not in (None, "", "all"):
            vfilter += " AND pv.situacao = %s"
            vparams.append(situacao)

        # Quantidade de pedidos do dia
        cur.execute(
            f"SELECT COUNT(*) AS qtd FROM pedido_venda pv "
            f"WHERE CAST(pv.data AS DATE) = %s{vfilter}",
            tuple([data_iso] + vparams),
        )
        qtd = int((cur.fetchone() or {}).get("qtd") or 0)

        # Totais de produtos x serviços + venda/custo do dia (p/ margem)
        cur.execute(
            "SELECT "
            "  SUM(CASE WHEN pe.codigo_int IS NOT NULL THEN i.p_venda*i.qtd_pedida ELSE 0 END) AS prod, "
            "  SUM(CASE WHEN sv.codigo IS NOT NULL THEN i.p_venda*i.qtd_pedida ELSE 0 END) AS serv, "
            "  SUM(i.p_venda*i.qtd_pedida) AS venda_total, "
            "  SUM(COALESCE(NULLIF(pe.custo_reposicao,0), NULLIF(sv.custo_hora,0), NULLIF(i.custo_ped,0), 0) * i.qtd_pedida) AS custo_total "
            "FROM pedido_venda pv "
            "JOIN pedido_venda_prod i ON i.pedido = pv.pedido AND ISNULL(i.item_cancelado,0)=0 "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            f"WHERE CAST(pv.data AS DATE) = %s{vfilter}",
            tuple([data_iso] + vparams),
        )
        tr = cur.fetchone() or {}
        venda_total = float(tr.get("venda_total") or 0)
        custo_total = float(tr.get("custo_total") or 0)
        margem = round(venda_total - custo_total, 2)
        totais = {
            "pedidos": qtd,
            "produtos": float(tr.get("prod") or 0),
            "servicos": float(tr.get("serv") or 0),
            "margem": margem,
            "margem_pct": round((margem / venda_total * 100), 2) if venda_total > 0 else 0.0,
        }

        # Lista de pedidos do dia
        cur.execute(
            "SELECT TOP 50 pv.pedido, c.nome AS cliente, ISNULL(pv.total,0) AS valor, "
            "       f.nome AS vendedor_nome "
            "FROM pedido_venda pv "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            f"WHERE CAST(pv.data AS DATE) = %s{vfilter} "
            "ORDER BY pv.pedido DESC",
            tuple([data_iso] + vparams),
        )
        pedidos = []
        for r in cur.fetchall():
            pedidos.append({
                "pedido": int(r.get("pedido") or 0),
                "cliente": (r.get("cliente") or "").strip(),
                "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
                "valor": float(r.get("valor") or 0),
            })
        cur.close()
        conn.close()
        return {"success": True, "totais": totais, "pedidos": pedidos}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro consulta dashboard: {e}",
                "totais": {"pedidos": 0, "produtos": 0, "servicos": 0}, "pedidos": []}


@api_router.get("/dashboard/me")
async def dashboard_me(servidor: str, banco: str, vendedor: Optional[str] = None,
                       data: Optional[str] = None, situacao: Optional[str] = None):
    # data padrão = hoje (YYYY-MM-DD); vendedor/situacao vazio/None/all = todos
    from datetime import date  # noqa: E402
    data_iso = data or date.today().isoformat()
    return await asyncio.to_thread(_dashboard_sync, servidor, banco, vendedor, data_iso, situacao)


# =====================================================================
# DOWNLOAD TEMPORÁRIO — remover após sincronizar com GitHub
# =====================================================================
from fastapi.responses import PlainTextResponse  # noqa: E402

_DEV_FILES = {
    "server.py": "/app/backend/server.py",
    "requirements-windows.txt": "/app/backend/requirements-windows.txt",
    "clientes.tsx": "/app/frontend/app/clientes.tsx",
    "cliente-form.tsx": "/app/frontend/app/cliente-form.tsx",
    "principal.tsx": "/app/frontend/app/principal.tsx",
    "produtos.tsx": "/app/frontend/app/produtos.tsx",
    "pedidos.tsx": "/app/frontend/app/pedidos.tsx",
    "pedido-form.tsx": "/app/frontend/app/pedido-form.tsx",
}


@api_router.get("/dev/file")
async def dev_file(name: str):
    path = _DEV_FILES.get(name)
    if not path:
        return PlainTextResponse(
            f"# arquivo não disponível: {name}\n# válidos: {list(_DEV_FILES.keys())}",
            status_code=404,
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    except Exception as e:
        return PlainTextResponse(f"# erro: {e}", status_code=500)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
