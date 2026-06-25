"""Helpers de baixo nível compartilhados pelos serviços de itens e descontos.

Todas as funções recebem um cursor (`cur`) já aberto — não abrem conexão.
Mantidas em módulo próprio para evitar import circular entre itens_service e
descontos_service.
"""
from typing import Optional


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
        valor = float(r.get("valor") or 0)
        return {
            "tipo": "S",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo") or "").strip(),
            "valor": valor,
            "unidade": "HR",
            "custo": valor,  # serviço: custo = valor_hora (regra de negócio)
        }
    return None
