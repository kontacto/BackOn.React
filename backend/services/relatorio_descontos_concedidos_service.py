"""Descontos (Concedidos) — Painel de Relatórios > Caixa.

Migração de `FrmRelDes.frm` ("Relatório de descontos concedidos por
venda/funcionário"). O legado lê `comanda`+`movimentacao`+
`DESCONTOS_CONCEDIDOS` (tipo='COM') e monta uma árvore de 3 níveis:
Comanda → Item → cada desconto concedido naquele item (podem existir
múltiplos registros históricos empilhados por item).

**Generalização Pedido/OS** (decisão do usuário, 2026-08-07 — mesma
diretriz do Apuração de Vendas-DRE/Resumo de Venda): nesta migração a
tabela real é `descontos_concedidos` (mesmo nome/colunas do legado,
TIPO/CODIGO/CODIGO_PRODUTO/PERCENTUAL/VALOR/USUARIO/TIPO_DESCONTO — ver
`descontos_service.py`), mas **só é gravada para Pedido** (`TIPO='PED'`,
em `_log_desconto_item`/`_aplicar_desconto_geral_sync`). O.S.
(`os_itens_service.py`) grava o desconto só como valor unitário direto em
`os_produto.desconto`, **sem** auditoria de quem concedeu/tipo Item-Geral
— confirmado por grep, não existe nenhum INSERT em `descontos_concedidos`
com `TIPO='OS'` nesta migração. Por isso:
- **Pedido**: linha por item com desconto > 0, JOIN em
  `descontos_concedidos` pra trazer percentual/tipo (Item/Geral)/quem
  concedeu (`nome_guerra`).
- **O.S.**: linha por item com desconto > 0, **sem** tipo/concedido_por
  (campos `null` — a UI mostra "—" em vez de inventar um valor).

**Simplificação de estrutura em relação ao legado**: no legado, um item
pode ter VÁRIOS registros históricos em `DESCONTOS_CONCEDIDOS` (append-
only). Nesta migração, `_log_desconto_item`/`_aplicar_desconto_geral_sync`
usam política **delete+insert** — um item tem NO MÁXIMO 1 linha ativa em
`descontos_concedidos` a qualquer momento (nunca 'I' e 'G' ao mesmo
tempo). Por isso a árvore de 3 níveis do legado (Documento → Item →
Grants) colapsa em 2 níveis aqui (Documento → Item, cada item já carrega
seu único desconto ativo) — não há informação perdida, é o formato real
do dado nesta migração.

**Sem filtro por situação** — mesma convenção de
`_relatorio_desc_margem_sync` (relatório irmão mais próximo desta tela),
que também não filtra por `situacao`; mostra descontos concedidos em
qualquer situação do documento, não só faturado.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _descontos_concedidos_sync(
    servidor: str, banco: str,
    data_ini: str, data_fim: str,
    tipo: Optional[str], cliente_nome: Optional[str],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "documentos": [], "totais": {}}
    tipo_v = (tipo or "").strip().lower()
    if tipo_v not in ("", "pedido", "os", "todos"):
        return {"success": False, "message": "Tipo inválido.", "documentos": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        cli_sql, cli_p = "", []
        if cliente_nome and cliente_nome.strip():
            like = f"%{cliente_nome.strip()}%"
            cli_sql = "AND (c.nome LIKE %s OR c.fantasia LIKE %s)"
            cli_p = [like, like]

        blocos = []
        params: list = []
        if tipo_v in ("", "pedido", "todos"):
            blocos.append((
                "SELECT 'PEDIDO' AS doc_tipo, pv.pedido AS doc_numero, pv.data AS doc_data, "
                "  c.nome AS cliente_nome, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, "
                "  i.codauto AS item_cod, COALESCE(pe.descricao, sv.descricao, 'Item') AS item_descricao, "
                "  i.qtd_pedida AS qtd, i.p_normal AS p_normal, i.desconto AS desconto_unit, "
                "  d.TIPO_DESCONTO AS tipo_desconto, d.PERCENTUAL AS percentual, "
                "  COALESCE(NULLIF(fg.nome_guerra,''), fg.nome) AS concedido_por "
                "FROM pedido_venda_prod i "
                "JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "LEFT JOIN cliente c ON c.codigo = pv.cliente "
                "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
                "LEFT JOIN servicos sv ON sv.codigo = i.produto "
                "LEFT JOIN descontos_concedidos d ON d.TIPO = 'PED' AND d.CODIGO = i.pedido AND d.CODIGO_PRODUTO = i.codauto "
                "LEFT JOIN funcionarios fg ON fg.codigo_int = d.USUARIO "
                "WHERE ISNULL(i.item_cancelado,0) = 0 AND ISNULL(i.desconto,0) > 0 "
                "  AND CAST(pv.data AS DATE) BETWEEN %s AND %s " + cli_sql
            ))
            params += [data_ini, data_fim] + cli_p
        if tipo_v in ("", "os", "todos"):
            blocos.append((
                "SELECT 'OS' AS doc_tipo, o.codigo AS doc_numero, o.data_entrada AS doc_data, "
                "  c.nome AS cliente_nome, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, "
                "  i.cod_os_prod AS item_cod, COALESCE(pe.descricao, sv.descricao, 'Item') AS item_descricao, "
                "  i.quant AS qtd, i.preco_unitario AS p_normal, i.desconto AS desconto_unit, "
                "  NULL AS tipo_desconto, NULL AS percentual, NULL AS concedido_por "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "LEFT JOIN cliente c ON c.codigo = o.cliente "
                "LEFT JOIN funcionarios f ON f.codigo_int = i.vendedor "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE ISNULL(i.item_cancelado,0) = 0 AND ISNULL(i.desconto,0) > 0 "
                "  AND CAST(o.data_entrada AS DATE) BETWEEN %s AND %s " + cli_sql
            ))
            params += [data_ini, data_fim] + cli_p

        query = " UNION ALL ".join(blocos) + " ORDER BY doc_tipo, doc_numero, item_cod"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        docs: dict = {}
        ordem: list = []
        for r in rows:
            chave = (r["doc_tipo"], int(r["doc_numero"]))
            doc = docs.get(chave)
            if not doc:
                d = r.get("doc_data")
                doc = {
                    "tipo": r["doc_tipo"],
                    "numero": int(r["doc_numero"]),
                    "data": d.isoformat() if hasattr(d, "isoformat") else (str(d)[:10] if d else None),
                    "cliente_nome": (r.get("cliente_nome") or "").strip() or "—",
                    "vendedor_nome": (r.get("vendedor_nome") or "").strip() or "—",
                    "itens": [], "total_bruto": 0.0, "total_desconto": 0.0, "total_liquido": 0.0,
                }
                docs[chave] = doc
                ordem.append(chave)
            qtd = float(r.get("qtd") or 0)
            p_normal = float(r.get("p_normal") or 0)
            desconto_unit = float(r.get("desconto_unit") or 0)
            valor_bruto = round(p_normal * qtd, 2)
            valor_desconto = round(desconto_unit * qtd, 2)
            valor_liquido = round(valor_bruto - valor_desconto, 2)
            pct = float(r.get("percentual") or 0)
            if pct <= 0 and p_normal > 0:
                pct = round(desconto_unit / p_normal * 100, 2)
            tipo_d = r.get("tipo_desconto")
            tipo_label = None
            if r["doc_tipo"] == "PEDIDO":
                tipo_d = (tipo_d or "I").strip().upper() or "I"
                tipo_label = "Geral" if tipo_d == "G" else "Item"
            doc["itens"].append({
                "descricao": (r.get("item_descricao") or "Item").strip(),
                "qtd": qtd,
                "valor_bruto": valor_bruto,
                "percentual": pct,
                "valor_desconto": valor_desconto,
                "valor_liquido": valor_liquido,
                "tipo_desconto_label": tipo_label,
                "concedido_por": (r.get("concedido_por") or "").strip() or None,
            })
            doc["total_bruto"] += valor_bruto
            doc["total_desconto"] += valor_desconto
            doc["total_liquido"] += valor_liquido

        documentos = []
        tot_bruto = tot_desconto = tot_liquido = 0.0
        for chave in ordem:
            doc = docs[chave]
            doc["total_bruto"] = round(doc["total_bruto"], 2)
            doc["total_desconto"] = round(doc["total_desconto"], 2)
            doc["total_liquido"] = round(doc["total_liquido"], 2)
            tot_bruto += doc["total_bruto"]
            tot_desconto += doc["total_desconto"]
            tot_liquido += doc["total_liquido"]
            documentos.append(doc)

        totais = {
            "bruto": round(tot_bruto, 2),
            "desconto": round(tot_desconto, 2),
            "liquido": round(tot_liquido, 2),
            "desconto_pct": round((tot_desconto / tot_bruto * 100), 2) if tot_bruto else 0.0,
        }
        return {"success": True, "documentos": documentos, "totais": totais}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "documentos": [], "totais": {}}
    finally:
        conn.close()


async def descontos_concedidos(servidor, banco, data_ini, data_fim, tipo, cliente_nome):
    return await asyncio.to_thread(_descontos_concedidos_sync, servidor, banco, data_ini, data_fim, tipo, cliente_nome)
