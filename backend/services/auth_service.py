"""Autenticação (login) contra SQL Server + usuário master."""
import asyncio
from typing import Optional

import pymssql

from db.connection import (
    _pick_sql_credentials, SQL_TDS_VERSION, _to_json_safe, _err_origin,
)
from models.schemas import LoginRequest, LoginResponse

GENERIC_AUTH_ERROR = "Usuário ou senha inválidos."

# Usuário master do sistema BackOn — acesso total, sem depender da tabela usuarios.
MASTER_USER_NAME = "KONTACTO"
MASTER_USER_PASSWORD = "$KONT2011"

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


def criptografa_frase(senha: str) -> str:
    """Equivalente Python à função C# Criptografa_Frase do sistema BackOn.
    Aplica cifra de César +3 (cada caractere + 3 no código Unicode).
    Mesma lógica usada para gravar a senha em usuarios.senha."""
    if not senha:
        return ""
    senha = senha.strip()
    return "".join(chr(ord(c) + 3) for c in senha)


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
            # Credencial inválida: NÃO expor dados de conexão/diagnóstico
            return LoginResponse(
                success=False,
                message=GENERIC_AUTH_ERROR,
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


async def login(payload: LoginRequest) -> LoginResponse:
    return await asyncio.to_thread(_sql_login_sync, payload)
