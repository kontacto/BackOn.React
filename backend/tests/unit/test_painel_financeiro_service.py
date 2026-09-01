"""Testes unitários do Painel de Movimentações (Financeiro > Fluxo de
Caixa, migração de `Kontacto\\FrmPnlCon.frm` — ver
services/painel_financeiro_service.py pro rastreio completo, inclusive
as fórmulas conferidas direto contra `Dao_Kash_Painel.vb`)."""
from datetime import date

import services.painel_financeiro_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestResolverPeriodo:
    def test_hoje(self):
        ini, fim = svc._resolver_periodo("hoje", None)
        assert ini == fim == date.today().isoformat()

    def test_tudo_sem_filtro(self):
        assert svc._resolver_periodo("tudo", None) == (None, None)

    def test_mes_com_referencia(self):
        assert svc._resolver_periodo("mes", "2026-02") == ("2026-02-01", "2026-02-28")

    def test_mes_dezembro_vira_ano(self):
        assert svc._resolver_periodo("mes", "2026-12") == ("2026-12-01", "2026-12-31")

    def test_30dias_termina_hoje(self):
        ini, fim = svc._resolver_periodo("30dias", None)
        assert fim == date.today().isoformat()


class TestResumoContaSync:
    def test_sem_periodo_so_saldo_inicial_e_totais_sem_filtro_data(self, monkeypatch):
        cur = FakeCursor(one=[
            {"saldo_inicial": 1000.0},  # contas.saldo_inicial
            {"totmov": 200.0},          # despesas (sem filtro periodo -> tudo)
            {"totmov": 300.0},          # receitas
        ])
        r = svc._resumo_conta_sync(cur, 1, None, None)
        assert r["saldo_anterior_periodo"] == 1000.0
        assert r["total_despesas_periodo"] == 200.0
        assert r["total_receitas_periodo"] == 300.0
        assert r["saldo_fim_periodo"] == 1100.0

    def test_com_periodo_desconta_movimentacoes_anteriores(self, monkeypatch):
        cur = FakeCursor(one=[
            {"saldo_inicial": 1000.0},  # contas.saldo_inicial
            {"totmov": 100.0},          # despesas antes do periodo (tipo 0/3/2)
            {"totmov": 50.0},           # receitas antes do periodo (tipo 1 ou 2/classe)
            {"totmov": 40.0},           # despesas do periodo
            {"totmov": 60.0},           # receitas do periodo
        ])
        r = svc._resumo_conta_sync(cur, 1, "2026-08-01", "2026-08-31")
        # saldo_anterior = 1000 - 100 + 50 = 950
        assert r["saldo_anterior_periodo"] == 950.0
        assert r["total_despesas_periodo"] == 40.0
        assert r["total_receitas_periodo"] == 60.0
        # saldo_fim = 950 + 60 - 40 = 970
        assert r["saldo_fim_periodo"] == 970.0
        assert "BETWEEN" in cur.queries[-1][0]
        assert "BETWEEN" in cur.queries[-2][0]

    def test_totmov_none_vira_zero(self, monkeypatch):
        cur = FakeCursor(one=[{"saldo_inicial": 500.0}, {"totmov": None}, {"totmov": None}])
        r = svc._resumo_conta_sync(cur, 1, None, None)
        assert r["total_despesas_periodo"] == 0.0
        assert r["saldo_fim_periodo"] == 500.0


class TestAlertasSync:
    def test_monta_os_4_blocos(self, monkeypatch):
        cur = FakeCursor(one=[
            {"total": 500.0, "qtd": 2},   # receber atraso
            {"total": 100.0, "qtd": 1},   # receber hoje
            {"total": 300.0, "qtd": 3},   # pagar atraso
            {"total": 80.0, "qtd": 1},    # pagar hoje
        ])
        r = svc._alertas_sync(cur, [1, 2])
        assert r["contas_a_receber_atraso"]["total"] == 500.0
        assert r["contas_a_receber_hoje"]["qtd"] == 1
        assert r["pagamentos_atraso"]["total"] == 300.0
        assert r["a_pagar_hoje"]["total"] == 80.0
        # confirma que a query de "a pagar" filtra por conta quando informado
        pagar_queries = [q for q, p in cur.queries if "FROM previsoes" in q]
        assert all("conta IN" in q for q in pagar_queries)

    def test_sem_contas_nao_filtra_previsoes_por_conta(self, monkeypatch):
        cur = FakeCursor(one=[
            {"total": 0.0, "qtd": 0}, {"total": 0.0, "qtd": 0},
            {"total": 0.0, "qtd": 0}, {"total": 0.0, "qtd": 0},
        ])
        svc._alertas_sync(cur, [])
        pagar_queries = [q for q, p in cur.queries if "FROM previsoes" in q]
        assert all("conta IN" not in q for q in pagar_queries)


class TestResumoSync:
    def test_conta_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._resumo_sync("srv", "bd", 999, "mes", None)
        assert r["success"] is False

    def test_soma_saldo_atual_de_todas_as_contas(self, monkeypatch):
        cur = FakeCursor(
            many=[[{"codigo": 1, "descricao": "A", "saldo_inicial": 0, "saldo_atual": 100.0},
                   {"codigo": 2, "descricao": "B", "saldo_inicial": 0, "saldo_atual": 50.0}]],
            one=(
                [{"saldo_inicial": 0}, {"totmov": 0}, {"totmov": 0}, {"totmov": 0}, {"totmov": 0}] * 2
                + [{"total": 0, "qtd": 0}] * 4
            ),
        )
        _patch(monkeypatch, cur)
        r = svc._resumo_sync("srv", "bd", None, "mes", None)
        assert r["success"] is True
        assert r["saldo_atual"] == 150.0


class TestLancarSync:
    def test_tipo_invalido(self, monkeypatch):
        r = svc._lancar_sync("srv", "bd", {"tipo": 9, "conta": 1, "valor": 10, "data_liquidacao": "2026-01-01"})
        assert r["success"] is False

    def test_valor_zero_bloqueia(self, monkeypatch):
        r = svc._lancar_sync("srv", "bd", {"tipo": 0, "conta": 1, "valor": 0, "data_liquidacao": "2026-01-01"})
        assert r["success"] is False

    def test_rateio_nao_bate_bloqueia(self, monkeypatch):
        r = svc._lancar_sync("srv", "bd", {
            "tipo": 0, "conta": 1, "valor": 100, "data_liquidacao": "2026-01-01",
            "rateio": [{"centro_custo": 1, "valor": 40}],
        })
        assert r["success"] is False

    def test_pagar_debita_conta(self, monkeypatch):
        # classe é código real (combobox), sem query de resolução
        cur = FakeCursor(one=[None, {"codigo": 1}, {"codigo": 700}])
        conn = _patch(monkeypatch, cur)
        r = svc._lancar_sync("srv", "bd", {
            "tipo": 0, "conta": 1, "valor": 100.0, "data_liquidacao": "2026-01-10",
            "favorecido_nome": "X", "classe": 5,
        })
        assert r["success"] is True
        assert conn.committed is True
        deb = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        assert len(deb) == 1

    def test_receber_credita_conta(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 1}, {"codigo": 701}])
        _patch(monkeypatch, cur)
        r = svc._lancar_sync("srv", "bd", {
            "tipo": 1, "conta": 1, "valor": 100.0, "data_liquidacao": "2026-01-10",
            "favorecido_nome": "X", "classe": 5,
        })
        assert r["success"] is True

    def test_saque_debita_como_pagar(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 702}])
        _patch(monkeypatch, cur)
        r = svc._lancar_sync("srv", "bd", {"tipo": 3, "conta": 1, "valor": 50.0, "data_liquidacao": "2026-01-10"})
        assert r["success"] is True
        deb = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        assert len(deb) == 1

    def test_transferencia_exige_conta_destino(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._lancar_sync("srv", "bd", {"tipo": 2, "conta": 1, "valor": 10, "data_liquidacao": "2026-01-01"})
        assert r["success"] is False

    def test_transferencia_debita_origem_credita_destino(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 703}])
        _patch(monkeypatch, cur)
        r = svc._lancar_sync("srv", "bd", {"tipo": 2, "conta": 1, "conta_destino": 2, "valor": 10, "data_liquidacao": "2026-01-01"})
        assert r["success"] is True
        deb = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        cred = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        assert deb[0][1] == 1
        assert cred[0][1] == 2


class TestSerieSaldo:
    def test_serie_saldo_conta_agrupa_por_dia_com_periodo(self):
        cur = FakeCursor(many=[
            [{"bucket": date(2026, 8, 1), "total": 40.0}, {"bucket": date(2026, 8, 3), "total": 10.0}],
            [{"bucket": date(2026, 8, 2), "total": 100.0}],
        ])
        r = svc._serie_saldo_conta_sync(cur, 1, "2026-08-01", "2026-08-31")
        assert r == {date(2026, 8, 1): -40.0, date(2026, 8, 2): 100.0, date(2026, 8, 3): -10.0}
        assert "BETWEEN" in cur.queries[0][0]

    def test_serie_saldo_conta_sem_periodo_agrupa_por_mes(self):
        cur = FakeCursor(many=[[], []])
        svc._serie_saldo_conta_sync(cur, 1, None, None)
        assert "DATEADD" in cur.queries[0][0]
        assert "BETWEEN" not in cur.queries[0][0]

    def test_serie_saldo_sync_acumula_a_partir_do_saldo_anterior(self, monkeypatch):
        cur = FakeCursor(
            many=[
                [{"codigo": 1, "descricao": "A", "saldo_inicial": 0, "saldo_atual": 100.0}],
                [{"bucket": date(2026, 8, 1), "total": 20.0}],
                [{"bucket": date(2026, 8, 1), "total": 50.0}],
            ],
            one=[
                {"saldo_inicial": 200.0},
                {"totmov": 0},
                {"totmov": 0},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._serie_saldo_sync("srv", "bd", None, "tudo", None)
        assert r["success"] is True
        assert r["saldo_inicial"] == 200.0
        assert r["pontos"] == [{"data": "2026-08-01", "saldo": 230.0}]

    def test_serie_saldo_sync_sem_contas(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._serie_saldo_sync("srv", "bd", 999, "mes", None)
        assert r["success"] is False


class TestSaldoPrevistoReal:
    def test_avancar_mes_painel_normal(self):
        assert svc._avancar_mes_painel(2026, 1, 15, 2) == date(2026, 3, 15)

    def test_avancar_mes_painel_dia_invalido_vira_dia1_mes_seguinte(self):
        # fallback ESPECÍFICO desta expansão — diferente de avancar_data_frequencia
        assert svc._avancar_mes_painel(2026, 1, 31, 1) == date(2026, 3, 1)

    def test_pendencia_conta_liquido_entrada_menos_saida(self):
        cur = FakeCursor(many=[
            [{"valor": 100.0, "tipo": 0, "conta": 1}],
            [{"valor": 40.0, "tipo": 2, "conta": 2}],
        ])
        r = svc._pendencia_conta_sync(cur, 1, "2026-08-01")
        assert r == -60.0

    def test_previsoes_expandidas_unica_vez_dentro_do_periodo(self):
        cur = FakeCursor(many=[
            [{"valor": 50.0, "tipo": 0, "conta": 1, "data_vencimento": date(2026, 8, 15), "frequencia": 10}],
            [],
        ])
        desp, rec = svc._previsoes_expandidas_conta_sync(cur, 1, date(2026, 8, 1), date(2026, 8, 31))
        assert desp == 50.0
        assert rec == 0.0

    def test_previsoes_expandidas_unica_vez_fora_do_periodo_nao_conta(self):
        cur = FakeCursor(many=[
            [{"valor": 50.0, "tipo": 0, "conta": 1, "data_vencimento": date(2026, 9, 15), "frequencia": 10}],
            [],
        ])
        desp, rec = svc._previsoes_expandidas_conta_sync(cur, 1, date(2026, 8, 1), date(2026, 8, 31))
        assert desp == 0.0
        assert rec == 0.0

    def test_previsoes_expandidas_diario_multiplas_ocorrencias(self):
        cur = FakeCursor(many=[
            [{"valor": 10.0, "tipo": 1, "conta": 1, "data_vencimento": date(2026, 8, 1), "frequencia": 0}],
            [],
        ])
        desp, rec = svc._previsoes_expandidas_conta_sync(cur, 1, date(2026, 8, 1), date(2026, 8, 5))
        assert desp == 0.0
        assert rec == 50.0  # 5 ocorrencias (1,2,3,4,5/08) x 10

    def test_previsoes_expandidas_mensal_3_ocorrencias(self):
        cur = FakeCursor(many=[
            [{"valor": 30.0, "tipo": 1, "conta": 1, "data_vencimento": date(2026, 6, 10), "frequencia": 4}],
            [],
        ])
        desp, rec = svc._previsoes_expandidas_conta_sync(cur, 1, date(2026, 7, 1), date(2026, 9, 30))
        assert desp == 0.0
        assert rec == 90.0

    def test_previsoes_expandidas_transferencia_saida_e_entrada(self):
        # conta=1 é ORIGEM (despesa) de uma transferencia recorrente
        cur = FakeCursor(many=[
            [{"valor": 20.0, "tipo": 2, "conta": 1, "data_vencimento": date(2026, 8, 5), "frequencia": 10}],
            [],
        ])
        desp, rec = svc._previsoes_expandidas_conta_sync(cur, 1, date(2026, 8, 1), date(2026, 8, 31))
        assert desp == 20.0
        assert rec == 0.0

    def test_saldo_previsto_real_periodo_tudo_cai_no_fallback(self):
        cur = FakeCursor()
        alertas = {"pagamentos_atraso": {"total": 10}, "a_pagar_hoje": {"total": 0}, "contas_a_receber_atraso": {"total": 20}, "contas_a_receber_hoje": {"total": 0}}
        r = svc._saldo_previsto_real_sync(cur, [], 100.0, None, None, alertas, False, False)
        assert r == 110.0

    def test_saldo_previsto_real_desconsiderar_pendencias_pula_pendencia(self, monkeypatch):
        cur = FakeCursor(many=[[], []])
        chamado = {"pendencia": False}
        monkeypatch.setattr(svc, "_pendencia_conta_sync", lambda *a, **k: chamado.update(pendencia=True) or 999)
        alertas = {"pagamentos_atraso": {"total": 0}, "a_pagar_hoje": {"total": 0}, "contas_a_receber_atraso": {"total": 0}, "contas_a_receber_hoje": {"total": 0}}
        r = svc._saldo_previsto_real_sync(cur, [{"codigo": 1}], 100.0, "2026-08-01", "2026-08-31", alertas, False, True)
        assert chamado["pendencia"] is False
        assert r == 100.0

    def test_saldo_previsto_real_partir_de_hoje_usa_hoje_na_pendencia(self, monkeypatch):
        cur = FakeCursor(many=[[], []])
        recebido = {}
        monkeypatch.setattr(svc, "_pendencia_conta_sync", lambda cur, codigo, di: recebido.update(di=di) or 0)
        alertas = {"pagamentos_atraso": {"total": 0}, "a_pagar_hoje": {"total": 0}, "contas_a_receber_atraso": {"total": 0}, "contas_a_receber_hoje": {"total": 0}}
        svc._saldo_previsto_real_sync(cur, [{"codigo": 1}], 100.0, "2026-08-01", "2026-08-31", alertas, True, False)
        assert recebido["di"] == date.today().isoformat()


class TestReceitasDespesasMes:
    def test_agrega_receitas_e_despesas_por_mes(self, monkeypatch):
        cur = FakeCursor(
            many=[
                [{"codigo": 1, "descricao": "A", "saldo_inicial": 0, "saldo_atual": 100.0}],
                [{"bucket": date(2026, 7, 1), "total": 20.0}, {"bucket": date(2026, 8, 1), "total": 40.0}],
                [{"bucket": date(2026, 7, 1), "total": 50.0}],
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._receitas_despesas_mes_sync("srv", "bd", None, "tudo", None)
        assert r["success"] is True
        assert r["linhas"] == [
            {"mes": "2026-07-01", "receitas": 50.0, "despesas": 20.0, "saldo": 30.0},
            {"mes": "2026-08-01", "receitas": 0.0, "despesas": 40.0, "saldo": -40.0},
        ]

    def test_sem_contas(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._receitas_despesas_mes_sync("srv", "bd", 999, "tudo", None)
        assert r["success"] is False


class TestExcluirLancamento:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_lancamento_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_bloqueia_de_outra_tela(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": 0, "valor": 10, "conta": 1, "classe": None, "flag_transf_caixa": "R"}])
        _patch(monkeypatch, cur)
        r = svc._excluir_lancamento_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "outra tela" in r["message"]

    def test_pagar_reverte_credita_de_volta(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": 0, "valor": 10, "conta": 1, "classe": None, "flag_transf_caixa": ""}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_lancamento_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        cred = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        assert len(cred) == 1

    def test_transferencia_reverte_as_duas_contas(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": 2, "valor": 10, "conta": 1, "classe": 2, "flag_transf_caixa": None}])
        _patch(monkeypatch, cur)
        r = svc._excluir_lancamento_sync("srv", "bd", 1)
        assert r["success"] is True
        cred = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        deb = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        assert cred[0][1] == 1
        assert deb[0][1] == 2


class TestRelatorioDuplicatasRecebidas:
    """"Duplicatas Recebidas" (`Revenda/frmreldur.frm`) — achado do
    usuário 2026-08-31, análise de Contas a Receber."""

    def test_lista_vazia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._relatorio_duplicatas_recebidas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        assert r["success"] is True
        assert r["itens"] == []
        assert r["total_valor_pag"] == 0

    def test_agrupa_resumo_por_forma_pagamento(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"duplicata": 100, "desmembramento": 0, "cliente_nome": "Cliente A", "valor": 100.0,
             "dt_vencimento": "2026-08-10", "data_pag": "2026-08-10", "juros_pag": 0, "outros_acrescimos": 0,
             "desconto_pag": 0, "outros_desc_pag": 0, "valor_pag": 100.0, "forma_pagamento": "DINHEIRO"},
            {"duplicata": 101, "desmembramento": 0, "cliente_nome": "Cliente B", "valor": 50.0,
             "dt_vencimento": "2026-08-11", "data_pag": "2026-08-11", "juros_pag": 0, "outros_acrescimos": 0,
             "desconto_pag": 0, "outros_desc_pag": 0, "valor_pag": 50.0, "forma_pagamento": "DINHEIRO"},
            {"duplicata": 102, "desmembramento": 0, "cliente_nome": "Cliente C", "valor": 30.0,
             "dt_vencimento": "2026-08-12", "data_pag": "2026-08-12", "juros_pag": 0, "outros_acrescimos": 0,
             "desconto_pag": 0, "outros_desc_pag": 0, "valor_pag": 30.0, "forma_pagamento": None},
        ]])
        _patch(monkeypatch, cur)
        r = svc._relatorio_duplicatas_recebidas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        assert r["success"] is True
        assert len(r["itens"]) == 3
        assert r["total_valor_pag"] == 180.0
        resumo = {x["forma_pagamento"]: x["valor"] for x in r["resumo_forma_pag"]}
        assert resumo["DINHEIRO"] == 150.0
        assert resumo["SEM FORMA CADASTRADA"] == 30.0

    def test_base_pagamento_usa_coluna_data_pag(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", base="pagamento")
        q = cur.queries[0][0]
        assert "drv.data_pag >= %s" in q
        assert "ORDER BY drv.data_pag" in q

    def test_base_vencimento_e_o_padrao(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        q = cur.queries[0][0]
        assert "drv.dt_vencimento >= %s" in q

    def test_filtro_cliente_e_forma_pag_aplicados(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", cliente=42, forma_pag="01",
        )
        q, p = cur.queries[0]
        assert "dr.cliente = %s" in q and "drv.forma_pag = %s" in q
        assert p == ("2026-08-01", "2026-08-31", 42, "01")

    def test_falha_conexao_nao_propaga(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("boom")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._relatorio_duplicatas_recebidas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        assert r["success"] is False

    def test_filtro_banco_cedente_aplicado(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", banco_cedente=7,
        )
        q, p = cur.queries[0]
        assert "drv.banco_cedente = %s" in q
        assert p == ("2026-08-01", "2026-08-31", 7)

    def test_ambos_marcados_nao_filtra_por_origem(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        q = cur.queries[0][0]
        assert "dr.desmembramento = 'CM'" not in q and "dr.desmembramento <> 'CM'" not in q

    def test_nenhum_marcado_cai_no_fallback_de_ambos(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", comandas=False, notas_fiscais=False,
        )
        q = cur.queries[0][0]
        assert "dr.desmembramento = 'CM'" not in q and "dr.desmembramento <> 'CM'" not in q

    def test_so_comandas_filtra_cm(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", comandas=True, notas_fiscais=False,
        )
        q = cur.queries[0][0]
        assert "dr.desmembramento = 'CM'" in q

    def test_so_nf_exclui_cm(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", comandas=False, notas_fiscais=True,
        )
        q = cur.queries[0][0]
        assert "dr.desmembramento <> 'CM'" in q

    def test_filtro_vendedor_aplicado(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_recebidas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", vendedor=15,
        )
        q, p = cur.queries[0]
        assert "m.vendedor = %s" in q and "serie_nf = 'CM'" in q
        assert p == ("2026-08-01", "2026-08-31", 15)


class TestRelatorioDuplicatasPagas:
    """"Duplicatas Pagas" (`Revenda/frmreldup.frm`) — mirror mais simples
    de "Duplicatas Recebidas" (só período + Fornecedor, agrupado por dia,
    sem forma de pagamento). Achado na varredura do ecossistema Pagar,
    ver AJUSTES.md #039."""

    def test_lista_vazia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._relatorio_duplicatas_pagas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        assert r["success"] is True
        assert r["itens"] == []
        assert r["total"]["valor_pag"] == 0

    def test_agrupa_resumo_por_dia(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"duplicata": 100, "desmembramento": 0, "fornecedor_nome": "Fornecedor A", "valor": 100.0,
             "dt_vencimento": "2026-08-10", "data_pag": "2026-08-10", "juros_pag": 0, "outros_acres_pag": 0,
             "desconto_pag": 0, "outros_desc_pag": 0, "valor_pag": 100.0, "obs_vencimento": None},
            {"duplicata": 101, "desmembramento": 0, "fornecedor_nome": "Fornecedor B", "valor": 50.0,
             "dt_vencimento": "2026-08-10", "data_pag": "2026-08-10", "juros_pag": 5, "outros_acres_pag": 0,
             "desconto_pag": 0, "outros_desc_pag": 0, "valor_pag": 55.0, "obs_vencimento": None},
            {"duplicata": 102, "desmembramento": 0, "fornecedor_nome": "Fornecedor C", "valor": 30.0,
             "dt_vencimento": "2026-08-12", "data_pag": "2026-08-12", "juros_pag": 0, "outros_acres_pag": 0,
             "desconto_pag": 0, "outros_desc_pag": 0, "valor_pag": 30.0, "obs_vencimento": "obs"},
        ]])
        _patch(monkeypatch, cur)
        r = svc._relatorio_duplicatas_pagas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        assert r["success"] is True
        assert len(r["itens"]) == 3
        assert r["total"]["valor_pag"] == 185.0
        dia10 = next(d for d in r["resumo_por_dia"] if d["data"] == "2026-08-10")
        assert dia10["valor_pag"] == 155.0
        dia12 = next(d for d in r["resumo_por_dia"] if d["data"] == "2026-08-12")
        assert dia12["valor_pag"] == 30.0

    def test_base_pagamento_usa_coluna_data_pag(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_pagas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", base="pagamento")
        q = cur.queries[0][0]
        assert "drv.data_pag >= %s" in q
        assert "ORDER BY drv.data_pag" in q

    def test_base_vencimento_e_o_padrao(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_pagas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        q = cur.queries[0][0]
        assert "drv.dt_vencimento >= %s" in q

    def test_filtro_fornecedor_aplicado(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_pagas_sync(
            "srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31", fornecedor=460,
        )
        q, p = cur.queries[0]
        assert "dp.fornecedor = %s" in q
        assert p == ("2026-08-01", "2026-08-31", 460)

    def test_falha_conexao_nao_propaga(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("boom")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._relatorio_duplicatas_pagas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        assert r["success"] is False

    def test_nao_junta_forma_pagamento(self, monkeypatch):
        # Diferente de "Duplicatas Recebidas" — a fonte real
        # (`frmreldup.frm`) não junta `forma_pagamento`, confirmado ao
        # ler o SQL de `Command1_Click`.
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._relatorio_duplicatas_pagas_sync("srv", "bd", data_ini="2026-08-01", data_fim="2026-08-31")
        q = cur.queries[0][0]
        assert "forma_pagamento" not in q
