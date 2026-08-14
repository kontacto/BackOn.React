"""Testes unitários de Venda por Cliente/Produto — unificação de
`Geral\\FrmRelVenCli.frm` + `Geral\\FrmRelVenPro.frm` (ver docstring do
service pro raciocínio completo)."""
import services.relatorio_venda_cliente_produto_service as svc


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
    def test_periodo_obrigatorio(self):
        r = svc._venda_cliente_produto_sync("srv", "bd", "", "2026-08-07", None, None)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_sem_filtros(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._venda_cliente_produto_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        query, params = cur.queries[-1]
        assert "pv.cliente = %s" not in query
        assert "i.produto = %s" not in query

    def test_filtro_cliente(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._venda_cliente_produto_sync("srv", "bd", "2026-01-01", "2026-01-31", 100, None)
        query, params = cur.queries[-1]
        assert "pv.cliente = %s" in query and "o.cliente = %s" in query
        assert 100 in params

    def test_filtro_produto(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._venda_cliente_produto_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "P001")
        query, params = cur.queries[-1]
        assert "i.produto = %s" in query and "i.codigo_interno = %s" in query
        assert "P001" in params


class TestResultado:
    def test_calcula_valor_e_totaliza(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"cliente_codigo": 1, "cliente_nome": "Cliente A", "item_codigo": "P1", "item_descricao": "Prod 1",
             "doc_tipo": "PED", "doc_numero": 55, "data": "2026-01-05", "qtd": 2.0, "valor": 20.0},
            {"cliente_codigo": 1, "cliente_nome": "Cliente A", "item_codigo": "S1", "item_descricao": "Serv 1",
             "doc_tipo": "OS", "doc_numero": 9, "data": "2026-01-06", "qtd": 1.0, "valor": 30.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._venda_cliente_produto_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert r["success"] is True
        assert len(r["itens"]) == 2
        assert r["totais"]["valor"] == 50.0
        assert r["itens"][0]["doc_tipo"] == "PED"

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._venda_cliente_produto_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert r["itens"] == []
        assert r["totais"]["valor"] == 0.0
