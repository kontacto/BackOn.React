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
# CREDENCIAIS SQL SERVER — ESTÁTICAS NO CÓDIGO
# =====================================================================
# Por design do sistema BackOn, a conta administrativa do SQL Server é
# fixa e única para todos os clientes. O app envia apenas o servidor
# (instância) e o nome do banco no momento do login; o backend completa
# o objeto de conexão com estas credenciais antes de abrir a conexão.
# =====================================================================
SQL_ADMIN_USER = "sa"
SQL_ADMIN_PASSWORD = "Cmslrav@155"

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
            "classe": 9,
            "classe_label": "Administrador",
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
    # Descrição do grupo vem do JOIN classes_usuarios (campo classe_descricao)
    if out.get("classe_descricao"):
        out["classe_label"] = str(out["classe_descricao"]).strip()
    elif "classe" in out and out["classe"] is not None:
        out["classe_label"] = f"Classe {out['classe']}"
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

    attempted = {
        "empresa": payload.empresa,
        "server": servidor,
        "database": payload.banco,
        "sql_user": SQL_ADMIN_USER,
        "login_user": payload.usuario,
        "login_timeout": payload.timeout or 8,
    }

    # ------- Etapa 1: abrir conexão -------
    try:
        conn = pymssql.connect(
            server=servidor,                        # ← do app, sem alteração
            user=SQL_ADMIN_USER,                    # ← FIXO no código
            password=SQL_ADMIN_PASSWORD,            # ← FIXO no código
            database=payload.banco,                 # ← do app
            login_timeout=payload.timeout or 8,
            timeout=payload.timeout or 8,
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

        usuario_obj = _to_json_safe(usuario_row)
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
    """Abre conexão SQL Server com as credenciais administrativas fixas."""
    return pymssql.connect(
        server=(servidor or "").strip(),
        user=SQL_ADMIN_USER,
        password=SQL_ADMIN_PASSWORD,
        database=banco,
        login_timeout=timeout, timeout=timeout,
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
            f"SELECT c.codigo, c.nome, c.cgc_cpf, c.ddd_cli, c.telefone_cli, c.e_mail, c.situacao, "
            f"       t.descricao AS tipo_descricao "
            f"FROM cliente c LEFT JOIN tipo_cliente t ON t.codigo = TRY_CAST(c.tipo AS INT) "
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
            "SELECT c.codigo, c.cgc_cpf, c.nome, c.e_mail, c.inscre, c.tipo, "
            "       c.aceita_email, c.vendedor, c.situacao, "
            "       c.ddd_cli, c.telefone_cli, "
            "       t.descricao AS tipo_descricao "
            "FROM cliente c "
            "LEFT JOIN tipo_cliente t ON t.codigo = TRY_CAST(c.tipo AS INT) "
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

    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}

    try:
        cur = conn.cursor()

        # Telefone primário (replicado nos campos inline ddd_cli/telefone_cli)
        primary = telefones[0] if telefones else None
        ddd_cli = ((primary.ddd or "").strip()[:4]) if primary else ""
        tel_cli = ((primary.tel or "").strip()[:10]) if primary else ""

        usuario_cad = req.usuario_cadastro if req.usuario_cadastro is not None else req.vendedor
        usuario_alt = req.usuario_alteracao if req.usuario_alteracao is not None else req.vendedor

        if codigo is None:
            # INSERT cliente
            cur.execute(
                "INSERT INTO cliente "
                "(cgc_cpf, nome, e_mail, inscre, tipo, aceita_email, vendedor, "
                " usuario_cadastro, data, situacao, ddd_cli, telefone_cli) "
                "OUTPUT INSERTED.codigo "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CAST(GETDATE() AS DATE), 'A', %s, %s)",
                (
                    cgc or None,
                    nome,
                    (req.e_mail or "").strip() or None,
                    (req.inscre or "").strip() or None,
                    (req.tipo or "").strip() or None,
                    1 if req.aceita_email else 0,
                    req.vendedor,
                    usuario_cad,
                    ddd_cli or None,
                    tel_cli or None,
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
                " cgc_cpf=%s, nome=%s, e_mail=%s, inscre=%s, tipo=%s, "
                " aceita_email=%s, vendedor=%s, usuario_alteracao=%s, "
                " data_alteracao=CAST(GETDATE() AS DATE), "
                " ddd_cli=%s, telefone_cli=%s "
                "WHERE codigo=%s",
                (
                    cgc or None,
                    nome,
                    (req.e_mail or "").strip() or None,
                    (req.inscre or "").strip() or None,
                    (req.tipo or "").strip() or None,
                    1 if req.aceita_email else 0,
                    req.vendedor,
                    usuario_alt,
                    ddd_cli or None,
                    tel_cli or None,
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
                    (endereco.endereco or "").strip()[:64] or None,
                    endereco.numero,
                    (endereco.complemento or "").strip() or None,
                    (endereco.bairro or "").strip()[:35] or None,
                    (endereco.cidade or "").strip()[:35] or None,
                    uf or None,
                    cep or None,
                ),
            )

        # INSERT telefones (até 3)
        for tel in telefones[:3]:
            ddd_n = (tel.ddd or "").strip()[:4]
            tel_n = (tel.tel or "").strip()[:10]
            if not tel_n:
                continue
            cur.execute(
                "INSERT INTO cliente_tel (codigo, ddd, tel, descricao) "
                "VALUES (%s, %s, %s, %s)",
                (
                    cliente_codigo,
                    ddd_n or "21",
                    tel_n,
                    (tel.descricao or "").strip() or None,
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
def _dashboard_sync(servidor: str, banco: str, vendedor: int, data_iso: str) -> dict:
    """Retorna totais e pedidos do dia para o vendedor. Schema esperado da tabela `pedidos`:
        - codigo (int PK)
        - data (date)
        - vendedor (int)
        - cliente (int FK -> cliente.codigo)
        - valor_produtos, valor_servicos (decimal)
    Caso o schema seja diferente, devolve estrutura zerada com 'message' explicando.
    """
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {
            "success": False,
            "message": f"Falha conexão: {e}",
            "totais": {"pedidos": 0, "produtos": 0, "servicos": 0},
            "pedidos": [],
        }
    try:
        cur = conn.cursor(as_dict=True)
        # Totais do dia
        cur.execute(
            "SELECT "
            "  COUNT(*) AS qtd_pedidos, "
            "  COALESCE(SUM(valor_produtos), 0) AS total_produtos, "
            "  COALESCE(SUM(valor_servicos), 0) AS total_servicos "
            "FROM pedidos "
            "WHERE vendedor = %s AND CAST(data AS DATE) = %s",
            (vendedor, data_iso),
        )
        tot_row = cur.fetchone() or {}
        totais = {
            "pedidos": int(tot_row.get("qtd_pedidos") or 0),
            "produtos": float(tot_row.get("total_produtos") or 0),
            "servicos": float(tot_row.get("total_servicos") or 0),
        }

        # Lista de pedidos do dia
        cur.execute(
            "SELECT TOP 50 "
            "  p.codigo AS pedido, "
            "  c.nome AS cliente, "
            "  (COALESCE(p.valor_produtos, 0) + COALESCE(p.valor_servicos, 0)) AS valor "
            "FROM pedidos p "
            "LEFT JOIN cliente c ON c.codigo = p.cliente "
            "WHERE p.vendedor = %s AND CAST(p.data AS DATE) = %s "
            "ORDER BY p.codigo DESC",
            (vendedor, data_iso),
        )
        pedidos = []
        for r in cur.fetchall():
            pedidos.append({
                "pedido": int(r.get("pedido") or 0),
                "cliente": (r.get("cliente") or "").strip() if r.get("cliente") else "",
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
        return {
            "success": False,
            "message": f"Erro consulta dashboard: {e}",
            "totais": {"pedidos": 0, "produtos": 0, "servicos": 0},
            "pedidos": [],
        }


@api_router.get("/dashboard/me")
async def dashboard_me(servidor: str, banco: str, vendedor: int, data: Optional[str] = None):
    # data padrão = hoje (YYYY-MM-DD)
    from datetime import date  # noqa: E402
    data_iso = data or date.today().isoformat()
    return await asyncio.to_thread(_dashboard_sync, servidor, banco, vendedor, data_iso)


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
