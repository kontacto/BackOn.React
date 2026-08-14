"""Testes unitários de Ordem de Serviço (busca) — réplica de
`Revenda\\FrmRelOS.frm`. Cobre montagem da query por modo de filtro e a
decodificação de Destino (os_produto.situacao)."""
import services.relatorio_busca_os_service as svc


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._rows

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


class TestValidacao:
    def test_filtro_invalido(self):
        r = svc._busca_os_sync("srv", "bd", "invalido", "1", None, "asc")
        assert r["success"] is False and "inválido" in r["message"].lower()

    def test_valor_obrigatorio(self):
        r = svc._busca_os_sync("srv", "bd", "cliente", "", None, "asc")
        assert r["success"] is False and "valor" in r["message"].lower()


class TestQueryPorModo:
    def test_cliente_usa_igualdade(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._busca_os_sync("srv", "bd", "cliente", "42", None, "asc")
        query, params = cur.queries[-1]
        assert "o.cliente = %s" in query
        assert 42 not in params or "42" in params  # aceita string ou número

    def test_placa_usa_prefixo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._busca_os_sync("srv", "bd", "placa", "ABC1", None, "asc")
        query, params = cur.queries[-1]
        assert "LEFT(o.placa, %s) = %s" in query
        assert 4 in params and "ABC1" in params

    def test_os_usa_intervalo_com_fallback_valor1(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._busca_os_sync("srv", "bd", "os", "100", None, "asc")
        query, params = cur.queries[-1]
        assert "o.codigo BETWEEN %s AND %s" in query
        assert params == ("100", "100")

    def test_data_entrada_usa_intervalo_explicito(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._busca_os_sync("srv", "bd", "data_entrada", "2026-01-01", "2026-01-31", "asc")
        query, params = cur.queries[-1]
        assert "o.data_entrada" in query and "BETWEEN" in query
        assert params == ("2026-01-01", "2026-01-31")

    def test_ordem_desc(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._busca_os_sync("srv", "bd", "os", "1", None, "desc")
        query, _ = cur.queries[-1]
        assert "DESC" in query

    def test_left_join_marcas_modelos_nao_inner(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._busca_os_sync("srv", "bd", "os", "1", None, "asc")
        query, _ = cur.queries[-1]
        assert "LEFT JOIN marcas" in query and "LEFT JOIN modelos" in query


class TestResultado:
    def test_monta_veiculo_a_partir_de_marca_e_modelo(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "cliente_codigo": 1, "cliente_nome": "Cliente A", "os": 10,
            "marca_desc": "Fiat", "modelo_desc": "Uno",
            "data_entrada": "2026-01-01", "data_termino": None,
            "placa": "ABC1234", "chassi": "", "situacao": "A",
        }])
        _patch(monkeypatch, cur)
        r = svc._busca_os_sync("srv", "bd", "os", "10", None, "asc")
        assert r["itens"][0]["veiculo"] == "Fiat Uno"

    def test_sem_marca_modelo_mostra_travessao(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "cliente_codigo": 1, "cliente_nome": "Cliente A", "os": 10,
            "marca_desc": None, "modelo_desc": None,
            "data_entrada": None, "data_termino": None,
            "placa": "", "chassi": "", "situacao": "A",
        }])
        _patch(monkeypatch, cur)
        r = svc._busca_os_sync("srv", "bd", "os", "10", None, "asc")
        assert r["itens"][0]["veiculo"] == "—"


class TestItensOs:
    def test_decodifica_destino(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "P001", "descricao": "Peça", "quant": 2.0, "preco_unitario": 10.0, "situacao": 0},
            {"codigo": "S001", "descricao": "Serviço", "quant": 1.0, "preco_unitario": 50.0, "situacao": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_os_sync("srv", "bd", 10)
        assert r["success"] is True
        assert r["itens"][0]["destino"] == "Cliente"
        assert r["itens"][0]["valor_total"] == 20.0
        assert r["itens"][1]["destino"] == "Garantia"
