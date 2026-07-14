"""Tabelas auxiliares: Marcas e Modelos (veículo/produto) + import FIPE.

- marcas(codigo nvarchar, descricao, marca_produto bit/int)
  marca_produto = 0 -> listada na O.S. (veículo) ; 1 -> listada em Produtos.
- modelos(cod_marca, codigo nvarchar, descricao, ...)

Regras:
- Não excluir marca que possua modelos vinculados.
- Não criar modelo sem marca.
- `codigo` gerado sequencialmente (MAX numérico + 1, 3 dígitos).
Sem dependência de `requests`: usa urllib para a API FIPE.
"""
import asyncio
import json
import urllib.request
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc, _to_json_safe

FIPE_BASE = "https://parallelum.com.br/fipe/api/v1"


def _next_codigo(cur, tabela: str) -> str:
    cur.execute(
        f"SELECT MAX(CAST(codigo AS INT)) AS mx FROM {tabela} "
        f"WHERE ISNUMERIC(codigo) = 1"
    )
    r = cur.fetchone()
    nxt = int((r.get("mx") if r else None) or 0) + 1
    return f"{nxt:03d}"


# ---------------- MARCAS ----------------
def _list_marcas_sync(servidor: str, banco: str, marca_produto: Optional[bool], search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if marca_produto is not None:
            where.append("ISNULL(marca_produto,'0') = %s")
            params.append("1" if marca_produto else "0")
        if search and search.strip():
            where.append("descricao LIKE %s")
            params.append(f"%{search.strip()}%")
        sql = "SELECT codigo, descricao, ISNULL(marca_produto,'0') AS marca_produto FROM marcas"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY descricao"
        cur.execute(sql, tuple(params))
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "marca_produto": str(r.get("marca_produto") or "0").strip() == "1",
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_marca_sync(servidor: str, banco: str, codigo: Optional[str], descricao: str, marca_produto: bool) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        mp = 1 if marca_produto else 0
        if codigo:  # update
            cur.execute("UPDATE marcas SET descricao=%s, marca_produto=%s WHERE codigo=%s", (desc, mp, codigo))
            novo = codigo
        else:  # create
            novo = _next_codigo(cur, "marcas")
            cur.execute("INSERT INTO marcas (codigo, descricao, marca_produto) VALUES (%s,%s,%s)", (novo, desc, mp))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Marca gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_marca_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM modelos WHERE cod_marca=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Marca vinculada a modelos — não pode ser excluída."}
        cur.execute("DELETE FROM marcas WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Marca excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- ÁREA ----------------
# area(codigo smallint, descricao nvarchar(30)) — área de estoque do produto
# (Loja/Depósito etc.), referenciada por pecas.area. Distinta de `area_atuacao`
# (classificação de Pedido/O.S.), que já tem seu próprio lookup em lookups_service.
def _list_area_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM area {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_area_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if codigo is not None:  # update
            cur.execute("UPDATE area SET descricao=%s WHERE codigo=%s", (desc, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Área não encontrada."}
            novo = codigo
        else:  # create
            cur.execute("SELECT ISNULL(MAX(codigo), -1) + 1 AS novo FROM area")
            novo = int(cur.fetchone()["novo"])
            cur.execute("INSERT INTO area (codigo, descricao) VALUES (%s, %s)", (novo, desc))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Área gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_area_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM pecas WHERE area=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Área vinculada a produtos — não pode ser excluída."}
        cur.execute("DELETE FROM area WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Área excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- ÁREA DE ATUAÇÃO ----------------
# area_atuacao(area int PK, descricao nvarchar(50), centro_custo int,
#   TIPO_MOV_AREA_ATUACAO nvarchar(3), MODELO_OS smallint, MODELO_PEDIDO smallint,
#   INTERMEDIADOR int, INTERMEDIADOR_identificacao nvarchar(60)) — classificação
# usada em Pedidos/O.S. (pedido_venda.area_atuacao / os.area_atuacao). Distinta da
# tabela `area` (Loja/Depósito, usada em pecas.area).
# O lookup enxuto (codigo/descricao) para o combo de Pedido/O.S. já existe em
# lookups_service.list_area_atuacao — aqui é o CRUD completo da tela de manutenção.
def _list_area_atuacao_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(
            f"SELECT area AS codigo, descricao, centro_custo, "
            f"       TIPO_MOV_AREA_ATUACAO AS tipo_mov, MODELO_OS AS modelo_os, "
            f"       MODELO_PEDIDO AS modelo_pedido, INTERMEDIADOR AS intermediador, "
            f"       INTERMEDIADOR_identificacao AS intermediador_identificacao "
            f"FROM area_atuacao {where} ORDER BY descricao",
            params,
        )
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
            "centro_custo": r.get("centro_custo"),
            "tipo_mov": (r.get("tipo_mov") or "").strip() or None,
            "modelo_os": r.get("modelo_os"),
            "modelo_pedido": r.get("modelo_pedido"),
            "intermediador": r.get("intermediador"),
            "intermediador_identificacao": (r.get("intermediador_identificacao") or "").strip() or None,
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_area_atuacao_sync(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    centro_custo: Optional[int], tipo_mov: Optional[str], modelo_os: Optional[int],
    modelo_pedido: Optional[int], intermediador: Optional[int],
    intermediador_identificacao: Optional[str],
) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "area_atuacao")
        tipo_mov_v = _trunc((tipo_mov or "").strip(), sz, "tipo_mov_area_atuacao", 3) or None
        interm_id_v = _trunc((intermediador_identificacao or "").strip(), sz, "intermediador_identificacao", 60) or None
        params = (desc, centro_custo, tipo_mov_v, modelo_os, modelo_pedido, intermediador, interm_id_v)
        if codigo is not None:  # update
            cur.execute(
                "UPDATE area_atuacao SET descricao=%s, centro_custo=%s, "
                "TIPO_MOV_AREA_ATUACAO=%s, MODELO_OS=%s, MODELO_PEDIDO=%s, "
                "INTERMEDIADOR=%s, INTERMEDIADOR_identificacao=%s WHERE area=%s",
                params + (codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Área de atuação não encontrada."}
            novo = codigo
        else:  # create — `area` é IDENTITY, não gerar manualmente
            cur.execute(
                "INSERT INTO area_atuacao (descricao, centro_custo, "
                "TIPO_MOV_AREA_ATUACAO, MODELO_OS, MODELO_PEDIDO, INTERMEDIADOR, "
                "INTERMEDIADOR_identificacao) OUTPUT INSERTED.area "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                params,
            )
            row = cur.fetchone()
            novo = int(row["area"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Área de atuação gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_area_atuacao_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM pedido_venda WHERE area_atuacao=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Área de atuação vinculada a pedidos — não pode ser excluída."}
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE area_atuacao=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Área de atuação vinculada a O.S. — não pode ser excluída."}
        cur.execute("DELETE FROM area_atuacao WHERE area=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Área de atuação excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- MODELOS ----------------
def _list_modelos_sync(servidor: str, banco: str, cod_marca: Optional[str], search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if cod_marca:
            where.append("cod_marca = %s")
            params.append(cod_marca)
        if search and search.strip():
            where.append("descricao LIKE %s")
            params.append(f"%{search.strip()}%")
        sql = "SELECT codigo, cod_marca, descricao FROM modelos"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY descricao"
        cur.execute(sql, tuple(params))
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "cod_marca": (r.get("cod_marca") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_modelo_sync(servidor: str, banco: str, codigo: Optional[str], cod_marca: str, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not (cod_marca or "").strip():
        return {"success": False, "message": "Selecione a marca do modelo."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM marcas WHERE codigo=%s", (cod_marca,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Marca inexistente."}
        if codigo:
            cur.execute("UPDATE modelos SET cod_marca=%s, descricao=%s WHERE codigo=%s", (cod_marca, desc, codigo))
            novo = codigo
        else:
            novo = _next_codigo(cur, "modelos")
            cur.execute("INSERT INTO modelos (codigo, cod_marca, descricao) VALUES (%s,%s,%s)", (novo, cod_marca, desc))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Modelo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_modelo_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE modelo=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Modelo vinculado a O.S. — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM modelos_produtos WHERE modelo=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Modelo vinculado a produtos — não pode ser excluído."}
        cur.execute("DELETE FROM modelos WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Modelo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- GRUPO DE USUÁRIO ----------------
# classes_usuarios(codigo IDENTITY, classe nvarchar(15), EXIGE_TIPO_CLIENTE bit,
#   EXIGE_CANAL_AQUISICAO_CLIENTE bit, NAO_VISUALIZA_PEDIDO_ABERTO/FECHADO/
#   CANCELADO/FATURADO bit) — legado FrmManUsu (rótulo "Descrição do Grupo" na
#   tela, mas a coluna real no banco chama-se `classe`; mesmo tipo de mismatch
#   rótulo/coluna já documentado para `cliente` em CLAUDE.md).
#
# Os 4 campos NAO_VISUALIZA_PEDIDO_* são gravados INVERTIDOS em relação à tela:
# o checkbox exibido ao usuário é positivo ("Visualiza Pedidos Abertos" etc.),
# confirmado com o usuário (sem o .frm desta tela para conferir a fonte) — então
# marcado na UI -> grava 0 no banco (libera), desmarcado -> grava 1 (bloqueia).
#
# Ligada a `usuarios.classe` (grupo do usuário) e a `permissoes.classe` (usada
# pelo combo "Grupo (Classe)" da tela de Permissões — lookup já existente em
# permissoes_service._list_classes_sync, que lê a mesma tabela). Delete guard:
# bloqueia se houver usuário nesse grupo. Não cascateia limpeza de `permissoes`
# — a tabela é compartilhada com o sistema de retaguarda legado (outros
# `sistema`), então preferimos deixar linhas órfãs a arriscar apagar
# configuração de outro sistema.
def _list_grupos_usuario_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE classe LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(
            "SELECT codigo, classe, EXIGE_TIPO_CLIENTE AS exige_tipo_cliente, "
            "EXIGE_CANAL_AQUISICAO_CLIENTE AS exige_canal_aquisicao_cliente, "
            "NAO_VISUALIZA_PEDIDO_ABERTO AS nvpa, NAO_VISUALIZA_PEDIDO_FECHADO AS nvpf, "
            "NAO_VISUALIZA_PEDIDO_CANCELADO AS nvpc, NAO_VISUALIZA_PEDIDO_FATURADO AS nvpft "
            f"FROM classes_usuarios {where} ORDER BY classe",
            params,
        )
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("classe") or "").strip(),
            "exige_tipo_cliente": bool(r.get("exige_tipo_cliente")),
            "exige_canal_aquisicao_cliente": bool(r.get("exige_canal_aquisicao_cliente")),
            "visualiza_pedido_aberto": not bool(r.get("nvpa")),
            "visualiza_pedido_fechado": not bool(r.get("nvpf")),
            "visualiza_pedido_cancelado": not bool(r.get("nvpc")),
            "visualiza_pedido_faturado": not bool(r.get("nvpft")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_grupo_usuario_sync(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    exige_tipo_cliente: bool, exige_canal_aquisicao_cliente: bool,
    visualiza_pedido_aberto: bool, visualiza_pedido_fechado: bool,
    visualiza_pedido_cancelado: bool, visualiza_pedido_faturado: bool,
) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição do grupo é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "classes_usuarios")
        desc_v = _trunc(desc, sz, "classe", 15)
        cur.execute("SELECT TOP 1 codigo FROM classes_usuarios WHERE classe=%s AND codigo<>%s", (desc_v, codigo or 0))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Já existe um grupo com essa descrição."}
        params = (
            desc_v,
            1 if exige_tipo_cliente else 0,
            1 if exige_canal_aquisicao_cliente else 0,
            0 if visualiza_pedido_aberto else 1,
            0 if visualiza_pedido_fechado else 1,
            0 if visualiza_pedido_cancelado else 1,
            0 if visualiza_pedido_faturado else 1,
        )
        if codigo:  # update
            cur.execute(
                "UPDATE classes_usuarios SET classe=%s, EXIGE_TIPO_CLIENTE=%s, "
                "EXIGE_CANAL_AQUISICAO_CLIENTE=%s, NAO_VISUALIZA_PEDIDO_ABERTO=%s, "
                "NAO_VISUALIZA_PEDIDO_FECHADO=%s, NAO_VISUALIZA_PEDIDO_CANCELADO=%s, "
                "NAO_VISUALIZA_PEDIDO_FATURADO=%s WHERE codigo=%s",
                params + (codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Grupo não encontrado."}
            novo = codigo
        else:  # create — codigo é IDENTITY
            cur.execute(
                "INSERT INTO classes_usuarios (classe, EXIGE_TIPO_CLIENTE, "
                "EXIGE_CANAL_AQUISICAO_CLIENTE, NAO_VISUALIZA_PEDIDO_ABERTO, "
                "NAO_VISUALIZA_PEDIDO_FECHADO, NAO_VISUALIZA_PEDIDO_CANCELADO, "
                "NAO_VISUALIZA_PEDIDO_FATURADO) OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s)",
                params,
            )
            row = cur.fetchone()
            novo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Grupo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_grupo_usuario_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM usuarios WHERE classe=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Grupo vinculado a usuários — não pode ser excluído."}
        cur.execute("DELETE FROM classes_usuarios WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Grupo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- FUNÇÕES ----------------
# funcoes(codigo nvarchar(3) PK, descricao nvarchar(30), altera_cx bit,
#   cancelar_os bit, altera_tec_resp_os bit, FUNCAO_VENDEDOR bit,
#   FUNCAO_EXECUTOR bit, FUNCAO_ATENDENTE bit, libera_debito_pedido bit).
#
# Como Icms/Situação, `codigo` é digitado pelo usuário — mas aqui é sempre
# numérico (o VB6 força `Format(Campo(0), "00")` = 2 dígitos com zero à
# esquerda); replicamos isso: entrada puramente numérica é preenchida com
# zero à esquerda até 2 dígitos. Upsert-by-codigo, mesmo padrão das demais
# tabelas de código digitado.
#
# `funcionarios.cod_funcao` (nvarchar(3)) É lido de verdade por este app
# (auth_service.py monta a sessão com ele; lookups_service.py expõe a lista
# de funcionários com esse campo; frontend usa isManagerFuncao para
# cod_funcao 01/02) — soft FK sem constraint de banco, mas guard de exclusão
# real: bloqueia se houver funcionário com esse cod_funcao.
def _list_funcoes_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR codigo LIKE %s"
            params = (like, like)
        cur.execute(
            f"SELECT codigo, descricao, altera_cx, cancelar_os, altera_tec_resp_os, "
            f"FUNCAO_VENDEDOR, FUNCAO_EXECUTOR, FUNCAO_ATENDENTE, libera_debito_pedido "
            f"FROM funcoes {where} ORDER BY codigo", params,
        )
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "permite_altera_caixa": bool(r.get("altera_cx")),
            "cancelar_os": bool(r.get("cancelar_os")),
            "alterar_tecnico_responsavel": bool(r.get("altera_tec_resp_os")),
            "funcao_vendedor": bool(r.get("FUNCAO_VENDEDOR")),
            "funcao_executor": bool(r.get("FUNCAO_EXECUTOR")),
            "funcao_atendente": bool(r.get("FUNCAO_ATENDENTE")),
            "libera_cliente_debito": bool(r.get("libera_debito_pedido")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_funcoes_sync(
    servidor: str, banco: str, codigo: str, descricao: str,
    permite_altera_caixa: bool, cancelar_os: bool, alterar_tecnico_responsavel: bool,
    funcao_vendedor: bool, funcao_executor: bool, funcao_atendente: bool,
    libera_cliente_debito: bool,
) -> dict:
    cod = (codigo or "").strip()
    if cod.isdigit():
        cod = cod.zfill(2)
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "funcoes")
        cod_v = _trunc(cod, sz, "codigo", 3)
        desc_v = _trunc(desc, sz, "descricao", 30)
        cur.execute("SELECT TOP 1 1 AS ok FROM funcoes WHERE codigo=%s", (cod_v,))
        exists = cur.fetchone() is not None
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM funcoes WHERE codigo <> %s AND descricao = %s",
            (cod_v, desc_v),
        )
        if cur.fetchone():
            return {"success": False, "message": "Já existe função com essa descrição."}
        vals = (
            int(bool(funcao_executor)), int(bool(funcao_vendedor)), int(bool(funcao_atendente)),
            int(bool(libera_cliente_debito)), int(bool(permite_altera_caixa)),
            int(bool(cancelar_os)), int(bool(alterar_tecnico_responsavel)), desc_v,
        )
        if exists:  # upsert-by-codigo: codigo é digitado pelo usuário
            cur.execute(
                "UPDATE funcoes SET FUNCAO_EXECUTOR=%s, FUNCAO_VENDEDOR=%s, FUNCAO_ATENDENTE=%s, "
                "libera_debito_pedido=%s, altera_cx=%s, cancelar_os=%s, altera_tec_resp_os=%s, "
                "descricao=%s WHERE codigo=%s",
                vals + (cod_v,),
            )
        else:
            cur.execute(
                "INSERT INTO funcoes (FUNCAO_EXECUTOR, FUNCAO_VENDEDOR, FUNCAO_ATENDENTE, "
                "libera_debito_pedido, altera_cx, cancelar_os, altera_tec_resp_os, descricao, codigo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                vals + (cod_v,),
            )
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "Função gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_funcoes_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM funcionarios WHERE cod_funcao=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Função vinculada a funcionário(s) — não pode ser excluída."}
        cur.execute("DELETE FROM funcoes WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Função não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Função excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- STATUS DE O.S. ----------------
# status_os(codigo smallint NOT NULL — não IDENTITY, descricao nvarchar(50)).
#
# Correção 2026-07-07 (confirmado contra o .frm legado FrmManStaOs, campo
# "Tipo"): o código NÃO é auto-gerado — é digitado pelo usuário e a gravação
# é upsert-by-codigo (existe -> UPDATE descricao; não existe -> INSERT com o
# código informado), mesmo padrão de `situacao`/`icms`/`origem`. Uma versão
# anterior desta função gerava o código via MAX+1 (mesmo padrão de Regiões/
# Tipo Cliente) — estava errada, o legado nunca fez isso aqui.
#
# Diferente da maioria das tabelas recentes desta sessão: `os.status_os` É
# gravado de verdade por este app (os_service.py — campo próprio, distinto de
# `os.situacao`/Aberto-Fechado-Cancelado). Delete guard real: bloqueia se
# houver O.S. usando o status.
def _list_status_os_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM status_os {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_status_os_sync(servidor: str, banco: str, codigo: int, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not codigo:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "status_os")
        desc_v = _trunc(desc, sz, "descricao", 50)
        cur.execute("SELECT TOP 1 1 AS ok FROM status_os WHERE codigo=%s", (codigo,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário (campo "Tipo" no legado)
            cur.execute("UPDATE status_os SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
        else:
            cur.execute("INSERT INTO status_os (codigo, descricao) VALUES (%s,%s)", (codigo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": codigo, "message": "Status gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_status_os_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE status_os=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Status vinculado a O.S. — não pode ser excluído."}
        cur.execute("DELETE FROM status_os WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Status excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- TIPO DE DOCUMENTO ----------------
# tipo_doc(codigo smallint NOT NULL — não IDENTITY, auto-gerado MAX+1 mesmo
#   padrão de Regiões/Tipo Cliente —, descricao nvarchar(60)).
#
# Referenciada por tabelas de nota fiscal (n_fiscal.tipo_doc, nf_importada.
# tipo_doc, nf_recebimento.tipo_doc) e tipo_mov.tipo_doc — nenhuma delas é
# escrita por este app ainda (emissão de NF não está implementada). Guard de
# exclusão é só existência.
def _list_tipo_doc_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM tipo_doc {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_doc_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "tipo_doc")
        desc_v = _trunc(desc, sz, "descricao", 60)
        if codigo is not None:  # update
            cur.execute("UPDATE tipo_doc SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Tipo não encontrado."}
            novo = codigo
        else:  # create — codigo não é IDENTITY, gera MAX+1
            cur.execute("SELECT ISNULL(MAX(codigo), 0) + 1 AS novo FROM tipo_doc")
            novo = int(cur.fetchone()["novo"])
            cur.execute("INSERT INTO tipo_doc (codigo, descricao) VALUES (%s,%s)", (novo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Tipo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_doc_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM tipo_doc WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Tipo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tipo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- TIPO CLIENTE/FORNECEDOR ----------------
# tipo_cliente(codigo smallint NOT NULL — não IDENTITY, auto-gerado MAX+1
#   mesmo padrão de Regiões/Área —, descricao nvarchar(20)).
#
# Já é usada de verdade por este app: `cliente.cliente_forn` (campo "Tipo
# Cliente" do cadastro completo de cliente, clientes_service.py) referencia
# tipo_cliente.codigo. `fornecedor.cliente_forn` também referencia, mas este
# app não tem nenhuma tela/serviço de Fornecedor ainda — guard de exclusão
# checa só `cliente`.
def _list_tipo_cliente_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM tipo_cliente {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_cliente_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "tipo_cliente")
        desc_v = _trunc(desc, sz, "descricao", 20)
        if codigo is not None:  # update
            cur.execute("UPDATE tipo_cliente SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Tipo não encontrado."}
            novo = codigo
        else:  # create — codigo não é IDENTITY, gera MAX+1
            cur.execute("SELECT ISNULL(MAX(codigo), 0) + 1 AS novo FROM tipo_cliente")
            novo = int(cur.fetchone()["novo"])
            cur.execute("INSERT INTO tipo_cliente (codigo, descricao) VALUES (%s,%s)", (novo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Tipo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_cliente_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE cliente_forn=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Tipo vinculado a clientes — não pode ser excluído."}
        cur.execute("DELETE FROM tipo_cliente WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tipo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- GRUPO PIS/COFINS ----------------
# grupo_pis_cofins(cod_grupo nvarchar(3) PK — nome real da coluna é
#   `cod_grupo`, não `codigo` —, descricao nvarchar(35)). Agrupamento
#   definido pela própria empresa para regras de PIS/COFINS (diferente de
#   Icms/Origem, que são vocabulário fixo da legislação — aqui não há uma
#   tabela padrão externa, então o código é auto-gerado sequencial, mesmo
#   padrão de Marcas/Segmentos).
#
# Referenciada por `pecas.cod_grupo_pis_cofins` / `servicos.cod_grupo_pis_cofins`
# (tabelas mestras de produto/serviço já usadas por este app), mas nenhum
# service grava esse campo ainda — guard de exclusão é só existência.
def _list_grupo_pis_cofins_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR cod_grupo LIKE %s"
            params = (like, like)
        cur.execute(f"SELECT cod_grupo, descricao FROM grupo_pis_cofins {where} ORDER BY descricao", params)
        items = [{
            "codigo": (r.get("cod_grupo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_grupo_pis_cofins_sync(servidor: str, banco: str, codigo: Optional[str], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "grupo_pis_cofins")
        desc_v = _trunc(desc, sz, "descricao", 35)
        if codigo:  # update
            cur.execute("UPDATE grupo_pis_cofins SET descricao=%s WHERE cod_grupo=%s", (desc_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Grupo não encontrado."}
            novo = codigo
        else:  # create — cod_grupo não é IDENTITY, gera 3 dígitos sequenciais
            cur.execute(
                "SELECT MAX(CAST(cod_grupo AS INT)) AS mx FROM grupo_pis_cofins WHERE ISNUMERIC(cod_grupo) = 1"
            )
            r = cur.fetchone()
            novo = f"{int((r.get('mx') if r else None) or 0) + 1:03d}"
            cur.execute("INSERT INTO grupo_pis_cofins (cod_grupo, descricao) VALUES (%s,%s)", (novo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Grupo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_grupo_pis_cofins_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM grupo_pis_cofins WHERE cod_grupo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Grupo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Grupo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- TAMANHO ----------------
# tamanho(codigo nvarchar(3) PK) — tabela de UMA coluna só (sem descricao):
# uma lista simples de rótulos de tamanho (ex.: "P", "M", "G", "GG"), o
# próprio código já é o valor exibido. Igual ao legado (FrmManTam só tem
# Novo/Gravar/Exclui, sem "Altera" — não existe o que "alterar" numa linha
# de uma coluna só; renomear um tamanho é excluir e criar outro).
#
# Referenciada por `pecas_grade.tamanho` (variação de produto), mas nenhum
# service deste app grava/lê isso ainda — guard de exclusão é só existência.
def _list_tamanho_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE codigo LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo FROM tamanho {where} ORDER BY codigo", params)
        items = [{"codigo": (r.get("codigo") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tamanho_sync(servidor: str, banco: str, codigo: str) -> dict:
    cod = (codigo or "").strip().upper()
    if not cod:
        return {"success": False, "message": "Tamanho é obrigatório."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "tamanho")
        cod_v = _trunc(cod, sz, "codigo", 3)
        cur.execute("SELECT TOP 1 1 AS ok FROM tamanho WHERE codigo=%s", (cod_v,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Esse tamanho já está cadastrado."}
        cur.execute("INSERT INTO tamanho (codigo) VALUES (%s)", (cod_v,))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "Tamanho gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tamanho_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM tamanho WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Tamanho não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tamanho excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- SITUAÇÃO ----------------
# situacao(codigo nvarchar(2) PK, descricao nvarchar(30)) — tabela genérica de
# situações (ex.: A=Ativo, I=Inativo), referenciada de forma livre (texto, sem
# FK de banco) por vários campos espalhados pelo sistema (forma_pagamento.
# situacao, contas.situacao...). NÃO confundir com `STATUS_CLIENTE` — tabela
# dedicada e distinta para o status do cliente (ver CLAUDE.md).
#
# Como Icms/Origem, `codigo` é um mnemônico curto digitado pelo usuário (ex.:
# "A", "I"), não sequencial — upsert-by-codigo, travado depois de criado.
# Nenhum service deste app hoje valida contra esta tabela (os campos que
# citam "situacao" em outras tabelas são texto livre) — guard de exclusão é
# só existência.
def _list_situacao_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR codigo LIKE %s"
            params = (like, like)
        cur.execute(f"SELECT codigo, descricao FROM situacao {where} ORDER BY descricao", params)
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_situacao_sync(servidor: str, banco: str, codigo: str, descricao: str) -> dict:
    cod = (codigo or "").strip().upper()
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "situacao")
        cod_v = _trunc(cod, sz, "codigo", 2)
        desc_v = _trunc(desc, sz, "descricao", 30)
        cur.execute("SELECT TOP 1 1 AS ok FROM situacao WHERE codigo=%s", (cod_v,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: codigo é mnemônico digitado pelo usuário
            cur.execute("UPDATE situacao SET descricao=%s WHERE codigo=%s", (desc_v, cod_v))
        else:
            cur.execute("INSERT INTO situacao (codigo, descricao) VALUES (%s,%s)", (cod_v, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "Situação gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_situacao_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM situacao WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Situação não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Situação excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- SEGMENTOS ----------------
# segmentos(codigo nvarchar(3) PK — auto-gerado via _next_codigo, mesmo padrão
#   de Marcas/Forma de Pagamento —, descricao nvarchar(30)).
#
# Já existe lookup somente-leitura em lookups_service.list_segmentos (usado no
# combo "Segmento" do cadastro completo de cliente) — esta tela é o CRUD
# completo. Delete guard real: `cliente.segmento` é gravado de verdade por
# este app (cliente-completo).
def _list_segmentos_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR codigo LIKE %s"
            params = (like, like)
        cur.execute(f"SELECT codigo, descricao FROM segmentos {where} ORDER BY descricao", params)
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_segmento_sync(servidor: str, banco: str, codigo: Optional[str], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "segmentos")
        desc_v = _trunc(desc, sz, "descricao", 30)
        if codigo:  # update
            cur.execute("UPDATE segmentos SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Segmento não encontrado."}
            novo = codigo
        else:  # create
            novo = _next_codigo(cur, "segmentos")
            cur.execute("INSERT INTO segmentos (codigo, descricao) VALUES (%s,%s)", (novo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Segmento gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_segmento_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE segmento=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Segmento vinculado a clientes — não pode ser excluído."}
        cur.execute("DELETE FROM segmentos WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Segmento excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- ROTAS ----------------
# rotas(codigo int NOT NULL — não IDENTITY, auto-gerado MAX+1 mesmo padrão de
#   Regiões/Área —, descricao nvarchar(30), prioridade smallint,
#   codigo_regiao int NOT NULL FK -> regioes.codigo, obrigatória).
#
# Já existe lookup somente-leitura em lookups_service.list_rotas (usado no
# combo "Rota" do cadastro completo de cliente) — esta tela é o CRUD completo.
# Delete guard real: `cliente.rota` é gravado de verdade por este app.
def _list_rotas_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao, prioridade, codigo_regiao FROM rotas {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
            "prioridade": r.get("prioridade"),
            "codigo_regiao": int(r["codigo_regiao"]) if r.get("codigo_regiao") is not None else None,
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_rota_sync(
    servidor: str, banco: str, codigo: Optional[int], descricao: str,
    prioridade: Optional[int], codigo_regiao: Optional[int],
) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    if not codigo_regiao:
        return {"success": False, "message": "Selecione a região."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM regioes WHERE codigo=%s", (codigo_regiao,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Região inexistente."}
        sz = _get_col_sizes(conn, banco, "rotas")
        desc_v = _trunc(desc, sz, "descricao", 30)
        if codigo is not None:  # update
            cur.execute(
                "UPDATE rotas SET descricao=%s, prioridade=%s, codigo_regiao=%s WHERE codigo=%s",
                (desc_v, prioridade, codigo_regiao, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Rota não encontrada."}
            novo = codigo
        else:  # create — codigo não é IDENTITY, gera MAX+1
            cur.execute("SELECT ISNULL(MAX(codigo), 0) + 1 AS novo FROM rotas")
            novo = int(cur.fetchone()["novo"])
            cur.execute(
                "INSERT INTO rotas (codigo, descricao, prioridade, codigo_regiao) VALUES (%s,%s,%s,%s)",
                (novo, desc_v, prioridade, codigo_regiao),
            )
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Rota gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_rota_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE rota=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Rota vinculada a clientes — não pode ser excluída."}
        cur.execute("DELETE FROM rotas WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Rota excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- REGIÕES ----------------
# regioes(codigo int NOT NULL — não é IDENTITY, mas sequencial simples,
#   descricao nvarchar(20)). Diferente de Icms/Origem (vocabulário fixo da
#   legislação fiscal), aqui os códigos são só uma numeração arbitrária da
#   empresa — mesmo padrão de "Área" (auto-gerado via MAX+1, não digitado).
#
# Já existe um lookup somente-leitura em lookups_service.list_regioes (usado
# pelo combo "Região" do cadastro completo de cliente) — esta tela é o CRUD
# completo. Delete guard real: `cliente.regiao` é gravado de verdade por este
# app (cliente-completo), então bloqueamos exclusão se houver cliente vinculado.
def _list_regioes_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM regioes {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_regiao_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "regioes")
        desc_v = _trunc(desc, sz, "descricao", 20)
        if codigo is not None:  # update
            cur.execute("UPDATE regioes SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Região não encontrada."}
            novo = codigo
        else:  # create — codigo não é IDENTITY, gera MAX+1 (mesmo padrão de "Área")
            cur.execute("SELECT ISNULL(MAX(codigo), 0) + 1 AS novo FROM regioes")
            novo = int(cur.fetchone()["novo"])
            cur.execute("INSERT INTO regioes (codigo, descricao) VALUES (%s,%s)", (novo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Região gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_regiao_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE regiao=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Região vinculada a clientes — não pode ser excluída."}
        cur.execute("SELECT TOP 1 1 AS ok FROM rotas WHERE codigo_regiao=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Região vinculada a rotas — não pode ser excluída."}
        cur.execute("DELETE FROM regioes WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Região excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- ORIGEM ----------------
# origem(codigo nvarchar(1) PK, descricao nvarchar(MAX)) — "Origem da
# Mercadoria" padrão NFe (0-8: Nacional, Importação direta, Importação c/
# mercado interno, etc.). Como ICMS, `codigo` é o dígito padronizado pela
# legislação fiscal (0-8), digitado pelo usuário — upsert-by-codigo, travado
# depois de criado. Nenhuma tabela deste app grava/lê `pecas.origem` (ou
# equivalentes) ainda — guard de exclusão é só existência.
def _list_origem_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR codigo LIKE %s"
            params = (like, like)
        cur.execute(f"SELECT codigo, descricao FROM origem {where} ORDER BY codigo", params)
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_origem_sync(servidor: str, banco: str, codigo: str, descricao: str) -> dict:
    cod = (codigo or "").strip()
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "origem")
        cod_v = _trunc(cod, sz, "codigo", 1)
        desc_v = _trunc(desc, sz, "descricao", 500)
        cur.execute("SELECT TOP 1 1 AS ok FROM origem WHERE codigo=%s", (cod_v,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: codigo é natural key digitada pelo usuário
            cur.execute("UPDATE origem SET descricao=%s WHERE codigo=%s", (desc_v, cod_v))
        else:
            cur.execute("INSERT INTO origem (codigo, descricao) VALUES (%s,%s)", (cod_v, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "Origem gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_origem_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM origem WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Origem não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Origem excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- ICMS ----------------
# dscr_icms(cod_icms nvarchar(3) PK, descricao nvarchar(35)) — tabela de
# situações tributárias de ICMS (CST/CSOSN, ex.: "00" Tributada integralmente,
# "20" Com redução de base de cálculo, "101" Simples Nacional c/ permissão de
# crédito...). Referenciada por pecas.cod_icms / servicos.cod_icms / taxas.cod_icms
# (nenhuma escrita por este app ainda — guard de exclusão é só existência).
#
# Diferente de Marcas/Cores, `cod_icms` NÃO é sequencial arbitrário — é o
# código padronizado da legislação fiscal (CST/CSOSN), então o próprio código
# é digitado pelo usuário (mesmo padrão de Centro de Custo): upsert-by-codigo,
# travado depois de criado.
#
# ATENÇÃO: existe também uma tabela chamada exatamente `icms` (codigo_nota,
# codigo_interno, base_calculo, valor) — é um detalhe de cálculo por item de
# nota fiscal, não uma tabela de cadastro. Não confundir as duas; esta tela é
# sobre `dscr_icms`.
def _list_icms_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR cod_icms LIKE %s"
            params = (like, like)
        cur.execute(f"SELECT cod_icms, descricao FROM dscr_icms {where} ORDER BY descricao", params)
        items = [{
            "codigo": (r.get("cod_icms") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_icms_sync(servidor: str, banco: str, codigo: str, descricao: str) -> dict:
    cod = (codigo or "").strip().upper()
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "dscr_icms")
        cod_v = _trunc(cod, sz, "cod_icms", 3)
        desc_v = _trunc(desc, sz, "descricao", 35)
        cur.execute("SELECT TOP 1 1 AS ok FROM dscr_icms WHERE cod_icms=%s", (cod_v,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: cod_icms é natural key digitada pelo usuário
            cur.execute("UPDATE dscr_icms SET descricao=%s WHERE cod_icms=%s", (desc_v, cod_v))
        else:
            cur.execute("INSERT INTO dscr_icms (cod_icms, descricao) VALUES (%s,%s)", (cod_v, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "ICMS gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_icms_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM dscr_icms WHERE cod_icms=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "ICMS não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "ICMS excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- CORES ----------------
# cores(codigo nvarchar(3) PK, descricao nvarchar(30), cor_fabrica nvarchar(10)
#   — código da cor de fábrica/montadora, texto livre). Nenhuma tabela deste app
# grava/lê `cor` hoje (os.cor, veiculos.cor, pecas_grade.cor etc. existem no
# banco mas não são usadas por nenhum service atual) — por isso o delete guard
# aqui é só a existência do registro, sem checar tabelas cruzadas.
def _list_cores_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR codigo LIKE %s"
            params = (like, like)
        cur.execute(f"SELECT codigo, descricao, cor_fabrica FROM cores {where} ORDER BY descricao", params)
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cor_fabrica": (r.get("cor_fabrica") or "").strip() or None,
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_cor_sync(servidor: str, banco: str, codigo: Optional[str], descricao: str, cor_fabrica: Optional[str]) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, banco, "cores")
        desc_v = _trunc(desc, sz, "descricao", 30)
        fabrica_v = _trunc((cor_fabrica or "").strip() or None, sz, "cor_fabrica", 10)
        if codigo:  # update
            cur.execute("UPDATE cores SET descricao=%s, cor_fabrica=%s WHERE codigo=%s", (desc_v, fabrica_v, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Cor não encontrada."}
            novo = codigo
        else:  # create
            novo = _next_codigo(cur, "cores")
            cur.execute("INSERT INTO cores (codigo, descricao, cor_fabrica) VALUES (%s,%s,%s)", (novo, desc_v, fabrica_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Cor gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_cor_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM cores WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Cor não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Cor excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- GRUPO MERCADOLÓGICO ----------------
# niveis(cod_nivel IDENTITY, nivel1..nivel5 nvarchar(3) NOT NULL — segmento vazio
#   "" quando o nível não é usado naquela profundidade —, descr, custo FK->
#   centro_custo.codigo, classe_entrada/sub_classe_entrada/classe_saida/
#   sub_classe_saida FK-> classes/sub_classes). Legado: FRMMANNIVNEW ("Definição
#   de Níveis"). Árvore de até 5 níveis usada para classificar produtos/serviços
#   (pecas.nivel1..5 / servicos.nivel1..5) — path materializado por concatenação
#   de segmentos, não por parent_id.
#
# Cada linha é UM nó da árvore (não só as folhas): o nó "Produto" tem sua própria
# linha (nivel1='001', nivel2='002', nivel3..5='') além de cada filho dele ter
# a sua. O código de cada segmento é sequencial (MAX+1) dentro do escopo do pai
# — replicado abaixo com a mesma lógica do Select Case do legado.
#
# Fora de escopo (Tray/e-commerce, sem infra no projeto): caracteristicas,
# url_tray, id_tray.
#
# Alterar um nó só atualiza descr/custo/classe_* dele mesmo — o legado oferece
# propagar as mudanças de classe/subclasse para os níveis inferiores também
# ("Aplicar Alterações aos níveis inferiores?"); não implementado aqui.
#
# Delete guard: bloqueia se o nó tiver subníveis, ou se houver produto
# (`pecas`) ou serviço (`servicos`) classificado exatamente nesse nível — esses
# são dados de negócio reais (tabelas mestras de produto/serviço já usadas por
# este app), diferente das tabelas de detalhe do legado que ignoramos em telas
# anteriores (ex.: Forma de Pagamento).
def _next_nivel_segment(cur, nivel1: str, nivel2: str, nivel3: str, nivel4: str) -> str:
    if not nivel1:
        cur.execute("SELECT MAX(TRY_CAST(nivel1 AS INT)) AS mx FROM niveis")
    elif not nivel2:
        cur.execute("SELECT MAX(TRY_CAST(nivel2 AS INT)) AS mx FROM niveis WHERE nivel1=%s AND nivel2<>''", (nivel1,))
    elif not nivel3:
        cur.execute("SELECT MAX(TRY_CAST(nivel3 AS INT)) AS mx FROM niveis WHERE nivel1=%s AND nivel2=%s AND nivel3<>''", (nivel1, nivel2))
    elif not nivel4:
        cur.execute(
            "SELECT MAX(TRY_CAST(nivel4 AS INT)) AS mx FROM niveis WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4<>''",
            (nivel1, nivel2, nivel3),
        )
    else:
        cur.execute(
            "SELECT MAX(TRY_CAST(nivel5 AS INT)) AS mx FROM niveis WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4=%s AND nivel5<>''",
            (nivel1, nivel2, nivel3, nivel4),
        )
    r = cur.fetchone()
    nxt = int((r.get("mx") if r else None) or 0) + 1
    return f"{nxt:03d}"


def _list_niveis_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_nivel, nivel1, nivel2, nivel3, nivel4, nivel5, descr, custo, "
            "classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida "
            "FROM niveis ORDER BY nivel1, nivel2, nivel3, nivel4, nivel5"
        )
        items = [{
            "cod_nivel": int(r["cod_nivel"]),
            "nivel1": (r.get("nivel1") or "").strip(),
            "nivel2": (r.get("nivel2") or "").strip(),
            "nivel3": (r.get("nivel3") or "").strip(),
            "nivel4": (r.get("nivel4") or "").strip(),
            "nivel5": (r.get("nivel5") or "").strip(),
            "descricao": (r.get("descr") or "").strip(),
            "custo": r.get("custo"),
            "classe_entrada": r.get("classe_entrada"),
            "sub_classe_entrada": r.get("sub_classe_entrada"),
            "classe_saida": r.get("classe_saida"),
            "sub_classe_saida": r.get("sub_classe_saida"),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_nivel_sync(
    servidor: str, banco: str, cod_nivel: Optional[int], parent_cod_nivel: Optional[int], descricao: str,
    custo: Optional[int], classe_entrada: Optional[int], sub_classe_entrada: Optional[int],
    classe_saida: Optional[int], sub_classe_saida: Optional[int],
) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if custo is not None:
            cur.execute("SELECT TOP 1 1 AS ok FROM centro_custo WHERE codigo=%s", (custo,))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": "Centro de custo não cadastrado."}
        sz = _get_col_sizes(conn, banco, "niveis")
        desc_v = _trunc(desc, sz, "descr", 35)
        params_fluxo = (custo, classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida)

        if cod_nivel:  # update — nivel1..5 permanecem fixos, só descr/custo/classe_* mudam
            cur.execute(
                "UPDATE niveis SET descr=%s, custo=%s, classe_entrada=%s, sub_classe_entrada=%s, "
                "classe_saida=%s, sub_classe_saida=%s WHERE cod_nivel=%s",
                (desc_v,) + params_fluxo + (cod_nivel,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Grupo não encontrado."}
            conn.commit()
            cur.close()
            return {"success": True, "cod_nivel": cod_nivel, "message": "Grupo gravado."}

        # create
        levels = ["", "", "", "", ""]
        if parent_cod_nivel:
            cur.execute("SELECT nivel1, nivel2, nivel3, nivel4, nivel5 FROM niveis WHERE cod_nivel=%s", (parent_cod_nivel,))
            p = cur.fetchone()
            if not p:
                cur.close()
                return {"success": False, "message": "Nível pai não encontrado."}
            levels = [(p.get(f"nivel{i}") or "").strip() for i in range(1, 6)]
            if levels[4]:
                cur.close()
                return {"success": False, "message": "Nível máximo (5) já atingido — não é possível criar subnível."}
        try:
            idx = next(i for i, v in enumerate(levels) if not v)
        except StopIteration:
            cur.close()
            return {"success": False, "message": "Nível máximo (5) já atingido — não é possível criar subnível."}
        novo_seg = _next_nivel_segment(cur, levels[0], levels[1], levels[2], levels[3])
        levels[idx] = novo_seg

        cur.execute(
            "INSERT INTO niveis (nivel1, nivel2, nivel3, nivel4, nivel5, descr, custo, classe_entrada, "
            "sub_classe_entrada, classe_saida, sub_classe_saida) OUTPUT INSERTED.cod_nivel "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            tuple(levels) + (desc_v,) + params_fluxo,
        )
        row = cur.fetchone()
        novo = int(row["cod_nivel"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "cod_nivel": novo, "message": "Grupo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_nivel_sync(servidor: str, banco: str, cod_nivel: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT nivel1, nivel2, nivel3, nivel4, nivel5 FROM niveis WHERE cod_nivel=%s", (cod_nivel,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Grupo não encontrado."}
        levels = [(row.get(f"nivel{i}") or "").strip() for i in range(1, 6)]
        depth = sum(1 for v in levels if v)

        if depth < 5:
            next_col = f"nivel{depth + 1}"
            where = " AND ".join(f"nivel{i}=%s" for i in range(1, depth + 1)) if depth else "1=1"
            params = tuple(levels[:depth]) + ("", cod_nivel)
            cur.execute(f"SELECT TOP 1 1 AS ok FROM niveis WHERE {where} AND {next_col}<>%s AND cod_nivel<>%s", params)
            if cur.fetchone():
                cur.close()
                return {"success": False, "message": "Grupo possui subníveis — exclua-os primeiro."}

        cur.execute(
            "SELECT TOP 1 1 AS ok FROM pecas WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4=%s AND nivel5=%s",
            tuple(levels),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Existem produtos classificados neste grupo — não pode ser excluído."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM servicos WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4=%s AND nivel5=%s",
            tuple(levels),
        )
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Existem serviços classificados neste grupo — não pode ser excluído."}

        cur.execute("DELETE FROM niveis WHERE cod_nivel=%s", (cod_nivel,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Grupo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- FORMA DE PAGAMENTO ----------------
# forma_pagamento(codigo nvarchar(3) PK, descricao, tipo, taxa_adm, prazo, prazo_rec,
#   situacao, periodo, faturar_para, FORMA_PAG_GARANTIA, Exige_Documentos, vale_devolucao,
#   nao_totaliza_caixa, parcelador, parcela_max, cod_mov, perc_desc_comissao,
#   valor_desc_comissao, perc_acres_comissao, valor_acres_comissao, transf_caixa,
#   conta_transf_caixa, classe_caixa, sub_classe_caixa, ...) — tela inspirada no legado
# VB6 FrmManForPag. Fora do escopo: integração Tray (id_tray) e colunas obsoletas
# (usa_tef, descricao_ecf, banco/agencia/numero da forma, TAC, aceita_troco/gorjeta,
# administradora, agrupamento) — não usadas por este app.
#
# forma_pag_prazo(cod IDENTITY, forma_pag FK nvarchar(3), prazo smallint, percentual float)
#   — escalonamento de recebimento por prazo; substituído por completo a cada gravação
#   (mesmo padrão de telefones/endereços do cadastro de cliente).
#
# Não há FK declarada no banco para `forma_pag`: dezenas de tabelas legadas a referenciam
# por convenção (os_*, pedido_venda_*, comanda_*...), mas nenhuma delas é escrita por este
# app ainda — apenas `cliente.forma_pag` é. Por isso o guard de exclusão checa só `cliente`.
def _list_forma_pagamento_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR codigo LIKE %s"
            params = (like, like)
        cur.execute(
            "SELECT codigo, descricao, tipo, taxa_adm, prazo, prazo_rec, situacao, periodo, "
            "faturar_para, FORMA_PAG_GARANTIA AS forma_pag_garantia, "
            "Exige_Documentos AS exige_documentos, vale_devolucao, nao_totaliza_caixa, "
            "parcelador, parcela_max, cod_mov, perc_desc_comissao, valor_desc_comissao, "
            "perc_acres_comissao, valor_acres_comissao, transf_caixa, conta_transf_caixa, "
            f"classe_caixa, sub_classe_caixa FROM forma_pagamento {where} ORDER BY descricao",
            params,
        )
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "tipo": (r.get("tipo") or "").strip() or None,
            "taxa_adm": float(r.get("taxa_adm") or 0),
            "prazo": r.get("prazo"),
            "prazo_rec": r.get("prazo_rec"),
            "situacao": (r.get("situacao") or "").strip() or None,
            "periodo": r.get("periodo"),
            "faturar_para": (r.get("faturar_para") or "").strip() or None,
            "forma_pag_garantia": bool(r.get("forma_pag_garantia")),
            "exige_documentos": bool(r.get("exige_documentos")),
            "vale_devolucao": bool(r.get("vale_devolucao")),
            "nao_totaliza_caixa": bool(r.get("nao_totaliza_caixa")),
            "parcelador": (r.get("parcelador") or "").strip() or None,
            "parcela_max": r.get("parcela_max"),
            "cod_mov": (r.get("cod_mov") or "").strip() or None,
            "perc_desc_comissao": float(r.get("perc_desc_comissao") or 0),
            "valor_desc_comissao": float(r.get("valor_desc_comissao") or 0),
            "perc_acres_comissao": float(r.get("perc_acres_comissao") or 0),
            "valor_acres_comissao": float(r.get("valor_acres_comissao") or 0),
            "transf_caixa": (r.get("transf_caixa") or "").strip() or None,
            "conta_transf_caixa": r.get("conta_transf_caixa"),
            "classe_caixa": r.get("classe_caixa"),
            "sub_classe_caixa": r.get("sub_classe_caixa"),
            "prazos": [],
        } for r in cur.fetchall()]

        cur.execute("SELECT forma_pag, prazo, percentual FROM forma_pag_prazo ORDER BY forma_pag, prazo")
        prazos_by_forma: dict = {}
        for r in cur.fetchall():
            fp = (r.get("forma_pag") or "").strip()
            prazos_by_forma.setdefault(fp, []).append({
                "prazo": int(r["prazo"]),
                "percentual": float(r.get("percentual") or 0),
            })
        for it in items:
            it["prazos"] = prazos_by_forma.get(it["codigo"], [])

        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_forma_pagamento_sync(req) -> dict:
    desc = (req.descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    tipo = (req.tipo or "").strip().upper()
    if not tipo:
        return {"success": False, "message": "Selecione o tipo."}
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        sz = _get_col_sizes(conn, req.banco, "forma_pagamento")
        situacao = _trunc((req.situacao or "A").strip().upper() or "A", sz, "situacao", 2)
        faturar_para = _trunc((req.faturar_para or "C").strip().upper() or "C", sz, "faturar_para", 1)
        parcelador = _trunc((req.parcelador or "L").strip().upper() or "L", sz, "parcelador", 1)
        transf_caixa = _trunc((req.transf_caixa or "").strip().upper(), sz, "transf_caixa", 1) or None
        cod_mov = _trunc((req.cod_mov or "").strip() or None, sz, "cod_mov", 3)
        tipo_v = _trunc(tipo, sz, "tipo", 2)

        params = (
            desc, tipo_v, req.taxa_adm or 0, req.prazo, req.prazo_rec, situacao, req.periodo,
            faturar_para, 1 if req.forma_pag_garantia else 0, 1 if req.exige_documentos else 0,
            1 if req.vale_devolucao else 0, 1 if req.nao_totaliza_caixa else 0,
            parcelador, req.parcela_max, cod_mov,
            req.perc_desc_comissao or 0, req.valor_desc_comissao or 0,
            req.perc_acres_comissao or 0, req.valor_acres_comissao or 0,
            transf_caixa, req.conta_transf_caixa, req.classe_caixa, req.sub_classe_caixa,
        )
        if req.codigo:  # update
            cur.execute(
                "UPDATE forma_pagamento SET descricao=%s, tipo=%s, taxa_adm=%s, prazo=%s, "
                "prazo_rec=%s, situacao=%s, periodo=%s, faturar_para=%s, FORMA_PAG_GARANTIA=%s, "
                "Exige_Documentos=%s, vale_devolucao=%s, nao_totaliza_caixa=%s, parcelador=%s, "
                "parcela_max=%s, cod_mov=%s, perc_desc_comissao=%s, valor_desc_comissao=%s, "
                "perc_acres_comissao=%s, valor_acres_comissao=%s, transf_caixa=%s, "
                "conta_transf_caixa=%s, classe_caixa=%s, sub_classe_caixa=%s WHERE codigo=%s",
                params + (req.codigo,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Forma de pagamento não encontrada."}
            novo = req.codigo
        else:  # create
            novo = _next_codigo(cur, "forma_pagamento")
            cur.execute(
                "INSERT INTO forma_pagamento (codigo, descricao, tipo, taxa_adm, prazo, "
                "prazo_rec, situacao, periodo, faturar_para, FORMA_PAG_GARANTIA, "
                "Exige_Documentos, vale_devolucao, nao_totaliza_caixa, parcelador, "
                "parcela_max, cod_mov, perc_desc_comissao, valor_desc_comissao, "
                "perc_acres_comissao, valor_acres_comissao, transf_caixa, conta_transf_caixa, "
                "classe_caixa, sub_classe_caixa) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (novo,) + params,
            )

        cur.execute("DELETE FROM forma_pag_prazo WHERE forma_pag=%s", (novo,))
        for p in (req.prazos or []):
            cur.execute(
                "INSERT INTO forma_pag_prazo (forma_pag, prazo, percentual) VALUES (%s,%s,%s)",
                (novo, p.prazo, p.percentual or 0),
            )

        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Forma de pagamento gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_forma_pagamento_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE forma_pag=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Forma de pagamento vinculada a clientes — não pode ser excluída."}
        cur.execute("DELETE FROM forma_pag_prazo WHERE forma_pag=%s", (codigo,))
        cur.execute("DELETE FROM forma_pagamento WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Forma de pagamento excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- CFOP ----------------
# cfops(cfop nvarchar(4) PK, descricao nvarchar(MAX), descricao_nf nvarchar(20)
#   default '', aplicacao nvarchar(MAX) default '', cod_contabil int default 0
#   FK solto -> codigo_contabil.codigo). Legado: FrmManCFO ("Manutenção de
#   Código Fiscal de Operações"). Como Icms/Situação, `cfop` é o código
#   padronizado da legislação fiscal, digitado pelo usuário — upsert-by-codigo,
#   travado depois de criado.
#
# Delete guard real: bloqueia se o CFOP estiver referenciado em `taxas.cfop`
# ou `n_fiscal.cfop` (mesmas duas tabelas checadas pelo legado antes de excluir).
def _list_cfop_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            like = f"%{search.strip()}%"
            where = "WHERE descricao LIKE %s OR cfop LIKE %s"
            params = (like, like)
        cur.execute(
            f"SELECT cfop, descricao, descricao_nf, aplicacao, cod_contabil FROM cfops {where} ORDER BY cfop",
            params,
        )
        items = [{
            "codigo": (r.get("cfop") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "descricao_nf": (r.get("descricao_nf") or "").strip(),
            "aplicacao": (r.get("aplicacao") or "").strip(),
            "cod_contabil": r.get("cod_contabil"),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_cfop_sync(
    servidor: str, banco: str, codigo: str, descricao: str,
    descricao_nf: Optional[str], aplicacao: Optional[str], cod_contabil: Optional[int],
) -> dict:
    cod = (codigo or "").strip()
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if cod_contabil:
            cur.execute("SELECT TOP 1 1 AS ok FROM codigo_contabil WHERE codigo=%s", (cod_contabil,))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": "Código contábil não cadastrado."}
        sz = _get_col_sizes(conn, banco, "cfops")
        cod_v = _trunc(cod, sz, "cfop", 4)
        desc_nf_v = _trunc((descricao_nf or "").strip(), sz, "descricao_nf", 20)
        aplicacao_v = (aplicacao or "").strip()
        cur.execute("SELECT TOP 1 1 AS ok FROM cfops WHERE cfop=%s", (cod_v,))
        exists = cur.fetchone() is not None
        params = (desc, desc_nf_v, aplicacao_v, cod_contabil or 0)
        if exists:  # upsert-by-codigo: cfop é natural key digitada pelo usuário
            cur.execute(
                "UPDATE cfops SET descricao=%s, descricao_nf=%s, aplicacao=%s, cod_contabil=%s WHERE cfop=%s",
                params + (cod_v,),
            )
        else:
            cur.execute(
                "INSERT INTO cfops (cfop, descricao, descricao_nf, aplicacao, cod_contabil) VALUES (%s,%s,%s,%s,%s)",
                (cod_v,) + params,
            )
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "CFOP gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_cfop_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM taxas WHERE cfop=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "CFOP vinculado a taxas — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM n_fiscal WHERE cfop=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "CFOP vinculado a notas fiscais — não pode ser excluído."}
        cur.execute("DELETE FROM cfops WHERE cfop=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "CFOP não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "CFOP excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- CFOP X.M.L. (vínculos) ----------------
# cfop_xml(cfop_xml nvarchar(4), cfop nvarchar(4), PK composta (cfop_xml, cfop)
#   no banco) — dicionário "CFOP do XML importado -> CFOP de entrada" usado na
#   importação de NF-e por XML. Na prática cada `cfop_xml` deve mapear para um
#   único `cfop` de entrada, então tratamos como upsert-by-cfop_xml (mais
#   seguro que o legado, que só fazia INSERT cru e podia duplicar o mapeamento).
def _list_cfop_xml_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cfop_xml, cfop FROM cfop_xml ORDER BY cfop_xml")
        items = [{
            "cfop_xml": (r.get("cfop_xml") or "").strip(),
            "cfop": (r.get("cfop") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_cfop_xml_sync(servidor: str, banco: str, cfop_xml: str, cfop: str) -> dict:
    xml_v = (cfop_xml or "").strip()
    cfop_v = (cfop or "").strip()
    if not xml_v:
        return {"success": False, "message": "Informe o CFOP no XML."}
    if not cfop_v:
        return {"success": False, "message": "Informe o CFOP de entrada."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cfops WHERE cfop=%s", (cfop_v,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "CFOP de entrada não cadastrado."}
        cur.execute("SELECT TOP 1 1 AS ok FROM cfop_xml WHERE cfop_xml=%s", (xml_v,))
        if cur.fetchone():
            cur.execute("UPDATE cfop_xml SET cfop=%s WHERE cfop_xml=%s", (cfop_v, xml_v))
        else:
            cur.execute("INSERT INTO cfop_xml (cfop_xml, cfop) VALUES (%s,%s)", (xml_v, cfop_v))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Vínculo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_cfop_xml_sync(servidor: str, banco: str, cfop_xml: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM cfop_xml WHERE cfop_xml=%s", (cfop_xml,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Vínculo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Vínculo removido."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- CFOP x PIS/COFINS ----------------
# cfop_pis_cofins(Cod_Auto int IDENTITY PK, CFOP nvarchar(4) FK solto ->
#   cfops.cfop, grupo_pis_cofins smallint, tributacao_qtd bit,
#   tributacao_pis smallint, perc_valor_pis real, tributacao_cofins smallint,
#   perc_valor_cofins real, Acatar_nfe bit). Legado: FrmCfoPis
#   ("CFOP´s x Pis e Cofins"). Fora de escopo (colunas existentes na tabela
#   mas não usadas pela tela legado): vr_base_subst_ant, vr_icms_subst_ant.
#
# Duas colunas guardam um mismatch texto/numérico, o mesmo padrão já visto em
# outras tabelas deste projeto: `grupo_pis_cofins` (smallint) referencia
# `grupo_pis_cofins.cod_grupo`, que é nvarchar(3) (ex.: "001"); `tributacao_pis`/
# `tributacao_cofins` (smallint) referenciam `cst_pis.CST_Pis`/
# `cst_cofins.CST_Cofins`, nvarchar(2) (ex.: "01"). Convertemos com
# TRY_CAST(... AS INT) nas duas pontas para validar/juntar.
#
# Chave natural do legado é o par (cfop, grupo_pis_cofins) — sem unique
# constraint no banco, mas o form sempre faz um SELECT por esse par antes de
# decidir Insert/Update. Reproduzido abaixo como upsert-by-(cfop, grupo)
# quando `cod_auto` não é informado (tela "Novo"); com `cod_auto` informado,
# atualiza direto por PK (edição de uma linha já carregada da grade).
#
# Delete guard: nenhuma outra tabela deste app grava/lê `cfop_pis_cofins` —
# guard de exclusão é só existência (mesmo padrão de Tamanho/Tipo de Documento).
def _list_cfop_pis_cofins_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE c.cfop LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(
            f"SELECT c.Cod_Auto, c.CFOP, c.grupo_pis_cofins, g.descricao AS grupo_descricao, "
            f"c.tributacao_qtd, c.tributacao_pis, c.perc_valor_pis, "
            f"c.tributacao_cofins, c.perc_valor_cofins, c.Acatar_nfe "
            f"FROM cfop_pis_cofins c "
            f"LEFT JOIN grupo_pis_cofins g ON TRY_CAST(g.cod_grupo AS INT) = c.grupo_pis_cofins "
            f"{where} ORDER BY c.CFOP, c.grupo_pis_cofins",
            params,
        )
        items = [{
            "cod_auto": int(r["Cod_Auto"]),
            "cfop": (r.get("CFOP") or "").strip(),
            "grupo_pis_cofins": r.get("grupo_pis_cofins"),
            "grupo_descricao": (r.get("grupo_descricao") or "").strip() or None,
            "tributacao_qtd": bool(r.get("tributacao_qtd")),
            "tributacao_pis": r.get("tributacao_pis"),
            "perc_valor_pis": float(r.get("perc_valor_pis") or 0),
            "tributacao_cofins": r.get("tributacao_cofins"),
            "perc_valor_cofins": float(r.get("perc_valor_cofins") or 0),
            "acatar_nfe": bool(r.get("Acatar_nfe")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_cfop_pis_cofins_sync(
    servidor: str, banco: str, cod_auto: Optional[int], cfop: str, grupo_pis_cofins: int,
    tributacao_qtd: bool, tributacao_pis: Optional[int], perc_valor_pis: float,
    tributacao_cofins: Optional[int], perc_valor_cofins: float, acatar_nfe: bool,
) -> dict:
    cfop_v = (cfop or "").strip()
    if not cfop_v:
        return {"success": False, "message": "Informe o CFOP."}
    if not grupo_pis_cofins:
        return {"success": False, "message": "Informe o grupo de Pis/Cofins."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cfops WHERE cfop=%s", (cfop_v,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "CFOP não cadastrado."}
        cur.execute("SELECT TOP 1 1 AS ok FROM grupo_pis_cofins WHERE TRY_CAST(cod_grupo AS INT)=%s", (grupo_pis_cofins,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Grupo de Pis/Cofins não cadastrado."}
        if tributacao_pis is not None:
            cur.execute("SELECT TOP 1 1 AS ok FROM cst_pis WHERE TRY_CAST(CST_Pis AS INT)=%s", (tributacao_pis,))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": "CST de Pis não cadastrado."}
        if tributacao_cofins is not None:
            cur.execute("SELECT TOP 1 1 AS ok FROM cst_cofins WHERE TRY_CAST(CST_Cofins AS INT)=%s", (tributacao_cofins,))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": "CST de Cofins não cadastrado."}

        vals = (
            1 if tributacao_qtd else 0,
            tributacao_pis if tributacao_pis is not None else 6, perc_valor_pis or 0,
            tributacao_cofins if tributacao_cofins is not None else 6, perc_valor_cofins or 0,
            1 if acatar_nfe else 0,
        )
        if cod_auto:  # edição de linha já carregada — atualiza direto por PK
            cur.execute(
                "UPDATE cfop_pis_cofins SET CFOP=%s, grupo_pis_cofins=%s, tributacao_qtd=%s, "
                "tributacao_pis=%s, perc_valor_pis=%s, tributacao_cofins=%s, perc_valor_cofins=%s, "
                "Acatar_nfe=%s WHERE Cod_Auto=%s",
                (cfop_v, grupo_pis_cofins) + vals + (cod_auto,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Registro não encontrado."}
            novo = cod_auto
        else:  # upsert-by-(cfop, grupo): mesmo comportamento do legado
            cur.execute(
                "SELECT Cod_Auto FROM cfop_pis_cofins WHERE CFOP=%s AND grupo_pis_cofins=%s",
                (cfop_v, grupo_pis_cofins),
            )
            existing = cur.fetchone()
            if existing:
                novo = int(existing["Cod_Auto"])
                cur.execute(
                    "UPDATE cfop_pis_cofins SET tributacao_qtd=%s, tributacao_pis=%s, perc_valor_pis=%s, "
                    "tributacao_cofins=%s, perc_valor_cofins=%s, Acatar_nfe=%s WHERE Cod_Auto=%s",
                    vals + (novo,),
                )
            else:
                cur.execute(
                    "INSERT INTO cfop_pis_cofins (CFOP, grupo_pis_cofins, tributacao_qtd, tributacao_pis, "
                    "perc_valor_pis, tributacao_cofins, perc_valor_cofins, Acatar_nfe) "
                    "OUTPUT INSERTED.Cod_Auto VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (cfop_v, grupo_pis_cofins) + vals,
                )
                row = cur.fetchone()
                novo = int(row["Cod_Auto"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "cod_auto": novo, "message": "Registro gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_cfop_pis_cofins_sync(servidor: str, banco: str, cod_auto: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM cfop_pis_cofins WHERE Cod_Auto=%s", (cod_auto,))
        if cur.rowcount == 0:
            conn.rollback()
            cur.close()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- FIPE (urllib, sem requests) ----------------
def _fipe_get(path: str) -> list:
    url = f"{FIPE_BASE}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "BackOn/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fipe_marcas_sync(tipo: str) -> dict:
    try:
        data = _fipe_get(f"{tipo}/marcas")
        items = [{"id": str(m.get("codigo")), "nome": m.get("nome")} for m in data]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Falha FIPE: {e}", "items": []}


def _fipe_modelos_sync(tipo: str, marca_id: str) -> dict:
    try:
        data = _fipe_get(f"{tipo}/marcas/{marca_id}/modelos")
        modelos = (data or {}).get("modelos", [])
        items = [{"id": str(m.get("codigo")), "nome": m.get("nome")} for m in modelos]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Falha FIPE: {e}", "items": []}


def _import_fipe_sync(servidor: str, banco: str, tipo: str, fipe_marca_id: str, descricao: str) -> dict:
    """Cria a marca (veículo, marca_produto=0) se não existir e importa TODOS os
    modelos da marca FIPE escolhida (ignorando duplicados por descrição)."""
    nome_marca = (descricao or "").strip()
    if not nome_marca:
        return {"success": False, "message": "Marca FIPE inválida."}
    fipe = _fipe_modelos_sync(tipo, fipe_marca_id)
    if not fipe.get("success"):
        return fipe
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        # marca (procura por descrição entre as de veículo)
        cur.execute("SELECT TOP 1 codigo FROM marcas WHERE descricao=%s AND ISNULL(marca_produto,0)=0", (nome_marca,))
        row = cur.fetchone()
        if row:
            cod_marca = (row.get("codigo") or "").strip()
        else:
            cod_marca = _next_codigo(cur, "marcas")
            cur.execute("INSERT INTO marcas (codigo, descricao, marca_produto) VALUES (%s,%s,0)", (cod_marca, nome_marca))
        # modelos existentes p/ evitar duplicar
        cur.execute("SELECT descricao FROM modelos WHERE cod_marca=%s", (cod_marca,))
        existentes = {(r.get("descricao") or "").strip().upper() for r in cur.fetchall()}
        novos = 0
        for m in fipe["items"]:
            nome = (m.get("nome") or "").strip()
            if not nome or nome.upper() in existentes:
                continue
            cod = _next_codigo(cur, "modelos")
            cur.execute("INSERT INTO modelos (codigo, cod_marca, descricao) VALUES (%s,%s,%s)", (cod, cod_marca, nome))
            existentes.add(nome.upper())
            novos += 1
        conn.commit()
        cur.close()
        return {"success": True, "cod_marca": cod_marca, "importados": novos,
                "message": f"Marca '{nome_marca}' importada · {novos} modelos."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao importar: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def list_marcas(servidor, banco, marca_produto, search):
    return await asyncio.to_thread(_list_marcas_sync, servidor, banco, marca_produto, search)


async def save_marca(servidor, banco, codigo, descricao, marca_produto):
    return await asyncio.to_thread(_save_marca_sync, servidor, banco, codigo, descricao, marca_produto)


async def delete_marca(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_marca_sync, servidor, banco, codigo)


async def list_area(servidor, banco, search):
    return await asyncio.to_thread(_list_area_sync, servidor, banco, search)


async def save_area(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_area_sync, servidor, banco, codigo, descricao)


async def delete_area(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_area_sync, servidor, banco, codigo)


async def list_area_atuacao_crud(servidor, banco, search):
    return await asyncio.to_thread(_list_area_atuacao_sync, servidor, banco, search)


async def save_area_atuacao(servidor, banco, codigo, descricao, centro_custo, tipo_mov, modelo_os, modelo_pedido, intermediador, intermediador_identificacao):
    return await asyncio.to_thread(
        _save_area_atuacao_sync, servidor, banco, codigo, descricao, centro_custo,
        tipo_mov, modelo_os, modelo_pedido, intermediador, intermediador_identificacao,
    )


async def delete_area_atuacao(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_area_atuacao_sync, servidor, banco, codigo)


async def list_modelos(servidor, banco, cod_marca, search):
    return await asyncio.to_thread(_list_modelos_sync, servidor, banco, cod_marca, search)


async def save_modelo(servidor, banco, codigo, cod_marca, descricao):
    return await asyncio.to_thread(_save_modelo_sync, servidor, banco, codigo, cod_marca, descricao)


async def delete_modelo(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_modelo_sync, servidor, banco, codigo)


async def list_funcoes(servidor, banco, search):
    return await asyncio.to_thread(_list_funcoes_sync, servidor, banco, search)


async def save_funcoes(
    servidor, banco, codigo, descricao,
    permite_altera_caixa, cancelar_os, alterar_tecnico_responsavel,
    funcao_vendedor, funcao_executor, funcao_atendente, libera_cliente_debito,
):
    return await asyncio.to_thread(
        _save_funcoes_sync, servidor, banco, codigo, descricao,
        permite_altera_caixa, cancelar_os, alterar_tecnico_responsavel,
        funcao_vendedor, funcao_executor, funcao_atendente, libera_cliente_debito,
    )


async def delete_funcoes(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_funcoes_sync, servidor, banco, codigo)


async def list_status_os(servidor, banco, search):
    return await asyncio.to_thread(_list_status_os_sync, servidor, banco, search)


async def save_status_os(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_status_os_sync, servidor, banco, codigo, descricao)


async def delete_status_os(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_status_os_sync, servidor, banco, codigo)


async def list_tipo_doc(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_doc_sync, servidor, banco, search)


async def save_tipo_doc(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_tipo_doc_sync, servidor, banco, codigo, descricao)


async def delete_tipo_doc(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_doc_sync, servidor, banco, codigo)


async def list_tipo_cliente(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_cliente_sync, servidor, banco, search)


async def save_tipo_cliente(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_tipo_cliente_sync, servidor, banco, codigo, descricao)


async def delete_tipo_cliente(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_cliente_sync, servidor, banco, codigo)


async def list_grupo_pis_cofins(servidor, banco, search):
    return await asyncio.to_thread(_list_grupo_pis_cofins_sync, servidor, banco, search)


async def save_grupo_pis_cofins(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_grupo_pis_cofins_sync, servidor, banco, codigo, descricao)


async def delete_grupo_pis_cofins(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_grupo_pis_cofins_sync, servidor, banco, codigo)


async def list_tamanho(servidor, banco, search):
    return await asyncio.to_thread(_list_tamanho_sync, servidor, banco, search)


async def save_tamanho(servidor, banco, codigo):
    return await asyncio.to_thread(_save_tamanho_sync, servidor, banco, codigo)


async def delete_tamanho(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tamanho_sync, servidor, banco, codigo)


async def list_situacao(servidor, banco, search):
    return await asyncio.to_thread(_list_situacao_sync, servidor, banco, search)


async def save_situacao(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_situacao_sync, servidor, banco, codigo, descricao)


async def delete_situacao(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_situacao_sync, servidor, banco, codigo)


async def list_segmentos(servidor, banco, search):
    return await asyncio.to_thread(_list_segmentos_sync, servidor, banco, search)


async def save_segmento(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_segmento_sync, servidor, banco, codigo, descricao)


async def delete_segmento(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_segmento_sync, servidor, banco, codigo)


async def list_rotas(servidor, banco, search):
    return await asyncio.to_thread(_list_rotas_sync, servidor, banco, search)


async def save_rota(servidor, banco, codigo, descricao, prioridade, codigo_regiao):
    return await asyncio.to_thread(_save_rota_sync, servidor, banco, codigo, descricao, prioridade, codigo_regiao)


async def delete_rota(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_rota_sync, servidor, banco, codigo)


async def list_regioes(servidor, banco, search):
    return await asyncio.to_thread(_list_regioes_sync, servidor, banco, search)


async def save_regiao(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_regiao_sync, servidor, banco, codigo, descricao)


async def delete_regiao(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_regiao_sync, servidor, banco, codigo)


async def list_origem(servidor, banco, search):
    return await asyncio.to_thread(_list_origem_sync, servidor, banco, search)


async def save_origem(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_origem_sync, servidor, banco, codigo, descricao)


async def delete_origem(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_origem_sync, servidor, banco, codigo)


async def list_icms(servidor, banco, search):
    return await asyncio.to_thread(_list_icms_sync, servidor, banco, search)


async def save_icms(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_icms_sync, servidor, banco, codigo, descricao)


async def delete_icms(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_icms_sync, servidor, banco, codigo)


async def list_cores(servidor, banco, search):
    return await asyncio.to_thread(_list_cores_sync, servidor, banco, search)


async def save_cor(servidor, banco, codigo, descricao, cor_fabrica):
    return await asyncio.to_thread(_save_cor_sync, servidor, banco, codigo, descricao, cor_fabrica)


async def delete_cor(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_cor_sync, servidor, banco, codigo)


async def list_niveis(servidor, banco):
    return await asyncio.to_thread(_list_niveis_sync, servidor, banco)


async def save_nivel(
    servidor, banco, cod_nivel, parent_cod_nivel, descricao, custo,
    classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida,
):
    return await asyncio.to_thread(
        _save_nivel_sync, servidor, banco, cod_nivel, parent_cod_nivel, descricao, custo,
        classe_entrada, sub_classe_entrada, classe_saida, sub_classe_saida,
    )


async def delete_nivel(servidor, banco, cod_nivel):
    return await asyncio.to_thread(_delete_nivel_sync, servidor, banco, cod_nivel)


async def list_grupos_usuario(servidor, banco, search):
    return await asyncio.to_thread(_list_grupos_usuario_sync, servidor, banco, search)


async def save_grupo_usuario(
    servidor, banco, codigo, descricao, exige_tipo_cliente, exige_canal_aquisicao_cliente,
    visualiza_pedido_aberto, visualiza_pedido_fechado, visualiza_pedido_cancelado, visualiza_pedido_faturado,
):
    return await asyncio.to_thread(
        _save_grupo_usuario_sync, servidor, banco, codigo, descricao,
        exige_tipo_cliente, exige_canal_aquisicao_cliente,
        visualiza_pedido_aberto, visualiza_pedido_fechado, visualiza_pedido_cancelado, visualiza_pedido_faturado,
    )


async def delete_grupo_usuario(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_grupo_usuario_sync, servidor, banco, codigo)


async def list_forma_pagamento(servidor, banco, search):
    return await asyncio.to_thread(_list_forma_pagamento_sync, servidor, banco, search)


async def save_forma_pagamento(req):
    return await asyncio.to_thread(_save_forma_pagamento_sync, req)


async def delete_forma_pagamento(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_forma_pagamento_sync, servidor, banco, codigo)


async def fipe_marcas(tipo):
    return await asyncio.to_thread(_fipe_marcas_sync, tipo)


async def fipe_modelos(tipo, marca_id):
    return await asyncio.to_thread(_fipe_modelos_sync, tipo, marca_id)


async def import_fipe(servidor, banco, tipo, fipe_marca_id, descricao):
    return await asyncio.to_thread(_import_fipe_sync, servidor, banco, tipo, fipe_marca_id, descricao)


async def list_cfop(servidor, banco, search):
    return await asyncio.to_thread(_list_cfop_sync, servidor, banco, search)


async def save_cfop(servidor, banco, codigo, descricao, descricao_nf, aplicacao, cod_contabil):
    return await asyncio.to_thread(
        _save_cfop_sync, servidor, banco, codigo, descricao, descricao_nf, aplicacao, cod_contabil,
    )


async def delete_cfop(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_cfop_sync, servidor, banco, codigo)


async def list_cfop_xml(servidor, banco):
    return await asyncio.to_thread(_list_cfop_xml_sync, servidor, banco)


async def save_cfop_xml(servidor, banco, cfop_xml, cfop):
    return await asyncio.to_thread(_save_cfop_xml_sync, servidor, banco, cfop_xml, cfop)


async def delete_cfop_xml(servidor, banco, cfop_xml):
    return await asyncio.to_thread(_delete_cfop_xml_sync, servidor, banco, cfop_xml)


async def list_cfop_pis_cofins(servidor, banco, search):
    return await asyncio.to_thread(_list_cfop_pis_cofins_sync, servidor, banco, search)


async def save_cfop_pis_cofins(
    servidor, banco, cod_auto, cfop, grupo_pis_cofins, tributacao_qtd,
    tributacao_pis, perc_valor_pis, tributacao_cofins, perc_valor_cofins, acatar_nfe,
):
    return await asyncio.to_thread(
        _save_cfop_pis_cofins_sync, servidor, banco, cod_auto, cfop, grupo_pis_cofins, tributacao_qtd,
        tributacao_pis, perc_valor_pis, tributacao_cofins, perc_valor_cofins, acatar_nfe,
    )


async def delete_cfop_pis_cofins(servidor, banco, cod_auto):
    return await asyncio.to_thread(_delete_cfop_pis_cofins_sync, servidor, banco, cod_auto)


# Mensagens(codigo int IDENTITY PK, descricao nvarchar(max)) — legado FrmManMsg
# ("Manutenção de Mensagens"). Textos padronizados usados em observação de nota
# fiscal/orçamento (ex.: enquadramento no Simples, base de cálculo reduzida).
# Sem tabela nenhuma referenciando `Mensagens` via FK ou coluna solta no banco
# de teste (INFORMATION_SCHEMA + sys.foreign_keys conferidos) — delete sem
# guard de dependência, mesmo padrão das demais tabelas simples desta tela.
def _list_mensagens_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM Mensagens {where} ORDER BY descricao", params)
        items = [
            {"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()}
            for r in cur.fetchall()
        ]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_mensagem_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if codigo:  # update
            cur.execute("UPDATE Mensagens SET descricao=%s WHERE codigo=%s", (desc, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Mensagem não encontrada."}
            novo = codigo
        else:  # create — codigo é IDENTITY
            cur.execute(
                "INSERT INTO Mensagens (descricao) OUTPUT INSERTED.codigo VALUES (%s)", (desc,),
            )
            row = cur.fetchone()
            novo = int(row["codigo"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Mensagem gravada."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_mensagem_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM Mensagens WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Mensagem não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Mensagem excluída."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()



# MensagensPDV(cod_mens int IDENTITY PK — irrelevante pro app, tabela é
# singleton de 1 linha só; linha1..linha5 nvarchar(48)) — legado FrmManMsgPDV
# ("Manutenção de Mensagens / PDV"). Só linha1/linha2/linha3 são editáveis na
# tela legada (linha4/linha5 ficam escondidas no .frm, Visible=False, e o
# legado sempre as regrava como string vazia) — reproduzido aqui só com as 3
# linhas visíveis; linha4/linha5 sempre gravadas vazias. Mesmo padrão
# "singleton, sem lista, INSERT se não existir/UPDATE sem WHERE se existir"
# de `controle_config_service.py` (Módulos e Recursos).
def _read_mensagens_pdv_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 linha1, linha2, linha3 FROM mensagenspdv")
        row = cur.fetchone() or {}
        cur.close()
        return {
            "success": True,
            "linha1": (row.get("linha1") or "").strip(),
            "linha2": (row.get("linha2") or "").strip(),
            "linha3": (row.get("linha3") or "").strip(),
        }
    finally:
        conn.close()


def _save_mensagens_pdv_sync(servidor: str, banco: str, linha1: str, linha2: str, linha3: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 cod_mens FROM mensagenspdv")
        existe = cur.fetchone()
        params = ((linha1 or "").strip(), (linha2 or "").strip(), (linha3 or "").strip())
        if existe:
            cur.execute(
                "UPDATE mensagenspdv SET linha1=%s, linha2=%s, linha3=%s, linha4='', linha5=''",
                params,
            )
        else:
            cur.execute(
                "INSERT INTO mensagenspdv (linha1, linha2, linha3, linha4, linha5) VALUES (%s,%s,%s,'','')",
                params,
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Mensagens do PDV gravadas."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


async def read_mensagens_pdv(servidor, banco):
    return await asyncio.to_thread(_read_mensagens_pdv_sync, servidor, banco)


async def save_mensagens_pdv(servidor, banco, linha1, linha2, linha3):
    return await asyncio.to_thread(_save_mensagens_pdv_sync, servidor, banco, linha1, linha2, linha3)


async def list_mensagens(servidor, banco, search):
    return await asyncio.to_thread(_list_mensagens_sync, servidor, banco, search)


async def save_mensagem(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_mensagem_sync, servidor, banco, codigo, descricao)


async def delete_mensagem(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_mensagem_sync, servidor, banco, codigo)


# Números de Série (tabela `pecas_num_serie`, PK própria `codigo` IDENTITY —
# `num_serie` é único GLOBALMENTE, não por produto, mesmo padrão do legado
# FrmManNDS: WHERE num_serie=... sem filtrar por codigo_int). Legado busca o
# produto em `pecas` tentando, em ordem, codigo_fab -> descricao -> codigo_int
# -> codigo_bar, e só aceita produtos com `controla_num_serie`=1.
#
# Guard de exclusão (replica o legado, que faz esse check manualmente em VB6
# — só `comanda_num_serie` tem FK real no banco, `n_fiscal_num_serie` é FK
# solta, então o guard aqui é obrigatório nos dois, não só no que tem FK):
#   • bloqueia se pertence a uma Comanda com situacao='PG' (paga)
#   • bloqueia se pertence a uma Nota Fiscal com situacao='A' (ativa)
#
# Desvio proposital do legado: `Command1_Click` (Gravar) só atualiza
# `disponivel` quando o número de série já existe — a edição de `Detalhes` no
# textbox é descartada silenciosamente nesse caso (parece bug, não regra de
# negócio: o campo é editável e recarregado do banco ao digitar um número
# existente). Aqui o GRAVAR atualiza `disponivel` E `detalhes` também no
# update — comportamento mais correto e não deveria surpreender ninguém.
def _buscar_produtos_num_serie_sync(servidor: str, banco: str, termo: str) -> dict:
    """Lista produtos com controla_num_serie=1 pro seletor de Produto da tela —
    diferente de `_resolve_produto_num_serie_sync` (que resolve um único
    produto por match exato, usado na tela legada de digitação livre)."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        t = (termo or "").strip()
        where = "WHERE controla_num_serie=1"
        params: tuple = ()
        if t:
            where += " AND (codigo_int LIKE %s OR codigo_fab LIKE %s OR descricao LIKE %s OR codigo_bar LIKE %s)"
            like = f"%{t}%"
            params = (like, like, like, like)
        cur.execute(f"SELECT TOP 50 codigo_int, codigo_fab, descricao FROM pecas {where} ORDER BY descricao", params)
        items = [{
            "codigo_int": (r.get("codigo_int") or "").strip(),
            "codigo_fab": (r.get("codigo_fab") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _resolve_produto_num_serie_sync(servidor: str, banco: str, termo: str) -> dict:
    termo = (termo or "").strip()
    if not termo:
        return {"success": False, "message": "Informe o produto."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        row = None
        for campo in ("codigo_fab", "descricao", "codigo_int", "codigo_bar"):
            cur.execute(
                f"SELECT TOP 1 codigo_int, codigo_fab, descricao, controla_num_serie "
                f"FROM pecas WHERE {campo}=%s", (termo,),
            )
            row = cur.fetchone()
            if row:
                break
        if not row:
            return {"success": False, "message": "Produto não cadastrado."}
        if not row.get("controla_num_serie"):
            return {"success": False, "message": "Este produto não controla Números de Série."}
        return {
            "success": True,
            "codigo_int": (row.get("codigo_int") or "").strip(),
            "codigo_fab": (row.get("codigo_fab") or "").strip(),
            "descricao": (row.get("descricao") or "").strip(),
        }
    finally:
        conn.close()


def _list_num_serie_sync(servidor: str, banco: str, codigo_int: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo, num_serie, disponivel, detalhes FROM pecas_num_serie "
            "WHERE codigo_int=%s ORDER BY disponivel DESC, num_serie",
            (codigo_int,),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "num_serie": (r.get("num_serie") or "").strip(),
            "disponivel": bool(r.get("disponivel")),
            "detalhes": (r.get("detalhes") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _buscar_num_serie_sync(servidor: str, banco: str, num_serie: str) -> dict:
    num_serie = (num_serie or "").strip()
    if not num_serie:
        return {"success": False, "encontrado": False}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT ns.codigo, ns.codigo_int, ns.num_serie, ns.disponivel, ns.detalhes, "
            "       p.codigo_fab, p.descricao "
            "FROM pecas_num_serie ns LEFT JOIN pecas p ON p.codigo_int = ns.codigo_int "
            "WHERE ns.num_serie=%s",
            (num_serie,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": True, "encontrado": False}
        return {
            "success": True,
            "encontrado": True,
            "codigo_int": (row.get("codigo_int") or "").strip(),
            "codigo_fab": (row.get("codigo_fab") or "").strip(),
            "descricao": (row.get("descricao") or "").strip(),
            "disponivel": bool(row.get("disponivel")),
            "detalhes": (row.get("detalhes") or "").strip(),
        }
    finally:
        conn.close()


def _save_num_serie_sync(
    servidor: str, banco: str, codigo_int: str, num_serie: str, disponivel: bool, detalhes: str,
) -> dict:
    codigo_int = (codigo_int or "").strip()
    num_serie = (num_serie or "").strip()
    if not codigo_int:
        return {"success": False, "message": "Defina o produto."}
    if not num_serie:
        return {"success": False, "message": "Defina o número de série."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM pecas_num_serie WHERE num_serie=%s", (num_serie,))
        existe = cur.fetchone()
        if existe:
            cur.execute(
                "UPDATE pecas_num_serie SET disponivel=%s, detalhes=%s WHERE num_serie=%s",
                (1 if disponivel else 0, detalhes or "", num_serie),
            )
        else:
            cur.execute(
                "INSERT INTO pecas_num_serie (codigo_int, num_serie, disponivel, detalhes) VALUES (%s,%s,%s,%s)",
                (codigo_int, num_serie, 1 if disponivel else 0, detalhes or ""),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro gravado."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_num_serie_sync(servidor: str, banco: str, num_serie: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM pecas_num_serie WHERE num_serie=%s", (num_serie,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Registro inexistente."}
        interno = int(row["codigo"])
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM comanda c JOIN comanda_num_serie cns ON c.comanda = cns.comanda "
            "WHERE c.situacao = 'PG' AND cns.num_serie = %s",
            (interno,),
        )
        if cur.fetchone():
            return {"success": False, "message": "Registro não pode ser excluído — pertence a uma Comanda."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM n_fiscal nf JOIN n_fiscal_num_serie nfns ON nf.codigo = nfns.n_fiscal "
            "WHERE nf.situacao = 'A' AND nfns.num_serie = %s",
            (interno,),
        )
        if cur.fetchone():
            return {"success": False, "message": "Registro não pode ser excluído — pertence a uma Nota Fiscal de Entrada ou Saída."}
        cur.execute("DELETE FROM pecas_num_serie WHERE num_serie=%s", (num_serie,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def resolve_produto_num_serie(servidor, banco, termo):
    return await asyncio.to_thread(_resolve_produto_num_serie_sync, servidor, banco, termo)


async def buscar_produtos_num_serie(servidor, banco, termo):
    return await asyncio.to_thread(_buscar_produtos_num_serie_sync, servidor, banco, termo)


async def list_num_serie(servidor, banco, codigo_int):
    return await asyncio.to_thread(_list_num_serie_sync, servidor, banco, codigo_int)


async def buscar_num_serie(servidor, banco, num_serie):
    return await asyncio.to_thread(_buscar_num_serie_sync, servidor, banco, num_serie)


async def save_num_serie(servidor, banco, codigo_int, num_serie, disponivel, detalhes):
    return await asyncio.to_thread(_save_num_serie_sync, servidor, banco, codigo_int, num_serie, disponivel, detalhes)


async def delete_num_serie(servidor, banco, num_serie):
    return await asyncio.to_thread(_delete_num_serie_sync, servidor, banco, num_serie)


# ---------------- TIPO DE MOVIMENTAÇÃO ----------------
# tipo_mov(codigo nvarchar(3) PK — "E"/"S" + sequência de 2 dígitos, ex. E15/
#   S20 — descricao, descricao_nf, origem_destino ("C"=Cliente/"F"=Fornecedor),
#   atualiza_est/transf_livro/transf_pagar/transf_contabil/transf_caixa/itens/
#   situacao são nvarchar(1) "S"/"N" — NÃO bit, mesmo padrão VB6 legado, mas
#   API/frontend expõem como bool — cod_contabil_* int, tipo_mov_contra_partida/
#   tipo_mov_origem nvarchar(3) FK solta pra própria tipo_mov, cfop/cfop_fora
#   nvarchar(4) FK pra `cfops`, tipo_doc smallint FK pra `tipo_doc`, centro_custo
#   int FK pra `centro_custo`, tipo_nf smallint índice de `tipo_nf` (+ 2 itens
#   fixos "Devolução Recebimento"/"NFe Complementar" que o legado sempre
#   concatena, sem estarem na tabela), estoque_atual/estoque_cliente/
#   estoque_fornecedor/altera_custo/altera_venda/emite_ecf são bit de verdade,
#   CODIGO_DANFE smallint — sem lookup próprio conhecido (a lista real do
#   combo do legado está no .frx binário, não no .frm texto; exposto aqui como
#   campo numérico simples).
#
# Legado: FrmManTip ("Cadastro de Tipos de Movimentação"). Regras de negócio
# replicadas fielmente (validadas contra o código VB6, não deduzidas):
#   • Códigos com sufixo numérico 00-07 são reservados do sistema: NUNCA podem
#     ser criados (nem pelo master); só podem ser ALTERADOS pelo usuário master.
#   • Exclusão só permitida com sufixo > 14 (faixa protegida MAIS ampla que a
#     de criação/alteração — 08-14 pode ser alterado mas não excluído).
#   • `atualiza_est` é imutável após criado (o legado bloqueia qualquer
#     mudança nesse campo, mesmo que a mensagem fale em "já foi movimentado" —
#     não há checagem real de movimentação, é trava incondicional).
#   • Mudar `origem_destino` só é bloqueado se já existir `n_fiscal` com
#     `mov`=este código (aí sim é uma checagem real).
#   • `tipo_doc`, `cfop` e `cfop_fora` precisam existir nas tabelas
#     respectivas — senão a gravação é rejeitada.
#   • `tipo_mov_contra_partida` e `prazo_contra_partida` são "tudo ou nada"
#     (um exige o outro) e mutuamente exclusivos com `tipo_mov_origem`.
#   • Guard de exclusão (3 tabelas, igual ao legado): bloqueia se houver
#     `movimentacao.tipo`, `n_fiscal.mov` (com situacao<>'C') ou `nf_aux.mov`
#     apontando pro código.
# Não replicado: `Pos_Sistema` (checagem de "caixa aberto"/PDV do legado —
# sem conceito equivalente neste app ainda) e a gravação na tabela `Logs`
# legada no exclui (usa `log_auditoria` novo em vez disso, política já
# estabelecida nesta sessão pra toda tela nova).
def _list_tipo_mov_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM tipo_mov {where} ORDER BY codigo", params)
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "natureza": "E" if (r.get("codigo") or "").strip().upper().startswith("E") else "S",
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _norm_bool_sn(v) -> bool:
    return (v or "").strip().upper() == "S"


def _get_tipo_mov_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM tipo_mov WHERE codigo=%s", ((codigo or "").strip().upper(),))
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": False, "message": "Tipo de movimentação não encontrado."}
        return {
            "success": True,
            "tipo_mov": {
                "codigo": (row.get("codigo") or "").strip(),
                "descricao": (row.get("descricao") or "").strip(),
                "descricao_nf": (row.get("descricao_nf") or "").strip(),
                "origem_destino": (row.get("origem_destino") or "").strip().upper(),
                "atualiza_est": _norm_bool_sn(row.get("atualiza_est")),
                "transf_livro": _norm_bool_sn(row.get("transf_livro")),
                "transf_pagar": _norm_bool_sn(row.get("transf_pagar")),
                "transf_contabil": _norm_bool_sn(row.get("transf_contabil")),
                "transf_caixa": _norm_bool_sn(row.get("transf_caixa")),
                "cod_contabil_livro": row.get("cod_contabil_livro"),
                "cod_contabil_pag": row.get("cod_contabil_pag"),
                "cod_contabil_juros": row.get("cod_contabil_juros"),
                "cod_contabil_descontos": row.get("cod_contabil_descontos"),
                "cod_contabil_acrescimos": row.get("cod_contabil_acrescimos"),
                "tipo_mov_contra_partida": (row.get("tipo_mov_contra_partida") or "").strip() or None,
                "prazo_contra_partida": row.get("prazo_contra_partida"),
                "tipo_mov_origem": (row.get("tipo_mov_origem") or "").strip() or None,
                "cfop": (row.get("cfop") or "").strip(),
                "cfop_fora": (row.get("cfop_fora") or "").strip(),
                "tipo_doc": row.get("tipo_doc"),
                "itens": _norm_bool_sn(row.get("itens")),
                "centro_custo": row.get("centro_custo") or None,
                "tipo_nf": row.get("tipo_nf"),
                "estoque_atual": bool(row.get("estoque_atual")),
                "estoque_cliente": bool(row.get("estoque_cliente")),
                "estoque_fornecedor": bool(row.get("estoque_fornecedor")),
                "altera_custo": bool(row.get("altera_custo")),
                "altera_venda": bool(row.get("altera_venda")),
                "emite_ecf": bool(row.get("emite_ecf")),
                "situacao": (row.get("situacao") or "").strip() or None,
                "codigo_danfe": row.get("CODIGO_DANFE") or 0,
            },
        }
    finally:
        conn.close()


def _proximo_codigo_tipo_mov_sync(servidor: str, banco: str, natureza: str) -> dict:
    nat = (natureza or "").strip().upper()
    if nat not in ("E", "S"):
        return {"success": False, "message": "Natureza inválida."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT MAX(CAST(SUBSTRING(codigo,2,2) AS INT)) AS ultimo FROM tipo_mov WHERE LEFT(codigo,1)=%s",
            (nat,),
        )
        row = cur.fetchone() or {}
        ultimo = row.get("ultimo")
        novo = (int(ultimo) if ultimo is not None else 0) + 1
        cur.close()
        return {"success": True, "codigo": f"{nat}{novo:02d}"}
    finally:
        conn.close()


def _list_tipo_nf_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, descricao FROM tipo_nf ORDER BY codigo")
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        if not items:
            items = [
                {"codigo": 0, "descricao": "Compra"}, {"codigo": 1, "descricao": "Venda"},
                {"codigo": 2, "descricao": "Devolução"}, {"codigo": 3, "descricao": "Oficina"},
                {"codigo": 4, "descricao": "Consignação"}, {"codigo": 5, "descricao": "Outras"},
            ]
        proximo = max((i["codigo"] for i in items), default=-1) + 1
        items.append({"codigo": proximo, "descricao": "Devolução Recebimento"})
        items.append({"codigo": proximo + 1, "descricao": "NFe Complementar"})
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_mov_sync(servidor: str, banco: str, dados: dict, is_master: bool) -> dict:
    cod = (dados.get("codigo") or "").strip().upper()
    desc = (dados.get("descricao") or "").strip()
    origem_destino = (dados.get("origem_destino") or "").strip().upper()
    tipo_mov_contra_partida = (dados.get("tipo_mov_contra_partida") or "").strip().upper() or None
    tipo_mov_origem = (dados.get("tipo_mov_origem") or "").strip().upper() or None
    prazo_contra_partida = dados.get("prazo_contra_partida")
    cfop = (dados.get("cfop") or "").strip()
    cfop_fora = (dados.get("cfop_fora") or "").strip()
    tipo_doc = dados.get("tipo_doc")

    if len(cod) < 2 or cod[0] not in ("E", "S") or not cod[1:].isdigit():
        return {"success": False, "message": "Código inválido — deve ser E ou S seguido de 2 dígitos."}
    if not desc:
        return {"success": False, "message": "O campo Descrição deve estar preenchido."}
    if origem_destino not in ("C", "F"):
        return {"success": False, "message": "Selecione Origem/Destino corretamente."}
    for label, val in (
        ("Livro", dados.get("cod_contabil_livro")), ("Pagamento", dados.get("cod_contabil_pag")),
        ("Juros", dados.get("cod_contabil_juros")), ("Descontos", dados.get("cod_contabil_descontos")),
        ("Acréscimos", dados.get("cod_contabil_acrescimos")),
    ):
        if val is not None and int(val) > 32000:
            return {"success": False, "message": f"Código Contábil {label} máximo é 32000."}
    if tipo_mov_contra_partida and not prazo_contra_partida:
        return {"success": False, "message": f"Preencha o Prazo para a Movimentação Contra Partida '{tipo_mov_contra_partida}'."}
    if prazo_contra_partida and not tipo_mov_contra_partida:
        return {"success": False, "message": "Preencha a Movimentação Contra Partida para o Prazo informado."}
    if prazo_contra_partida and int(prazo_contra_partida) > 365:
        return {"success": False, "message": "O prazo máximo é de 365 dias."}
    if tipo_mov_contra_partida and tipo_mov_origem:
        return {"success": False, "message": "Movimentação de Contra Partida e Movimentação de Origem não podem coexistir."}
    if not tipo_doc:
        return {"success": False, "message": "Tipo de Documento inválido."}
    if not cfop:
        return {"success": False, "message": "Cfop dentro do estado não cadastrado."}
    if not cfop_fora:
        return {"success": False, "message": "Cfop fora do estado não cadastrado."}

    suffix = int(cod[1:3])
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM tipo_mov WHERE codigo=%s", (cod,))
        existente = cur.fetchone()

        if not existente and 0 <= suffix <= 7:
            return {"success": False, "message": "Códigos 00 a 07 são reservados pelo sistema e não podem ser criados."}
        if existente and 0 <= suffix <= 7 and not is_master:
            return {"success": False, "message": "Códigos 00 a 07 são reservados pelo sistema — só o usuário master pode alterá-los."}

        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_doc WHERE codigo=%s", (tipo_doc,))
        if not cur.fetchone():
            return {"success": False, "message": "Tipo de Documento inválido."}
        cur.execute("SELECT TOP 1 1 AS ok FROM cfops WHERE cfop=%s", (cfop,))
        if not cur.fetchone():
            return {"success": False, "message": "Cfop dentro do estado não cadastrado."}
        cur.execute("SELECT TOP 1 1 AS ok FROM cfops WHERE cfop=%s", (cfop_fora,))
        if not cur.fetchone():
            return {"success": False, "message": "Cfop fora do estado não cadastrado."}

        atualiza_v = "S" if dados.get("atualiza_est") else "N"
        if existente and (existente.get("atualiza_est") or "").strip().upper() != atualiza_v:
            return {"success": False, "message": "Não é permitido alterar o campo Atualiza Estoque — este registro já foi movimentado."}
        if existente:
            existing_od = (existente.get("origem_destino") or "").strip().upper()
            if existing_od != origem_destino:
                cur.execute("SELECT TOP 1 1 AS ok FROM n_fiscal WHERE mov=%s", (cod,))
                if cur.fetchone():
                    return {"success": False, "message": "Não é permitido alterar Origem/Destino — esta movimentação já possui notas emitidas."}

        params = (
            desc[:60], (dados.get("descricao_nf") or "")[:25], origem_destino, atualiza_v,
            "S" if dados.get("transf_livro") else "N", "S" if dados.get("transf_pagar") else "N",
            "S" if dados.get("transf_contabil") else "N", "S" if dados.get("transf_caixa") else "N",
            dados.get("cod_contabil_livro"), dados.get("cod_contabil_pag"), dados.get("cod_contabil_juros"),
            dados.get("cod_contabil_descontos"), dados.get("cod_contabil_acrescimos"),
            tipo_mov_contra_partida, prazo_contra_partida if tipo_mov_contra_partida else 0, tipo_mov_origem,
            cfop[:4], cfop_fora[:4], tipo_doc, "S" if dados.get("itens") else "N",
            dados.get("centro_custo") or 0, dados.get("tipo_nf"),
            1 if dados.get("estoque_atual") else 0, 1 if dados.get("estoque_cliente") else 0,
            1 if dados.get("estoque_fornecedor") else 0, 1 if dados.get("altera_custo") else 0,
            1 if dados.get("altera_venda") else 0, 1 if dados.get("emite_ecf") else 0,
            ((dados.get("situacao") or "").strip()[:1] or None), dados.get("codigo_danfe") or 0,
        )
        if existente:
            cur.execute(
                "UPDATE tipo_mov SET descricao=%s, descricao_nf=%s, origem_destino=%s, atualiza_est=%s, "
                "transf_livro=%s, transf_pagar=%s, transf_contabil=%s, transf_caixa=%s, "
                "cod_contabil_livro=%s, cod_contabil_pag=%s, cod_contabil_juros=%s, cod_contabil_descontos=%s, cod_contabil_acrescimos=%s, "
                "tipo_mov_contra_partida=%s, prazo_contra_partida=%s, tipo_mov_origem=%s, "
                "cfop=%s, cfop_fora=%s, tipo_doc=%s, itens=%s, centro_custo=%s, tipo_nf=%s, "
                "estoque_atual=%s, estoque_cliente=%s, estoque_fornecedor=%s, altera_custo=%s, altera_venda=%s, "
                "emite_ecf=%s, situacao=%s, CODIGO_DANFE=%s WHERE codigo=%s",
                params + (cod,),
            )
        else:
            cur.execute(
                "INSERT INTO tipo_mov (codigo, descricao, descricao_nf, origem_destino, atualiza_est, "
                "transf_livro, transf_pagar, transf_contabil, transf_caixa, "
                "cod_contabil_livro, cod_contabil_pag, cod_contabil_juros, cod_contabil_descontos, cod_contabil_acrescimos, "
                "tipo_mov_contra_partida, prazo_contra_partida, tipo_mov_origem, "
                "cfop, cfop_fora, tipo_doc, itens, centro_custo, tipo_nf, "
                "estoque_atual, estoque_cliente, estoque_fornecedor, altera_custo, altera_venda, "
                "emite_ecf, situacao, CODIGO_DANFE) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cod,) + params,
            )
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod, "message": "Registro gravado."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_mov_sync(servidor: str, banco: str, codigo: str) -> dict:
    cod = (codigo or "").strip().upper()
    if len(cod) < 2 or not cod[1:].isdigit():
        return {"success": False, "message": "Código inválido."}
    suffix = int(cod[1:3])
    if suffix <= 14:
        return {"success": False, "message": "Registro protegido contra exclusão."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_mov WHERE codigo=%s", (cod,))
        if not cur.fetchone():
            return {"success": False, "message": "Tipo de movimentação não encontrado."}
        cur.execute("SELECT TOP 1 1 AS ok FROM movimentacao WHERE tipo=%s", (cod,))
        if cur.fetchone():
            return {"success": False, "message": "Existem movimentações com o tipo escolhido — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM n_fiscal WHERE mov=%s AND situacao<>'C'", (cod,))
        if cur.fetchone():
            return {"success": False, "message": "Existem notas fiscais com o tipo escolhido — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM nf_aux WHERE mov=%s", (cod,))
        if cur.fetchone():
            return {"success": False, "message": "Existem notas fiscais com o tipo escolhido — não pode ser excluído."}
        cur.execute("DELETE FROM tipo_mov WHERE codigo=%s", (cod,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tipo_mov(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_mov_sync, servidor, banco, search)


async def get_tipo_mov(servidor, banco, codigo):
    return await asyncio.to_thread(_get_tipo_mov_sync, servidor, banco, codigo)


async def proximo_codigo_tipo_mov(servidor, banco, natureza):
    return await asyncio.to_thread(_proximo_codigo_tipo_mov_sync, servidor, banco, natureza)


async def list_tipo_nf(servidor, banco):
    return await asyncio.to_thread(_list_tipo_nf_sync, servidor, banco)


async def save_tipo_mov(servidor, banco, dados, is_master):
    return await asyncio.to_thread(_save_tipo_mov_sync, servidor, banco, dados, is_master)


async def delete_tipo_mov(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_mov_sync, servidor, banco, codigo)


# ---------------- TIPO MOV x MENSAGENS ----------------
# tipo_msg(mov nvarchar(3), msg int) — tabela de relacionamento N:N entre
# `tipo_mov` e `Mensagens` (sem PK própria, sem FK no banco). Legado:
# FrmTipMsg ("Relacionamento Tipo Movimetação X Mensagens"), duas listas
# (Possíveis/Cadastrados) com transferência via >, >>, <, <<. Sem guard de
# dependência — é puramente uma tabela de junção, nada mais referencia ela.
def _list_tipo_msg_sync(servidor: str, banco: str, mov: str) -> dict:
    m = (mov or "").strip().upper()
    if not m:
        return {"success": False, "message": "Selecione o Tipo de Movimentação.", "disponiveis": [], "vinculados": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT ms.codigo, ms.descricao, "
            "CASE WHEN tm.msg IS NOT NULL THEN 1 ELSE 0 END AS vinculada "
            "FROM Mensagens ms LEFT JOIN tipo_msg tm ON tm.msg = ms.codigo AND tm.mov = %s "
            "ORDER BY ms.descricao",
            (m,),
        )
        disponiveis, vinculados = [], []
        for r in cur.fetchall():
            item = {"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()}
            (vinculados if r.get("vinculada") else disponiveis).append(item)
        cur.close()
        return {"success": True, "disponiveis": disponiveis, "vinculados": vinculados}
    finally:
        conn.close()


def _vincular_tipo_msg_sync(servidor: str, banco: str, mov: str, mensagens: list) -> dict:
    m = (mov or "").strip().upper()
    if not m:
        return {"success": False, "message": "Selecione o Tipo de Movimentação."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        for msg in mensagens:
            cur.execute("SELECT TOP 1 1 AS ok FROM tipo_msg WHERE mov=%s AND msg=%s", (m, msg))
            if not cur.fetchone():
                cur.execute("INSERT INTO tipo_msg (mov, msg) VALUES (%s,%s)", (m, msg))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Mensagem(ns) vinculada(s)."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao vincular: {e}"}
    finally:
        conn.close()


def _desvincular_tipo_msg_sync(servidor: str, banco: str, mov: str, mensagens: list) -> dict:
    m = (mov or "").strip().upper()
    if not m:
        return {"success": False, "message": "Selecione o Tipo de Movimentação."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        for msg in mensagens:
            cur.execute("DELETE FROM tipo_msg WHERE mov=%s AND msg=%s", (m, msg))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Mensagem(ns) desvinculada(s)."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao desvincular: {e}"}
    finally:
        conn.close()


def _vincular_todos_tipo_msg_sync(servidor: str, banco: str, mov: str) -> dict:
    m = (mov or "").strip().upper()
    if not m:
        return {"success": False, "message": "Selecione o Tipo de Movimentação."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM tipo_msg WHERE mov=%s", (m,))
        cur.execute("SELECT codigo FROM Mensagens")
        codigos = [r["codigo"] for r in cur.fetchall()]
        for cod in codigos:
            cur.execute("INSERT INTO tipo_msg (mov, msg) VALUES (%s,%s)", (m, cod))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Todas as mensagens vinculadas."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao vincular: {e}"}
    finally:
        conn.close()


def _desvincular_todos_tipo_msg_sync(servidor: str, banco: str, mov: str) -> dict:
    m = (mov or "").strip().upper()
    if not m:
        return {"success": False, "message": "Selecione o Tipo de Movimentação."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM tipo_msg WHERE mov=%s", (m,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Todas as mensagens desvinculadas."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao desvincular: {e}"}
    finally:
        conn.close()


async def list_tipo_msg(servidor, banco, mov):
    return await asyncio.to_thread(_list_tipo_msg_sync, servidor, banco, mov)


async def vincular_tipo_msg(servidor, banco, mov, mensagens):
    return await asyncio.to_thread(_vincular_tipo_msg_sync, servidor, banco, mov, mensagens)


async def desvincular_tipo_msg(servidor, banco, mov, mensagens):
    return await asyncio.to_thread(_desvincular_tipo_msg_sync, servidor, banco, mov, mensagens)


async def vincular_todos_tipo_msg(servidor, banco, mov):
    return await asyncio.to_thread(_vincular_todos_tipo_msg_sync, servidor, banco, mov)


async def desvincular_todos_tipo_msg(servidor, banco, mov):
    return await asyncio.to_thread(_desvincular_todos_tipo_msg_sync, servidor, banco, mov)


# ---------------- TIPO DE PRÉ-VENDA ----------------
# tipo_os(codigo smallint NOT NULL — digitado pelo usuário, NÃO auto-gerado —,
#   descricao nvarchar(160)). Legado: FrmManTipoOS ("Tipos de O.S."), campo
#   "Tipo" — upsert-by-codigo, mesmo padrão de Situação/Icms/Origem/Status de
#   O.S. (já corrigido nesta sessão — ver correção retroativa de status_os
#   logo abaixo neste arquivo).
#
# Renomeado nesta tela pra "Tipo de Pré-Venda" (pedido do usuário) porque
# `tipo_os.codigo` tem FK real de DUAS tabelas, não só `os`:
#   FK_os_tipo_os (os.tipo) e FK_pedido_venda_tipo_os (pedido_venda.tipo) —
#   confirmado via sys.foreign_keys. Ou seja, apesar do nome legado "Tipos de
#   O.S.", esse cadastro classifica o TIPO tanto de Pedidos quanto de O.S.
#   (ambos são o fluxo de "pré-venda" deste app) — daí o nome novo bater
#   melhor com o uso real. Delete guard checa as DUAS tabelas.
def _list_tipo_os_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM tipo_os {where} ORDER BY descricao", params)
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_os_sync(servidor: str, banco: str, codigo: int, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not codigo and codigo != 0:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        desc_v = desc[:160]
        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_os WHERE codigo=%s", (codigo,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário (campo "Tipo" no legado)
            cur.execute("UPDATE tipo_os SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
        else:
            cur.execute("INSERT INTO tipo_os (codigo, descricao) VALUES (%s,%s)", (codigo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": codigo, "message": "Tipo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_os_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE tipo=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a O.S. — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM pedido_venda WHERE tipo=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a Pedido — não pode ser excluído."}
        cur.execute("DELETE FROM tipo_os WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Tipo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tipo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tipo_os(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_os_sync, servidor, banco, search)


async def save_tipo_os(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_tipo_os_sync, servidor, banco, codigo, descricao)


async def delete_tipo_os(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_os_sync, servidor, banco, codigo)


# ---------------- EXECUTOR PADRÃO (por nível de produto/serviço) ----------------
# executor_padrao(nivel1..nivel5 nvarchar(3) NOT NULL, executor int NULL) — PK
# composta pelos 5 níveis (mesmo caminho materializado de `niveis`, reaproveita
# a mesma árvore/endpoint de Grupo Mercadológico). `executor` = 0 (ou NULL)
# significa "nenhum executor padrão definido" (sentinel do legado, replicado
# aqui). Legado FrmExePad ("Executor Padrão...") usava NULL nos níveis em
# branco, mas a coluna é NOT NULL — aqui usa-se string vazia "", mesmo padrão
# já usado pela própria tabela `niveis` (nível 4/5 vazios em produtos com
# menos de 5 níveis de profundidade).
#
# Ainda não consumido por nenhuma tela deste app (o objetivo futuro,
# confirmado pelo usuário: a tela de O.S. vai usar isso pra sugerir
# executor(es) ao selecionar um produto/serviço desse nível) — por isso não
# há guard de dependência no excluir, nada ainda referencia esta tabela.
def _get_executor_padrao_sync(servidor: str, banco: str, n1: str, n2: str, n3: str, n4: str, n5: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT ep.executor, f.nome_guerra FROM executor_padrao ep "
            "LEFT JOIN funcionarios f ON f.codigo_int = ep.executor "
            "WHERE ep.nivel1=%s AND ep.nivel2=%s AND ep.nivel3=%s AND ep.nivel4=%s AND ep.nivel5=%s",
            (n1, n2, n3, n4, n5),
        )
        row = cur.fetchone()
        cur.close()
        if not row or not row.get("executor"):
            return {"success": True, "executor": None, "executor_nome": None}
        return {"success": True, "executor": int(row["executor"]), "executor_nome": (row.get("nome_guerra") or "").strip() or None}
    finally:
        conn.close()


def _save_executor_padrao_sync(servidor: str, banco: str, n1: str, n2: str, n3: str, n4: str, n5: str, executor) -> dict:
    ep = int(executor) if executor else 0
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM executor_padrao WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4=%s AND nivel5=%s",
            (n1, n2, n3, n4, n5),
        )
        exists = cur.fetchone() is not None
        if exists:
            cur.execute(
                "UPDATE executor_padrao SET executor=%s WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4=%s AND nivel5=%s",
                (ep, n1, n2, n3, n4, n5),
            )
        else:
            cur.execute(
                "INSERT INTO executor_padrao (nivel1, nivel2, nivel3, nivel4, nivel5, executor) VALUES (%s,%s,%s,%s,%s,%s)",
                (n1, n2, n3, n4, n5, ep),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_executor_padrao_sync(servidor: str, banco: str, n1: str, n2: str, n3: str, n4: str, n5: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "DELETE FROM executor_padrao WHERE nivel1=%s AND nivel2=%s AND nivel3=%s AND nivel4=%s AND nivel5=%s",
            (n1, n2, n3, n4, n5),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def get_executor_padrao(servidor, banco, n1, n2, n3, n4, n5):
    return await asyncio.to_thread(_get_executor_padrao_sync, servidor, banco, n1, n2, n3, n4, n5)


async def save_executor_padrao(servidor, banco, n1, n2, n3, n4, n5, executor):
    return await asyncio.to_thread(_save_executor_padrao_sync, servidor, banco, n1, n2, n3, n4, n5, executor)


async def delete_executor_padrao(servidor, banco, n1, n2, n3, n4, n5):
    return await asyncio.to_thread(_delete_executor_padrao_sync, servidor, banco, n1, n2, n3, n4, n5)


# ---------------- TIPO DE PRODUTO ----------------
# Tipo_Peca(codigo int NOT NULL — digitado pelo usuário, NÃO auto-gerado —,
#   descricao nvarchar(30)). Legado: FrmManTipoProd ("Manutenção Tipo De
#   Produto"), campo "Tipo" — upsert-by-codigo, mesmo padrão de Situação/
#   Icms/Origem/Status de O.S./Tipo de Pré-Venda.
#
# Delete guard: `pecas.tipo_peca` tem FK real (`FK_pecas_tipo_peca`) — 426
# linhas reais no banco de teste. `pecaspreco`/`paf_pecas`/`veiculos.tipo_peca`
# são referências soltas (sem FK), vazias no banco de teste mas checadas do
# mesmo jeito por precaução (mesma convenção de guard completo já usada em
# Tipo de Movimentação/Tipo de Pré-Venda).
def _list_tipo_peca_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM Tipo_Peca {where} ORDER BY descricao", params)
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_peca_sync(servidor: str, banco: str, codigo: int, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not codigo and codigo != 0:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        desc_v = desc[:30]
        cur.execute("SELECT TOP 1 1 AS ok FROM Tipo_Peca WHERE codigo=%s", (codigo,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário (campo "Tipo" no legado)
            cur.execute("UPDATE Tipo_Peca SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
        else:
            cur.execute("INSERT INTO Tipo_Peca (codigo, descricao) VALUES (%s,%s)", (codigo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": codigo, "message": "Tipo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_peca_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM pecas WHERE tipo_peca=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a Produtos — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM pecaspreco WHERE tipo_peca=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a Preços de Produtos — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM paf_pecas WHERE tipo_peca=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a PAF — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM veiculos WHERE tipo_peca=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a Veículos — não pode ser excluído."}
        cur.execute("DELETE FROM Tipo_Peca WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Tipo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tipo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tipo_peca(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_peca_sync, servidor, banco, search)


async def save_tipo_peca(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_tipo_peca_sync, servidor, banco, codigo, descricao)


async def delete_tipo_peca(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_peca_sync, servidor, banco, codigo)


# ---------------- TIPO DE SERVIÇO ----------------
# tipo_servico(codigo smallint NOT NULL — digitado pelo usuário, NÃO
#   auto-gerado —, descricao nvarchar(20)). Legado: FrmManTipoServ
#   ("Manutenção Tipo De Serviços..."), campo "Tipo" — upsert-by-codigo,
#   mesmo padrão de Situação/Icms/Origem/Status de O.S./Tipo de Pré-Venda/
#   Tipo de Produto.
#
# Delete guard: sem FK real no banco, mas `servicos.tipo` é a referência de
# fato (mesmo tipo smallint, valores compatíveis — 0="Próprio"/1="Terceiro"
# confirmado contra o banco de teste) — checado por precaução.
def _list_tipo_servico_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM tipo_servico {where} ORDER BY descricao", params)
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_servico_sync(servidor: str, banco: str, codigo: int, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not codigo and codigo != 0:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        desc_v = desc[:20]
        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_servico WHERE codigo=%s", (codigo,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário (campo "Tipo" no legado)
            cur.execute("UPDATE tipo_servico SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
        else:
            cur.execute("INSERT INTO tipo_servico (codigo, descricao) VALUES (%s,%s)", (codigo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": codigo, "message": "Tipo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_servico_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM servicos WHERE tipo=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a Serviços — não pode ser excluído."}
        cur.execute("DELETE FROM tipo_servico WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Tipo não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tipo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tipo_servico(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_servico_sync, servidor, banco, search)


async def save_tipo_servico(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_tipo_servico_sync, servidor, banco, codigo, descricao)


async def delete_tipo_servico(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_servico_sync, servidor, banco, codigo)


# ---------------- TRIBUTAÇÃO ----------------
# Tributacao(codigo nvarchar(3) NOT NULL — digitado pelo usuário, códigos
#   CST/CSOSN de ICMS, ex. 00/10/101/102/... —, descricao nvarchar(80),
#   Aplicacao nvarchar(max), Regime_Tributario smallint DEFAULT 0). Legado:
#   FrmManTri ("Manutenção de Tributações"), campo "Código" — upsert-by-
#   codigo, mesmo padrão de Situação/Icms/Origem/Status de O.S./Tipo de
#   Pré-Venda/Tipo de Produto/Tipo de Serviço.
#
# Correção 2026-07-07 (bug do legado): `cmdGravar_Click` só grava `Descricao`
# — o campo "Aplicação" (Campo2, textarea visível e editável na tela, e
# mostrado na grid) NUNCA é persistido pelo Gravar do legado, só é lido na
# consulta por código. Isso tem cheiro de bug/funcionalidade incompleta, não
# regra de negócio (o campo existe, é editável, aparece na listagem — só não
# é salvo) — replicado aqui SALVANDO Aplicação também, mesma filosofia já
# aplicada em Números de Série (campo Detalhes). `Regime_Tributario` não tem
# controle nenhum na tela legada (nem Insert nem Update o define) — mantido
# assim aqui também (fica no DEFAULT 0 = "Normal" ao criar, nunca alterado
# por esta tela), só exibido na listagem via CASE.
#
# Delete guard: sem FK real no banco, mas 3 tabelas fiscais têm dados reais
# referenciando `tributacao` no banco de teste — `taxas` (6 linhas),
# `taxas_nfce` (2 linhas), `comanda_nfce_detalhe` (52 linhas). Há dezenas de
# outras colunas com nome parecido (paf_*, nf_*, n_fiscal_*) mas todas vazias
# no banco de teste e ligadas a emissão de NF-e/PAF-ECF — funcionalidade
# ainda não implementada neste app (mesma limitação já documentada em
# CLAUDE.md) — não guardadas por ora.
def _list_tributacao_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(
            f"SELECT codigo, descricao, Aplicacao, Regime_Tributario FROM Tributacao {where} ORDER BY descricao",
            params,
        )
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "aplicacao": (r.get("Aplicacao") or "").strip(),
            "regime_tributario": int(r.get("Regime_Tributario") or 0),
            "regime_label": "Simples Nacional" if int(r.get("Regime_Tributario") or 0) == 1 else "Normal",
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tributacao_sync(servidor: str, banco: str, codigo: str, descricao: str, aplicacao: str) -> dict:
    cod = (codigo or "").strip().upper()
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cod_v = cod[:3]
        desc_v = desc[:80]
        apl_v = (aplicacao or "").strip()
        cur.execute("SELECT TOP 1 1 AS ok FROM Tributacao WHERE codigo=%s", (cod_v,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário
            cur.execute("UPDATE Tributacao SET descricao=%s, Aplicacao=%s WHERE codigo=%s", (desc_v, apl_v, cod_v))
        else:
            cur.execute("INSERT INTO Tributacao (codigo, descricao, Aplicacao) VALUES (%s,%s,%s)", (cod_v, desc_v, apl_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "Tributação gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tributacao_sync(servidor: str, banco: str, codigo: str) -> dict:
    cod = (codigo or "").strip().upper()
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        for tabela, rotulo in (
            ("taxas", "Taxas de ECF"),
            ("taxas_nfce", "Taxas de NFC-e"),
            ("comanda_nfce_detalhe", "Detalhes de Comanda/NFC-e"),
        ):
            cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE tributacao=%s", (cod,))
            if cur.fetchone():
                return {"success": False, "message": f"Tributação vinculada a {rotulo} — não pode ser excluída."}
        cur.execute("DELETE FROM Tributacao WHERE codigo=%s", (cod,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Tributação não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Tributação excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tributacao(servidor, banco, search):
    return await asyncio.to_thread(_list_tributacao_sync, servidor, banco, search)


async def save_tributacao(servidor, banco, codigo, descricao, aplicacao):
    return await asyncio.to_thread(_save_tributacao_sync, servidor, banco, codigo, descricao, aplicacao)


async def delete_tributacao(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tributacao_sync, servidor, banco, codigo)


# ---------------- UNIDADE DE MEDIDA ----------------
# unid(cod nvarchar(3) NOT NULL — digitado pelo usuário, descricao no legado
#   é "des" —, des nvarchar(12), permite_decimais bit). Legado: FrmManUni
#   ("Manutenção de Unidades de Medidas"), campo "Código" — upsert-by-codigo,
#   mesmo padrão de Situação/Icms/Origem/Tributação/etc. Diferente de
#   Tributação, aqui o legado grava os 2 campos direito (Des E
#   Permite_Decimais), sem bug de campo esquecido.
#
# Delete guard: sem FK real no banco, mas `pecas.uni` é a referência de fato
# (426 produtos reais no banco de teste usam essa coluna) — mais
# `comanda_nfce_detalhe.unidade` (52 linhas reais) e `pecaspreco`/
# `paf_pecas`/`pecastemp.uni` (vazias no banco de teste, mesmo domínio,
# checadas por precaução).
def _list_unid_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE des LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT cod, des, permite_decimais FROM unid {where} ORDER BY des", params)
        items = [{
            "codigo": (r.get("cod") or "").strip(),
            "descricao": (r.get("des") or "").strip(),
            "permite_decimais": bool(r.get("permite_decimais")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_unid_sync(servidor: str, banco: str, codigo: str, descricao: str, permite_decimais: bool) -> dict:
    cod = (codigo or "").strip().upper()
    desc = (descricao or "").strip()
    if not cod:
        return {"success": False, "message": "Código é obrigatório."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cod_v = cod[:3]
        desc_v = desc[:12]
        pd = 1 if permite_decimais else 0
        cur.execute("SELECT TOP 1 1 AS ok FROM unid WHERE cod=%s", (cod_v,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário
            cur.execute("UPDATE unid SET des=%s, permite_decimais=%s WHERE cod=%s", (desc_v, pd, cod_v))
        else:
            cur.execute("INSERT INTO unid (cod, des, permite_decimais) VALUES (%s,%s,%s)", (cod_v, desc_v, pd))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_v, "message": "Unidade gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_unid_sync(servidor: str, banco: str, codigo: str) -> dict:
    cod = (codigo or "").strip().upper()
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        for tabela, coluna, rotulo in (
            ("pecas", "uni", "Produtos"),
            ("pecaspreco", "uni", "Preços de Produtos"),
            ("paf_pecas", "uni", "PAF"),
            ("pecastemp", "uni", "Produtos Temporários"),
            ("cupom_detalhe", "unidade", "Detalhes de Cupom Fiscal"),
            ("comanda_nfce_detalhe", "unidade", "Detalhes de Comanda/NFC-e"),
        ):
            cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE {coluna}=%s", (cod,))
            if cur.fetchone():
                return {"success": False, "message": f"Unidade vinculada a {rotulo} — não pode ser excluída."}
        cur.execute("DELETE FROM unid WHERE cod=%s", (cod,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Unidade não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Unidade excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_unid(servidor, banco, search):
    return await asyncio.to_thread(_list_unid_sync, servidor, banco, search)


async def save_unid(servidor, banco, codigo, descricao, permite_decimais):
    return await asyncio.to_thread(_save_unid_sync, servidor, banco, codigo, descricao, permite_decimais)


async def delete_unid(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_unid_sync, servidor, banco, codigo)


# ---------------- TIPO DESTINO ITENS OS (tipo_os_prod) ----------------
# tipo_os_prod(codigo smallint NOT NULL, descricao nvarchar(30)) — legado:
# FrmManTipos ("Manutenção Tipo de OS Produto"), campo "Tipo" — upsert-by-
# codigo-digitado, mesmo padrão de Situação/Icms/Origem/etc. Classifica o
# destino de cada item (produto) de uma O.S. — Cliente/Garantia/Interno/
# Revisão de Fábrica no banco de teste.
#
# Delete guard: FK real `FK_os_produto_tipo_os_prod` — `os_produto.situacao`
# (nome de coluna enganoso: não é a "situação" da O.S., é o código de
# `tipo_os_prod` — confirmado via sys.foreign_keys) referencia esta tabela.
def _list_tipo_os_prod_sync(servidor: str, banco: str, search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ""
        params: tuple = ()
        if search and search.strip():
            where = "WHERE descricao LIKE %s"
            params = (f"%{search.strip()}%",)
        cur.execute(f"SELECT codigo, descricao FROM tipo_os_prod {where} ORDER BY descricao", params)
        items = [{
            "codigo": int(r["codigo"]),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_tipo_os_prod_sync(servidor: str, banco: str, codigo: int, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if codigo is None:
        return {"success": False, "message": "O código não pode ficar em branco!"}
    if not desc:
        return {"success": False, "message": "A descrição não pode ficar em branco!"}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        desc_v = desc[:30]
        cur.execute("SELECT TOP 1 1 AS ok FROM tipo_os_prod WHERE codigo=%s", (codigo,))
        exists = cur.fetchone() is not None
        if exists:  # upsert-by-codigo: código é digitado pelo usuário
            cur.execute("UPDATE tipo_os_prod SET descricao=%s WHERE codigo=%s", (desc_v, codigo))
        else:
            cur.execute("INSERT INTO tipo_os_prod (codigo, descricao) VALUES (%s,%s)", (codigo, desc_v))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": codigo, "message": "Registro gravado com sucesso."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_tipo_os_prod_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os_produto WHERE situacao=%s", (codigo,))
        if cur.fetchone():
            return {"success": False, "message": "Tipo vinculado a itens de O.S. — não pode ser excluído."}
        cur.execute("DELETE FROM tipo_os_prod WHERE codigo=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído!"}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tipo_os_prod(servidor, banco, search):
    return await asyncio.to_thread(_list_tipo_os_prod_sync, servidor, banco, search)


async def save_tipo_os_prod(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_tipo_os_prod_sync, servidor, banco, codigo, descricao)


async def delete_tipo_os_prod(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_tipo_os_prod_sync, servidor, banco, codigo)


# =====================================================================
# ESPECIALIDADES (tabela `especialidades` — codigo_especialidade int
# IDENTITY PK, descricao nvarchar(50)). Legado: FrmCadEsp ("Cadastro de
# Especialidades"), aberto de dentro do próprio FrmManPro (tela de
# Funcionários) através de um ícone ao lado da lista "Especialidades
# Disponíveis" — não é uma tela própria de Tabelas Auxiliares, é um CRUD
# embutido na tela de Funcionários (mesmo espírito de Lista Negra dentro
# de Clientes). Listagem já existia como lookup somente-leitura
# (`lookups_service.list_especialidades`, `GET /api/especialidades`) —
# aqui entram só save/delete. Vínculo do funcionário fica em
# `funcionario_especialidades` (tabela separada, sem alteração aqui).
def _save_especialidade_sync(servidor: str, banco: str, codigo: Optional[int], descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Preencha a Descrição da Especialidade."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if codigo is not None:  # update
            cur.execute("UPDATE especialidades SET descricao=%s WHERE codigo_especialidade=%s", (desc, codigo))
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Especialidade não encontrada."}
            novo = codigo
        else:  # create — codigo_especialidade é IDENTITY
            cur.execute(
                "INSERT INTO especialidades (descricao) OUTPUT INSERTED.codigo_especialidade VALUES (%s)",
                (desc,),
            )
            row = cur.fetchone()
            novo = int(row["codigo_especialidade"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Registro Gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_especialidade_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM funcionario_especialidades WHERE codigo_especialidade=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Especialidade vinculada a funcionário(s) — não pode ser excluída."}
        cur.execute("DELETE FROM especialidades WHERE codigo_especialidade=%s", (codigo,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Especialidade não encontrada."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro Excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def save_especialidade(servidor, banco, codigo, descricao):
    return await asyncio.to_thread(_save_especialidade_sync, servidor, banco, codigo, descricao)


async def delete_especialidade(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_especialidade_sync, servidor, banco, codigo)


# =====================================================================
# TAXAS (tabela `taxas` — a maior/mais complexa desta leva; legado
# FrmManTaxas, "Manutenção de Taxas"). Chave primária de negócio (6 campos,
# confirmada pelo usuário): destino (UF) + cfop + cod_icms + tipo_mov +
# Simples_Nacional + consumidor_final. `SEQUENCIA_TAXAS` (IDENTITY) é usado
# aqui como PK técnica pra mirar update/delete, evitando repetir o WHERE de
# 6 campos do legado a cada operação.
#
# **Achado importante, favor confirmar com o usuário**: o checkbox do
# legado rotulado "Não Contribuinte" (Check1) na verdade grava na coluna
# `Simples_Nacional` — confirmado em TODAS as ocorrências do código (insert,
# update, os 2 selects de duplicata, delete): `IIf(Check1.Value=1,1,0)`
# sempre vira o valor de `simples_nacional`, nunca existe uma coluna
# "nao_contribuinte" na tabela. Isso é meio que o rótulo errado no
# Check1 do legado (mesma categoria de bug de legado/coluna já visto em
# Cliente: credita_icms/nao_contribuinte). Aqui o campo foi rotulado
# corretamente como "Simples Nacional" (bate com o nome real da coluna e
# com `ExibeDados`: "If RstAux!simples_nacional Then Check1.Value = 1").
#
# **Campos do legado excluídos por já estarem ocultos/mortos no `.frm`
# atual** (confirmado lendo `Visible = 0 'False` de cada controle):
# tipo_destino (Campo(3), auto-derivado de `tipo_mov.origem_destino` no
# save — nunca editável, mesmo no legado), tributacao_livro (Campo(11),
# sempre gravado como 1, hardcoded no próprio legado), cfop_livro
# (Campo(13), sempre = cfop), cod_contabil (Campo(14), campo e rótulo
# ocultos), margem_icms_recolher/icms_operacao_recolher/icms_recolher
# (Campo 15/16/17, campos e rótulos ocultos — cálculo de "recolhimento"
# não usado na tela atual). `CST_CBS` existe na tabela mas nunca é
# gravado por este formulário (a seção "IBS/CBS" do legado usa um único
# par CST/ClassTrib pra IBS e CBS juntos — `CST_IBS`/`CCLASSTRIB_IBS`).
CAMPOS_TAXAS = [
    "destino", "cfop", "cod_icms", "tipo_mov", "Simples_Nacional", "consumidor_final",
    "tributacao", "icms", "reducao_base_icms", "icms_substituicao", "margem_icms_substituicao",
    "reducao_base_retido", "ALQT_FCP", "ALQT_FCP_RETIDO", "ALQT_FCP_ST", "ALQT_CF", "ALQT_CRED_SN",
    "protocolo_st", "tipo_ipi", "INFORMA_BENEFICIO_FISCAL",
    "REDUCAO_BASE_PIS_COFINS", "CST_TRIB_PIS", "ALQT_TRIB_PIS", "CST_TRIB_COFINS", "ALQT_TRIB_COFINS",
    "PIS_COFINS_CUSTO_X_VENDA",
    "ALQT_ICMS_EFETIVO", "MARGEM_ICMS_EFETIVO", "REDUCAO_ICMS_EFETIVO", "ICMS_SUBSTITUTO",
    "dif_icms_bens", "ALQT_ICMS_DESONERADO", "MOTIVO_ICMS_DESONERADO",
    "aliquota_interestadual", "aliquota_interna_destino", "percentual_origem", "fundo_pobreza",
    # Reforma Tributária (IBS/CBS/IS)
    "INFORMA_CBS_IBS",
    "CST_IS", "CCLASSTRIB_IS", "ALQT_IS",
    "CST_IBS", "CCLASSTRIB_IBS",
    "ALQT_IBS_ESTADO", "GRUPO_DIFERIMENTO_IBS_ESTADO", "PERC_DIFERIMENTO_IBS_ESTADO",
    "GRUPO_REDUCAO_IBS_ESTADO", "PERC_REDUCAO_IBS_ESTADO", "ALQT_EFETIVA_REDUCAO_IBS_ESTADO",
    "ALQT_IBS_MUNICIPIO", "GRUPO_DIFERIMENTO_IBS_MUNICIPIO", "PERC_DIFERIMENTO_IBS_MUNICIPIO",
    "GRUPO_REDUCAO_IBS_MUNICIPIO", "PERC_REDUCAO_IBS_MUNICIPIO", "ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO",
    "ALQT_CBS_ESTADO", "GRUPO_DIFERIMENTO_CBS_ESTADO", "PERC_DIFERIMENTO_CBS_ESTADO",
    "GRUPO_REDUCAO_CBS_ESTADO", "PERC_REDUCAO_CBS_ESTADO", "ALQT_EFETIVA_REDUCAO_CBS_ESTADO",
    "GTRIBREGULAR", "gMonoPadrao", "gMonoReten", "gMonoRet", "gMonoDif",
    "ALQT_ADREM_PADRAO_IBS", "ALQT_ADREM_PADRAO_CBS",
    "ALQT_ADREM_RETENCAO_IBS", "ALQT_ADREM_RETENCAO_CBS",
    "ALQT_ADREM_RETIDO_IBS", "ALQT_ADREM_RETIDO_CBS",
    "ALQT_ADREM_DIFERIMENTO_IBS", "ALQT_ADREM_DIFERIMENTO_CBS",
]

# `taxas_nfce` (legado ainda não tem um `.frm` próprio pra ela — reaproveita a
# mesma rotina de `taxas`, pedido explícito do usuário) tem 75 colunas contra
# 90 de `taxas`: faltam nela, confirmado via INFORMATION_SCHEMA em
# GERDELL/BARESTELA, exatamente estes 15 campos de CAMPOS_TAXAS —
# Simples_Nacional/consumidor_final (2 dos 6 campos da chave de negócio),
# protocolo_st, tipo_ipi, ALQT_CRED_SN, o grupo inteiro de PIS/COFINS atual
# (REDUCAO_BASE_PIS_COFINS/CST_TRIB_PIS/ALQT_TRIB_PIS/CST_TRIB_COFINS/
# ALQT_TRIB_COFINS/PIS_COFINS_CUSTO_X_VENDA — pedido do usuário pra tirar
# essa seção da tela de NFCe) e as 4 alíquotas de DIFAL (aliquota_interestadual/
# aliquota_interna_destino/percentual_origem/fundo_pobreza). Em troca ela tem
# um PIS/COFINS "antigo" (tributacao_pis/perc_valor_pis/tributacao_cofins/
# perc_valor_cofins) e um campo a mais, `gIBSCBSMono` — nenhum dos dois é
# gerenciado por esta tela (mesmo critério dos campos ocultos do `.frm` de
# `taxas`, ver nota grande logo abaixo de `TAXA_VARIANTES`).
CAMPOS_TAXAS_NFCE = [c for c in CAMPOS_TAXAS if c not in {
    "Simples_Nacional", "consumidor_final", "protocolo_st", "tipo_ipi", "ALQT_CRED_SN",
    "REDUCAO_BASE_PIS_COFINS", "CST_TRIB_PIS", "ALQT_TRIB_PIS", "CST_TRIB_COFINS", "ALQT_TRIB_COFINS",
    "PIS_COFINS_CUSTO_X_VENDA",
    "aliquota_interestadual", "aliquota_interna_destino", "percentual_origem", "fundo_pobreza",
}]

_TAXAS_BOOL_FIELDS = {
    "Simples_Nacional", "consumidor_final", "protocolo_st", "tipo_ipi", "INFORMA_BENEFICIO_FISCAL",
    "PIS_COFINS_CUSTO_X_VENDA", "INFORMA_CBS_IBS",
    "GRUPO_DIFERIMENTO_IBS_ESTADO", "GRUPO_REDUCAO_IBS_ESTADO",
    "GRUPO_DIFERIMENTO_IBS_MUNICIPIO", "GRUPO_REDUCAO_IBS_MUNICIPIO",
    "GRUPO_DIFERIMENTO_CBS_ESTADO", "GRUPO_REDUCAO_CBS_ESTADO",
    "GTRIBREGULAR", "gMonoPadrao", "gMonoReten", "gMonoRet", "gMonoDif",
}
_TAXAS_TEXT_FIELDS = {
    "destino", "cfop", "cod_icms", "tipo_mov", "tributacao",
    "CST_TRIB_PIS", "CST_TRIB_COFINS", "MOTIVO_ICMS_DESONERADO",
    "CST_IS", "CCLASSTRIB_IS", "CST_IBS", "CCLASSTRIB_IBS",
}
_TAXAS_NFCE_BOOL_FIELDS = _TAXAS_BOOL_FIELDS - {"Simples_Nacional", "consumidor_final", "protocolo_st", "tipo_ipi", "PIS_COFINS_CUSTO_X_VENDA"}
_TAXAS_NFCE_TEXT_FIELDS = _TAXAS_TEXT_FIELDS - {"CST_TRIB_PIS", "CST_TRIB_COFINS"}

# Config por variante — única diferença estrutural entre "Taxas NFe/NFSe" e
# "Taxas NFCe" no front (mesma tela, mesmas rotas, só troca a tabela/PK/
# conjunto de campos). `chave_extra` são os campos além de
# destino+cfop+cod_icms+tipo_mov que entram na checagem de duplicidade — em
# `taxas` a chave de negócio tem 6 campos (confirmada pelo usuário); em
# `taxas_nfce` fica reduzida a 4, já que Simples_Nacional/consumidor_final
# não existem nessa tabela.
TAXA_VARIANTES = {
    "nfe": {
        "tabela": "taxas", "pk": "SEQUENCIA_TAXAS",
        "campos": CAMPOS_TAXAS, "bool_fields": _TAXAS_BOOL_FIELDS, "text_fields": _TAXAS_TEXT_FIELDS,
        "chave_extra": ["Simples_Nacional", "consumidor_final"],
        "tem_simples_consumidor_protocolo": True,
    },
    "nfce": {
        "tabela": "taxas_nfce", "pk": "SEQUENCIA_TAXAS_NFCE",
        "campos": CAMPOS_TAXAS_NFCE, "bool_fields": _TAXAS_NFCE_BOOL_FIELDS, "text_fields": _TAXAS_NFCE_TEXT_FIELDS,
        "chave_extra": [],
        "tem_simples_consumidor_protocolo": False,
    },
}


def _coerce_taxas_vals(dados: dict, cfg: dict) -> dict:
    vals = {}
    for c in cfg["campos"]:
        v = dados.get(c)
        if c in cfg["bool_fields"]:
            vals[c] = 1 if v else 0
        elif c in cfg["text_fields"]:
            vals[c] = (v or "").strip() or None
        else:
            try:
                vals[c] = float(v) if v not in (None, "") else 0.0
            except (TypeError, ValueError):
                vals[c] = 0.0
    return vals


def _list_taxas_sync(servidor: str, banco: str, variante: str, tipo_mov: str, destino: str, cod_icms: str) -> dict:
    cfg = TAXA_VARIANTES.get(variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    tabela, pk = cfg["tabela"], cfg["pk"]
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if tipo_mov and tipo_mov.strip():
            where.append("t.tipo_mov=%s")
            params.append(tipo_mov.strip())
        if destino and destino.strip():
            where.append("t.destino=%s")
            params.append(destino.strip())
        if cod_icms and cod_icms.strip():
            where.append("t.cod_icms=%s")
            params.append(cod_icms.strip())
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        extra_cols = ", t.Simples_Nacional, t.consumidor_final, t.protocolo_st" if cfg["tem_simples_consumidor_protocolo"] else ""
        cur.execute(f"""
            SELECT t.{pk} AS SEQUENCIA_TAXAS, t.destino, t.cfop, t.cod_icms, t.tipo_mov, t.tributacao,
                   t.icms{extra_cols},
                   tm.descricao AS tipo_mov_descricao, di.descricao AS cod_icms_descricao
            FROM {tabela} t
            LEFT JOIN tipo_mov tm ON tm.codigo = t.tipo_mov
            LEFT JOIN dscr_icms di ON di.cod_icms = t.cod_icms
            {where_sql}
            ORDER BY t.destino, t.cfop, t.cod_icms, t.tipo_mov
        """, tuple(params))
        items = [{
            "sequencia": int(r["SEQUENCIA_TAXAS"]),
            "destino": (r.get("destino") or "").strip(),
            "cfop": (r.get("cfop") or "").strip(),
            "cod_icms": (r.get("cod_icms") or "").strip(),
            "cod_icms_descricao": (r.get("cod_icms_descricao") or "").strip(),
            "tipo_mov": (r.get("tipo_mov") or "").strip(),
            "tipo_mov_descricao": (r.get("tipo_mov_descricao") or "").strip(),
            "tributacao": (r.get("tributacao") or "").strip(),
            "icms": float(r.get("icms") or 0),
            "simples_nacional": bool(r.get("Simples_Nacional")),
            "consumidor_final": bool(r.get("consumidor_final")),
            "protocolo_st": bool(r.get("protocolo_st")),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _list_taxas_opcoes_filtro_sync(servidor: str, banco: str, variante: str, tipo_mov: str, destino: str) -> dict:
    """Opções dos 3 combos de filtro da grade de Taxas — só traz valores que
    realmente têm pelo menos uma taxa cadastrada (não a lista completa das
    tabelas de apoio), em cascata: Tipo Mov (sempre todos os que têm taxa) →
    UF (só as que têm taxa para o Tipo Mov escolhido) → Código de ICMS (só os
    que têm taxa pro par Tipo Mov + UF escolhido). Pedido explícito do
    usuário pra não obrigar ele a "pesquisar VENDA, DEVOLUÇÃO etc." numa
    lista cheia."""
    cfg = TAXA_VARIANTES.get(variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    tabela = cfg["tabela"]
    tipo_mov = (tipo_mov or "").strip()
    destino = (destino or "").strip()
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute(f"""
            SELECT DISTINCT t.tipo_mov AS codigo, tm.descricao AS descricao
            FROM {tabela} t LEFT JOIN tipo_mov tm ON tm.codigo = t.tipo_mov
            ORDER BY t.tipo_mov
        """)
        tipo_mov_opts = [{"codigo": (r["codigo"] or "").strip(), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]

        if tipo_mov:
            cur.execute(f"SELECT DISTINCT destino FROM {tabela} WHERE tipo_mov=%s ORDER BY destino", (tipo_mov,))
        else:
            cur.execute(f"SELECT DISTINCT destino FROM {tabela} ORDER BY destino")
        destino_opts = [(r["destino"] or "").strip() for r in cur.fetchall()]

        where = []
        params: list = []
        if tipo_mov:
            where.append("t.tipo_mov=%s"); params.append(tipo_mov)
        if destino:
            where.append("t.destino=%s"); params.append(destino)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cur.execute(f"""
            SELECT DISTINCT t.cod_icms AS codigo, di.descricao AS descricao
            FROM {tabela} t LEFT JOIN dscr_icms di ON di.cod_icms = t.cod_icms
            {where_sql}
            ORDER BY t.cod_icms
        """, tuple(params))
        cod_icms_opts = [{"codigo": (r["codigo"] or "").strip(), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]

        cur.close()
        return {"success": True, "tipo_mov": tipo_mov_opts, "destino": destino_opts, "cod_icms": cod_icms_opts}
    finally:
        conn.close()


def _get_taxa_sync(servidor: str, banco: str, variante: str, sequencia: int) -> dict:
    cfg = TAXA_VARIANTES.get(variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    tabela, pk = cfg["tabela"], cfg["pk"]
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cols = ", ".join(cfg["campos"])
        cur.execute(f"SELECT {pk} AS SEQUENCIA_TAXAS, {cols} FROM {tabela} WHERE {pk}=%s", (sequencia,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return {"success": False, "message": "Taxa não encontrada."}
        taxa = _to_json_safe(row)
        for k, v in taxa.items():
            if isinstance(v, str):
                taxa[k] = v.strip()
        cur.close()
        return {"success": True, "taxa": taxa}
    finally:
        conn.close()


def _save_taxa_sync(servidor: str, banco: str, variante: str, sequencia: Optional[int], dados: dict) -> dict:
    cfg = TAXA_VARIANTES.get(variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    tabela, pk, campos = cfg["tabela"], cfg["pk"], cfg["campos"]
    destino = (dados.get("destino") or "").strip().upper()
    cfop = (dados.get("cfop") or "").strip()
    cod_icms = (dados.get("cod_icms") or "").strip()
    tipo_mov = (dados.get("tipo_mov") or "").strip().upper()
    if not destino:
        return {"success": False, "message": "Preencha a UF corretamente!"}
    if not cfop:
        return {"success": False, "message": "Preenchimento Obrigatório: CFOP"}
    if not cod_icms:
        return {"success": False, "message": "Defina o Código de ICMS!"}
    if not tipo_mov:
        return {"success": False, "message": "Preenchimento Obrigatório: Movimentação"}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT TOP 1 1 AS ok FROM cfops WHERE cfop=%s", (cfop,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Código Fiscal da Operação (Cfop) não Cadastrado!"}

        cur.execute("SELECT TOP 1 origem_destino FROM tipo_mov WHERE codigo=%s", (tipo_mov,))
        tm_row = cur.fetchone()
        if not tm_row:
            cur.close()
            return {"success": False, "message": "Tipo de Movimentação não Cadastrado!"}
        tipo_destino = (tm_row.get("origem_destino") or "C").strip() or "C"

        tributacao = (dados.get("tributacao") or "").strip()
        if tributacao:
            cur.execute("SELECT TOP 1 1 AS ok FROM tributacao WHERE codigo=%s AND situacao='A'", (tributacao,))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": "Código de Tributação não Cadastrado ou Desativado!"}

        # Reforma Tributária — CST/ClassTrib do IBS/CBS: cada campo pode
        # existir isoladamente na tabela `classtrib` (ex.: CST 000 existe,
        # ClassTrib 000001 existe) sem que a COMBINAÇÃO dos dois exista —
        # pedido explícito do usuário pra validar a combinação, não só cada
        # campo isolado.
        cst_ibs = (dados.get("CST_IBS") or "").strip()
        cclasstrib_ibs = (dados.get("CCLASSTRIB_IBS") or "").strip()
        if cst_ibs or cclasstrib_ibs:
            if not cst_ibs or not cclasstrib_ibs:
                cur.close()
                return {"success": False, "message": "Preencha CST e ClassTrib do IBS/CBS juntos."}
            cur.execute("SELECT TOP 1 1 AS ok FROM classtrib WHERE [CST]=%s AND [cClassTrib]=%s", (cst_ibs, cclasstrib_ibs))
            if not cur.fetchone():
                cur.close()
                return {"success": False, "message": "Combinação de CST e ClassTrib do IBS/CBS não encontrada na tabela ClassTrib!"}

        vals = _coerce_taxas_vals(dados, cfg)
        vals["destino"] = destino
        vals["cfop"] = cfop
        vals["cod_icms"] = cod_icms
        vals["tipo_mov"] = tipo_mov

        # Chave de negócio (4 campos fixos + `chave_extra` da variante) —
        # bloqueia duplicata, igual ao legado (sem unique constraint no banco).
        chave_where = "destino=%s AND cfop=%s AND cod_icms=%s AND tipo_mov=%s"
        chave_params = [destino, cfop, cod_icms, tipo_mov]
        for campo in cfg["chave_extra"]:
            chave_where += f" AND {campo}=%s"
            chave_params.append(vals[campo])
        cur.execute(f"SELECT {pk} FROM {tabela} WHERE {chave_where}", tuple(chave_params))
        existing = cur.fetchone()
        if existing and (not sequencia or int(existing[pk]) != int(sequencia)):
            cur.close()
            return {"success": False, "message": "Já existe uma Taxa cadastrada com essa combinação de UF/CFOP/Código de ICMS/Movimentação" + (
                "/Simples Nacional/Consumidor Final." if cfg["chave_extra"] else "."
            )}

        if sequencia:
            set_sql = ", ".join(f"{c}=%s" for c in campos)
            set_sql += ", tipo_destino=%s, tributacao_livro=1, cfop_livro=%s"
            cur.execute(
                f"UPDATE {tabela} SET {set_sql} WHERE {pk}=%s",
                tuple(vals[c] for c in campos) + (tipo_destino, cfop, sequencia),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Taxa não encontrada."}
            nova_sequencia = sequencia
        else:
            cols_sql = ", ".join(campos) + ", tipo_destino, tributacao_livro, cfop_livro"
            placeholders = ", ".join(["%s"] * (len(campos) + 3))
            cur.execute(
                f"INSERT INTO {tabela} ({cols_sql}) OUTPUT INSERTED.{pk} VALUES ({placeholders})",
                tuple(vals[c] for c in campos) + (tipo_destino, 1, cfop),
            )
            nova_sequencia = int(cur.fetchone()[pk])

        conn.commit()
        cur.close()
        return {"success": True, "sequencia": nova_sequencia, "message": "Registro Gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_taxa_sync(servidor: str, banco: str, variante: str, sequencia: int) -> dict:
    cfg = TAXA_VARIANTES.get(variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    tabela, pk = cfg["tabela"], cfg["pk"]
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(f"DELETE FROM {tabela} WHERE {pk}=%s", (sequencia,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não Cadastrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro Excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


def _list_dscr_icms_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod_icms, descricao FROM dscr_icms ORDER BY cod_icms")
        items = [{"codigo": (r.get("cod_icms") or "").strip(), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _classtrib_lookup_sync(servidor: str, banco: str, cst: str, cclasstrib: str) -> dict:
    cst = (cst or "").strip()
    cclasstrib = (cclasstrib or "").strip()
    if not cst or not cclasstrib:
        return {"success": False, "message": "Informe CST e ClassTrib."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 [CST], [cClassTrib], [pRedIBS], [pRedCBS], [ind_gTribRegular], "
            "[ind_gMonoPadrao], [ind_gMonoReten], [ind_gMonoRet], [ind_gMonoDif] "
            "FROM classtrib WHERE [CST]=%s AND [cClassTrib]=%s",
            (cst, cclasstrib),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return {"success": False, "message": "Não foi encontrada essa combinação de CST e ClassTrib!"}
        return {
            "success": True,
            "pred_ibs": float(row.get("pRedIBS") or 0),
            "pred_cbs": float(row.get("pRedCBS") or 0),
            "g_trib_regular": bool(row.get("ind_gTribRegular")),
            "g_mono_padrao": bool(row.get("ind_gMonoPadrao")),
            "g_mono_reten": bool(row.get("ind_gMonoReten")),
            "g_mono_ret": bool(row.get("ind_gMonoRet")),
            "g_mono_dif": bool(row.get("ind_gMonoDif")),
        }
    finally:
        conn.close()


# Opções pros 2 combos em cascata de CST/ClassTrib do IBS/CBS na tela de
# Taxas — pedido explícito do usuário pra facilitar o preenchimento (antes
# eram campos de texto livre, validados só no blur/gravar). `CST` sempre
# traz todos os distintos da tabela; `ClassTrib` é filtrado pelo CST
# escolhido (relação real 1-CST-pra-N-ClassTrib na tabela nacional).
def _list_classtrib_opcoes_sync(servidor: str, banco: str, cst: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        # `Descricao` não é 1-pra-1 com CST (varia por sub-regra dentro do
        # mesmo CST) — agrupa e usa MIN() só pra garantir 1 linha por CST
        # distinto (senão o combo teria valores duplicados/ambíguos).
        cur.execute("SELECT [CST], MIN([Descricao]) AS Descricao FROM classtrib GROUP BY [CST] ORDER BY [CST]")
        cst_opts = [{"cst": (r["CST"] or "").strip(), "descricao": (r.get("Descricao") or "").strip()} for r in cur.fetchall()]

        cst_v = (cst or "").strip()
        if cst_v:
            cur.execute("SELECT [cClassTrib], [Nome_cClassTrib] FROM classtrib WHERE [CST]=%s ORDER BY [cClassTrib]", (cst_v,))
        else:
            cur.execute("SELECT [cClassTrib], [Nome_cClassTrib] FROM classtrib ORDER BY [cClassTrib]")
        classtrib_opts = [{"cclasstrib": (r["cClassTrib"] or "").strip(), "nome": (r.get("Nome_cClassTrib") or "").strip()} for r in cur.fetchall()]

        cur.close()
        return {"success": True, "cst": cst_opts, "classtrib": classtrib_opts}
    finally:
        conn.close()


async def list_taxas(servidor, banco, variante, tipo_mov, destino, cod_icms):
    return await asyncio.to_thread(_list_taxas_sync, servidor, banco, variante, tipo_mov, destino, cod_icms)


async def list_taxas_opcoes_filtro(servidor, banco, variante, tipo_mov, destino):
    return await asyncio.to_thread(_list_taxas_opcoes_filtro_sync, servidor, banco, variante, tipo_mov, destino)


async def get_taxa(servidor, banco, variante, sequencia):
    return await asyncio.to_thread(_get_taxa_sync, servidor, banco, variante, sequencia)


async def save_taxa(servidor, banco, variante, sequencia, dados):
    return await asyncio.to_thread(_save_taxa_sync, servidor, banco, variante, sequencia, dados)


async def delete_taxa(servidor, banco, variante, sequencia):
    return await asyncio.to_thread(_delete_taxa_sync, servidor, banco, variante, sequencia)


async def list_dscr_icms(servidor, banco):
    return await asyncio.to_thread(_list_dscr_icms_sync, servidor, banco)


async def classtrib_lookup(servidor, banco, cst, cclasstrib):
    return await asyncio.to_thread(_classtrib_lookup_sync, servidor, banco, cst, cclasstrib)


async def list_classtrib_opcoes(servidor, banco, cst):
    return await asyncio.to_thread(_list_classtrib_opcoes_sync, servidor, banco, cst)
