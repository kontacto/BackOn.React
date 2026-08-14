"""Testes unitários de Itens Vendidos O.S./Balcão — réplica de
`FrmRelVenOsB.frm`, generalizado pra Pedido+O.S. (não Comanda)."""
import services.relatorio_itens_vendidos_service as svc


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
        r = svc._itens_vendidos_sync("srv", "bd", "", "2026-08-07")
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_cobre_pedido_e_os(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._itens_vendidos_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert r["success"] is True
        query, params = cur.queries[-1]
        assert "pedido_venda_prod" in query and "os_produto" in query
        assert params == ("2026-01-01", "2026-01-31", "2026-01-01", "2026-01-31")


class TestAgregacao:
    def test_soma_mesmo_produto_entre_pedido_e_os(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "P001", "descricao": "Parafuso", "qtd": 10.0, "valor": 100.0},
            {"codigo": "P001", "descricao": "Parafuso", "qtd": 5.0, "valor": 50.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_vendidos_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert len(r["itens"]) == 1
        item = r["itens"][0]
        assert item["qtd"] == 15.0 and item["valor"] == 150.0
        assert r["total_valor"] == 150.0

    def test_produtos_diferentes_nao_se_misturam(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "A", "descricao": "Zebra", "qtd": 1.0, "valor": 10.0},
            {"codigo": "B", "descricao": "Abelha", "qtd": 2.0, "valor": 20.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_vendidos_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert len(r["itens"]) == 2
        assert r["itens"][0]["descricao"] == "Abelha"  # ordenado por descrição

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._itens_vendidos_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert r["itens"] == [] and r["total_valor"] == 0.0
