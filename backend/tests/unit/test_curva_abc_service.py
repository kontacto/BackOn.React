"""Testes UNITÁRIOS de Curva ABC e Estoques."""
import services.curva_abc_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []
        self._last_query = ""

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_query = q

    def fetchone(self):
        # `_modulo_curva_abc_ativo` (pedido_common.py) roda antes da lógica
        # real de toda função deste service — devolve "módulo ligado" sem
        # consumir da fila `_one` (reservada pras queries de negócio de
        # cada teste; nenhum teste deste arquivo cobre o cenário "módulo
        # desligado").
        if "Curva_abc" in self._last_query:
            return {"Curva_abc": True}
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


class TestNumeroDeMeses:
    def test_mesmo_ano(self):
        assert svc._numero_de_meses("2026-01-01", "2026-06-30") == 6

    def test_anos_diferentes(self):
        # jan/2025 a fev/2026: 12*(0) + fev(2) + (12-jan(1)+1=12) = 14
        assert svc._numero_de_meses("2025-01-01", "2026-02-28") == 14

    def test_minimo_um_mes(self):
        assert svc._numero_de_meses("2026-06-01", "2026-06-01") >= 1


class TestGerarCurvaValidacoesSemBanco:
    def test_sem_periodo(self):
        r = svc._gerar_curva_sync("srv", "bd", "", "", "financeira", [{"curva": "A", "percentual": 100}])
        assert not r["success"]

    def test_tipo_invalido(self):
        r = svc._gerar_curva_sync("srv", "bd", "2026-01-01", "2026-06-30", "xyz", [{"curva": "A", "percentual": 100}])
        assert not r["success"] and "tipo" in r["message"].lower()

    def test_sem_faixas(self):
        r = svc._gerar_curva_sync("srv", "bd", "2026-01-01", "2026-06-30", "financeira", [])
        assert not r["success"]

    def test_soma_percentual_diferente_de_100(self):
        r = svc._gerar_curva_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", "financeira",
            [{"curva": "A", "percentual": 50}, {"curva": "B", "percentual": 40}],
        )
        assert not r["success"] and "100" in r["message"]


class TestGerarCurvaComBanco:
    def test_sem_vendas_no_periodo_bloqueia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        conn = _patch(monkeypatch, cur)
        r = svc._gerar_curva_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", "financeira",
            [{"curva": "A", "percentual": 100}],
        )
        assert not r["success"]
        assert conn.rolled

    def test_classifica_por_quantidade_de_itens_proporcional(self, monkeypatch):
        vendas = [
            {"codigo_int": f"P{i}", "descricao": f"Produto {i}", "total": 100.0 - i}
            for i in range(4)
        ]
        cur = FakeCursor(many=[vendas])
        conn = _patch(monkeypatch, cur)
        r = svc._gerar_curva_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", "financeira",
            [{"curva": "A", "percentual": 50}, {"curva": "B", "percentual": 50}],
        )
        assert r["success"] and conn.committed
        assert r["total_itens"] == 4
        curvas = [it["curva"] for it in r["items"]]
        # 4 itens, faixa A=50% -> max(1, int(50*4/100))=2 itens; B pega o resto (2)
        assert curvas == ["A", "A", "B", "B"]

    def test_reset_usa_letra_seguinte_a_ultima_faixa(self, monkeypatch):
        vendas = [{"codigo_int": "P1", "descricao": "X", "total": 10.0}]
        cur = FakeCursor(many=[vendas])
        _patch(monkeypatch, cur)
        svc._gerar_curva_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", "quantidade",
            [{"curva": "A", "percentual": 60}, {"curva": "C", "percentual": 40}],
        )
        # queries[0] é sempre a checagem de módulo (_modulo_curva_abc_ativo,
        # roda antes de qualquer lógica de negócio) — o reset é a seguinte.
        reset_q, reset_p = cur.queries[1]
        assert "update pecas set curva_abc = %s" in reset_q.lower()
        assert reset_p[0] == "D"  # próxima letra depois de C

    def test_usa_colunas_financeiras_quando_tipo_financeira(self, monkeypatch):
        vendas = [{"codigo_int": "P1", "descricao": "X", "total": 10.0}]
        cur = FakeCursor(many=[vendas])
        _patch(monkeypatch, cur)
        svc._gerar_curva_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", "financeira",
            [{"curva": "A", "percentual": 100}],
        )
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "curva_abc_fin" in joined and "percent_abc_fin" in joined


class TestReprocessarEstoquesValidacoesSemBanco:
    def test_sem_periodo(self):
        r = svc._reprocessar_estoques_sync("srv", "bd", "", "", 20.0)
        assert not r["success"]

    def test_sem_grau_atendimento(self):
        r = svc._reprocessar_estoques_sync("srv", "bd", "2026-01-01", "2026-06-30", None)
        assert not r["success"]


class TestReprocessarEstoquesComBanco:
    def test_sem_vendas_bloqueia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._reprocessar_estoques_sync("srv", "bd", "2026-01-01", "2026-06-30", 20.0)
        assert not r["success"]

    def test_calcula_com_prazo_direto_na_peca(self, monkeypatch):
        vendas = [{"codigo_int": "P1", "descricao": "Produto 1", "total": 300.0}]
        cur = FakeCursor(
            many=[vendas],
            one=[{"estoque_minimo": 5.0, "estoque_ressuprimento": 8.0, "estoque_maximo": 50.0, "prazo_fornecedor": 10}],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._reprocessar_estoques_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", 20.0,
            atualizar_minimo=True, atualizar_ressuprimento=True, atualizar_maximo=True, atualizar_consumo=True,
        )
        assert r["success"] and conn.committed
        item = r["items"][0]
        # meses = 6; cmm = int(300/6) = 50; cmm_diario = 50/30 = 1.666
        assert item["consumo_medio_mensal"] == 50
        assert item["tempo_reposicao"] == 10
        # estoque_minimo = int(50*20/100) = 10
        assert item["estoque_minimo_atual"] == 10
        # estoque_ressuprimento = int(1.666*10 + 10) = int(26.66) = 26
        assert item["estoque_ressuprimento_atual"] == 26
        # estoque_maximo = int(10+1.666)*10 = int(11.666)*10 = 11*10 = 110
        assert item["estoque_maximo_atual"] == 110

    def test_busca_prazo_do_fornecedor_quando_peca_nao_tem(self, monkeypatch):
        vendas = [{"codigo_int": "P1", "descricao": "Produto 1", "total": 60.0}]
        cur = FakeCursor(
            many=[vendas],
            one=[
                {"estoque_minimo": 0.0, "estoque_ressuprimento": 0.0, "estoque_maximo": 0.0, "prazo_fornecedor": None},
                {"prazo_pgto": 15},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._reprocessar_estoques_sync("srv", "bd", "2026-01-01", "2026-06-30", 10.0)
        item = r["items"][0]
        assert item["tempo_reposicao"] == 15

    def test_so_atualiza_campos_marcados(self, monkeypatch):
        vendas = [{"codigo_int": "P1", "descricao": "Produto 1", "total": 60.0}]
        cur = FakeCursor(
            many=[vendas],
            one=[{"estoque_minimo": 0.0, "estoque_ressuprimento": 0.0, "estoque_maximo": 0.0, "prazo_fornecedor": 5}],
        )
        _patch(monkeypatch, cur)
        svc._reprocessar_estoques_sync(
            "srv", "bd", "2026-01-01", "2026-06-30", 10.0, atualizar_minimo=True,
        )
        update_q = cur.queries[-1][0]
        assert "estoque_minimo=%s" in update_q
        assert "estoque_maximo" not in update_q and "estoque_ressuprimento" not in update_q and "consumo_medio_mensal" not in update_q.lower()
