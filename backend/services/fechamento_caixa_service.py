"""Fechamento de Caixa (Comandas) — consolidado de recebimentos por forma de
pagamento + entradas/saídas de caixa + despesas, num período. Migrado de
`frmFechaCaixa.frm` (Kontacto).

Correção de arquitetura importante em relação ao legado (2026-07-16):
o `.frm` lê os lançamentos de forma de pagamento das tabelas
`comanda_dinheiro`/`comanda_cheque`/... (uma por tipo), populadas pela
rotina completa de fechamento de caixa do PDV do legado (`GeraComanda`).
Esta migração **não grava nessas tabelas** — o Faturar Pedido
(`pedidos_service._faturar_pedido_sync`) grava a forma de pagamento nas
tabelas `pedido_venda_dinheiro`/`pedido_venda_cheque`/... (mesmo esquema
genérico de `DavPagamento` já usado na feature "Forma de Pagamento", ver
`pedido_common.py`). Consultar `comanda_dinheiro`/etc. aqui faria este
relatório voltar sempre vazio para qualquer comanda gerada por este app.
Por isso a agregação abaixo soma `pedido_venda_*`/`os_*` (via
`COMANDA_PED`/`comanda_os`, as tabelas de vínculo comanda→documento), não
as tabelas `comanda_*`. Ver PENDENCIAS.md > "Fechamento de Caixa" para o
detalhe completo desta decisão.

Simplificações conscientes em relação ao legado (ver "Não replicar truques
VB6" em CLAUDE.md):
- Sem "Empresas" (Filial/multi-banco) — este app opera com uma conexão
  (servidor+banco) por vez; não existe em nenhum outro lugar da migração o
  conceito de trocar de banco dentro da mesma tela (diferente do relatório
  de Margem de Lucro, que consolida MÚLTIPLAS conexões já salvas do
  usuário — não é o mesmo conceito de "Filial" do legado).
- Sem Troco/Gorjeta/Vale Devolução — nenhuma tela migrada grava
  `comanda_troco`/`comanda_gorjeta`/`vale_devolucao`/
  `comanda_vale_devolucao` ainda; portar a leitura sem nenhuma escrita
  correspondente só adicionaria seções sempre vazias.
- Sem o bloco de `Select Case Combo1.ListIndex` do legado (monta uma
  `SqlStr` de listagem de Comanda por situação) — essa string é montada em
  `cmdSelecionar_Click` mas nunca é lida por `FazTudo`; é código morto no
  original, não uma regra de negócio.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.pedido_common import FORMA_PAG_SUFIXO_TIPO, FORMA_PAG_VALOR_COL

TIPO_LABEL = {
    "DI": "Dinheiro", "VA": "Vale", "CH": "Cheque", "CC": "Cartão de Crédito",
    "TI": "Tícket", "DU": "Duplicata", "CD": "Cartão de Débito", "FI": "Financiado",
}


def _resumo_forma_pagamento_sync(
    cur, data_ini: str, data_fim: str, atendente: Optional[int],
    campo_atendente: str, area: Optional[int], exibir_garantias: bool,
) -> list[dict]:
    """Agrega os lançamentos das 8 tabelas de forma de pagamento
    (pedido_venda_*/os_*, via COMANDA_PED/comanda_os) por descrição —
    réplica das 8 consultas quase-idênticas de `FazTudo` (uma por tipo),
    generalizada num loop sobre `FORMA_PAG_VALOR_COL` em vez de repetir o
    SQL 8 vezes."""
    por_descricao: dict[str, dict] = {}
    for tipo_forma, valor_col in FORMA_PAG_VALOR_COL.items():
        sufixo = FORMA_PAG_SUFIXO_TIPO[tipo_forma]
        sql = (
            "SELECT fp.descricao, fp.tipo, fp.nao_totaliza_caixa, SUM(x.valor) AS total "
            "FROM ("
            f"  SELECT pv.forma_pag, pv.{valor_col} AS valor, c.data, c.{campo_atendente} AS atend, c.area_atuacao "
            "   FROM COMANDA_PED cp "
            "   JOIN comanda c ON c.comanda = cp.comanda "
            f"  JOIN pedido_venda_{sufixo} pv ON pv.pedido_venda = cp.ped "
            "  UNION ALL "
            f"  SELECT os_.forma_pag, os_.{valor_col} AS valor, c2.data, c2.{campo_atendente} AS atend, c2.area_atuacao "
            "   FROM comanda_os co "
            "   JOIN comanda c2 ON c2.comanda = co.comanda "
            f"  JOIN os_{sufixo} os_ ON os_.os = co.os "
            ") x "
            "JOIN forma_pagamento fp ON fp.codigo = x.forma_pag "
            "WHERE x.data BETWEEN %s AND %s"
        )
        params: list = [data_ini, data_fim]
        if atendente is not None:
            sql += " AND x.atend = %s"
            params.append(atendente)
        if area is not None:
            sql += " AND x.area_atuacao = %s"
            params.append(area)
        if not exibir_garantias:
            sql += " AND ISNULL(fp.FORMA_PAG_GARANTIA, 0) = 0"
        sql += " GROUP BY fp.descricao, fp.tipo, fp.nao_totaliza_caixa"
        cur.execute(sql, tuple(params))
        for r in cur.fetchall():
            desc = (r.get("descricao") or "").strip()
            if not desc:
                continue
            valor = float(r.get("total") or 0)
            if valor == 0:
                continue
            atual = por_descricao.get(desc)
            if atual:
                atual["valor"] += valor
            else:
                por_descricao[desc] = {
                    "descricao": desc,
                    "tipo": (r.get("tipo") or "").strip(),
                    "nao_totaliza_caixa": bool(r.get("nao_totaliza_caixa")),
                    "valor": valor,
                }
    return sorted(por_descricao.values(), key=lambda x: x["descricao"])


def _entradas_saidas_sync(cur, data_ini: str, data_fim: str, atendente: Optional[int]) -> dict:
    """Entrada/Saída de Caixa (`entrada_caixa`/`saida_caixa`, já gravadas
    pela tela migrada de mesmo nome) + Despesas com/sem comprovante
    (tabela `despesas` — ainda sem tela de cadastro migrada, normalmente
    vazia nesta versão, mas a leitura já fica pronta). Sempre filtradas
    pelo atendente "puro" (`atendente`), nunca pelo `atendente_dav` — o
    legado usa `FiltroDAVAtendente` (sempre `atendente=`) pra essas 3
    fontes, distinto do `FiltroAtendente` usado no resumo por forma de
    pagamento (que respeita o checkbox)."""
    params_base: list = [data_ini, data_fim]

    def _agrupado(tabela: str) -> list[dict]:
        sql = f"SELECT descricao, SUM(valor) AS total FROM {tabela} WHERE data BETWEEN %s AND %s"
        params = list(params_base)
        if atendente is not None:
            sql += " AND atendente = %s"
            params.append(atendente)
        sql += " GROUP BY descricao ORDER BY descricao"
        cur.execute(sql, tuple(params))
        return [
            {"descricao": (r.get("descricao") or "").strip(), "valor": float(r.get("total") or 0)}
            for r in cur.fetchall()
        ]

    entradas = _agrupado("entrada_caixa")
    saidas = _agrupado("saida_caixa")

    sql = "SELECT tipo, SUM(valor) AS total FROM despesas WHERE data BETWEEN %s AND %s"
    params = list(params_base)
    if atendente is not None:
        sql += " AND atendente = %s"
        params.append(atendente)
    sql += " GROUP BY tipo"
    cur.execute(sql, tuple(params))
    despesas_com = 0.0
    despesas_sem = 0.0
    for r in cur.fetchall():
        v = float(r.get("total") or 0)
        if int(r.get("tipo") or 0) == 0:
            despesas_com = v
        else:
            despesas_sem = v

    return {
        "entradas": entradas,
        "total_entradas": round(sum(e["valor"] for e in entradas), 2),
        "saidas": saidas,
        "total_saidas": round(sum(s["valor"] for s in saidas), 2),
        "despesas_com_comprovante": round(despesas_com, 2),
        "despesas_sem_comprovante": round(despesas_sem, 2),
    }


def _pedidos_faturados_sem_forma_pagamento_sync(
    cur, data_ini: str, data_fim: str, atendente: Optional[int],
    campo_atendente: str, area: Optional[int],
) -> list[dict]:
    """Pedidos faturados (com comanda) no período que não têm NENHUMA linha
    em nenhuma das 8 tabelas de forma de pagamento — gap real de dados,
    achado 2026-07-16 (usuário reportou o total do Fechamento de Caixa não
    batendo com o total "Faturado" da Tela Principal; a diferença exata
    era o valor de um pedido faturado sem forma de pagamento nunca
    lançada — provavelmente Fechado antes de `_fecha_fpag_dav` existir).
    Sem isso esses pedidos somem silenciosamente do total do Fechamento de
    Caixa (que só soma o que está de fato lançado), mas continuam contando
    no total "Faturado" da Tela Principal (que soma `pedido_venda.total`
    direto) — a diferença precisa ficar visível, não escondida."""
    not_exists = " AND ".join(
        f"NOT EXISTS (SELECT 1 FROM pedido_venda_{sufixo} x WHERE x.pedido_venda = cp.ped)"
        for sufixo in FORMA_PAG_SUFIXO_TIPO.values()
    )
    sql = (
        "SELECT cp.ped AS pedido, ISNULL(pv.total,0) AS total "
        "FROM COMANDA_PED cp "
        "JOIN comanda c ON c.comanda = cp.comanda "
        "JOIN pedido_venda pv ON pv.pedido = cp.ped "
        "WHERE c.data BETWEEN %s AND %s"
    )
    params: list = [data_ini, data_fim]
    if atendente is not None:
        sql += f" AND c.{campo_atendente} = %s"
        params.append(atendente)
    if area is not None:
        sql += " AND c.area_atuacao = %s"
        params.append(area)
    sql += f" AND {not_exists} ORDER BY cp.ped"
    cur.execute(sql, tuple(params))
    return [{"pedido": int(r.get("pedido")), "valor": float(r.get("total") or 0)} for r in cur.fetchall()]


def _fechamento_caixa_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    atendente: Optional[int], filtrar_atendente_dav: bool, area: Optional[int],
    exibir_garantias: bool,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        campo_atendente = "atendente_dav" if filtrar_atendente_dav else "atendente"
        formas = _resumo_forma_pagamento_sync(cur, data_ini, data_fim, atendente, campo_atendente, area, exibir_garantias)
        extra = _entradas_saidas_sync(cur, data_ini, data_fim, atendente)
        pedidos_sem_forma = _pedidos_faturados_sem_forma_pagamento_sync(
            cur, data_ini, data_fim, atendente, campo_atendente, area
        )
        cur.close()
        conn.close()

        total_sem_forma_pagamento = round(sum(p["valor"] for p in pedidos_sem_forma), 2)

        # "(*) " nos itens configurados pra não somar no total do caixa —
        # mesma marcação do rodapé do form legado.
        subtotal_formas = round(sum(f["valor"] for f in formas if not f["nao_totaliza_caixa"]), 2)
        total_caixa = round(
            subtotal_formas + extra["total_entradas"] - extra["total_saidas"]
            - extra["despesas_com_comprovante"] - extra["despesas_sem_comprovante"],
            2,
        )

        # Resumo por tipo (DI/CH/CC/CD/DU/TI/VA/FI), com percentual do total
        # dos recebimentos (mesma base de `TotFormaPag` no legado — soma de
        # TODAS as formas, inclusive as marcadas nao_totaliza_caixa).
        por_tipo: dict[str, float] = {}
        for f in formas:
            por_tipo[f["tipo"]] = por_tipo.get(f["tipo"], 0.0) + f["valor"]
        total_recebimentos = round(sum(por_tipo.values()), 2)
        resumo_tipo = [
            {
                "tipo": t,
                "label": TIPO_LABEL.get(t, t),
                "valor": round(v, 2),
                "percentual": round((v / total_recebimentos * 100) if total_recebimentos else 0, 2),
            }
            for t, v in sorted(por_tipo.items())
        ]

        return {
            "success": True,
            "formas_pagamento": formas,
            "subtotal_formas_pagamento": subtotal_formas,
            "resumo_tipo": resumo_tipo,
            "total_recebimentos": total_recebimentos,
            **extra,
            "total_caixa": total_caixa,
            "pedidos_sem_forma_pagamento": pedidos_sem_forma,
            "total_sem_forma_pagamento": total_sem_forma_pagamento,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def fechamento_caixa(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    atendente: Optional[int] = None, filtrar_atendente_dav: bool = False,
    area: Optional[int] = None, exibir_garantias: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _fechamento_caixa_sync, servidor, banco, data_ini, data_fim,
        atendente, filtrar_atendente_dav, area, exibir_garantias,
    )
