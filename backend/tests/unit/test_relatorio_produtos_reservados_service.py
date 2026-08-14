"""Testes unitários de Produtos Reservados — réplica de `frmrelpecres.frm`."""
import services.relatorio_produtos_reservados_service as svc


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


class TestQuery:
    def test_filtra_reserva_diferente_de_zero(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._produtos_reservados_sync("srv", "bd", None)
        query, _ = cur.queries[-1]
        assert "(reservado_os + reservado) <> 0" in query

    def test_ordenacao_padrao_codigo_int(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._produtos_reservados_sync("srv", "bd", None)
        query, _ = cur.queries[-1]
        assert "ORDER BY codigo_int" in query

    def test_ordenacao_por_descricao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._produtos_reservados_sync("srv", "bd", "descricao")
        query, _ = cur.queries[-1]
        assert "ORDER BY descricao" in query

    def test_ordenacao_invalida_cai_no_padrao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._produtos_reservados_sync("srv", "bd", "algo_invalido; DROP TABLE pecas")
        query, _ = cur.queries[-1]
        assert "ORDER BY codigo_int" in query


class TestAgregacao:
    def test_calcula_preco_total_e_soma(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo_int": "P001", "codigo_fab": "F1", "descricao": "Produto 1", "p_venda": 10.0, "reserva": 2.0},
            {"codigo_int": "P002", "codigo_fab": "F2", "descricao": "Produto 2", "p_venda": 5.0, "reserva": 3.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._produtos_reservados_sync("srv", "bd", None)
        assert r["success"] is True
        assert r["itens"][0]["preco_total"] == 20.0
        assert r["itens"][1]["preco_total"] == 15.0
        assert r["total"] == 35.0

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._produtos_reservados_sync("srv", "bd", None)
        assert r["itens"] == [] and r["total"] == 0.0
