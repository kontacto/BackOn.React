"""Modificadores (Cadastros > Tabelas Auxiliares) — cadastro novo, sem
tabela/tela equivalente no legado VB6 (pedido explícito do usuário,
2026-07-23). Uma Categoria de Modificador (ex.: "Ponto da Carne") agrupa
vários Modificadores (ex.: "Mal passado"/"Ao ponto"/"Bem passado"), cada um
podendo lançar um acréscimo e/ou desconto (valor fixo em R$) no item da
pré-venda ao qual for aplicado. Categoria tem uma condição (Obrigatório/
Opcional) e um modo de seleção (um único modificador ou vários) — ambos só
fazem sentido quando a tela de venda (Fase 2, ainda não implementada) abrir
o seletor de modificadores ao incluir um item associado.

3 tabelas novas (migração idempotente, mesmo padrão de
`gestao_compras_service._DDL_ALERTAS_ESTOQUE_CACHE`):
  • `modificador_categoria` — a categoria em si.
  • `modificador` — os modificadores de uma categoria (FK `categoria`).
  • `modificador_categoria_item` — associação N:N entre categoria e
    Produto (`pecas.codigo_int`) e/ou Serviço (`servicos.codigo`),
    discriminada por `tipo` ('P'/'S') já que as duas entidades vivem em
    tabelas diferentes neste sistema (confirmado em `servicos_service.py`
    — Serviço NÃO é uma linha de `pecas`, é tabela própria).

Fase 1 (esta) é só o cadastro: Categorias + Modificadores + associação com
Produto/Serviço, nos dois sentidos (aqui e retrofit em Produto Completo/
Serviços). A tela de seleção de modificador na hora da venda (Pedido Bar/
Geral/O.S.) é Fase 2, ainda não implementada — ver PENDENCIAS.md >
"Modificadores"."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.pedido_common import _modulo_bar_ativo

TIPOS_ITEM = {"P": "Produto", "S": "Serviço"}

_MODULO_OFF_MSG = "Módulo Bar está desativado — fale com o administrador em Configurações > Módulos e Recursos."

_DDL_CATEGORIA = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'modificador_categoria')
BEGIN
    CREATE TABLE modificador_categoria (
        codigo INT IDENTITY(1,1) PRIMARY KEY,
        nome NVARCHAR(150) NOT NULL,
        obrigatorio BIT NOT NULL DEFAULT 1,
        selecao_multipla BIT NOT NULL DEFAULT 0
    );
END
"""

_DDL_MODIFICADOR = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'modificador')
BEGIN
    CREATE TABLE modificador (
        codigo INT IDENTITY(1,1) PRIMARY KEY,
        categoria INT NOT NULL,
        nome NVARCHAR(150) NOT NULL,
        acrescimo NUMERIC(15,2) NOT NULL DEFAULT 0,
        desconto NUMERIC(15,2) NOT NULL DEFAULT 0,
        situacao NVARCHAR(1) NOT NULL DEFAULT 'A',
        CONSTRAINT FK_modificador_categoria FOREIGN KEY (categoria)
            REFERENCES modificador_categoria(codigo)
    );
END
"""

_DDL_CATEGORIA_ITEM = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'modificador_categoria_item')
BEGIN
    CREATE TABLE modificador_categoria_item (
        id INT IDENTITY(1,1) PRIMARY KEY,
        categoria INT NOT NULL,
        tipo NVARCHAR(1) NOT NULL,
        codigo NVARCHAR(30) NOT NULL,
        CONSTRAINT FK_modcatitem_categoria FOREIGN KEY (categoria)
            REFERENCES modificador_categoria(codigo)
    );
END
"""


def _ensure_tables(cur) -> None:
    # 3 execute() separados (não uma string única com os 3 CREATE TABLE) —
    # referenciar uma tabela recém-criada no MESMO batch de quem a cria dá
    # erro de bind em tempo de parse no SQL Server (achado ao vivo nesta
    # mesma sessão, ver Inventário > Fase 3 > "_ensure_usuario_digitacao_col"
    # — mesma lição, `modificador`/`modificador_categoria_item` referenciam
    # `modificador_categoria` via FK).
    cur.execute(_DDL_CATEGORIA)
    cur.execute(_DDL_MODIFICADOR)
    cur.execute(_DDL_CATEGORIA_ITEM)


def _row_str(row: dict, key: str) -> str:
    v = row.get(key)
    return (v or "").strip() if isinstance(v, str) else str(v or "")


def _list_categorias_sync(servidor: str, banco: str, busca: Optional[str] = None) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG, "items": []}
        _ensure_tables(cur)
        where = ""
        params: tuple = ()
        if busca and busca.strip():
            where = "WHERE mc.nome LIKE %s"
            params = (f"%{busca.strip()}%",)
        cur.execute(
            "SELECT mc.codigo, mc.nome, mc.obrigatorio, mc.selecao_multipla, "
            "(SELECT COUNT(*) FROM modificador m WHERE m.categoria=mc.codigo) AS qtd_modificadores, "
            "(SELECT COUNT(*) FROM modificador_categoria_item i WHERE i.categoria=mc.codigo) AS qtd_associados "
            f"FROM modificador_categoria mc {where} ORDER BY mc.nome",
            params,
        )
        items = [{
            "codigo": r.get("codigo"),
            "nome": _row_str(r, "nome"),
            "obrigatorio": bool(r.get("obrigatorio")),
            "selecao_multipla": bool(r.get("selecao_multipla")),
            "qtd_modificadores": int(r.get("qtd_modificadores") or 0),
            "qtd_associados": int(r.get("qtd_associados") or 0),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _resolver_descricoes_itens_sync(cur, itens: list) -> list:
    """`itens`: [{"tipo","codigo"}] -> mesma lista com "descricao" resolvida
    (cascata pecas/servicos, cada tipo na sua tabela própria)."""
    out = []
    for it in itens:
        descricao = ""
        if it["tipo"] == "P":
            cur.execute("SELECT descricao FROM pecas WHERE codigo_int=%s", (it["codigo"],))
            row = cur.fetchone()
            descricao = _row_str(row, "descricao") if row else "(produto não encontrado)"
        else:
            cur.execute("SELECT descricao FROM servicos WHERE codigo=%s", (it["codigo"],))
            row = cur.fetchone()
            descricao = _row_str(row, "descricao") if row else "(serviço não encontrado)"
        out.append({"tipo": it["tipo"], "codigo": it["codigo"], "descricao": descricao})
    return out


def _get_categoria_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute(
            "SELECT codigo, nome, obrigatorio, selecao_multipla FROM modificador_categoria WHERE codigo=%s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Categoria não encontrada."}
        cur.execute(
            "SELECT codigo, nome, acrescimo, desconto, situacao FROM modificador "
            "WHERE categoria=%s ORDER BY codigo",
            (codigo,),
        )
        modificadores = [{
            "codigo": r.get("codigo"),
            "nome": _row_str(r, "nome"),
            "acrescimo": float(r.get("acrescimo") or 0),
            "desconto": float(r.get("desconto") or 0),
            "situacao": _row_str(r, "situacao") or "A",
        } for r in cur.fetchall()]
        cur.execute(
            "SELECT tipo, codigo FROM modificador_categoria_item WHERE categoria=%s ORDER BY tipo, codigo",
            (codigo,),
        )
        itens_brutos = [{"tipo": _row_str(r, "tipo"), "codigo": _row_str(r, "codigo")} for r in cur.fetchall()]
        itens_associados = _resolver_descricoes_itens_sync(cur, itens_brutos)
        cur.close()
        return {
            "success": True,
            "codigo": row.get("codigo"),
            "nome": _row_str(row, "nome"),
            "obrigatorio": bool(row.get("obrigatorio")),
            "selecao_multipla": bool(row.get("selecao_multipla")),
            "modificadores": modificadores,
            "itens_associados": itens_associados,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _save_categoria_sync(servidor: str, banco: str, dados: dict) -> dict:
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return {"success": False, "message": "Informe o nome da categoria."}
    modificadores = dados.get("modificadores") or []
    for m in modificadores:
        if not (m.get("nome") or "").strip():
            return {"success": False, "message": "Todo modificador precisa de um nome."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        codigo = dados.get("codigo")
        obrigatorio = bool(dados.get("obrigatorio", True))
        selecao_multipla = bool(dados.get("selecao_multipla", False))

        if codigo:
            cur.execute("SELECT TOP 1 1 AS ok FROM modificador_categoria WHERE codigo=%s", (codigo,))
            if not cur.fetchone():
                return {"success": False, "message": "Categoria não encontrada."}
            cur.execute(
                "UPDATE modificador_categoria SET nome=%s, obrigatorio=%s, selecao_multipla=%s WHERE codigo=%s",
                (nome, obrigatorio, selecao_multipla, codigo),
            )
        else:
            cur.execute(
                "INSERT INTO modificador_categoria (nome, obrigatorio, selecao_multipla) "
                "OUTPUT INSERTED.codigo VALUES (%s, %s, %s)",
                (nome, obrigatorio, selecao_multipla),
            )
            codigo = cur.fetchone()["codigo"]

        # Modificadores e itens associados são gravados replace-all — mesmo
        # padrão já usado pra telefones/endereços/contatos do Cliente (a
        # lista inteira é enviada a cada save, sem endpoint de update/delete
        # por linha própria). Lista pequena (poucas dezenas no máximo por
        # categoria), sem custo real.
        cur.execute("DELETE FROM modificador WHERE categoria=%s", (codigo,))
        for m in modificadores:
            cur.execute(
                "INSERT INTO modificador (categoria, nome, acrescimo, desconto, situacao) "
                "VALUES (%s, %s, %s, %s, %s)",
                (codigo, m["nome"].strip(), float(m.get("acrescimo") or 0),
                 float(m.get("desconto") or 0), (m.get("situacao") or "A").strip().upper()[:1] or "A"),
            )

        itens_associados = dados.get("itens_associados") or []
        cur.execute("DELETE FROM modificador_categoria_item WHERE categoria=%s", (codigo,))
        for it in itens_associados:
            cur.execute(
                "INSERT INTO modificador_categoria_item (categoria, tipo, codigo) VALUES (%s, %s, %s)",
                (codigo, it["tipo"], it["codigo"]),
            )

        conn.commit()
        cur.close()
        return {"success": True, "message": "Categoria de modificador gravada.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _delete_categoria_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute("SELECT TOP 1 nome FROM modificador_categoria WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Categoria não encontrada."}
        # A Fase 2 (seletor de modificador na venda) só guarda o NOME dos
        # modificadores escolhidos como texto solto no Complemento do item
        # (ver AddItemModal.tsx) — não existe FK de um item de pedido pra
        # `modificador`/`modificador_categoria`, então excluir em cascata
        # continua seguro mesmo com a Fase 2 já em uso. Se algum dia um
        # pedido passar a referenciar o modificador por código (não só por
        # nome), isso precisa passar a bloquear com histórico de uso.
        cur.execute("DELETE FROM modificador_categoria_item WHERE categoria=%s", (codigo,))
        cur.execute("DELETE FROM modificador WHERE categoria=%s", (codigo,))
        cur.execute("DELETE FROM modificador_categoria WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Categoria de modificador excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _list_categorias_por_item_sync(servidor: str, banco: str, tipo: str, codigo: str) -> dict:
    """Categorias de modificador já associadas a UM produto/serviço —
    reaproveitado pelo retrofit em Produto Completo/Serviços (associação
    "pelo outro lado", ver docstring do módulo)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG, "items": []}
        _ensure_tables(cur)
        cur.execute(
            "SELECT mc.codigo, mc.nome FROM modificador_categoria mc "
            "INNER JOIN modificador_categoria_item i ON i.categoria=mc.codigo "
            "WHERE i.tipo=%s AND i.codigo=%s ORDER BY mc.nome",
            (tipo, codigo),
        )
        items = [{"codigo": r.get("codigo"), "nome": _row_str(r, "nome")} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _get_modificadores_completo_por_item_sync(servidor: str, banco: str, tipo: str, codigo: str) -> dict:
    """Categorias de modificador associadas a um produto/serviço, COM os
    modificadores aninhados (nome/acrescimo/desconto) — usado pelo seletor
    de modificadores na hora da venda (Fase 2, Pedido Bar). Diferente de
    `_list_categorias_por_item_sync` acima (retrofit em Produto Completo/
    Serviços), que só devolve {codigo,nome} — insuficiente pro seletor de
    venda, que precisa saber obrigatorio/selecao_multipla e a lista de
    modificadores pra montar checkboxes/radios. Só modificadores com
    situacao='A' entram aqui — um modificador Desativado não deve aparecer
    pro atendente selecionar."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG, "items": []}
        _ensure_tables(cur)
        cur.execute(
            "SELECT mc.codigo, mc.nome, mc.obrigatorio, mc.selecao_multipla "
            "FROM modificador_categoria mc "
            "INNER JOIN modificador_categoria_item i ON i.categoria=mc.codigo "
            "WHERE i.tipo=%s AND i.codigo=%s ORDER BY mc.nome",
            (tipo, codigo),
        )
        categorias = [{
            "codigo": r.get("codigo"),
            "nome": _row_str(r, "nome"),
            "obrigatorio": bool(r.get("obrigatorio")),
            "selecao_multipla": bool(r.get("selecao_multipla")),
            "modificadores": [],
        } for r in cur.fetchall()]
        for cat in categorias:
            cur.execute(
                "SELECT codigo, nome, acrescimo, desconto FROM modificador "
                "WHERE categoria=%s AND situacao='A' ORDER BY nome",
                (cat["codigo"],),
            )
            cat["modificadores"] = [{
                "codigo": r.get("codigo"),
                "nome": _row_str(r, "nome"),
                "acrescimo": float(r.get("acrescimo") or 0),
                "desconto": float(r.get("desconto") or 0),
            } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": categorias}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": []}
    finally:
        conn.close()


def _associar_item_categorias_sync(servidor: str, banco: str, tipo: str, codigo: str, categorias: list) -> dict:
    """Substitui (replace-all) as categorias de modificador associadas a UM
    produto/serviço — retrofit em Produto Completo/Serviços."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_bar_ativo(cur):
            cur.close()
            return {"success": False, "message": _MODULO_OFF_MSG}
        _ensure_tables(cur)
        cur.execute("DELETE FROM modificador_categoria_item WHERE tipo=%s AND codigo=%s", (tipo, codigo))
        for cat_codigo in categorias:
            cur.execute(
                "INSERT INTO modificador_categoria_item (categoria, tipo, codigo) VALUES (%s, %s, %s)",
                (cat_codigo, tipo, codigo),
            )
        conn.commit()
        cur.close()
        return {"success": True, "message": "Modificadores associados."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def list_categorias(servidor: str, banco: str, busca: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_list_categorias_sync, servidor, banco, busca)


async def get_categoria(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_categoria_sync, servidor, banco, codigo)


async def save_categoria(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_save_categoria_sync, servidor, banco, dados)


async def delete_categoria(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_categoria_sync, servidor, banco, codigo)


async def list_categorias_por_item(servidor: str, banco: str, tipo: str, codigo: str) -> dict:
    return await asyncio.to_thread(_list_categorias_por_item_sync, servidor, banco, tipo, codigo)


async def get_modificadores_completo_por_item(servidor: str, banco: str, tipo: str, codigo: str) -> dict:
    return await asyncio.to_thread(_get_modificadores_completo_por_item_sync, servidor, banco, tipo, codigo)


async def associar_item_categorias(servidor: str, banco: str, tipo: str, codigo: str, categorias: list) -> dict:
    return await asyncio.to_thread(_associar_item_categorias_sync, servidor, banco, tipo, codigo, categorias)
