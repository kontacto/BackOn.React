"""Testes unitários de Estoque por Nível — réplica de `FrmRelFecEst.frm`."""
import services.relatorio_estoque_nivel_service as svc


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
    def test_filtra_estoque_positivo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._estoque_nivel_sync("srv", "bd")
        query, _ = cur.queries[-1]
        assert "(qtd+reservado+reservado_os) > 0" in query
        assert "GROUP BY nivel1, nivel2, nivel3, nivel4, nivel5" in query


class TestAgregacao:
    def test_monta_codigo_e_soma(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"nivel1": "001", "nivel2": "002", "nivel3": "", "nivel4": "", "nivel5": "",
             "unidades": 10.0, "valor_custo": 100.0, "valor_venda": 150.0},
            {"nivel1": "003", "nivel2": "", "nivel3": "", "nivel4": "", "nivel5": "",
             "unidades": 5.0, "valor_custo": 50.0, "valor_venda": 80.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._estoque_nivel_sync("srv", "bd")
        assert r["success"] is True
        assert len(r["itens"]) == 2
        n1 = next(i for i in r["itens"] if i["codigo"] == "001002")
        assert n1["unidades"] == 10.0 and n1["valor_custo"] == 100.0 and n1["valor_venda"] == 150.0
        assert r["totais"]["unidades"] == 15.0
        assert r["totais"]["valor_custo"] == 150.0
        assert r["totais"]["valor_venda"] == 230.0

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._estoque_nivel_sync("srv", "bd")
        assert r["itens"] == []
        assert r["totais"]["unidades"] == 0.0
