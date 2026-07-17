"""Relatório de Caixa Analítico — quebra de recebimentos/entradas/saídas por
período (dia, dia da semana, semana, mês, trimestre, semestre, ano), com uma
linha de TOTAIS. Migrado de `FrmTotCaixa.frm` (Kontacto).

Mesma correção de arquitetura já documentada em `fechamento_caixa_service.py`:
o legado soma `comanda_dinheiro`/`comanda_cheque`/... (uma tabela por tipo de
forma de pagamento), populadas pela rotina de fechamento de caixa do PDV
legado — esta migração nunca grava nessas tabelas, o Faturar Pedido grava em
`pedido_venda_*`/`os_*` (ver `pedido_common.py` — `FORMA_PAG_SUFIXO_TIPO`/
`FORMA_PAG_VALOR_COL`). Por isso a agregação abaixo soma essas tabelas via
`COMANDA_PED`/`comanda_os`, não as tabelas `comanda_*`.

Diferente de `fechamento_caixa_service.py`: `FrmTotCaixa` não filtra por
atendente/área (não existem esses campos no form) e não tem o conceito de
`forma_pagamento.nao_totaliza_caixa`/despesas — não junta a tabela
`forma_pagamento` em nenhum momento, só soma direto por tipo hardcoded. O
port replica esse recorte mais simples (não generaliza pra reusar
`_resumo_forma_pagamento_sync` do Fechamento de Caixa, que tem um contrato
diferente — filtros e regras de negócio distintos, ver "Não replicar truques
VB6" no CLAUDE.md pra o princípio geral).

Agrupamento — a matemática de datas do legado (reset pra 01/01 do ano em
Mensal/Trimestral/Semestral/Anual, arredondamento pra Domingo/Sábado em
Semanal/Dia da Semana) é tratada como regra de negócio real (mostrar o
ANO/SEMANA inteiro que contém o período selecionado, não só o recorte exato
digitado) — replicada abaixo com aritmética de datas do Python
(`_add_months`/`_ultimo_dia_mes`) em vez de transliterar os hacks de string
do VB6 (`Format(Mes+2,"00")` etc, que também tinha bugs latentes pra
Mes+2>12 nunca exercitados pela combinação real de meses usada).
"""
import asyncio
import calendar
from datetime import date, timedelta
from typing import Optional

from db.connection import _open_conn
from services.pedido_common import FORMA_PAG_SUFIXO_TIPO, FORMA_PAG_VALOR_COL

WEEKDAY_LABELS_PT = [
    "Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira",
    "Quinta-feira", "Sexta-feira", "Sábado",
]
MONTH_LABELS_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Ordem/rótulo das 8 colunas de forma de pagamento exibidas na grade —
# mesma ordem das colunas do `.frm` (`PrepLV`).
COLUNA_TIPO = [
    ("dinheiro", "DI"), ("cheque", "CH"), ("credito", "CC"), ("debito", "CD"),
    ("vale", "VA"), ("ticket", "TI"), ("duplicata", "DU"), ("financiado", "FI"),
]

_SOMA_KEYS = ["total_caixa", "total_recebidos", "total_entradas", "total_saidas"] + [k for k, _ in COLUNA_TIPO]


def _dow0(d: date) -> int:
    """0=Domingo ... 6=Sábado (convenção do Check1 do legado) — Python usa
    Segunda=0..Domingo=6, então precisa deslocar."""
    return (d.weekday() + 1) % 7


def _ultimo_dia_mes(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _add_months(d: date, n: int) -> date:
    total = d.month - 1 + n
    y = d.year + total // 12
    m = total % 12 + 1
    return date(y, m, 1)


def _build_buckets(data_ini: date, data_fim: date, agrupamento: str, dias_semana: set[int]):
    """Monta a lista de períodos (linhas do relatório) + o intervalo total
    (possivelmente maior que o digitado, ver docstring do módulo) que precisa
    ser buscado no banco pra cobrir todos os períodos."""
    if agrupamento == "diario":
        buckets = []
        d = data_ini
        while d <= data_fim:
            if _dow0(d) in dias_semana:
                buckets.append({
                    "label": f"{d.day:02d}/{d.month:02d} {WEEKDAY_LABELS_PT[_dow0(d)]}",
                    "ini": d, "fim": d,
                })
            d += timedelta(days=1)
        return buckets, data_ini, data_fim

    if agrupamento in ("dia_semana", "semanal"):
        ini = data_ini - timedelta(days=_dow0(data_ini))
        fim = data_fim + timedelta(days=(6 - _dow0(data_fim)))
        if agrupamento == "dia_semana":
            buckets = [
                {"label": WEEKDAY_LABELS_PT[w], "ini": ini, "fim": fim, "dow_filter": w}
                for w in range(7)
            ]
        else:
            buckets = []
            d = ini
            while d <= fim:
                fim_semana = d + timedelta(days=6)
                buckets.append({"label": f"{d.day:02d}/{d.month:02d} a {fim_semana.day:02d}/{fim_semana.month:02d}", "ini": d, "fim": fim_semana})
                d += timedelta(days=7)
        return buckets, ini, fim

    if agrupamento == "mensal":
        ini = date(data_ini.year, 1, 1)
        fim = _ultimo_dia_mes(data_fim)
        buckets = []
        d = ini
        while d <= fim:
            fim_mes = _ultimo_dia_mes(d)
            buckets.append({"label": f"{MONTH_LABELS_PT[d.month - 1]}/{d.year}", "ini": d, "fim": fim_mes})
            d = _add_months(d, 1)
        return buckets, ini, fim

    if agrupamento in ("trimestral", "semestral"):
        ini = date(data_ini.year, 1, 1)
        fim = date(data_fim.year, 12, 31)
        passo = 3 if agrupamento == "trimestral" else 6
        buckets = []
        d = ini
        while d <= fim:
            fim_periodo = _ultimo_dia_mes(_add_months(d, passo - 1))
            if agrupamento == "trimestral":
                num = (d.month - 1) // 3 + 1
                label = f"{num}º Trimestre / {d.year}"
            else:
                num = 1 if d.month == 1 else 2
                label = f"{num}º Semestre / {d.year}"
            buckets.append({"label": label, "ini": d, "fim": fim_periodo})
            d = _add_months(d, passo)
        return buckets, ini, fim

    if agrupamento == "anual":
        ini = date(data_ini.year, 1, 1)
        fim = date(data_fim.year, 12, 31)
        buckets = [{"label": str(y), "ini": date(y, 1, 1), "fim": date(y, 12, 31)} for y in range(data_ini.year, data_fim.year + 1)]
        return buckets, ini, fim

    raise ValueError(f"Agrupamento inválido: {agrupamento}")


def _por_tipo_por_dia_sync(cur, data_ini: str, data_fim: str) -> list[dict]:
    """Uma linha por (data, tipo) com o total pago naquele dia — granularidade
    diária é suficiente pra somar qualquer agrupamento mais largo depois."""
    rows: list[dict] = []
    for tipo_forma, valor_col in FORMA_PAG_VALOR_COL.items():
        sufixo = FORMA_PAG_SUFIXO_TIPO[tipo_forma]
        sql = (
            "SELECT x.data AS data, SUM(x.valor) AS total FROM ("
            f"  SELECT c.data AS data, pv.{valor_col} AS valor "
            "   FROM COMANDA_PED cp JOIN comanda c ON c.comanda = cp.comanda "
            f"  JOIN pedido_venda_{sufixo} pv ON pv.pedido_venda = cp.ped "
            "  UNION ALL "
            f"  SELECT c2.data AS data, os_.{valor_col} AS valor "
            "   FROM comanda_os co JOIN comanda c2 ON c2.comanda = co.comanda "
            f"  JOIN os_{sufixo} os_ ON os_.os = co.os "
            ") x WHERE x.data BETWEEN %s AND %s GROUP BY x.data"
        )
        cur.execute(sql, (data_ini, data_fim))
        for r in cur.fetchall():
            total = float(r.get("total") or 0)
            if total == 0 or not r.get("data"):
                continue
            rows.append({"tipo": tipo_forma, "data": r["data"], "valor": total})
    return rows


def _por_dia_sync(cur, tabela: str, data_ini: str, data_fim: str) -> list[dict]:
    sql = f"SELECT data, SUM(valor) AS total FROM {tabela} WHERE data BETWEEN %s AND %s GROUP BY data"
    cur.execute(sql, (data_ini, data_fim))
    return [
        {"data": r["data"], "valor": float(r.get("total") or 0)}
        for r in cur.fetchall() if r.get("data")
    ]


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _caixa_analitico_sync(
    servidor: str, banco: str, data_ini_s: str, data_fim_s: str,
    agrupamento: str, dias_semana: list[int],
) -> dict:
    try:
        data_ini = date.fromisoformat(data_ini_s)
        data_fim = date.fromisoformat(data_fim_s)
    except ValueError:
        return {"success": False, "message": "Período inválido."}
    if data_ini > data_fim:
        return {"success": False, "message": "Data inicial não pode ser depois da data final."}

    try:
        buckets, range_ini, range_fim = _build_buckets(data_ini, data_fim, agrupamento, set(dias_semana))
    except ValueError as e:
        return {"success": False, "message": str(e)}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        range_ini_s, range_fim_s = range_ini.isoformat(), range_fim.isoformat()
        tipo_por_dia = _por_tipo_por_dia_sync(cur, range_ini_s, range_fim_s)
        entradas_por_dia = _por_dia_sync(cur, "entrada_caixa", range_ini_s, range_fim_s)
        saidas_por_dia = _por_dia_sync(cur, "saida_caixa", range_ini_s, range_fim_s)
        cur.close()
        conn.close()

        linhas = []
        for b in buckets:
            dow_filter = b.get("dow_filter")

            def _in_bucket(d: date) -> bool:
                if dow_filter is not None:
                    return _dow0(d) == dow_filter
                return b["ini"] <= d <= b["fim"]

            por_tipo = {t: 0.0 for _, t in COLUNA_TIPO}
            for r in tipo_por_dia:
                if _in_bucket(_as_date(r["data"])):
                    por_tipo[r["tipo"]] += r["valor"]
            entradas = sum(r["valor"] for r in entradas_por_dia if _in_bucket(_as_date(r["data"])))
            saidas = sum(r["valor"] for r in saidas_por_dia if _in_bucket(_as_date(r["data"])))
            total_recebidos = sum(por_tipo.values())

            linha = {"label": b["label"]}
            for chave, tipo in COLUNA_TIPO:
                linha[chave] = round(por_tipo[tipo], 2)
            linha["total_recebidos"] = round(total_recebidos, 2)
            linha["total_entradas"] = round(entradas, 2)
            linha["total_saidas"] = round(saidas, 2)
            linha["total_caixa"] = round(total_recebidos + entradas - saidas, 2)
            linhas.append(linha)

        totais = {"label": "TOTAIS"}
        for k in _SOMA_KEYS:
            totais[k] = round(sum(l[k] for l in linhas), 2)

        return {"success": True, "linhas": linhas, "totais": totais}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def caixa_analitico(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    agrupamento: str = "diario", dias_semana: Optional[list[int]] = None,
) -> dict:
    return await asyncio.to_thread(
        _caixa_analitico_sync, servidor, banco, data_ini, data_fim,
        agrupamento, dias_semana if dias_semana is not None else [0, 1, 2, 3, 4, 5, 6],
    )
