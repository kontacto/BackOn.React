"""Descontos — validação de limite por função, log de descontos concedidos,
relatório de descontos do pedido e aplicação de desconto geral."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import DescontoGeralRequest
from services.constants import SITUACAO_LABEL
from services.controle_service import _get_limites_sync
from services.pedido_common import _check_pedido_aberto, _recalc_pedido_total


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


def _limite_por_funcao(lim: dict, funcao: int) -> float:
    # funcao: 1=gerente, 2=supervisor, 3=vendedor (master = gerente)
    if funcao == 2:
        return float(lim.get("supervisor") or 0)
    if funcao == 3:
        return float(lim.get("vendedor") or 0)
    return float(lim.get("gerente") or 0)


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


async def list_descontos(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_list_descontos_sync, servidor, banco, pedido)


async def aplicar_desconto_geral(req: DescontoGeralRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_aplicar_desconto_geral_sync, req, pedido)
