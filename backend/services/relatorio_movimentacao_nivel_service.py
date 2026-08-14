"""Movimentações por Nível — Painel de Relatórios > Estoque.

Migração de `frmrelvenlojas.frm` (pasta `Gilson Pneus\\`, referenciado
pelo `backon.vbp` real do Kontacto — mesmo padrão de arquivo
compartilhado entre pastas de linha de negócio já visto em outros
relatórios desta sessão). **Achado de correção**: a caption interna do
form diz "Transferência para as Filiais", mas isso é artefato de
copiar-colar de outro form da pasta específica de cliente — a query real
não tem nada a ver com filiais/transferência entre lojas, é só soma de
`qtd`/`qtd*p_unit` de `movimentacao` por UM tipo de movimentação
escolhido, agrupada por nível de produto, num período. Replicado só essa
parte (que bate com o nome do botão no painel, "Movimentações por
Nível"), não o conceito de filial.

Simplificações conscientes:
- **`PECASEQ` (produtos equivalentes/similares) não portado** — o legado
  consolida o movimento de um produto e seus equivalentes sob um único
  código antes de agrupar por nível; aqui cada produto soma pro seu
  próprio nível, sem essa consolidação.
- Workaround de tabela temporária (`create table teste`) do legado vira
  `GROUP BY` direto — puro artefato de VB6/Access.
"""
import asyncio

from db.connection import _open_conn


def _movimentacao_nivel_sync(servidor: str, banco: str, tipo: str, data_ini: str, data_fim: str) -> dict:
    if not (tipo or "").strip():
        return {"success": False, "message": "Selecione o tipo de movimentação.", "itens": [], "totais": {}}
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.nivel1, p.nivel2, p.nivel3, p.nivel4, p.nivel5, "
            "  SUM(m.qtd) AS qtd, SUM(m.qtd * m.p_unit) AS valor "
            "FROM movimentacao m "
            "JOIN pecas p ON p.codigo_int = m.codigo_int "
            "WHERE m.tipo = %s AND CAST(m.data AS DATE) BETWEEN %s AND %s "
            "GROUP BY p.nivel1, p.nivel2, p.nivel3, p.nivel4, p.nivel5",
            (tipo, data_ini, data_fim),
        )
        rows = cur.fetchall()
        cur.close()

        itens = []
        tot_qtd = tot_valor = 0.0
        for r in rows:
            partes = [(r.get(f"nivel{i}") or "").strip() for i in range(1, 6)]
            codigo = "".join(partes)
            qtd = float(r.get("qtd") or 0)
            valor = round(float(r.get("valor") or 0), 2)
            itens.append({"codigo": codigo, "qtd": qtd, "valor": valor})
            tot_qtd += qtd
            tot_valor += valor
        itens.sort(key=lambda x: x["codigo"])

        return {
            "success": True, "itens": itens,
            "totais": {"qtd": round(tot_qtd, 2), "valor": round(tot_valor, 2)},
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def movimentacao_nivel(servidor, banco, tipo, data_ini, data_fim):
    return await asyncio.to_thread(_movimentacao_nivel_sync, servidor, banco, tipo, data_ini, data_fim)
