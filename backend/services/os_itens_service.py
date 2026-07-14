"""Itens da Ordem de Serviço (os_produto) — listagem e CRUD.

Relacionamentos:
  os.codigo = os_produto.os
  os_produto.codigo_interno = pecas.codigo_int (produto 'P') ou servicos.codigo (serviço 'S')
Regras:
  • Só OS com situacao='A' (Aberta) permite CRUD de itens.
  • vendedor e executor ficam POR ITEM (diferente do pedido_venda).
  • Total do item = quant * p_venda; p_venda = preco_unitario - desconto + acrescimo.
  • os.valor = SUM dos itens não cancelados.
"""
import asyncio

from db.connection import _open_conn
from models.schemas import OSItemSaveRequest
from services.constants import SITUACAO_LABEL
from services.pedido_common import _resolve_produto, _mover_estoque, _modulo_servicos_ativo


def _check_os_aberta(cur, codigo: int) -> tuple[bool, str]:
    cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
    row = cur.fetchone()
    if not row:
        return (False, "")
    return (True, (row.get("situacao") or "").strip().upper())


def _recalc_os_total(cur, codigo: int) -> float:
    cur.execute(
        "UPDATE os SET valor = ISNULL(("
        "  SELECT SUM(quant * p_venda) FROM os_produto "
        "  WHERE os=%s AND ISNULL(item_cancelado,0)=0), 0) WHERE codigo=%s",
        (codigo, codigo),
    )
    cur.execute("SELECT valor FROM os WHERE codigo=%s", (codigo,))
    r = cur.fetchone()
    return float((r.get("valor") if isinstance(r, dict) else (r[0] if r else 0)) or 0)


def _list_itens_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "subtotal": 0}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada.", "items": [], "subtotal": 0}
        cur.execute(
            "SELECT i.cod_os_prod, i.codigo_interno, i.quant, i.p_venda, i.preco_unitario, "
            "       i.desconto, i.acrescimo, i.vendedor, i.executor, i.descricao_produto_os, "
            "       pe.descricao AS peca_desc, pe.codigo_fab AS peca_fab, pe.uni AS peca_uni, "
            "       sv.descricao AS serv_desc, "
            "       fv.nome AS vend_nome, fv.nome_guerra AS vend_guerra, "
            "       fe.nome AS exec_nome, fe.nome_guerra AS exec_guerra "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "LEFT JOIN funcionarios fv ON fv.codigo_int = i.vendedor "
            "LEFT JOIN funcionarios fe ON fe.codigo_int = i.executor "
            "WHERE i.os = %s AND ISNULL(i.item_cancelado,0) = 0 "
            "ORDER BY i.cod_os_prod",
            (codigo,),
        )
        items = []
        subtotal = 0.0
        for r in cur.fetchall():
            is_peca = r.get("peca_desc") is not None
            tipo = "P" if is_peca else ("S" if r.get("serv_desc") is not None else "?")
            base_desc = (r.get("peca_desc") if is_peca else r.get("serv_desc")) or ""
            qtd = float(r.get("quant") or 0)
            pv = float(r.get("p_venda") or 0)
            pnorm = float(r.get("preco_unitario") or 0)
            desc = float(r.get("desconto") or 0)
            acr = float(r.get("acrescimo") or 0)
            tot = round(qtd * pv, 2)
            subtotal += tot
            items.append({
                "cod_os_prod": int(r["cod_os_prod"]),
                "produto": (r.get("codigo_interno") or "").strip(),
                "tipo": tipo,
                "descricao": base_desc.strip(),
                "complemento": (r.get("descricao_produto_os") or "").strip(),
                "cod_fab": (r.get("peca_fab") or r.get("codigo_interno") or "").strip(),
                "unidade": (r.get("peca_uni") or ("HR" if tipo == "S" else "")).strip(),
                "qtd": qtd,
                "p_normal": pnorm,
                "valor_unitario": pv,
                "desconto": desc,
                "acrescimo": acr,
                "total": tot,
                "vendedor": int(r["vendedor"]) if r.get("vendedor") else None,
                "vendedor_nome": (r.get("vend_guerra") or r.get("vend_nome") or "").strip(),
                "executor": int(r["executor"]) if r.get("executor") else None,
                "executor_nome": (r.get("exec_guerra") or r.get("exec_nome") or "").strip(),
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


def _add_item_sync(req: OSItemSaveRequest, codigo: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        prod_cod = (req.produto or "").strip()
        if not prod_cod:
            conn.close()
            return {"success": False, "message": "Produto/serviço obrigatório."}
        prod = _resolve_produto(cur, prod_cod)
        if not prod:
            conn.close()
            return {"success": False, "message": f"Produto/serviço '{prod_cod}' não encontrado."}
        if prod["tipo"] == "S" and not _modulo_servicos_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Serviço está desativado — não é possível incluir serviços na O.S."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
        p_normal = float(p_normal or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)
        complemento = (req.complemento or "").strip()
        custo = float(prod.get("custo") or 0)

        cur.execute(
            "INSERT INTO os_produto "
            "(os, codigo_interno, quant, p_venda, preco_unitario, desconto, acrescimo, custo_os, "
            " vendedor, executor, descricao_produto_os, situacao, item_cancelado, faturado, data_inclusao_item) "
            "OUTPUT INSERTED.cod_os_prod "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,0,CAST(GETDATE() AS DATE))",
            (codigo, prod_cod, qtd, p_venda, p_normal, desc, acr, custo,
             req.vendedor, req.executor, complemento),
        )
        row = cur.fetchone()
        cod_os_prod = int(row["cod_os_prod"] if isinstance(row, dict) else row[0])
        # Estoque: OS aberta reserva imediatamente (qtd -= q ; reservado_os += q).
        # _mover_estoque ignora serviços automaticamente.
        _mover_estoque(cur, prod_cod, qtd, "reservado_os")
        novo_total = _recalc_os_total(cur, codigo)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "cod_os_prod": cod_os_prod, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _update_item_sync(req: OSItemSaveRequest, codigo: int, cod_os_prod: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        p_normal = float(req.valor_unitario or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)
        complemento = (req.complemento or "").strip()

        # Quantidade anterior p/ ajustar estoque reservado (somente peças).
        cur.execute("SELECT quant, codigo_interno FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                    (cod_os_prod, codigo))
        old = cur.fetchone()
        if not old:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        old_qtd = float(old.get("quant") or 0)
        old_cod = (old.get("codigo_interno") or "").strip()

        cur.execute(
            "UPDATE os_produto SET "
            " quant=%s, preco_unitario=%s, p_venda=%s, desconto=%s, acrescimo=%s, "
            " vendedor=%s, executor=%s, descricao_produto_os=%s, "
            " data_alteracao_item=CAST(GETDATE() AS DATE) "
            "WHERE cod_os_prod=%s AND os=%s",
            (qtd, p_normal, p_venda, desc, acr, req.vendedor, req.executor,
             complemento, cod_os_prod, codigo),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        # Ajusta a reserva pela diferença de quantidade.
        _mover_estoque(cur, old_cod, qtd - old_qtd, "reservado_os")
        novo_total = _recalc_os_total(cur, codigo)
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


def _delete_item_sync(servidor: str, banco: str, codigo: int, cod_os_prod: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        # Captura qtd/produto antes de excluir p/ estornar a reserva de estoque.
        cur.execute("SELECT quant, codigo_interno FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                    (cod_os_prod, codigo))
        old = cur.fetchone()
        if not old:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        cur.execute("DELETE FROM os_produto WHERE cod_os_prod=%s AND os=%s", (cod_os_prod, codigo))
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        # Estorno: qtd += quant ; reservado_os -= quant (delta negativo).
        _mover_estoque(cur, (old.get("codigo_interno") or "").strip(),
                       -float(old.get("quant") or 0), "reservado_os")
        novo_total = _recalc_os_total(cur, codigo)
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


async def list_itens(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_itens_sync, servidor, banco, codigo)


async def add_item(req: OSItemSaveRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_add_item_sync, req, codigo)


async def update_item(req: OSItemSaveRequest, codigo: int, cod_os_prod: int) -> dict:
    return await asyncio.to_thread(_update_item_sync, req, codigo, cod_os_prod)


async def delete_item(servidor: str, banco: str, codigo: int, cod_os_prod: int) -> dict:
    return await asyncio.to_thread(_delete_item_sync, servidor, banco, codigo, cod_os_prod)


# ---------- Descontos concedidos & Análise de margem ----------
def _list_descontos_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Lê os itens da OS com desconto > 0 (descontos concedidos)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.cod_os_prod, i.codigo_interno, i.quant, i.preco_unitario, i.desconto, "
            "       pe.descricao AS peca_desc, sv.descricao AS serv_desc "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE i.os=%s AND ISNULL(i.item_cancelado,0)=0 AND ISNULL(i.desconto,0) > 0 "
            "ORDER BY i.cod_os_prod",
            (codigo,),
        )
        items = []
        total = 0.0
        for r in cur.fetchall():
            qtd = float(r.get("quant") or 0)
            desc_unit = float(r.get("desconto") or 0)
            p_normal = float(r.get("preco_unitario") or 0)
            valor_total = round(desc_unit * qtd, 2)
            total += valor_total
            pct = round(desc_unit / p_normal * 100, 2) if p_normal > 0 else 0
            desc = (r.get("peca_desc") or r.get("serv_desc") or r.get("codigo_interno") or "Item")
            items.append({
                "cod": int(r["cod_os_prod"]),
                "tipo_label": "Item",
                "descricao": (desc or "").strip(),
                "percentual": pct,
                "valor_unitario": desc_unit,
                "qtd": qtd,
                "valor_total": valor_total,
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


def _analise_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Análise de margem & descontos da OS, calculada a partir de os_produto.
    venda = quant*p_venda; desconto = quant*desconto; custo = quant*custo_os."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.cod_os_prod, i.codigo_interno, i.quant, i.p_venda, i.preco_unitario, "
            "       i.desconto, i.custo_os, "
            "       pe.descricao AS peca_desc, sv.descricao AS serv_desc "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE i.os=%s AND ISNULL(i.item_cancelado,0)=0 "
            "ORDER BY i.cod_os_prod",
            (codigo,),
        )
        itens = []
        t_venda = t_desc = t_custo = 0.0
        for r in cur.fetchall():
            qtd = float(r.get("quant") or 0)
            pv = float(r.get("p_venda") or 0)
            desc_unit = float(r.get("desconto") or 0)
            custo_unit = float(r.get("custo_os") or 0)
            venda = round(qtd * pv, 2)
            desconto = round(qtd * desc_unit, 2)
            custo = round(qtd * custo_unit, 2)
            margem = round(venda - custo, 2)
            margem_pct = round(margem / venda * 100, 2) if venda > 0 else 0.0
            t_venda += venda
            t_desc += desconto
            t_custo += custo
            desc = (r.get("peca_desc") or r.get("serv_desc") or r.get("codigo_interno") or "Item")
            itens.append({
                "cod": int(r["cod_os_prod"]),
                "descricao": (desc or "").strip(),
                "qtd": qtd,
                "venda": venda,
                "desconto": desconto,
                "custo": custo,
                "margem": margem,
                "margem_pct": margem_pct,
            })
        cur.close()
        conn.close()
        t_margem = round(t_venda - t_custo, 2)
        t_pct = round(t_margem / t_venda * 100, 2) if t_venda > 0 else 0.0
        return {
            "success": True,
            "itens": itens,
            "totais": {
                "venda": round(t_venda, 2),
                "desconto": round(t_desc, 2),
                "custo": round(t_custo, 2),
                "margem": t_margem,
                "margem_pct": t_pct,
                "qtd_itens": len(itens),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def list_descontos(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_descontos_sync, servidor, banco, codigo)


async def analise(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_analise_sync, servidor, banco, codigo)


# ---------- Desconto geral (distribuído entre os itens) ----------
def _aplicar_desconto_geral_sync(req, codigo: int) -> dict:
    from services.controle_service import _get_limites_sync
    from services.descontos_service import _limite_por_funcao
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        valor = float(req.valor or 0)
        if valor < 0:
            conn.close()
            return {"success": False, "message": "Valor inválido."}

        cur.execute(
            "SELECT cod_os_prod, preco_unitario, acrescimo, quant FROM os_produto "
            "WHERE os=%s AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
        itens = cur.fetchall()
        if not itens:
            conn.close()
            return {"success": False, "message": "OS sem itens para aplicar desconto."}

        # base = soma dos itens a preço cheio (preco_unitario * quant)
        base = sum(float(it.get("preco_unitario") or 0) * float(it.get("quant") or 0) for it in itens)
        if valor > 0 and base <= 0:
            conn.close()
            return {"success": False, "message": "Itens sem valor para distribuir o desconto."}

        pct_efetivo = round(valor / base * 100, 4) if base > 0 else 0
        if valor > 0:
            lim = _get_limites_sync(req.servidor, req.banco)
            limite = _limite_por_funcao(lim, int(req.funcao or 1))
            usuario = req.usuario_codigo if req.usuario_codigo is not None else -2
            if usuario != -2 and limite > 0 and pct_efetivo > limite + 1e-6:
                conn.close()
                return {"success": False, "message": f"Desconto ({pct_efetivo:g}%) acima do limite ({limite:g}%) para sua função."}
            if valor > base + 1e-6:
                conn.close()
                return {"success": False, "message": "Desconto maior que o total dos itens."}

        for it in itens:
            cod = int(it["cod_os_prod"])
            p_normal = float(it.get("preco_unitario") or 0)
            acr = float(it.get("acrescimo") or 0)
            desconto_unit = round(valor * p_normal / base, 2) if (valor > 0 and base > 0) else 0.0
            p_venda = round(p_normal - desconto_unit + acr, 4)
            cur.execute(
                "UPDATE os_produto SET desconto=%s, p_venda=%s, "
                "data_alteracao_item=CAST(GETDATE() AS DATE) WHERE cod_os_prod=%s AND os=%s",
                (desconto_unit, p_venda, cod, codigo),
            )
        novo_total = _recalc_os_total(cur, codigo)
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


async def aplicar_desconto_geral(req, codigo: int) -> dict:
    return await asyncio.to_thread(_aplicar_desconto_geral_sync, req, codigo)
