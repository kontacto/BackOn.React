"""Apuração de Vendas - DRE — Painel de Relatórios > Caixa.

Migração de `FrmRelAPV.frm` — usada a variante `Kontacto\\FrmRelAPV.frm`
(1953 linhas, mais completa que `Geral\\` — este form nem existe em
`Geral\\` — e que `consult\\`), ver PENDENCIAS.md > "Painel de Relatórios
(VB6)" pro rastreio completo.

**Fase 1 (esta implementação)** — o núcleo do DRE: 5 categorias de receita
por mês, custo, margem. Decisão do usuário (2026-08-07, `AskUserQuestion`):
generalizar as categorias que no legado só liam `comanda` (Venda Produtos/
Serviços, Produtos/Serviços O.S.) para lerem as tabelas REAIS desta
migração (`pedido_venda`/`pedido_venda_prod`, `os`/`os_produto`) em vez de
replicar a leitura via `comanda`+`movimentacao` do legado — nesta migração
Pedido e O.S. já são documentos próprios, não passam por `comanda` como
ledger de item (`comanda` aqui é só o "envelope" de fechamento/pagamento,
ver `fechamento_caixa_service.py`). **Exceção: "Contratos" continua via
`comanda`+`movimentacao`** — não é workaround, é a tabela REAL usada pelo
faturamento de Contratos nesta migração (`contratos_service.py`'s
`_faturar_contratos_sync`, grava `movimentacao(codigo_int=cod_servico_
contrato, serie_nf='CM')` + `comanda`, sem equivalente em `pedido_venda`/
`os` — decisão de arquitetura já tomada e documentada em
`project_contratos`).

Categorias e fonte real:
- **Contratos**: `movimentacao` (serie_nf='CM', codigo_int=cod_servico_
  contrato) + `comanda` (situacao='PG').
- **Produtos O.S. / Serviços O.S.**: `os_produto` (codigo_interno prefixo
  'P'/'S', ver docstring de `os_itens_service.py`) + `os` (situacao='PG').
- **Venda Produtos / Venda Serviços**: `pedido_venda_prod` (produto→pecas
  ou →servicos) + `pedido_venda` (situacao='PG').

Simplificações conscientes desta Fase 1 (não são regra de negócio perdida
— ver "Não replicar truques VB6" em CLAUDE.md):
- **Sempre agrupa por mês/ano** — o legado tinha uma lógica dupla (período
  alinhado a mês(es) inteiros → linhas mensais; período parcial → uma
  única linha "Período") só por limitação do FlexGrid; agrupar sempre por
  mês é estritamente mais informativo e não perde nenhuma regra de
  negócio real.
- **"Incluir Vendas de Garantia" não implementado** — no legado é
  `comanda.tipo=0`, mas `pedido_venda.tipo`/`os` desta migração já foram
  reaproveitados para outra coisa (tipo Mesa/Comanda/Balcão do Pedido
  Bar — ver "Campo Tipo do Pedido Bar" em CLAUDE.md), não existe campo
  equivalente direto. Fechamento de Caixa já resolve um problema parecido
  via `forma_pagamento.FORMA_PAG_GARANTIA` (join pela forma de pagamento
  usada no fechamento) — não replicado aqui ainda porque exigiria juntar
  cada uma das 3 fontes às tabelas de forma de pagamento
  (`pedido_venda_dinheiro`/etc., `os_dinheiro`/etc.) só para esse filtro;
  fica registrado como possível Fase 1.5 se o usuário pedir.
- **Sem "Despesas"** (Fase 2 — depende de um sub-sistema próprio de seleção
  de classes/sub_classes de despesa + integração com `movimentacoes_
  centro_custo`, ver `CalculaDespesas`/`executa2` no `.frm`) — Margem
  aqui é só `Total - Custo`, não `Total - Custo - Despesas`.
- **Sem "Por Nível"/"Produto específico"/"Preço Médio"/impressão
  detalhada por item** (Fase 3) — só o grid consolidado por mês.
- **Preço de venda é bruto** (sem descontar `desconto`) — mesma convenção
  já usada em `_relatorio_pedidos_sync`/`_relatorio_os_desc_margem_sync`
  (desconto é rastreado à parte, não abatido do valor de venda "bruto").
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _cod_servico_contrato_sync(cur) -> str:
    cur.execute("SELECT cod_servico_contrato FROM controle")
    row = cur.fetchone()
    return ((row or {}).get("cod_servico_contrato") or "S999").strip()


def _apuracao_vendas_sync(
    servidor: str, banco: str,
    data_ini: str, data_fim: str,
    vendedor: Optional[int], regiao: Optional[int], segmento: Optional[str],
    rota: Optional[int], tipo_cliente: Optional[int],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "meses": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cod_contrato = _cod_servico_contrato_sync(cur)

        cli_filtros = []
        cli_params: list = []
        if regiao:
            cli_filtros.append("cli.regiao = %s")
            cli_params.append(regiao)
        if segmento:
            cli_filtros.append("cli.segmento = %s")
            cli_params.append(segmento)
        if rota:
            cli_filtros.append("cli.rota = %s")
            cli_params.append(rota)
        if tipo_cliente:
            cli_filtros.append("cli.cliente_forn = %s")
            cli_params.append(tipo_cliente)
        cli_sql = ("AND " + " AND ".join(cli_filtros)) if cli_filtros else ""

        def _vend_sql(col: str) -> tuple[str, list]:
            if vendedor:
                return f"AND {col} = %s", [vendedor]
            return "", []

        vend_contrato_sql, vend_contrato_p = _vend_sql("m.vendedor")
        vend_os_sql, vend_os_p = _vend_sql("i.vendedor")
        vend_ped_sql, vend_ped_p = _vend_sql("pv.vendedor")

        query = (
            "SELECT 'CONTRATO' AS categoria, YEAR(c.data) AS ano, MONTH(c.data) AS mes, "
            "  SUM(m.qtd*m.p_unit) AS total, SUM(m.qtd*ISNULL(m.custo_mov,0)) AS custo "
            "FROM movimentacao m "
            "JOIN comanda c ON c.comanda = m.num_nf AND m.serie_nf = 'CM' "
            "JOIN cliente cli ON cli.codigo = c.cliente "
            "WHERE c.situacao = 'PG' AND m.codigo_int = %s "
            "  AND c.data BETWEEN %s AND %s " + cli_sql + " " + vend_contrato_sql +
            " GROUP BY YEAR(c.data), MONTH(c.data) "
            "UNION ALL "
            "SELECT 'OS_PRODUTO', YEAR(o.data_entrada), MONTH(o.data_entrada), "
            "  SUM(i.p_venda*i.quant), SUM(i.custo_os*i.quant) "
            "FROM os_produto i JOIN os o ON o.codigo = i.os "
            "JOIN cliente cli ON cli.codigo = o.cliente "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 AND LEFT(i.codigo_interno,1) = 'P' "
            "  AND o.data_entrada BETWEEN %s AND %s " + cli_sql + " " + vend_os_sql +
            " GROUP BY YEAR(o.data_entrada), MONTH(o.data_entrada) "
            "UNION ALL "
            "SELECT 'OS_SERVICO', YEAR(o.data_entrada), MONTH(o.data_entrada), "
            "  SUM(i.p_venda*i.quant), SUM(i.custo_os*i.quant) "
            "FROM os_produto i JOIN os o ON o.codigo = i.os "
            "JOIN cliente cli ON cli.codigo = o.cliente "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 AND LEFT(i.codigo_interno,1) = 'S' "
            "  AND o.data_entrada BETWEEN %s AND %s " + cli_sql + " " + vend_os_sql +
            " GROUP BY YEAR(o.data_entrada), MONTH(o.data_entrada) "
            "UNION ALL "
            "SELECT 'PEDIDO_PRODUTO', YEAR(pv.data), MONTH(pv.data), "
            "  SUM(i.p_venda*i.qtd_pedida), SUM(ISNULL(pe.custo_reposicao,0)*i.qtd_pedida) "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN cliente cli ON cli.codigo = pv.cliente "
            "JOIN pecas pe ON pe.codigo_int = i.produto "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND pv.data BETWEEN %s AND %s " + cli_sql + " " + vend_ped_sql +
            " GROUP BY YEAR(pv.data), MONTH(pv.data) "
            "UNION ALL "
            "SELECT 'PEDIDO_SERVICO', YEAR(pv.data), MONTH(pv.data), "
            "  SUM(i.p_venda*i.qtd_pedida), SUM(ISNULL(sv.custo_hora,0)*i.qtd_pedida) "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN cliente cli ON cli.codigo = pv.cliente "
            "JOIN servicos sv ON sv.codigo = i.produto "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND pv.data BETWEEN %s AND %s " + cli_sql + " " + vend_ped_sql +
            " GROUP BY YEAR(pv.data), MONTH(pv.data)"
        )
        params = (
            [cod_contrato, data_ini, data_fim] + cli_params + vend_contrato_p
            + [data_ini, data_fim] + cli_params + vend_os_p
            + [data_ini, data_fim] + cli_params + vend_os_p
            + [data_ini, data_fim] + cli_params + vend_ped_p
            + [data_ini, data_fim] + cli_params + vend_ped_p
        )
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        CATS = ["CONTRATO", "OS_PRODUTO", "OS_SERVICO", "PEDIDO_PRODUTO", "PEDIDO_SERVICO"]
        por_mes: dict[tuple, dict] = {}
        for r in rows:
            chave = (int(r["ano"]), int(r["mes"]))
            m = por_mes.setdefault(chave, {c: {"total": 0.0, "custo": 0.0} for c in CATS})
            m[r["categoria"]]["total"] += float(r["total"] or 0)
            m[r["categoria"]]["custo"] += float(r["custo"] or 0)

        meses = []
        tot_geral = {"total": 0.0, "custo": 0.0}
        for (ano, mes) in sorted(por_mes.keys()):
            cats = por_mes[(ano, mes)]
            total_mes = sum(cats[c]["total"] for c in CATS)
            custo_mes = sum(cats[c]["custo"] for c in CATS)
            margem = total_mes - custo_mes
            margem_pct = round((margem / total_mes * 100), 2) if total_mes else 0.0
            meses.append({
                "ano": ano, "mes": mes,
                "contratos": round(cats["CONTRATO"]["total"], 2),
                "produtos_os": round(cats["OS_PRODUTO"]["total"], 2),
                "servicos_os": round(cats["OS_SERVICO"]["total"], 2),
                "venda_produtos": round(cats["PEDIDO_PRODUTO"]["total"], 2),
                "venda_servicos": round(cats["PEDIDO_SERVICO"]["total"], 2),
                "total": round(total_mes, 2),
                "custo": round(custo_mes, 2),
                "margem": round(margem, 2),
                "margem_pct": margem_pct,
            })
            tot_geral["total"] += total_mes
            tot_geral["custo"] += custo_mes

        margem_geral = tot_geral["total"] - tot_geral["custo"]
        totais = {
            "total": round(tot_geral["total"], 2),
            "custo": round(tot_geral["custo"], 2),
            "margem": round(margem_geral, 2),
            "margem_pct": round((margem_geral / tot_geral["total"] * 100), 2) if tot_geral["total"] else 0.0,
        }
        return {"success": True, "meses": meses, "totais": totais}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "meses": [], "totais": {}}
    finally:
        conn.close()


async def apuracao_vendas(servidor, banco, data_ini, data_fim, vendedor, regiao, segmento, rota, tipo_cliente):
    return await asyncio.to_thread(
        _apuracao_vendas_sync, servidor, banco, data_ini, data_fim, vendedor, regiao, segmento, rota, tipo_cliente
    )
