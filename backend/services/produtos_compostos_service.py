"""Produtos Compostos / Previsão de Produtos — tabela compartilhada entre
Produtos (composição de kit) e Serviços (previsão de materiais). Legado:
`FrmManReceita.frm` ("Produtos Compostos / Previsão de produtos por
serviço"), aberta como modal a partir do botão "Previsão de Produtos" em
`FrmManSer2.frm` (Command15_Click) — e, presumivelmente, de uma tela
equivalente em Produtos (fora de escopo aqui: só a integração em Serviços
foi pedida nesta leva).

Schema real (conferido ao vivo em GERDELL/BARESTELA, não assumido do VB6):
- `produtos_compostos(codigo int IDENTITY, principal nvarchar(8),
  vinculado nvarchar(8), qtd real, valor_no_kit float,
  descricao_no_kit nvarchar(max))`.
- **Chave primária real é composta (`principal`, `vinculado`)** — não
  `codigo` (que existe só como PK técnica pra permitir DELETE por linha na
  grade, mas não é a constraint de unicidade). Ou seja, o mesmo par
  (serviço, produto) não pode aparecer duas vezes — confirmado pelo
  "duplicate-check" que o próprio legado já fazia antes do INSERT
  (`FrmManReceita.Command1_Click`).
- `principal` e `vinculado` são códigos-texto, sem coluna própria dizendo
  se cada um é Produto (`pecas.codigo_int`) ou Serviço (`servicos.codigo`)
  — o legado resolve isso com UNION ALL contra as duas tabelas. Nesta
  integração (Serviços → Previsão de Produtos), `principal` é sempre o
  serviço que está sendo editado e `vinculado` é sempre um Produto — mas a
  listagem replica o UNION ALL do legado por fidelidade/segurança (linhas
  legadas com `vinculado` apontando pra outro serviço, se existirem,
  continuam aparecendo em vez de sumir silenciosamente).
- Sem edição in-place no legado: só Incluir (grid) e Excluir (duplo-clique
  na grade, com confirmação) — replicado aqui como Add/Delete, sem Update.
  Para "editar" qtd/valor, o usuário exclui e re-inclui.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _list_sync(servidor: str, banco: str, principal: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT pc.codigo, pc.vinculado, pc.qtd, pc.valor_no_kit, pc.descricao_no_kit, "
            "       p.codigo_fab AS cod_fab, p.descricao AS descricao_item, p.uni AS unidade "
            "FROM produtos_compostos pc JOIN pecas p ON p.codigo_int = pc.vinculado "
            "WHERE pc.principal = %s "
            "UNION ALL "
            "SELECT pc.codigo, pc.vinculado, pc.qtd, pc.valor_no_kit, pc.descricao_no_kit, "
            "       s.codigo AS cod_fab, s.descricao AS descricao_item, CAST('' AS nvarchar(10)) AS unidade "
            "FROM produtos_compostos pc JOIN servicos s ON s.codigo = pc.vinculado "
            "WHERE pc.principal = %s "
            "ORDER BY descricao_item",
            (principal, principal),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "vinculado": (r.get("vinculado") or "").strip(),
            "cod_fab": (r.get("cod_fab") or "").strip(),
            "descricao": (r.get("descricao_no_kit") or "").strip() or (r.get("descricao_item") or "").strip(),
            "qtd": float(r.get("qtd") or 0),
            "valor_no_kit": float(r.get("valor_no_kit") or 0),
            "unidade": (r.get("unidade") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_sync(
    servidor: str, banco: str, *, principal: str, vinculado: str,
    qtd: float, valor_no_kit: float, descricao_no_kit: str,
) -> dict:
    principal = (principal or "").strip().upper()
    vinculado = (vinculado or "").strip().upper()
    if not principal:
        return {"success": False, "message": "Serviço principal não informado."}
    if not vinculado:
        return {"success": False, "message": "Selecione um produto."}
    if vinculado == principal:
        return {"success": False, "message": "Um item não pode compor a si mesmo."}
    if not qtd or qtd <= 0:
        return {"success": False, "message": "Informe uma Quantidade maior que zero."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT 1 AS ok FROM pecas WHERE codigo_int=%s", (vinculado,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Produto não encontrado."}
        cur.execute(
            "SELECT 1 AS ok FROM produtos_compostos WHERE principal=%s AND vinculado=%s",
            (principal, vinculado),
        )
        if cur.fetchone():
            cur.close()
            return {
                "success": False,
                "message": "Este produto já está na composição — exclua o item existente antes de adicionar novamente.",
            }
        cur.execute(
            "INSERT INTO produtos_compostos (principal, vinculado, qtd, valor_no_kit, descricao_no_kit) "
            "VALUES (%s,%s,%s,%s,%s)",
            (principal, vinculado, qtd, valor_no_kit or 0, (descricao_no_kit or "").strip() or None),
        )
        conn.commit()
        cur.execute("SELECT @@IDENTITY AS codigo")
        codigo = int(cur.fetchone()["codigo"])
        cur.close()
        return {"success": True, "message": "Item adicionado à composição.", "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, codigo: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM produtos_compostos WHERE codigo=%s", (codigo,))
        afetadas = cur.rowcount
        conn.commit()
        cur.close()
        if not afetadas:
            return {"success": False, "message": "Item não encontrado."}
        return {"success": True, "message": "Item removido da composição."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_composicao(servidor: str, banco: str, principal: str) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, principal)


async def save_item(servidor: str, banco: str, **kwargs) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, **kwargs)


async def delete_item(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, codigo)
