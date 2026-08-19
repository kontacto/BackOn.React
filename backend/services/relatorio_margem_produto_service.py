"""Margem de Lucro (por produto) — Painel de Relatórios > Margem.

Migração de `Gilson Pneus\\FrmRelPecMLC.frm` (717 linhas, único ponto da
árvore VB6 com esse form — "Relatório de Margem de Lucro"). Rastreio
confirmou que a implementação já existente antes desta rodada
(`margem_lucro_service.py`/`relatorio-margem-lucro.tsx`) é na verdade o
outro relatório do grupo, **"Margem de Lucro x DAV"** (`FrmResDAV.frm`,
período/DAV/área de atuação) — este service aqui é o que faltava: uma
"foto" simples do catálogo, sem período, comparando o preço de venda e o
custo ATUAIS de cada produto Ativo.

Regras replicadas fielmente do legado:
- Só produtos com `pecas.situacao = 'A'`.
- Coluna de código exibida depende de `controle.cod_rel` (mesma coluna já
  usada em `controle_service.py` pro cabeçalho de recibo): `'I'` ->
  `codigo_int` (rótulo "Cód. Interno"), qualquer outro valor (inclusive
  vazio) -> `codigo_fab` (rótulo "Cód. Fábrica", default do legado).
- Filtro de Nível: opcional, mesma semântica já usada em
  `margem_lucro_service._nivel_clause` (código concatenado em blocos de 3
  dígitos, um por `nivel1..nivel5`) — sem nível selecionado, traz TODOS os
  produtos Ativos (equivalente ao item "TODOS" do combo do legado).
- Ordenação: por código ou por descrição (`Opt1`/`Opt2` do legado).
- Margem % por item: `((venda - custo) / custo) * 100`, arredondada a 2
  casas; custo zero devolve `margem_pct = None` (o legado mostra
  "-------" nesse caso, ver `Flex1.AddItem`) — decisão do frontend como
  exibir `None`.
- Total geral: soma de custo e soma de venda de TODOS os itens (não a
  média das margens individuais), margem calculada com a MESMA fórmula
  sobre os somatórios — réplica exata do `Flex1.AddItem "" & ... &
  "TOTAL GERAL" & ...` do legado.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _nivel_clause(nivel: Optional[str]) -> tuple[list, list]:
    clauses, params = [], []
    if nivel and nivel.strip():
        n = nivel.strip()
        parts = [n[i:i + 3] for i in range(0, len(n), 3)][:5]
        for idx, part in enumerate(parts, start=1):
            if part:
                clauses.append(f"nivel{idx} = %s")
                params.append(part)
    return clauses, params


def _margem_pct(venda: float, custo: float) -> Optional[float]:
    if custo == 0:
        return None
    return round((venda - custo) / custo * 100, 2)


def _margem_produto_sync(servidor: str, banco: str, nivel: Optional[str], ordenar_por: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha de conexão: {e}", "itens": [], "qtd_itens": 0,
                "total_custo": 0.0, "total_venda": 0.0, "margem_total_pct": None}
    try:
        cur = conn.cursor(as_dict=True)

        cur.execute("SELECT TOP 1 cod_rel FROM controle")
        row = cur.fetchone() or {}
        usa_interno = (row.get("cod_rel") or "").strip().upper() == "I"
        cod_col = "codigo_int" if usa_interno else "codigo_fab"
        codigo_label = "Cód. Interno" if usa_interno else "Cód. Fábrica"

        where = ["situacao = 'A'"]
        params: list = []
        nc, npar = _nivel_clause(nivel)
        where += nc
        params += npar

        order_col = "descricao" if ordenar_por == "descricao" else cod_col
        query = (
            f"SELECT {cod_col} AS codigo, descricao, custo_reposicao, p_venda "
            f"FROM pecas WHERE {' AND '.join(where)} ORDER BY {order_col}"
        )
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        itens = []
        total_custo = total_venda = 0.0
        for r in rows:
            custo = float(r.get("custo_reposicao") or 0)
            venda = float(r.get("p_venda") or 0)
            itens.append({
                "codigo": r.get("codigo"),
                "descricao": (r.get("descricao") or "").strip(),
                "custo": round(custo, 3),
                "venda": round(venda, 3),
                "margem_pct": _margem_pct(venda, custo),
            })
            total_custo += custo
            total_venda += venda

        return {
            "success": True,
            "codigo_label": codigo_label,
            "itens": itens,
            "qtd_itens": len(itens),
            "total_custo": round(total_custo, 3),
            "total_venda": round(total_venda, 3),
            "margem_total_pct": _margem_pct(total_venda, total_custo),
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "qtd_itens": 0,
                "total_custo": 0.0, "total_venda": 0.0, "margem_total_pct": None}
    finally:
        conn.close()


async def margem_produto(servidor, banco, nivel, ordenar_por):
    return await asyncio.to_thread(_margem_produto_sync, servidor, banco, nivel, ordenar_por)
