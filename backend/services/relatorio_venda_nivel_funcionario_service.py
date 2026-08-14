"""Venda por Vendedor × Nível — Painel de Relatórios > Vendas.

Migração de `Kontacto\\frmrelvennivfun.frm` (1357 linhas, "Vendas por
Níveis por Funcionário" / "Venda por Vendedor/Executor O.S"). Mesmo
toggle Vendedor(Pedido)/Executor(O.S.) de "Itens por Funcionário"
(`relatorio_itens_funcionario_service.py`), mas agregado por NÍVEL de
produto (venda/custo/margem) em vez de só por funcionário isoladamente —
mesmo padrão de agregação por nível já usado em "Resumo de Venda" (Caixa),
reaproveitando `buildNivelBreadcrumb` no frontend.

Generalizado (mesma diretriz 2026-08-07) pra ler `pedido_venda_prod`/
`pedido_venda` (Vendedor) e `os_produto`/`os` (Executor) diretamente, sem
passar por `comanda`. Custo: `custo_reposicao` (produto)/`custo_hora`
(serviço) no Pedido, `custo_os` já pronto no item de O.S. — mesmas
colunas já validadas em Resumo de Venda/Apuração de Vendas-DRE.

**Simplificação consciente**: o legado permite "TODOS os funcionários"
com quebra por funcionário dentro do mesmo relatório (2 dimensões
empilhadas: funcionário × nível). Aqui só "todos agregados juntos" ou "um
funcionário específico" — evita empilhar 2 dimensões de agrupamento na
mesma tela; se o usuário precisar comparar vários funcionários lado a
lado, roda o relatório uma vez por funcionário.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _venda_nivel_funcionario_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    modo: str, funcionario: Optional[int],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "niveis": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        func_nome = None
        if funcionario:
            cur.execute(
                "SELECT COALESCE(NULLIF(nome_guerra,''), nome) AS nome FROM funcionarios WHERE codigo_int = %s",
                (funcionario,),
            )
            row = cur.fetchone()
            func_nome = (row or {}).get("nome")

        if modo == "executor":
            func_sql, func_p = ("AND i.executor = %s ", [funcionario]) if funcionario else ("", [])
            query = (
                "SELECT pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5, "
                "  SUM(i.p_venda*i.quant) AS venda, SUM(ISNULL(i.custo_os,0)*i.quant) AS custo "
                "FROM os_produto i JOIN os o ON o.codigo = i.os "
                "JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 AND LEFT(i.codigo_interno,1) = 'P' "
                "  AND o.data_entrada BETWEEN %s AND %s " + func_sql +
                "GROUP BY pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5 "
                "UNION ALL "
                "SELECT sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5, "
                "  SUM(i.p_venda*i.quant), SUM(ISNULL(i.custo_os,0)*i.quant) "
                "FROM os_produto i JOIN os o ON o.codigo = i.os "
                "JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 AND LEFT(i.codigo_interno,1) = 'S' "
                "  AND o.data_entrada BETWEEN %s AND %s " + func_sql +
                "GROUP BY sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5"
            )
            params = [data_ini, data_fim] + func_p + [data_ini, data_fim] + func_p
        else:
            func_sql, func_p = ("AND pv.vendedor = %s ", [funcionario]) if funcionario else ("", [])
            query = (
                "SELECT pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5, "
                "  SUM(i.p_venda*i.qtd_pedida) AS venda, SUM(ISNULL(pe.custo_reposicao,0)*i.qtd_pedida) AS custo "
                "FROM pedido_venda_prod i JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "JOIN pecas pe ON pe.codigo_int = i.produto "
                "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND pv.data BETWEEN %s AND %s " + func_sql +
                "GROUP BY pe.nivel1, pe.nivel2, pe.nivel3, pe.nivel4, pe.nivel5 "
                "UNION ALL "
                "SELECT sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5, "
                "  SUM(i.p_venda*i.qtd_pedida), SUM(ISNULL(sv.custo_hora,0)*i.qtd_pedida) "
                "FROM pedido_venda_prod i JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "JOIN servicos sv ON sv.codigo = i.produto "
                "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND pv.data BETWEEN %s AND %s " + func_sql +
                "GROUP BY sv.nivel1, sv.nivel2, sv.nivel3, sv.nivel4, sv.nivel5"
            )
            params = [data_ini, data_fim] + func_p + [data_ini, data_fim] + func_p

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        por_nivel: dict = {}
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

        margem_geral = tot_venda - tot_custo
        return {
            "success": True, "func_nome": func_nome, "niveis": niveis,
            "totais": {
                "venda": round(tot_venda, 2), "custo": round(tot_custo, 2),
                "margem": round(margem_geral, 2),
                "margem_pct": round((margem_geral / tot_venda * 100), 2) if tot_venda else 0.0,
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "niveis": [], "totais": {}}
    finally:
        conn.close()


async def venda_nivel_funcionario(servidor, banco, data_ini, data_fim, modo, funcionario):
    return await asyncio.to_thread(
        _venda_nivel_funcionario_sync, servidor, banco, data_ini, data_fim, modo, funcionario
    )
