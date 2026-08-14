"""Resumo de Venda — Painel de Relatórios > Caixa.

Migração de `FrmRelFec.frm` (Geral, 837 linhas). O legado agrega
faturamento (`qtd*p_unit`) e custo (`custo_reposicao`) por nível de
produto (hierarquia `niveis`), lendo `comanda`+`movimentacao` (situação
'PG', serie_nf 'CM') cruzado com `pecas`/`servicos`/`veiculos`. O
algoritmo original monta a árvore via um loop aninhado gigante comparando
cada item contra as linhas já inseridas num FlexGrid — puro workaround de
VB6/FlexGrid (ver "Não replicar truques VB6" em CLAUDE.md); a regra real é
só um `GROUP BY nivel1..nivel5`, trivial em SQL moderno.

**Generalização Pedido/OS** (decisão do usuário, 2026-08-07 — mesma
diretriz do Apuração de Vendas-DRE): nesta migração `comanda`+
`movimentacao` não são o ledger geral de venda (são só o "envelope" de
fechamento — ver `fechamento_caixa_service.py` — com a única exceção real
sendo Contratos, que não faz parte deste relatório). As vendas reais estão
em `pedido_venda_prod`/`pedido_venda` e `os_produto`/`os` — mesmos joins já
validados em `relatorio_apuracao_vendas_service.py` (produto via
`pecas.codigo_int`/`servicos.codigo`, custo via `custo_reposicao`/
`custo_hora` no Pedido e `custo_os` já pronto no item de O.S.).

Simplificações conscientes:
- **Sem Veículos** — o legado cruza também com `VEICULOS`, mas
  `pedido_venda_prod`/`os_produto` nesta migração só referenciam
  `pecas`/`servicos` (prefixo 'P'/'S' do código interno) em qualquer outro
  ponto já migrado; não há evidência de item tipo veículo nesses fluxos,
  não portado sem confirmação.
- **Sem a seção de Saída de Caixa** que o `.frm` original anexa ao final —
  já existe como relatório próprio nesta migração
  (`relatorio-entrada-saida-caixa.tsx?tipo=S`), duplicar aqui seria
  redundante.
- **Filtro por atendente/vendedor** replicado (opcional) — `pv.vendedor`
  no Pedido (header), `i.vendedor` na O.S. (item), mesma assimetria já
  documentada no DRE.
- Venda é bruta (sem descontar `desconto`), mesma convenção dos demais
  relatórios desta migração.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _resumo_venda_sync(
    servidor: str, banco: str,
    data_ini: str, data_fim: str, vendedor: Optional[int],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "niveis": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        vend_ped_sql, vend_ped_p = ("AND pv.vendedor = %s", [vendedor]) if vendedor else ("", [])
        vend_os_sql, vend_os_p = ("AND i.vendedor = %s", [vendedor]) if vendedor else ("", [])

        query = (
            "SELECT pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5, "
            "  SUM(i.p_venda*i.qtd_pedida) AS venda, SUM(ISNULL(pe.custo_reposicao,0)*i.qtd_pedida) AS custo "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN pecas pe ON pe.codigo_int = i.produto "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND pv.data BETWEEN %s AND %s " + vend_ped_sql +
            " GROUP BY pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5 "
            "UNION ALL "
            "SELECT sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5, "
            "  SUM(i.p_venda*i.qtd_pedida), SUM(ISNULL(sv.custo_hora,0)*i.qtd_pedida) "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN servicos sv ON sv.codigo = i.produto "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND pv.data BETWEEN %s AND %s " + vend_ped_sql +
            " GROUP BY sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5 "
            "UNION ALL "
            "SELECT pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5, "
            "  SUM(i.p_venda*i.quant), SUM(i.custo_os*i.quant) "
            "FROM os_produto i JOIN os o ON o.codigo = i.os "
            "JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 AND LEFT(i.codigo_interno,1) = 'P' "
            "  AND o.data_entrada BETWEEN %s AND %s " + vend_os_sql +
            " GROUP BY pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5 "
            "UNION ALL "
            "SELECT sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5, "
            "  SUM(i.p_venda*i.quant), SUM(i.custo_os*i.quant) "
            "FROM os_produto i JOIN os o ON o.codigo = i.os "
            "JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 AND LEFT(i.codigo_interno,1) = 'S' "
            "  AND o.data_entrada BETWEEN %s AND %s " + vend_os_sql +
            " GROUP BY sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5"
        )
        params = (
            [data_ini, data_fim] + vend_ped_p
            + [data_ini, data_fim] + vend_ped_p
            + [data_ini, data_fim] + vend_os_p
            + [data_ini, data_fim] + vend_os_p
        )
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        por_nivel: dict[str, dict] = {}
        for r in rows:
            partes = [(r.get(f"nivel{i}") or "").strip() for i in range(1, 6)]
            codigo = "".join(partes)
            item = por_nivel.setdefault(codigo, {"codigo": codigo, "venda": 0.0, "custo": 0.0})
            item["venda"] += float(r.get("venda") or 0)
            item["custo"] += float(r.get("custo") or 0)

        niveis = []
        tot_venda = tot_custo = 0.0
        for codigo, item in por_nivel.items():
            venda = item["venda"]
            custo = item["custo"]
            margem = venda - custo
            niveis.append({
                "codigo": codigo,
                "venda": round(venda, 2),
                "custo": round(custo, 2),
                "margem": round(margem, 2),
                "margem_pct": round((margem / venda * 100), 2) if venda else 0.0,
            })
            tot_venda += venda
            tot_custo += custo
        niveis.sort(key=lambda x: x["codigo"])

        margem_geral = tot_venda - tot_custo
        totais = {
            "venda": round(tot_venda, 2),
            "custo": round(tot_custo, 2),
            "margem": round(margem_geral, 2),
            "margem_pct": round((margem_geral / tot_venda * 100), 2) if tot_venda else 0.0,
        }
        return {"success": True, "niveis": niveis, "totais": totais}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "niveis": [], "totais": {}}
    finally:
        conn.close()


async def resumo_venda(servidor, banco, data_ini, data_fim, vendedor):
    return await asyncio.to_thread(_resumo_venda_sync, servidor, banco, data_ini, data_fim, vendedor)
