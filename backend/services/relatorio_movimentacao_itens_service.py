"""Movimentação de Itens — Painel de Relatórios > Estoque.

Migração de `Geral\\FrmRelMovCli.frm`. Achado importante (2026-08-07):
`movimentacao` já é o ledger universal desta migração também, não só do
legado — confirmado por grep de `INSERT INTO movimentacao` em
`pedidos_service.py` (`tipo='S01', serie_nf='CM'`, ao faturar — cria uma
`comanda` "envelope" na hora, exatamente como `fechamento_caixa_service.py`
já documentava), `os_service.py`, `checkout_service.py`,
`contratos_service.py`, `requisicao_service.py` (`serie_nf='RQ'`),
`movimentacao_produtos_service.py` (`serie_nf='MV'`),
`inventario_service.py` (`serie_nf='IV'`, tipo `E00`/`S00` — mesmos
códigos do legado) e `agenda_service.py`. `tipo_mov` (codigo/descricao/
atualiza_est) também já é real e usada (`lookups_service.py`).

**Simplificação de arquitetura consciente**: o `.frm` original reconstrói
o ledger via 5+ branches `UNION ALL` por origem (Comanda/Requisição/
Inventário), com exclusão via `comanda_nf` pra não contar duas vezes uma
venda já com NF emitida — necessário porque no legado `movimentacao`
nem sempre é confiável sozinho. Nesta migração isso não é necessário:
como confirmado acima, todo módulo já grava fielmente em `movimentacao`
na hora certa — um `SELECT` direto (com joins simples pra `pecas`/
`servicos`/`tipo_mov`/`funcionarios`) já é a fonte completa e correta.

**Origem via `serie_nf`** — `CM` mistura Pedido/OS/Contrato/Checkout (todos
usam a mesma série ao faturar); não dá pra distinguir a origem exata sem
voltar em `COMANDA_PED`/`comanda_os`/`comanda_contrato`, não replicado
nesta primeira versão (fica como "Venda", rótulo genérico).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

ORIGEM_LABEL = {"CM": "Venda", "RQ": "Requisição", "IV": "Inventário", "MV": "Movimentação Manual"}

_ORDEM_COL = {"data": "m.data", "produto": "produto_descricao", "tipo": "m.tipo"}


def _movimentacao_itens_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    produto: Optional[str], tipo: Optional[str], entrada_saida: Optional[str],
    origem: Optional[str], ordenar_por: Optional[str],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = ["CAST(m.data AS DATE) BETWEEN %s AND %s"]
        params: list = [data_ini, data_fim]
        if produto and produto.strip():
            where.append("m.codigo_int = %s")
            params.append(produto.strip())
        tipos = [t.strip() for t in (tipo or "").split(",") if t.strip()]
        if tipos:
            where.append(f"m.tipo IN ({','.join(['%s'] * len(tipos))})")
            params.extend(tipos)
        if entrada_saida in ("E", "S"):
            where.append("LEFT(m.tipo,1) = %s")
            params.append(entrada_saida)
        origens = [o.strip() for o in (origem or "").split(",") if o.strip()]
        if origens:
            where.append(f"m.serie_nf IN ({','.join(['%s'] * len(origens))})")
            params.extend(origens)

        ordem = _ORDEM_COL.get(ordenar_por or "data", "m.data")
        cur.execute(
            "SELECT TOP 500 m.id_mov, m.data, m.tipo, tm.descricao AS tipo_desc, m.codigo_int, "
            "  COALESCE(pe.descricao, sv.descricao, m.codigo_int) AS produto_descricao, "
            "  m.qtd, m.p_unit, m.num_nf, m.serie_nf, "
            "  COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome "
            "FROM movimentacao m "
            "LEFT JOIN tipo_mov tm ON tm.codigo = m.tipo "
            "LEFT JOIN pecas pe ON pe.codigo_int = m.codigo_int "
            "LEFT JOIN servicos sv ON sv.codigo = m.codigo_int "
            "LEFT JOIN funcionarios f ON f.codigo_int = m.vendedor "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY {ordem} DESC",
            tuple(params),
        )
        itens = []
        tot_qtd = tot_valor = 0.0
        for r in cur.fetchall():
            d = r.get("data")
            qtd = float(r.get("qtd") or 0)
            p_unit = float(r.get("p_unit") or 0)
            valor = round(qtd * p_unit, 2)
            serie = (r.get("serie_nf") or "").strip()
            itens.append({
                "data": d.isoformat() if hasattr(d, "isoformat") else (str(d)[:10] if d else None),
                "tipo": (r.get("tipo") or "").strip(),
                "tipo_desc": (r.get("tipo_desc") or "").strip() or "—",
                "codigo_int": (r.get("codigo_int") or "").strip(),
                "produto_descricao": (r.get("produto_descricao") or "").strip(),
                "qtd": qtd,
                "p_unit": round(p_unit, 2),
                "valor": valor,
                "num_nf": r.get("num_nf"),
                "origem": serie,
                "origem_label": ORIGEM_LABEL.get(serie, serie or "—"),
                "vendedor_nome": (r.get("vendedor_nome") or "").strip() or "—",
            })
            tot_qtd += qtd
            tot_valor += valor
        cur.close()
        return {
            "success": True, "itens": itens,
            "totais": {"qtd": round(tot_qtd, 2), "valor": round(tot_valor, 2)},
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def movimentacao_itens(servidor, banco, data_ini, data_fim, produto, tipo, entrada_saida, origem, ordenar_por):
    return await asyncio.to_thread(
        _movimentacao_itens_sync, servidor, banco, data_ini, data_fim, produto, tipo, entrada_saida, origem, ordenar_por
    )
