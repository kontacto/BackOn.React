"""Financeiro > Fluxo de Caixa > Painel de Movimentações (`Kontacto\\
FrmPnlCon.frm`, caption real "Painel de Movimentações"). Dashboard do
Fluxo de Caixa (saldo/totais do período, 4 blocos de alerta, grade de
movimentações) + lançamento direto rápido (Pagar/Cheque, Receber/
Depósito, Transferência, Saque).

**Achado estrutural, confirmado direto na fonte VB.NET**: a regra real de
cálculo do painel não está no `.frm` — está em `Backon.Data.Dao_Kash_
Painel.vb` (`Movimentacoes_Por_Periodo`/`Previsoes_Por_Periodo`), chamada
via COM pelo `.frm`. As fórmulas abaixo foram conferidas linha a linha
contra esse arquivo, não deduzidas do `.frm`.

**Fórmulas reais** (por conta, depois somadas se "Todas" estiver
selecionado):
```
saldo_anterior_periodo = contas.saldo_inicial
  - SUM(movimentacoes.valor WHERE data_liquidacao < data_inicial
        AND conta=X AND tipo IN (0,3,2))
  + SUM(movimentacoes.valor WHERE data_liquidacao < data_inicial
        AND ((tipo=1 AND conta=X) OR (tipo=2 AND classe=X)))
total_despesas_periodo = SUM(valor WHERE conta=X AND tipo IN (0,3,2)
                              AND data_liquidacao BETWEEN ini,fim)
total_receitas_periodo = SUM(valor WHERE ((tipo=1 AND conta=X) OR
                              (tipo=2 AND classe=X)) AND data_liquidacao
                              BETWEEN ini,fim)
saldo_fim_periodo = saldo_anterior_periodo + total_receitas_periodo
                     - total_despesas_periodo
```
**`saldo_anterior_periodo`/`saldo_fim_periodo` são DIFERENTES de
`contas.saldo_atual`** — o 1º é recalculado a partir do histórico de
`movimentacoes` a cada consulta; o 2º é um contador incremental mantido
por UPDATE a cada gravação. Os dois são mostrados lado a lado no painel
de propósito (mesmo comportamento do legado) — não são a mesma coisa,
não devem ser unificados.

**4 blocos de alerta** — réplica das 2 fontes reais confirmadas:
Contas a Receber Atraso/Hoje vêm direto de `duplicata_rec_venc`
(`situacao='A' AND situacao_duplicata=0`); À Pagar Hoje/Atraso vêm de
`previsoes` (`tipo=0`) — **simplificação deliberada**: o legado usa uma
tabela de staging global sem escopo de sessão (`temp_kash_PREV`, mesmo
anti-padrão já identificado e descartado em `transferencia_caixa_
service.py`/`previsoes_service.py`) povoada por `Previsoes_Por_Periodo`;
aqui a mesma pergunta é respondida com uma consulta direta em `previsoes`,
sem staging nem projeção de ocorrências futuras de recorrência — mostra
só a PRÓXIMA ocorrência de cada previsão (mesmo modelo de "linha única
avançando", já estabelecido em `previsoes_service.py` — nunca projeta
séries futuras pra exibição).

**Lançamento direto** (Pagar/Cheque, Receber/Depósito, Transferência,
Saque) — 3º caminho real de criar uma `movimentacoes`, diferente de
`entrada_saida_caixa_service.py` (grava em `entrada_caixa`/`saida_caixa`,
precisa passar pela Transferência p/Fluxo de Caixa depois) e de
`previsoes_service.py` (passa por `previsoes` primeiro, só vira
`movimentacoes` ao ser efetivada) — aqui é direto, sem intermediário.
Reaproveita os helpers de achar-ou-criar Favorecido/Classe/Sub-Classe já
escritos em `previsoes_service.py` (mesmo padrão, sem duplicar).

**Guarda real, replicada**: uma `movimentacoes` com `flag_transf_caixa`
preenchido (não vazio) pertence a OUTRA tela (Transferência p/Fluxo de
Caixa, Previsões efetivada, Agrupamento de Comandas) — não pode ser
editada/excluída aqui, mesma regra já aplicada em `previsoes_service.py`
pro campo irmão `cod_transf_caixa`.

**Fora de escopo desta rodada, registrado**: projeção de ocorrências
futuras de previsão recorrente na tela (ver acima); regra "próximo dia
útil se hoje é sexta" nos blocos de alerta (o legado só trata sexta-feira,
não feriado — decisão de não replicar um hardcode parcial, mostrar sempre
o dia exato pedido); a exclusão obscura de lançamentos do mês de
fechamento de caixa do grid individual (`Data_Fecha_Cx`, absorvidos no
"Saldo Inicial do Período" no legado) — grid aqui sempre mostra todos os
lançamentos do período individualmente; "Recurso extra" do Carlos (decisão
híbrida já confirmada) ainda não implementado.
"""
import asyncio
from datetime import date, timedelta
from typing import Optional

from db.connection import _open_conn
from services.previsoes_service import _upsert_favorecido_sync

TIPO_LABEL = {0: "Pagar", 1: "Receber", 2: "Transferencia", 3: "Saque"}


def _round2(v) -> float:
    return round(float(v or 0), 2)


def _resolver_periodo(opcao: str, mes_ref: Optional[str]) -> tuple:
    """Réplica de `Periodo_Click`/navegação Mês — devolve (data_inicial,
    data_final) como strings ISO, ou (None, None) pra "Mostrar Todos"."""
    hoje = date.today()
    if opcao == "hoje":
        return hoje.isoformat(), hoje.isoformat()
    if opcao == "ontem":
        ontem = hoje - timedelta(days=1)
        return ontem.isoformat(), ontem.isoformat()
    if opcao == "semana":
        inicio = hoje - timedelta(days=hoje.weekday())
        return inicio.isoformat(), hoje.isoformat()
    if opcao == "30dias":
        return (hoje - timedelta(days=30)).isoformat(), hoje.isoformat()
    if opcao == "tudo":
        return None, None
    # "mes" (default) — navegável via mes_ref "AAAA-MM"
    if mes_ref:
        ano, mes = (int(x) for x in mes_ref.split("-"))
    else:
        ano, mes = hoje.year, hoje.month
    inicio = date(ano, mes, 1)
    fim_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    fim = fim_mes - timedelta(days=1)
    return inicio.isoformat(), fim.isoformat()


def _contas_alvo_sync(cur, conta: Optional[int]) -> list:
    if conta:
        cur.execute("SELECT codigo, descricao, saldo_inicial, saldo_atual FROM contas WHERE codigo = %s", (conta,))
    else:
        cur.execute("SELECT codigo, descricao, saldo_inicial, saldo_atual FROM contas WHERE situacao = 'A' ORDER BY descricao")
    return cur.fetchall() or []


def _resumo_conta_sync(cur, codigo_conta: int, data_inicial: Optional[str], data_final: Optional[str]) -> dict:
    cur.execute("SELECT saldo_inicial FROM contas WHERE codigo = %s", (codigo_conta,))
    row = cur.fetchone() or {}
    saldo_anterior = _round2(row.get("saldo_inicial"))

    if data_inicial:
        cur.execute(
            "SELECT SUM(valor) AS totmov FROM movimentacoes WHERE data_liquidacao < %s "
            "AND tipo IN (0,3,2) AND conta = %s",
            (data_inicial, codigo_conta),
        )
        r = cur.fetchone() or {}
        saldo_anterior = _round2(saldo_anterior - _round2(r.get("totmov")))
        cur.execute(
            "SELECT SUM(valor) AS totmov FROM movimentacoes WHERE data_liquidacao < %s "
            "AND ((tipo=1 AND conta=%s) OR (tipo=2 AND classe=%s))",
            (data_inicial, codigo_conta, codigo_conta),
        )
        r = cur.fetchone() or {}
        saldo_anterior = _round2(saldo_anterior + _round2(r.get("totmov")))

    filtro_periodo = ""
    params_desp: list = [codigo_conta]
    params_rec: list = [codigo_conta, codigo_conta]
    if data_inicial and data_final:
        filtro_periodo = " AND data_liquidacao BETWEEN %s AND %s"
        params_desp += [data_inicial, data_final]
        params_rec += [data_inicial, data_final]

    cur.execute(
        f"SELECT SUM(valor) AS totmov FROM movimentacoes WHERE tipo IN (0,3,2) AND conta = %s{filtro_periodo}",
        params_desp,
    )
    despesas = _round2((cur.fetchone() or {}).get("totmov"))
    cur.execute(
        f"SELECT SUM(valor) AS totmov FROM movimentacoes WHERE ((tipo=1 AND conta=%s) OR (tipo=2 AND classe=%s)){filtro_periodo}",
        params_rec,
    )
    receitas = _round2((cur.fetchone() or {}).get("totmov"))

    return {
        "saldo_anterior_periodo": saldo_anterior,
        "total_receitas_periodo": receitas,
        "total_despesas_periodo": despesas,
        "saldo_fim_periodo": _round2(saldo_anterior + receitas - despesas),
    }


def _alertas_sync(cur, contas_ids: list) -> dict:
    hoje = date.today().isoformat()
    # Contas a Receber (duplicata direto — não filtra por conta de caixa,
    # é receita "em aberto no comercial", mesmo escopo do legado).
    cur.execute(
        "SELECT SUM(drv.valor + ISNULL(drv.tarifa_banco,0) + ISNULL(drv.outros_acres_pag,0)) AS total, COUNT(*) AS qtd "
        "FROM duplicata_rec_venc drv JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
        "WHERE drv.situacao = 'A' AND ISNULL(drv.situacao_duplicata,0) = 0 AND drv.dt_vencimento < %s",
        (hoje,),
    )
    r = cur.fetchone() or {}
    receber_atraso = {"total": _round2(r.get("total")), "qtd": int(r.get("qtd") or 0)}

    cur.execute(
        "SELECT SUM(drv.valor + ISNULL(drv.tarifa_banco,0) + ISNULL(drv.outros_acres_pag,0)) AS total, COUNT(*) AS qtd "
        "FROM duplicata_rec_venc drv JOIN duplicata_receber dr ON dr.codigo = drv.duplicata "
        "WHERE drv.situacao = 'A' AND ISNULL(drv.situacao_duplicata,0) = 0 AND drv.dt_vencimento = %s",
        (hoje,),
    )
    r = cur.fetchone() or {}
    receber_hoje = {"total": _round2(r.get("total")), "qtd": int(r.get("qtd") or 0)}

    filtro_conta_prev = ""
    params_atraso = [hoje]
    params_hoje = [hoje]
    if contas_ids:
        placeholders = ",".join(["%s"] * len(contas_ids))
        filtro_conta_prev = f" AND conta IN ({placeholders})"
        params_atraso += contas_ids
        params_hoje += contas_ids

    # `tipo IN (0,3)` — Pagar E Saque, não só Pagar. Achado direto na fonte
    # (`Dao_Kash_Painel.vb:313-314`, `Case 0, 3 → tipolancamento = "SAIDA"`)
    # ao investigar divergência real reportada pelo usuário 2026-08-31
    # (VB6 R$8.618,55 x Web R$4.875,32 pra "Pagamentos em Atraso", mesma
    # conta/período) — o card original só filtrava `tipo = 0`, perdendo
    # previsões de Saque em atraso.
    cur.execute(
        f"SELECT SUM(valor) AS total, COUNT(*) AS qtd FROM previsoes WHERE tipo IN (0,3) AND data_vencimento < %s{filtro_conta_prev}",
        params_atraso,
    )
    r = cur.fetchone() or {}
    pagar_atraso = {"total": _round2(r.get("total")), "qtd": int(r.get("qtd") or 0)}

    cur.execute(
        f"SELECT SUM(valor) AS total, COUNT(*) AS qtd FROM previsoes WHERE tipo IN (0,3) AND data_vencimento = %s{filtro_conta_prev}",
        params_hoje,
    )
    r = cur.fetchone() or {}
    pagar_hoje = {"total": _round2(r.get("total")), "qtd": int(r.get("qtd") or 0)}

    return {
        "contas_a_receber_atraso": receber_atraso, "contas_a_receber_hoje": receber_hoje,
        "pagamentos_atraso": pagar_atraso, "a_pagar_hoje": pagar_hoje,
    }


# =============================================================================
# Saldo Previsto — fórmula real, réplica de `FrmPnlCon.frm:3299`
# (`Saldo_Previsto = saldo_atual + saldo_pendencia - Previsoes_Despesas +
# Previsoes_Receitas`) + os 2 checkboxes do cabeçalho do Painel legado
# (`pCheck5`="Previsões a partir de hoje", `pCheck6`="Desconsiderar
# Pendências", `FrmPnlCon.frm:922-930/160-166`, mutuamente exclusivos na
# UI — `PCheck5_Click`/`PCheck6_Click` desmarcam um ao marcar o outro).
#
# `Dao_Kash_Painel.vb::Previsoes_Por_Periodo` (linhas 203-696) tem 2
# componentes:
# - **Pendências**: previsões com `data_vencimento < data_inicial` — SEM
#   expansão de recorrência, só o valor da própria linha (réplica em
#   `_pendencia_conta_sync`).
# - **Previsões dentro do período**: EXPANDE cada previsão recorrente
#   virtualmente em toda ocorrência que cai em `[data_inicial,
#   data_final]` — uma Mensal aparece 1x no período de 1 mês, uma Semanal
#   pode aparecer várias vezes — mesmo que a linha real só exista 1 vez
#   na tabela (a ocorrência física só nasce quando o usuário Efetiva, em
#   Previsões). Réplica em `_previsoes_expandidas_conta_sync`.
#
# **Achado real, não um erro de leitura**: o fallback de "dia não existe
# no mês" usado NESTA expansão (linhas 607-617 do .vb — vira dia 01 do
# mês SEGUINTE) é DIFERENTE do fallback usado na Efetivação real de
# Previsões (`previsoes_service.avancar_data_frequencia` — decrementa
# pro último dia válido do MESMO mês, ex. 31/mar mensal → 30/abr). O
# legado genuinamente usa 2 algoritmos diferentes pra "avançar recorrência"
# em 2 lugares diferentes — não são a mesma rotina reaproveitada, cada um
# foi rastreado e replicado fielmente no seu próprio contexto.
#
# **Simplificações documentadas, deliberadas**:
# 1. Toda ocorrência projetada usa o valor CHEIO da previsão
#    (`previsoes.valor`) — não replica a nuance real do legado de usar só
#    a parte do rateio marcada `previsoes_centro_custo.repete_lancamento=1`
#    nas ocorrências seguintes à primeira.
# 2. Não inclui previsões com `cod_transf_caixa>0` (criadas por
#    Transferência p/Fluxo de Caixa) — o legado inclui algumas dessas via
#    `FiltroSituacaoDuplicata` (exclui só se a duplicata de origem tem
#    `situacao_duplicata<>0`); esta migração trata essas previsões como
#    pertencentes a outra tela em todo o resto do app (mesmo critério já
#    usado em Previsões), mantido aqui por consistência.
# 3. Período "Tudo" (sem `data_final`) não tem equivalente direto — a
#    função real do legado exige as duas datas preenchidas. Nesse caso
#    o Saldo Previsto cai pro cálculo mais simples (baseado só nos 4
#    alertas de atraso/hoje), sem os 2 checkboxes.
# =============================================================================

def _pendencia_conta_sync(cur, codigo_conta: int, data_inicial: str) -> float:
    cur.execute(
        "SELECT valor, tipo, conta FROM previsoes WHERE conta = %s AND data_vencimento < %s "
        "AND ISNULL(cod_transf_caixa,0) = 0",
        (codigo_conta, data_inicial),
    )
    linhas = list(cur.fetchall())
    cur.execute(
        "SELECT valor, tipo, conta FROM previsoes WHERE classe = %s AND tipo = 2 AND data_vencimento < %s "
        "AND ISNULL(cod_transf_caixa,0) = 0",
        (codigo_conta, data_inicial),
    )
    linhas += list(cur.fetchall())
    saldo = 0.0
    for r in linhas:
        tipo = int(r["tipo"])
        valor = float(r["valor"] or 0)
        eh_transferencia_saida = tipo == 2 and int(r["conta"]) == codigo_conta
        if tipo in (0, 3) or eh_transferencia_saida:
            saldo -= valor
        else:
            saldo += valor
    return _round2(saldo)


def _avancar_mes_painel(ano: int, mes: int, dia: int, total_meses: int) -> date:
    """Fallback específico desta expansão (dia inválido → dia 01 do mês
    seguinte) — ver nota grande acima sobre a divergência real do legado."""
    total = (mes - 1) + total_meses
    ano2 = ano + total // 12
    mes2 = total % 12 + 1
    try:
        return date(ano2, mes2, dia)
    except ValueError:
        mes3, ano3 = mes2 + 1, ano2
        if mes3 > 12:
            mes3 -= 12
            ano3 += 1
        return date(ano3, mes3, 1)


def _previsoes_expandidas_conta_sync(cur, codigo_conta: int, data_inicial: date, data_final: date) -> tuple:
    cur.execute(
        "SELECT valor, tipo, conta, data_vencimento, frequencia FROM previsoes "
        "WHERE conta = %s AND data_vencimento <= %s AND ISNULL(cod_transf_caixa,0) = 0",
        (codigo_conta, data_final),
    )
    linhas = list(cur.fetchall())
    cur.execute(
        "SELECT valor, tipo, conta, data_vencimento, frequencia FROM previsoes "
        "WHERE classe = %s AND tipo = 2 AND data_vencimento <= %s AND ISNULL(cod_transf_caixa,0) = 0",
        (codigo_conta, data_final),
    )
    linhas += list(cur.fetchall())

    despesas = 0.0
    receitas = 0.0
    for r in linhas:
        tipo = int(r["tipo"])
        valor = float(r["valor"] or 0)
        freq = int(r["frequencia"]) if r.get("frequencia") is not None else 10
        venc = r["data_vencimento"]
        if not isinstance(venc, date):
            venc = date.fromisoformat(str(venc)[:10])
        eh_transferencia_saida = tipo == 2 and int(r["conta"]) == codigo_conta

        def _somar(v):
            nonlocal despesas, receitas
            if tipo in (0, 3) or eh_transferencia_saida:
                despesas = _round2(despesas + v)
            else:
                receitas = _round2(receitas + v)

        if freq == 10:
            if data_inicial <= venc <= data_final:
                _somar(valor)
        elif freq in (0, 1, 2, 3):
            passo = {0: 1, 1: 7, 2: 10, 3: 15}[freq]
            atual = venc
            while atual <= data_final:
                if atual >= data_inicial:
                    _somar(valor)
                atual = atual + timedelta(days=passo)
        else:
            soma_meses = {4: 1, 5: 2, 6: 3, 7: 4, 8: 6, 9: 12}[freq]
            if venc >= data_inicial:
                _somar(valor)
            n = 1
            while True:
                atual = _avancar_mes_painel(venc.year, venc.month, venc.day, soma_meses * n)
                if atual > data_final:
                    break
                if atual >= data_inicial:
                    _somar(valor)
                n += 1

    return despesas, receitas


def _saldo_previsto_real_sync(cur, contas: list, saldo_atual: float, data_inicial: Optional[str], data_final: Optional[str],
                               alertas: dict, partir_de_hoje: bool, desconsiderar_pendencias: bool) -> float:
    if not data_inicial or not data_final:
        # Período "Tudo" — sem equivalente direto no legado, cai pro
        # cálculo baseado nos 4 alertas (mesmo comportamento de antes).
        return _round2(
            saldo_atual - alertas["pagamentos_atraso"]["total"] - alertas["a_pagar_hoje"]["total"]
            + alertas["contas_a_receber_atraso"]["total"] + alertas["contas_a_receber_hoje"]["total"]
        )

    hoje = date.today().isoformat()
    di_efetivo = hoje if partir_de_hoje else data_inicial
    df_date = data_final if isinstance(data_final, date) else date.fromisoformat(str(data_final))
    di_date = di_efetivo if isinstance(di_efetivo, date) else date.fromisoformat(str(di_efetivo))

    total_pendencia = 0.0
    total_despesas = 0.0
    total_receitas = 0.0
    for c in contas:
        codigo_conta = int(c["codigo"])
        if not desconsiderar_pendencias:
            total_pendencia = _round2(total_pendencia + _pendencia_conta_sync(cur, codigo_conta, di_efetivo))
        d, r = _previsoes_expandidas_conta_sync(cur, codigo_conta, di_date, df_date)
        total_despesas = _round2(total_despesas + d)
        total_receitas = _round2(total_receitas + r)

    return _round2(saldo_atual + total_pendencia - total_despesas + total_receitas)


def _resumo_sync(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str],
                  partir_de_hoje: bool = False, desconsiderar_pendencias: bool = False) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        data_inicial, data_final = _resolver_periodo(periodo, mes_ref)
        contas = _contas_alvo_sync(cur, conta)
        if not contas:
            return {"success": False, "message": "Nenhuma conta encontrada."}

        saldo_atual = 0.0
        agregado = {"saldo_anterior_periodo": 0.0, "total_receitas_periodo": 0.0, "total_despesas_periodo": 0.0, "saldo_fim_periodo": 0.0}
        for c in contas:
            saldo_atual = _round2(saldo_atual + _round2(c.get("saldo_atual")))
            parcial = _resumo_conta_sync(cur, int(c["codigo"]), data_inicial, data_final)
            for k in agregado:
                agregado[k] = _round2(agregado[k] + parcial[k])

        contas_ids = [int(c["codigo"]) for c in contas]
        alertas = _alertas_sync(cur, contas_ids)
        saldo_previsto = _saldo_previsto_real_sync(
            cur, contas, saldo_atual, data_inicial, data_final, alertas, partir_de_hoje, desconsiderar_pendencias,
        )

        cur.close()
        conn.close()
        return {
            "success": True, "saldo_atual": saldo_atual, "saldo_previsto": saldo_previsto,
            "data_inicial": data_inicial, "data_final": data_final,
            **agregado, "alertas": alertas,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def resumo(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str] = None,
                  partir_de_hoje: bool = False, desconsiderar_pendencias: bool = False) -> dict:
    return await asyncio.to_thread(_resumo_sync, servidor, banco, conta, periodo, mes_ref, partir_de_hoje, desconsiderar_pendencias)


# =============================================================================
# Série de saldo (gráfico) — "recurso extra" do Carlos (Protocolo Gauntlet),
# proposto e confirmado com o usuário 2026-08-29: SEM precedente no legado
# (`FrmPnlCon.frm` não tem gráfico nenhum) — visualização pontual em cima da
# fórmula que já existe, nenhum cálculo novo/especulativo. Só SALDO
# REALIZADO (nunca projeção) — mesma reserva já registrada em PENDENCIAS.md:
# projetar quando uma pendência em aberto vai se resolver seria suposição.
# =============================================================================

def _serie_saldo_conta_sync(cur, codigo_conta: int, data_inicial: Optional[str], data_final: Optional[str]) -> dict:
    """Net (receita-despesa) por dia (período explícito) ou por mês (período
    'tudo', sem data) — mesma fórmula assinada já usada em
    `_resumo_conta_sync`, só agrupada por baldes em vez de 1 total."""
    if data_inicial and data_final:
        bucket_expr = "CONVERT(date, data_liquidacao)"
        filtro = " AND data_liquidacao BETWEEN %s AND %s"
        params_range = [data_inicial, data_final]
    else:
        bucket_expr = "CONVERT(date, DATEADD(day, 1 - DAY(data_liquidacao), data_liquidacao))"
        filtro = ""
        params_range = []

    cur.execute(
        f"SELECT {bucket_expr} AS bucket, SUM(valor) AS total FROM movimentacoes "
        f"WHERE conta = %s AND tipo IN (0,3,2){filtro} GROUP BY {bucket_expr}",
        [codigo_conta] + params_range,
    )
    despesas = {r["bucket"]: _round2(r["total"]) for r in cur.fetchall()}

    cur.execute(
        f"SELECT {bucket_expr} AS bucket, SUM(valor) AS total FROM movimentacoes "
        f"WHERE ((tipo=1 AND conta=%s) OR (tipo=2 AND classe=%s)){filtro} GROUP BY {bucket_expr}",
        [codigo_conta, codigo_conta] + params_range,
    )
    receitas = {r["bucket"]: _round2(r["total"]) for r in cur.fetchall()}

    baldes = set(despesas) | set(receitas)
    return {b: _round2(receitas.get(b, 0) - despesas.get(b, 0)) for b in baldes}


def _serie_saldo_sync(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        data_inicial, data_final = _resolver_periodo(periodo, mes_ref)
        contas = _contas_alvo_sync(cur, conta)
        if not contas:
            return {"success": False, "message": "Nenhuma conta encontrada."}

        saldo_inicial = 0.0
        net_por_balde: dict = {}
        for c in contas:
            codigo_conta = int(c["codigo"])
            parcial = _resumo_conta_sync(cur, codigo_conta, data_inicial, data_final)
            saldo_inicial = _round2(saldo_inicial + parcial["saldo_anterior_periodo"])
            for balde, net in _serie_saldo_conta_sync(cur, codigo_conta, data_inicial, data_final).items():
                net_por_balde[balde] = _round2(net_por_balde.get(balde, 0) + net)

        pontos = []
        saldo = saldo_inicial
        for balde in sorted(net_por_balde.keys()):
            saldo = _round2(saldo + net_por_balde[balde])
            chave = balde.isoformat() if hasattr(balde, "isoformat") else str(balde)
            pontos.append({"data": chave, "saldo": saldo})

        cur.close()
        conn.close()
        return {"success": True, "saldo_inicial": saldo_inicial, "pontos": pontos}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def serie_saldo(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_serie_saldo_sync, servidor, banco, conta, periodo, mes_ref)


# =============================================================================
# Relatório "Receitas x Despesas por Mês" — Fase 1 do catálogo de
# relatórios do Fluxo de Caixa (menu real do legado, `FrmPnlCon.frm` >
# "Relatórios" > grupo Movimentação — ~20 relatórios ao todo; só este e
# mais 4 entraram nesta rodada, ver PENDENCIAS.md pro resto registrado
# como pendência). Reaproveita a MESMA fórmula assinada de
# `_serie_saldo_conta_sync`, só devolvendo Receitas/Despesas separados
# por balde em vez do net.
# =============================================================================

def _receitas_despesas_mes_conta_sync(cur, codigo_conta: int, data_inicial: Optional[str], data_final: Optional[str]) -> dict:
    if data_inicial and data_final:
        bucket_expr = "CONVERT(date, DATEADD(day, 1 - DAY(data_liquidacao), data_liquidacao))"
        filtro = " AND data_liquidacao BETWEEN %s AND %s"
        params_range = [data_inicial, data_final]
    else:
        bucket_expr = "CONVERT(date, DATEADD(day, 1 - DAY(data_liquidacao), data_liquidacao))"
        filtro = ""
        params_range = []

    cur.execute(
        f"SELECT {bucket_expr} AS bucket, SUM(valor) AS total FROM movimentacoes "
        f"WHERE conta = %s AND tipo IN (0,3,2){filtro} GROUP BY {bucket_expr}",
        [codigo_conta] + params_range,
    )
    despesas = {r["bucket"]: _round2(r["total"]) for r in cur.fetchall()}

    cur.execute(
        f"SELECT {bucket_expr} AS bucket, SUM(valor) AS total FROM movimentacoes "
        f"WHERE ((tipo=1 AND conta=%s) OR (tipo=2 AND classe=%s)){filtro} GROUP BY {bucket_expr}",
        [codigo_conta, codigo_conta] + params_range,
    )
    receitas = {r["bucket"]: _round2(r["total"]) for r in cur.fetchall()}
    return {"despesas": despesas, "receitas": receitas}


def _receitas_despesas_mes_sync(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        data_inicial, data_final = _resolver_periodo(periodo, mes_ref)
        contas = _contas_alvo_sync(cur, conta)
        if not contas:
            return {"success": False, "message": "Nenhuma conta encontrada."}

        despesas_por_mes: dict = {}
        receitas_por_mes: dict = {}
        for c in contas:
            r = _receitas_despesas_mes_conta_sync(cur, int(c["codigo"]), data_inicial, data_final)
            for balde, v in r["despesas"].items():
                despesas_por_mes[balde] = _round2(despesas_por_mes.get(balde, 0) + v)
            for balde, v in r["receitas"].items():
                receitas_por_mes[balde] = _round2(receitas_por_mes.get(balde, 0) + v)

        meses = sorted(set(despesas_por_mes) | set(receitas_por_mes))
        linhas = []
        for m in meses:
            rec = receitas_por_mes.get(m, 0)
            desp = despesas_por_mes.get(m, 0)
            chave = m.isoformat() if hasattr(m, "isoformat") else str(m)
            linhas.append({"mes": chave, "receitas": rec, "despesas": desp, "saldo": _round2(rec - desp)})

        cur.close()
        conn.close()
        return {"success": True, "linhas": linhas}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def receitas_despesas_mes(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_receitas_despesas_mes_sync, servidor, banco, conta, periodo, mes_ref)


# =============================================================================
# Grade de Movimentações do período
# =============================================================================

def _listar_movimentacoes_sync(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str]) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        data_inicial, data_final = _resolver_periodo(periodo, mes_ref)
        contas = _contas_alvo_sync(cur, conta)
        if not contas:
            return {"success": True, "items": []}
        contas_ids = [int(c["codigo"]) for c in contas]
        placeholders = ",".join(["%s"] * len(contas_ids))

        filtro_data = ""
        params = list(contas_ids) + list(contas_ids)
        if data_inicial and data_final:
            filtro_data = " AND m.data_liquidacao BETWEEN %s AND %s"
            params += [data_inicial, data_final]

        cur.execute(
            f"SELECT m.codigo, m.conta, m.classe, m.data_liquidacao, m.documento, m.favorecido, "
            f"f.descricao AS favorecido_nome, m.valor, m.tipo, m.memorando, "
            f"ISNULL(m.flag_transf_caixa,'') AS flag_transf_caixa "
            f"FROM movimentacoes m LEFT JOIN favorecidos f ON f.codigo = m.favorecido "
            f"WHERE (m.conta IN ({placeholders}) OR (m.tipo = 2 AND m.classe IN ({placeholders}))){filtro_data} "
            f"ORDER BY m.data_liquidacao DESC, m.codigo DESC",
            params,
        )
        items = []
        for r in cur.fetchall():
            eh_saida = int(r["tipo"]) in (0, 3) or (int(r["tipo"]) == 2 and int(r["conta"]) in contas_ids)
            items.append({
                "codigo": int(r["codigo"]), "conta": r["conta"], "classe": r.get("classe"),
                "data_liquidacao": r["data_liquidacao"].isoformat() if r.get("data_liquidacao") else None,
                "documento": r.get("documento"), "favorecido_nome": (r.get("favorecido_nome") or "").strip(),
                "valor": float(r.get("valor") or 0), "tipo": int(r["tipo"]), "memorando": (r.get("memorando") or "").strip(),
                "credito": (not eh_saida), "editavel": (r.get("flag_transf_caixa") or "").strip() == "",
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def listar_movimentacoes(servidor: str, banco: str, conta: Optional[int], periodo: str, mes_ref: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_listar_movimentacoes_sync, servidor, banco, conta, periodo, mes_ref)


# =============================================================================
# Lançamento direto — Pagar/Cheque(0), Receber/Depósito(1),
# Transferência(2), Saque(3). 3º caminho real de criar `movimentacoes`.
# =============================================================================

def _gravar_rateio_movimentacao_sync(cur, codigo_mov: int, rateio: list) -> None:
    cur.execute("DELETE FROM movimentacoes_centro_custo WHERE codigo_mov = %s", (codigo_mov,))
    for linha in rateio:
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (codigo_mov, linha.get("centro_custo"), linha.get("classe") or 0, linha.get("sub_classe") or 0,
             _round2(linha.get("valor")), (linha.get("memorando") or "").strip(),
             (linha.get("credito_debito") or "C").strip()[:1].upper()),
        )


def _lancar_sync(servidor: str, banco: str, dados: dict) -> dict:
    tipo = int(dados.get("tipo") if dados.get("tipo") is not None else 0)
    if tipo not in (0, 1, 2, 3):
        return {"success": False, "message": "Tipo inválido."}
    conta = dados.get("conta")
    if not conta:
        return {"success": False, "message": "Defina a Conta."}
    valor = _round2(dados.get("valor"))
    if valor <= 0:
        return {"success": False, "message": "Informe um Valor maior que zero."}
    data_liquidacao = dados.get("data_liquidacao")
    if not data_liquidacao:
        return {"success": False, "message": "Defina a Data de Liquidação."}

    rateio = dados.get("rateio") or []
    if rateio:
        soma = _round2(sum(_round2(r.get("valor")) for r in rateio))
        if soma != valor:
            return {"success": False, "message": f"A soma do rateio de centro de custo (R$ {soma:.2f}) precisa bater com o Valor (R$ {valor:.2f})."}

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        favorecido = _upsert_favorecido_sync(cur, dados.get("favorecido_nome"))

        if tipo == 2:
            conta_destino = dados.get("conta_destino")
            if not conta_destino:
                return {"success": False, "message": "Defina a Conta de destino da Transferência."}
            if int(conta_destino) == int(conta):
                return {"success": False, "message": "A conta de origem e destino não podem ser a mesma."}
            classe_codigo = int(conta_destino)
            sub_classe_codigo = None
        else:
            # Classe/Sub-Classe são códigos reais do Plano de Contas —
            # sempre escolhidos numa combobox no frontend, nunca texto
            # livre (mesmo achado/correção já aplicado em
            # previsoes_service.py, 2026-08-31).
            classe_codigo = dados.get("classe")
            sub_classe_codigo = dados.get("sub_classe")

        memorando = (dados.get("memorando") or "").strip()
        documento = (dados.get("documento") or "").strip() or None
        data_documento = dados.get("data_documento") or data_liquidacao
        data_vencimento = dados.get("data_vencimento") or data_liquidacao

        cur.execute(
            "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
            "favorecido,valor,classe,sub_classe,tipo,memorando) OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (int(conta), data_liquidacao, documento, data_documento, data_vencimento, favorecido, valor,
             classe_codigo, sub_classe_codigo, tipo, memorando),
        )
        cod_mov = int(cur.fetchone()["codigo"])

        if tipo == 1:
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, int(conta)))
        elif tipo == 2:
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, int(conta)))
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, int(dados.get("conta_destino"))))
        else:  # 0=Pagar, 3=Saque
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, int(conta)))

        _gravar_rateio_movimentacao_sync(cur, cod_mov, rateio)
        conn.commit()
        cur.close()
        return {"success": True, "codigo": cod_mov, "message": "Lançamento gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def lancar(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_lancar_sync, servidor, banco, dados)


def _excluir_lancamento_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT * FROM movimentacoes WHERE codigo = %s", (codigo,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Lançamento não encontrado."}
        if (row.get("flag_transf_caixa") or "").strip() != "":
            return {"success": False, "message": "Este lançamento pertence a outra tela (Transferência p/Fluxo de Caixa/Previsões/Agrupamento de Comandas) — a exclusão precisa ser feita lá."}

        tipo = int(row["tipo"])
        valor = _round2(row["valor"])
        conta = int(row["conta"])
        if tipo == 1:
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, conta))
        elif tipo == 2:
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, conta))
            if row.get("classe"):
                cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, int(row["classe"])))
        else:
            cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s", (valor, conta))

        cur.execute("DELETE FROM movimentacoes_centro_custo WHERE codigo_mov = %s", (codigo,))
        cur.execute("DELETE FROM movimentacoes WHERE codigo = %s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Lançamento excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


async def excluir_lancamento(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_excluir_lancamento_sync, servidor, banco, codigo)


# =============================================================================
# Relatório "Duplicatas Recebidas" — réplica de `Revenda/frmreldur.frm`
# (achado do usuário 2026-08-31, análise de Contas a Receber). Diferente
# de "Duplicatas à Receber em Aberto" (já existente nesta aba, consulta
# direta a `/api/contas-receber?situacao=A`) — este é o relatório das
# duplicatas JÁ PAGAS (`situacao='PG'`), por período (Vencimento OU Data
# de Pagamento, à escolha), com resumo por forma de pagamento.
#
# **Escopo desta rodada** (mesmo princípio de #027 — "Consultar" de Contas
# a Receber — filtros de alto valor primeiro, mais complexos registrados
# como pendência explícita, não construídos sem confirmação): Período,
# Cliente, Forma de Pagamento. **Fora desta rodada**: filtro por Banco
# (`drv.banco_cedente`, coluna real confirmada mas não exposta ainda) e
# por Vendedor (no legado, só funciona pra duplicata de origem Comanda,
# via join convoluto `duplicata_rec_nf→receber→movimentacao` com
# `movimentacao.serie_nf='CM'` — lógica genuinamente frágil/específica do
# legado, decidida deixar de fora até haver pedido explícito) — e o
# sub-filtro Comandas/NF's (`dr.desmembramento='CM'` vs. não).
# =============================================================================

def _relatorio_duplicatas_recebidas_sync(
    servidor: str, banco: str, *, data_ini: str, data_fim: str, base: str = "vencimento",
    cliente: Optional[int] = None, forma_pag: Optional[str] = None, banco_cedente: Optional[int] = None,
    vendedor: Optional[int] = None, comandas: bool = True, notas_fiscais: bool = True,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        coluna_data = "drv.data_pag" if base == "pagamento" else "drv.dt_vencimento"
        where = ["drv.situacao = 'PG'", f"{coluna_data} >= %s", f"{coluna_data} <= %s"]
        params: list = [data_ini, data_fim]
        if cliente:
            where.append("dr.cliente = %s")
            params.append(cliente)
        if forma_pag:
            where.append("drv.forma_pag = %s")
            params.append(forma_pag)
        if banco_cedente:
            where.append("drv.banco_cedente = %s")
            params.append(banco_cedente)
        # "Comandas"/"NF's" (`dr.desmembramento = 'CM'` marca origem por
        # Comanda, réplica de `frmreldur.frm::Check1`/`Check2`) — se os 2
        # estiverem marcados (ou os 2 desmarcados, mesmo fallback do
        # legado: "sem nenhum marcado" vira "os dois marcados") não filtra
        # nada; só restringe quando exatamente 1 dos 2 está ativo.
        if comandas and not notas_fiscais:
            where.append("dr.desmembramento = 'CM'")
        elif notas_fiscais and not comandas:
            where.append("dr.desmembramento <> 'CM'")
        # Vendedor — réplica do `Combo1` (só funciona pra duplicata de
        # origem Comanda no legado, via `duplicata_rec_nf→Receber→
        # movimentacao`, `serie_nf='CM'`; uma duplicata sem NF vinculada a
        # uma comanda desse vendedor nunca aparece com esse filtro ativo —
        # é limitação real da fonte, não bug desta migração). Aplicado
        # aqui independente da base do período (Vencimento/Data PG) — no
        # legado só funcionava na base "Data PG"; extensão deliberada,
        # não achado sem precedente (a relação de dados não depende de
        # qual data foi escolhida pro filtro de período).
        if vendedor:
            where.append(
                "EXISTS (SELECT 1 FROM Duplicata_Rec_Nf drnf JOIN Receber r ON r.codigo = drnf.nf_fiscal "
                "JOIN movimentacao m ON m.serie_nf = 'CM' AND m.num_nf = r.cod_n_fiscal "
                "WHERE drnf.duplicata = dr.codigo AND m.vendedor = %s)"
            )
            params.append(vendedor)
        cur.execute(
            "SELECT dr.duplicata, dr.desmembramento, "
            "ISNULL(c.fantasia, c.nome) AS cliente_nome, drv.valor, drv.dt_vencimento, drv.data_pag, "
            "ISNULL(drv.juros_pag,0) AS juros_pag, "
            "ISNULL(drv.outros_acres_pag,0) + ISNULL(drv.tarifa_banco,0) AS outros_acrescimos, "
            "ISNULL(drv.desconto_pag,0) AS desconto_pag, ISNULL(drv.outros_desc_pag,0) AS outros_desc_pag, "
            "ISNULL(drv.valor_pag,0) AS valor_pag, "
            "(SELECT fp.descricao FROM forma_pagamento fp WHERE fp.codigo = drv.forma_pag) AS forma_pagamento "
            "FROM Duplicata_Rec_Venc drv "
            "JOIN Duplicata_Receber dr ON dr.codigo = drv.duplicata "
            "JOIN Cliente c ON c.codigo = dr.cliente "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY {coluna_data}, dr.duplicata, dr.desmembramento",
            tuple(params),
        )
        linhas = cur.fetchall()
        cur.close(); conn.close()

        itens = []
        resumo_fp: dict[str, float] = {}
        total_valor_pag = 0.0
        for r in linhas:
            valor_pag = float(r["valor_pag"] or 0)
            total_valor_pag += valor_pag
            fp_nome = (r.get("forma_pagamento") or "SEM FORMA CADASTRADA").strip() or "SEM FORMA CADASTRADA"
            resumo_fp[fp_nome] = resumo_fp.get(fp_nome, 0.0) + valor_pag
            itens.append({
                "duplicata": r["duplicata"], "desmembramento": r["desmembramento"],
                "cliente_nome": r["cliente_nome"], "valor": float(r["valor"] or 0),
                "dt_vencimento": str(r["dt_vencimento"]) if r.get("dt_vencimento") else None,
                "data_pag": str(r["data_pag"]) if r.get("data_pag") else None,
                "juros_pag": float(r["juros_pag"] or 0), "outros_acrescimos": float(r["outros_acrescimos"] or 0),
                "desconto_pag": float(r["desconto_pag"] or 0), "outros_desc_pag": float(r["outros_desc_pag"] or 0),
                "valor_pag": valor_pag, "forma_pagamento": r.get("forma_pagamento"),
            })
        return {
            "success": True, "itens": itens,
            "resumo_forma_pag": [{"forma_pagamento": k, "valor": v} for k, v in sorted(resumo_fp.items())],
            "total_valor_pag": round(total_valor_pag, 2),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def relatorio_duplicatas_recebidas(
    servidor: str, banco: str, *, data_ini: str, data_fim: str, base: str = "vencimento",
    cliente: Optional[int] = None, forma_pag: Optional[str] = None, banco_cedente: Optional[int] = None,
    vendedor: Optional[int] = None, comandas: bool = True, notas_fiscais: bool = True,
) -> dict:
    return await asyncio.to_thread(
        _relatorio_duplicatas_recebidas_sync, servidor, banco, data_ini=data_ini, data_fim=data_fim,
        base=base, cliente=cliente, forma_pag=forma_pag, banco_cedente=banco_cedente,
        vendedor=vendedor, comandas=comandas, notas_fiscais=notas_fiscais,
    )


# =============================================================================
# Relatório "Duplicatas Pagas" — réplica de `Revenda/frmreldup.frm` (mirror
# de "Duplicatas Recebidas" acima, achado do usuário 2026-08-31 na
# varredura do ecossistema Pagar — ver AJUSTES.md #039).
#
# **Mais simples que o mirror de Receber, confirmado ao ler a fonte real**:
# só período (Vencimento OU Data de Pagamento, `Option1`/`Else`) e filtro
# opcional por Fornecedor (`proc_for`) — a fonte NÃO junta
# `forma_pagamento` nem tem filtro de Banco/Vendedor/Comandas-NF's aqui
# (diferente de `frmreldur.frm`). Agrupamento real do legado é por DIA
# (`Grid.AddItem "TO"..."Total do Dia"`), com subtotal de
# valor/juros/outros_acres/desconto/outros_desc/valor_pag por dia + Total
# Geral no fim — não por forma de pagamento.
# =============================================================================

def _relatorio_duplicatas_pagas_sync(
    servidor: str, banco: str, *, data_ini: str, data_fim: str, base: str = "vencimento",
    fornecedor: Optional[int] = None,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        coluna_data = "drv.data_pag" if base == "pagamento" else "drv.dt_vencimento"
        where = ["drv.situacao = 'PG'", f"{coluna_data} >= %s", f"{coluna_data} <= %s"]
        params: list = [data_ini, data_fim]
        if fornecedor:
            where.append("dp.fornecedor = %s")
            params.append(fornecedor)
        cur.execute(
            "SELECT dp.duplicata, drv.desmembramento, ISNULL(f.fantasia, f.nome) AS fornecedor_nome, "
            "drv.valor, drv.dt_vencimento, drv.data_pag, "
            "ISNULL(drv.juros_pag,0) AS juros_pag, ISNULL(drv.outros_acres_pag,0) AS outros_acres_pag, "
            "ISNULL(drv.desconto_pag,0) AS desconto_pag, ISNULL(drv.outros_desc_pag,0) AS outros_desc_pag, "
            "ISNULL(drv.valor_pag,0) AS valor_pag, drv.obs_vencimento "
            "FROM Duplicata_Pag_Venc drv "
            "JOIN Duplicata_Pagar dp ON dp.codigo = drv.duplicata "
            "JOIN Fornecedor f ON f.codigo_int = dp.fornecedor "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY {coluna_data}, dp.duplicata, drv.desmembramento",
            tuple(params),
        )
        linhas = cur.fetchall()
        cur.close(); conn.close()

        itens = []
        resumo_dia: dict[str, dict[str, float]] = {}
        total = {"valor": 0.0, "juros_pag": 0.0, "outros_acres_pag": 0.0, "desconto_pag": 0.0, "outros_desc_pag": 0.0, "valor_pag": 0.0}
        for r in linhas:
            data_grupo = str(r["dt_vencimento"] if base != "pagamento" else r["data_pag"])[:10]
            dia = resumo_dia.setdefault(data_grupo, {"valor": 0.0, "juros_pag": 0.0, "outros_acres_pag": 0.0, "desconto_pag": 0.0, "outros_desc_pag": 0.0, "valor_pag": 0.0})
            for campo in total:
                v = float(r.get(campo) or 0)
                dia[campo] += v
                total[campo] += v
            itens.append({
                "duplicata": r["duplicata"], "desmembramento": r["desmembramento"],
                "fornecedor_nome": r["fornecedor_nome"], "valor": float(r["valor"] or 0),
                "dt_vencimento": str(r["dt_vencimento"]) if r.get("dt_vencimento") else None,
                "data_pag": str(r["data_pag"]) if r.get("data_pag") else None,
                "juros_pag": float(r["juros_pag"] or 0), "outros_acres_pag": float(r["outros_acres_pag"] or 0),
                "desconto_pag": float(r["desconto_pag"] or 0), "outros_desc_pag": float(r["outros_desc_pag"] or 0),
                "valor_pag": float(r["valor_pag"] or 0), "observacao": r.get("obs_vencimento"),
            })
        resumo_por_dia = [
            {"data": k, **{campo: round(v, 2) for campo, v in vals.items()}}
            for k, vals in sorted(resumo_dia.items())
        ]
        return {
            "success": True, "itens": itens, "resumo_por_dia": resumo_por_dia,
            "total": {campo: round(v, 2) for campo, v in total.items()},
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def relatorio_duplicatas_pagas(
    servidor: str, banco: str, *, data_ini: str, data_fim: str, base: str = "vencimento",
    fornecedor: Optional[int] = None,
) -> dict:
    return await asyncio.to_thread(
        _relatorio_duplicatas_pagas_sync, servidor, banco, data_ini=data_ini, data_fim=data_fim,
        base=base, fornecedor=fornecedor,
    )
