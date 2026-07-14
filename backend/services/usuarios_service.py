"""Manutencao de usuarios (tabela usuarios) no estilo do legado VB6.

Regras principais:
- Inclusao exige funcionario previo em `funcionarios.nome_guerra`.
- Senha grava no mesmo formato do login legado (cifra Cesar +3).
- Exclusao bloqueia usuario KONTACTO (e MASTER por seguranca).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.auth_service import criptografa_frase

# Mesmos 2 nomes tratados como master em `_excluir_usuario_sync` (KONTACTO é o
# login master real — `auth_service.MASTER_USER_NAME`; MASTER é mantido por
# retrocompatibilidade/segurança extra, mesmo padrão já existente aqui).
_NOMES_MASTER = ("KONTACTO", "MASTER")

# Funções (funcionarios.cod_funcao) que dispensam a senha atual ao trocar a
# senha de OUTRO usuário — Gerente (01) e Supervisor (02), mesmo critério de
# `isManagerFuncao` no frontend (`src/permissions/index.tsx`).
_FUNCOES_GERENCIAIS = ("01", "02")


def _norm_user(usuario: str) -> str:
    return (usuario or "").strip().upper()


def _get_funcionario(cur, usuario: str) -> Optional[dict]:
    cur.execute(
        "SELECT TOP 1 codigo_int AS codigo, nome, nome_guerra "
        "FROM funcionarios WHERE nome_guerra=%s",
        (usuario,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "codigo": int(row.get("codigo") or 0),
        "nome": (row.get("nome") or "").strip(),
        "nome_guerra": (row.get("nome_guerra") or "").strip(),
    }


def _get_usuario(cur, usuario: str) -> Optional[dict]:
    cur.execute(
        "SELECT TOP 1 u.usuario, u.classe, u.administrador, "
        "c.classe AS classe_descricao "
        "FROM usuarios u "
        "LEFT JOIN classes_usuarios c ON c.codigo=u.classe "
        "WHERE u.usuario=%s",
        (usuario,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "usuario": (row.get("usuario") or "").strip(),
        "classe": int(row.get("classe") or 0),
        "classe_descricao": (row.get("classe_descricao") or "").strip(),
        "administrador": bool(row.get("administrador")),
    }


def _eh_gerente_ou_master(cur, usuario_logado: str) -> bool:
    """Confere no servidor (nunca confiando em flag vinda do cliente) se quem
    está executando a ação é master ou Gerente/Supervisor (funcionarios.cod_funcao
    01/02) — usado pra dispensar a senha atual ao trocar a senha de OUTRO
    usuário. Master (`KONTACTO`/`MASTER`) não depende de linha em `funcionarios`."""
    logado = _norm_user(usuario_logado)
    if not logado:
        return False
    if logado in _NOMES_MASTER:
        return True
    cur.execute(
        "SELECT TOP 1 fc.codigo AS cod_funcao FROM funcionarios f "
        "JOIN Funcoes fc ON fc.codigo = f.cod_funcao "
        "WHERE f.nome_guerra=%s",
        (logado,),
    )
    row = cur.fetchone()
    if not row:
        return False
    return (row.get("cod_funcao") or "").strip() in _FUNCOES_GERENCIAIS


def _classe_existe(cur, classe: int) -> bool:
    cur.execute("SELECT TOP 1 1 AS ok FROM classes_usuarios WHERE codigo=%s", (classe,))
    return cur.fetchone() is not None


def _list_usuarios_sync(servidor: str, banco: str) -> dict:
    """Lista todos os usuarios (usuario + nome do funcionario + grupo), para o
    seletor de busca da tela Perfil de Usuario. So deve ser chamado pelo
    frontend quando o usuario logado e Gerente/Supervisor/master ou tem a
    permissao PERFIL_USUARIO.GRAVAR — a checagem de quem pode ver essa lista
    e feita no frontend (mesmo modelo de permissao do resto do app: as rotas
    nao carregam identidade do chamador, so servidor/banco)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexao: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT u.usuario, u.classe, c.classe AS classe_descricao, "
            "f.nome AS nome_funcionario "
            "FROM usuarios u "
            "LEFT JOIN classes_usuarios c ON c.codigo = u.classe "
            "LEFT JOIN funcionarios f ON f.nome_guerra = u.usuario "
            "ORDER BY u.usuario"
        )
        items = [{
            "usuario": (r.get("usuario") or "").strip(),
            "nome_funcionario": (r.get("nome_funcionario") or "").strip(),
            "classe": int(r["classe"]) if r.get("classe") is not None else None,
            "classe_descricao": (r.get("classe_descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro ao listar usuarios: {e}", "items": []}
    finally:
        conn.close()


def _get_usuario_perfil_sync(servidor: str, banco: str, usuario: str) -> dict:
    usu = _norm_user(usuario)
    if not usu:
        return {"success": False, "message": "Usuario e obrigatorio."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexao: {e}"}

    try:
        cur = conn.cursor(as_dict=True)
        funcionario = _get_funcionario(cur, usu)
        usuario_obj = _get_usuario(cur, usu)
        cur.close()
        return {
            "success": True,
            "exists": usuario_obj is not None,
            "usuario": usuario_obj,
            "funcionario": funcionario,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro ao consultar usuario: {e}"}
    finally:
        conn.close()


def _incluir_usuario_sync(
    servidor: str,
    banco: str,
    usuario: str,
    classe: int,
    senha: str,
    confirmacao_senha: str,
    administrador: bool,
) -> dict:
    usu = _norm_user(usuario)
    if not usu:
        return {"success": False, "message": "Usuario e obrigatorio."}
    if classe is None:
        return {"success": False, "message": "Grupo e obrigatorio."}
    if not (senha or "").strip() or not (confirmacao_senha or "").strip():
        return {"success": False, "message": "Senha e confirmacao sao obrigatorias."}
    if (senha or "") != (confirmacao_senha or ""):
        return {"success": False, "message": "Confirmacao de senha invalida."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexao: {e}"}

    try:
        cur = conn.cursor(as_dict=True)

        if _get_usuario(cur, usu) is not None:
            cur.close()
            return {"success": False, "message": "Usuario ja cadastrado."}

        # Regra de negocio solicitada: nao cria usuario sem funcionario previo.
        if _get_funcionario(cur, usu) is None:
            cur.close()
            return {
                "success": False,
                "message": "Funcionario nao cadastrado para este usuario.",
            }

        if not _classe_existe(cur, int(classe)):
            cur.close()
            return {"success": False, "message": "Grupo de usuario invalido."}

        cur.execute(
            "INSERT INTO usuarios (usuario, senha, classe, administrador) VALUES (%s,%s,%s,%s)",
            (usu, criptografa_frase(senha), int(classe), 1 if administrador else 0),
        )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Usuario incluido."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao incluir usuario: {e}"}
    finally:
        conn.close()


def _alterar_usuario_sync(
    servidor: str,
    banco: str,
    usuario: str,
    classe: int,
    senha_atual: Optional[str],
    nova_senha: Optional[str],
    confirmacao_senha: Optional[str],
    administrador: bool,
    usuario_logado: Optional[str] = None,
) -> dict:
    usu = _norm_user(usuario)
    if not usu:
        return {"success": False, "message": "Usuario e obrigatorio."}
    if classe is None:
        return {"success": False, "message": "Grupo e obrigatorio."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexao: {e}"}

    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 senha FROM usuarios WHERE usuario=%s", (usu,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Usuario nao cadastrado."}

        if not _classe_existe(cur, int(classe)):
            cur.close()
            return {"success": False, "message": "Grupo de usuario invalido."}

        sets = ["classe=%s", "administrador=%s"]
        params: list = [int(classe), 1 if administrador else 0]

        # Regra de negócio (pedido do usuário, 2026-07-07): a senha atual só é
        # exigida no autoatendimento (usuário trocando a própria senha). Um
        # Gerente/Supervisor (funcionarios.cod_funcao 01/02) ou o master
        # trocando a senha de OUTRO usuário não precisa informar a senha
        # atual — checado no servidor (nunca confiando numa flag vinda do
        # cliente), via `_eh_gerente_ou_master`.
        dispensa_senha_atual = (
            _norm_user(usuario_logado) != usu
            and _eh_gerente_ou_master(cur, usuario_logado)
        )

        nova = (nova_senha or "").strip()
        if nova:
            conf = (confirmacao_senha or "").strip()
            if not conf or conf != nova:
                cur.close()
                return {"success": False, "message": "Confirmacao de senha invalida."}

            if not dispensa_senha_atual:
                antiga = (senha_atual or "").strip()
                if not antiga:
                    cur.close()
                    return {"success": False, "message": "Informe a senha atual."}
                senha_db = (row.get("senha") or "").strip()
                if senha_db != criptografa_frase(antiga):
                    cur.close()
                    return {"success": False, "message": "Senha atual invalida."}

            sets.append("senha=%s")
            params.append(criptografa_frase(nova))
        elif not dispensa_senha_atual and ((senha_atual or "").strip() or (confirmacao_senha or "").strip()):
            cur.close()
            return {
                "success": False,
                "message": "Para alterar senha, informe senha atual, nova senha e confirmacao.",
            }

        params.append(usu)
        cur.execute(f"UPDATE usuarios SET {', '.join(sets)} WHERE usuario=%s", tuple(params))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Usuario alterado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao alterar usuario: {e}"}
    finally:
        conn.close()


def _excluir_usuario_sync(servidor: str, banco: str, usuario: str) -> dict:
    usu = _norm_user(usuario)
    if not usu:
        return {"success": False, "message": "Usuario e obrigatorio."}
    if usu in ("KONTACTO", "MASTER"):
        return {"success": False, "message": "Acesso negado para excluir este usuario."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexao: {e}"}

    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM usuarios WHERE usuario=%s", (usu,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Usuario nao cadastrado."}

        # Regra de negócio (pedido do usuário, 2026-07-07): se o login ainda
        # tem funcionário cadastrado (`funcionarios.nome_guerra=usuario`), não
        # permite excluir — o desligamento/exclusão do funcionário tem que
        # acontecer primeiro (fora deste app), senão o login de alguém ainda
        # registrado como funcionário ficaria removido sem querer.
        if _get_funcionario(cur, usu) is not None:
            cur.close()
            return {
                "success": False,
                "message": "Usuario vinculado a um funcionario cadastrado — nao pode ser excluido.",
            }

        cur.execute("DELETE FROM usuarios WHERE usuario=%s", (usu,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Usuario excluido."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir usuario: {e}"}
    finally:
        conn.close()


async def list_usuarios(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_usuarios_sync, servidor, banco)


async def get_usuario_perfil(servidor: str, banco: str, usuario: str) -> dict:
    return await asyncio.to_thread(_get_usuario_perfil_sync, servidor, banco, usuario)


async def incluir_usuario(
    servidor: str,
    banco: str,
    usuario: str,
    classe: int,
    senha: str,
    confirmacao_senha: str,
    administrador: bool,
) -> dict:
    return await asyncio.to_thread(
        _incluir_usuario_sync,
        servidor,
        banco,
        usuario,
        classe,
        senha,
        confirmacao_senha,
        administrador,
    )


async def alterar_usuario(
    servidor: str,
    banco: str,
    usuario: str,
    classe: int,
    senha_atual: Optional[str],
    nova_senha: Optional[str],
    confirmacao_senha: Optional[str],
    administrador: bool,
    usuario_logado: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(
        _alterar_usuario_sync,
        servidor,
        banco,
        usuario,
        classe,
        senha_atual,
        nova_senha,
        confirmacao_senha,
        administrador,
        usuario_logado,
    )


async def excluir_usuario(servidor: str, banco: str, usuario: str) -> dict:
    return await asyncio.to_thread(_excluir_usuario_sync, servidor, banco, usuario)
