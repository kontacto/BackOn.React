"""Venda por Região/Segmento — Painel de Relatórios > Vendas.

Migração de `Guerengases\\FrmVenTot.frm` (847 linhas, "Relatório de
Vendas" / "Venda por Região/Segmento"). O legado monta a SQL (SELECT/
GROUP BY/WHERE, e até a tabela temporária de destino) **em string, na
hora**, conforme quais das 4 dimensões (Região/Segmento/Rota/Vendedor) o
usuário marca como "não filtrar"/"todos"/valor específico — puro
workaround de VB6 (ver "Não replicar truques VB6" em CLAUDE.md); a regra
real é só "agrupamento configurável por até 4 dimensões".

Generalizado (mesma diretriz 2026-08-07) pra ler `pedido_venda_prod`/
`pedido_venda` e `os_produto`/`os` diretamente, sem passar por `comanda`
(o legado lia via `comanda`+`movimentacao`, com `movimentacao.vendedor`
resolvendo o vendedor — aqui usa `pedido_venda.vendedor` no Pedido,
`os_produto.vendedor` na O.S., mesma assimetria cabeçalho/item já
documentada em Apuração de Vendas-DRE/Ranking de Vendas). Sem Veículos
(mesma simplificação consciente do resto do grupo).

**Implementação**: busca sempre as 4 dimensões de uma vez (uma query só,
baixa cardinalidade — regiões/segmentos/rotas/vendedores são tabelas
pequenas), agrega no Python pela combinação (`regiao`,`segmento`,`rota`,
`vendedor`), e só então RE-agrupa pelo subconjunto de dimensões que o
frontend pediu (`dimensoes`, CSV de `regiao,segmento,rota,vendedor`) —
sem nenhuma dimensão marcada, retorna só o total geral (equivalente ao
"tudo NÃO FILTRAR" do legado). Fallback de rótulo igual ao legado: "SEM
REGIÃO"/"SEM SEGMENTO"/"SEM ROTA"/"SEM VENDEDOR" quando o cliente/pedido
não tem o dado cadastrado.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

SEM = {"regiao": "SEM REGIÃO", "segmento": "SEM SEGMENTO", "rota": "SEM ROTA", "vendedor": "SEM VENDEDOR"}


def _venda_regiao_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str, dimensoes: Optional[str],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        query = (
            "SELECT r.descricao AS regiao, sg.descricao AS segmento, rt.descricao AS rota, "
            "  COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor, "
            "  SUM(i.qtd_pedida) AS qtd, SUM(i.p_venda*i.qtd_pedida) AS valor "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN cliente cli ON cli.codigo = pv.cliente "
            "LEFT JOIN regioes r ON r.codigo = cli.regiao "
            "LEFT JOIN segmentos sg ON sg.codigo = cli.segmento "
            "LEFT JOIN rotas rt ON rt.codigo = cli.rota "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND pv.data BETWEEN %s AND %s "
            "GROUP BY r.descricao, sg.descricao, rt.descricao, f.nome_guerra, f.nome "
            "UNION ALL "
            "SELECT r.descricao, sg.descricao, rt.descricao, "
            "  COALESCE(NULLIF(f.nome_guerra,''), f.nome), "
            "  SUM(i.quant), SUM(i.p_venda*i.quant) "
            "FROM os_produto i "
            "JOIN os o ON o.codigo = i.os "
            "JOIN cliente cli ON cli.codigo = o.cliente "
            "LEFT JOIN regioes r ON r.codigo = cli.regiao "
            "LEFT JOIN segmentos sg ON sg.codigo = cli.segmento "
            "LEFT JOIN rotas rt ON rt.codigo = cli.rota "
            "LEFT JOIN funcionarios f ON f.codigo_int = i.vendedor "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND o.data_entrada BETWEEN %s AND %s "
            "GROUP BY r.descricao, sg.descricao, rt.descricao, f.nome_guerra, f.nome"
        )
        params = [data_ini, data_fim, data_ini, data_fim]
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        dims_ativas = [d.strip() for d in (dimensoes or "").split(",") if d.strip() in SEM]

        por_chave: dict = {}
        for r in rows:
            valores = {
                "regiao": (r.get("regiao") or "").strip() or SEM["regiao"],
                "segmento": (r.get("segmento") or "").strip() or SEM["segmento"],
                "rota": (r.get("rota") or "").strip() or SEM["rota"],
                "vendedor": (r.get("vendedor") or "").strip() or SEM["vendedor"],
            }
            chave = tuple(valores[d] for d in dims_ativas) if dims_ativas else ("TOTAL",)
            item = por_chave.setdefault(chave, {d: valores[d] for d in dims_ativas} | {"qtd": 0.0, "valor": 0.0})
            item["qtd"] += float(r.get("qtd") or 0)
            item["valor"] += float(r.get("valor") or 0)

        itens = []
        tot_qtd = tot_valor = 0.0
        for chave in sorted(por_chave.keys()):
            item = por_chave[chave]
            item["qtd"] = round(item["qtd"], 3)
            item["valor"] = round(item["valor"], 2)
            itens.append(item)
            tot_qtd += item["qtd"]
            tot_valor += item["valor"]

        return {
            "success": True, "dimensoes": dims_ativas, "itens": itens,
            "totais": {"qtd": round(tot_qtd, 3), "valor": round(tot_valor, 2)},
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def venda_regiao(servidor, banco, data_ini, data_fim, dimensoes):
    return await asyncio.to_thread(_venda_regiao_sync, servidor, banco, data_ini, data_fim, dimensoes)
