"""Testes unitários de Inatividade de Clientes — réplica de
`Geral\\FrmRelCliSMV.frm`, generalizada pra Pedido/O.S. (ver docstring do
service pro raciocínio completo: ciclos, sub-checks de Contrato, filtro
"Acima de" como piso de data)."""
import services.relatorio_inatividade_clientes_service as svc


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

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


DEFAULTS = dict(
    vendedor=None, regiao=None, segmento=None, rota=None, tipo_cliente=None,
    situacao_cadastro="todos", situacao_contrato="todos", patrimonio="todos",
    modo_base="ultima_compra", data_base=None,
    fator1=360, fator2=180, fator3=90,
    ultima_compra_desde=None, exibir_contrato_faturamento=False, exibir_contrato_pago=False,
)


class TestValidacao:
    def test_periodo_obrigatorio(self):
        r = svc._inatividade_clientes_sync("srv", "bd", "", "2026-08-07", **DEFAULTS)
        assert r["success"] is False and "período" in r["message"].lower()


class TestFluxoMinimo:
    def test_um_candidato_sem_exhibits(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": "2026-01-05"}, {"qtd": 2}, {"qtd": 1}, {"qtd": 0}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}], []],
        )
        _patch(monkeypatch, cur)
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **DEFAULTS)
        assert r["success"] is True
        assert len(r["clientes"]) == 1
        item = r["clientes"][0]
        assert item["nome"] == "Cliente A"
        assert item["ultima_compra"] == "2026-01-05"
        assert len(item["ciclos"]) == 3
        assert item["ciclos"][0]["qtd_pedidos"] == 2
        assert item["ciclos"][2]["dias_medio"] is None  # qtd=0 não divide

    def test_query_candidatos_usa_pedido_e_os(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **DEFAULTS)
        query, params = cur.queries[0]
        assert "pedido_venda" in query and " FROM os " in query
        assert "situacao='PG'" in query


class TestFiltroAcimaDe:
    def test_exclui_cliente_com_ultima_compra_antes_do_piso(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": "2025-01-01"}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}]],
        )
        _patch(monkeypatch, cur)
        args = dict(DEFAULTS); args["ultima_compra_desde"] = "2026-01-01"
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **args)
        assert r["clientes"] == []

    def test_exclui_cliente_sem_nenhuma_compra_anterior(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": None}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}]],
        )
        _patch(monkeypatch, cur)
        args = dict(DEFAULTS); args["ultima_compra_desde"] = "2026-01-01"
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **args)
        assert r["clientes"] == []


class TestPatrimonio:
    def test_com_patrimonio_exclui_sem_contrato_ativo(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": None}, {"n": 0}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}]],
        )
        _patch(monkeypatch, cur)
        args = dict(DEFAULTS); args["patrimonio"] = "com"
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **args)
        assert r["clientes"] == []

    def test_sem_patrimonio_mantem_cliente_sem_contrato(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": None}, {"n": 0}, {"qtd": 0}, {"qtd": 0}, {"qtd": 0}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}], []],
        )
        _patch(monkeypatch, cur)
        args = dict(DEFAULTS); args["patrimonio"] = "sem"
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **args)
        assert len(r["clientes"]) == 1


class TestSubChecksContrato:
    def test_exibir_ultimo_faturamento_contrato(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": None}, {"qtd": 0}, {"qtd": 0}, {"qtd": 0}, {"data": "2026-01-10"}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}], []],
        )
        _patch(monkeypatch, cur)
        args = dict(DEFAULTS); args["exibir_contrato_faturamento"] = True
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **args)
        assert r["clientes"][0]["ultimo_faturamento_contrato"] == "2026-01-10"
        query = [q for q, _ in cur.queries if "comanda_contrato" in q][0]
        assert "JOIN contratos co" in query

    def test_exibir_ultimo_faturamento_pago_usa_serie_co(self, monkeypatch):
        cur = FakeCursor(
            one=[{"ultima": None}, {"qtd": 0}, {"qtd": 0}, {"qtd": 0}, {"data_pag": "2026-01-15"}],
            many=[[{"codigo": 1, "nome": "Cliente A", "situacao": "A"}], []],
        )
        _patch(monkeypatch, cur)
        args = dict(DEFAULTS); args["exibir_contrato_pago"] = True
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **args)
        assert r["clientes"][0]["ultimo_faturamento_contrato_pago"] == "2026-01-15"
        query = [q for q, _ in cur.queries if "Duplicata_Rec_Venc" in q][0]
        assert "r.serie = 'CO'" in query


class TestSemResultados:
    def test_sem_candidatos(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._inatividade_clientes_sync("srv", "bd", "2026-02-01", "2026-02-28", **DEFAULTS)
        assert r["clientes"] == []
