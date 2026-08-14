"""Itens do Pedido — Painel de Relatórios > Pré Venda.

Migração de `FrmItePEd.frm`. Soma a quantidade vendida de cada produto
(`pedido_venda_prod`, situação `'F'` — Fechado) no período — auxiliar de
reposição/compra. Colunas do grid original: Código, Descrição, Uni.
(`un_compra`), **Fator** (`qtd_un_compra`), Total Qtd. (soma de
`qtd_pedida`), **Total Geral** (`Total Qtd. × Fator` — fórmula literal do
legado, `Command1_Click`; replicada tal como está, sem reinterpretar o
significado de negócio do "Fator" além do que o próprio nome da coluna já
diz).

`situacao='F'` é uma regra real do legado (produto "comprometido" por um
pedido fechado já entra no cálculo de reposição, sem precisar esperar o
faturamento) — portada como está, só acrescida de
`ISNULL(i.item_cancelado,0)=0` (coluna real desta migração, ausente no
legado; toda outra query já a usa — sua omissão aqui seria bug, não
fidelidade histórica).

Só Pedido — o próprio legado não inclui O.S. neste relatório (recorte
original, não uma decisão desta migração).

Diferença em relação ao legado: a lista de pedidos que compõem cada
produto (checkbox "Detalhar" no `.frm`) é resolvida numa ÚNICA query
(agregação em Python), não um loop de sub-consulta por produto.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _itens_pedido_sync(servidor: str, banco: str, data_ini: str, data_fim: str) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.codigo_fab, p.descricao AS produto_descricao, p.un_compra, "
            "  ISNULL(p.qtd_un_compra,1) AS qtd_un_compra, "
            "  pv.pedido, c.nome AS cliente_nome, i.qtd_pedida "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN pecas p ON p.codigo_int = i.produto "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "WHERE pv.situacao = 'F' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND CAST(pv.data AS DATE) BETWEEN %s AND %s "
            "ORDER BY p.descricao, pv.pedido",
            (data_ini, data_fim),
        )
        rows = cur.fetchall()
        cur.close()

        produtos: dict = {}
        ordem: list = []
        for r in rows:
            cod = (r.get("codigo_fab") or "").strip()
            prod = produtos.get(cod)
            if not prod:
                fator = float(r.get("qtd_un_compra") or 1) or 1
                prod = {
                    "codigo_fab": cod,
                    "descricao": (r.get("produto_descricao") or "").strip(),
                    "unidade_compra": (r.get("un_compra") or "").strip(),
                    "fator": fator,
                    "qtd_total": 0.0,
                    "pedidos": [],
                }
                produtos[cod] = prod
                ordem.append(cod)
            qtd = float(r.get("qtd_pedida") or 0)
            prod["qtd_total"] += qtd
            prod["pedidos"].append({
                "pedido": int(r["pedido"]),
                "cliente_nome": (r.get("cliente_nome") or "").strip() or "—",
                "qtd_pedida": qtd,
            })

        itens = []
        for cod in ordem:
            prod = produtos[cod]
            prod["qtd_total"] = round(prod["qtd_total"], 2)
            prod["qtd_compra"] = round(prod["qtd_total"] * prod["fator"], 3)
            itens.append(prod)
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


async def itens_pedido(servidor, banco, data_ini, data_fim):
    return await asyncio.to_thread(_itens_pedido_sync, servidor, banco, data_ini, data_fim)
