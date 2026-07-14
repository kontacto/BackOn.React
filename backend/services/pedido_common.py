"""Helpers de baixo nível compartilhados pelos serviços de itens e descontos.

Todas as funções recebem um cursor (`cur`) já aberto — não abrem conexão.
Mantidas em módulo próprio para evitar import circular entre itens_service e
descontos_service.
"""
from typing import Optional

from services.constants import STATUS_CLIENTE_LABEL


def _check_cliente_ativo(cur, cliente_codigo: int) -> tuple[bool, str]:
    """Bloqueia nova movimentação (Pedido/O.S.) para cliente com STATUS_CLIENTE
    diferente de 'A' (Ativo). Cliente sem status definido (NULL/'') é tratado
    como Ativo (dado legado, coluna sem valor). Retorna (permitido, label)."""
    cur.execute("SELECT STATUS_CLIENTE FROM cliente WHERE codigo=%s", (cliente_codigo,))
    row = cur.fetchone()
    status = ((row.get("STATUS_CLIENTE") if row else None) or "").strip().upper()
    if not status or status == "A":
        return True, ""
    return False, STATUS_CLIENTE_LABEL.get(status, status)


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


def _modulo_servicos_ativo(cur) -> bool:
    """True se o módulo "Serviço" está ligado em Configurações de Módulo do
    Sistema (controle_configuracao.servicos). Cadastro/consulta/movimentação
    de Serviço só é permitido com o módulo ativo — usado para bloquear a
    inclusão de item do tipo Serviço em Pedido/O.S. quando desligado."""
    cur.execute("SELECT TOP 1 servicos FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("servicos") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


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



def _is_peca(cur, codigo: str) -> bool:
    """True se o código pertence a uma peça (movimenta estoque)."""
    cur.execute("SELECT 1 AS ok FROM pecas WHERE codigo_int=%s", (codigo,))
    return cur.fetchone() is not None


def _mover_estoque(cur, codigo: str, delta_qtd: float, campo_reservado: str) -> None:
    """Movimenta o estoque de uma PEÇA dentro da transação corrente.

    Efeito: pecas.qtd -= delta_qtd ; pecas.<campo_reservado> += delta_qtd.
    `campo_reservado` deve ser 'reservado' (Pedido) ou 'reservado_os' (O.S.).
    Não faz nada para serviços/itens inexistentes. delta_qtd pode ser negativo
    (estorno ao remover/reduzir item).
    """
    if campo_reservado not in ("reservado", "reservado_os"):
        raise ValueError("campo_reservado inválido")
    if not delta_qtd or not _is_peca(cur, codigo):
        return
    cur.execute(
        f"UPDATE pecas SET qtd = ISNULL(qtd,0) - %s, "
        f"{campo_reservado} = ISNULL({campo_reservado},0) + %s "
        f"WHERE codigo_int=%s",
        (delta_qtd, delta_qtd, codigo),
    )