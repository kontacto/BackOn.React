"""Testes unitários de Custo de O.S — réplica de `FrmCustoOS.frm`."""
import services.relatorio_custo_os_service as svc


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
        r = svc._custo_os_sync("srv", "bd", "", "2026-08-07", "cliente", None)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_agrupa_por_cliente_por_padrao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._custo_os_sync("srv", "bd", "2026-01-01", "2026-01-31", "cliente", None)
        query, params = cur.queries[-1]
        assert "GROUP BY c.nome" in query
        assert "i.situacao" not in query
        assert params == ("2026-01-01", "2026-01-31")

    def test_agrupa_por_produto(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._custo_os_sync("srv", "bd", "2026-01-01", "2026-01-31", "produto", None)
        query, _ = cur.queries[-1]
        assert "JOIN pecas pe" in query and "JOIN servicos sv" in query

    def test_filtro_tipo_aplica_situacao_item(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._custo_os_sync("srv", "bd", "2026-01-01", "2026-01-31", "cliente", 2)
        query, params = cur.queries[-1]
        assert "i.situacao = %s" in query
        assert 2 in params

    def test_situacao_sempre_exclui_cancelado(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._custo_os_sync("srv", "bd", "2026-01-01", "2026-01-31", "cliente", None)
        query, _ = cur.queries[-1]
        assert "o.situacao IN ('A','F','PG')" in query


class TestAgregacao:
    def test_soma_total(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"label": "Cliente A", "custo": 100.0, "qtd": 2.0},
            {"label": "Cliente B", "custo": 50.5, "qtd": 1.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._custo_os_sync("srv", "bd", "2026-01-01", "2026-01-31", "cliente", None)
        assert r["success"] is True
        assert r["total"] == 150.5
        assert len(r["itens"]) == 2

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._custo_os_sync("srv", "bd", "2026-01-01", "2026-01-31", "cliente", None)
        assert r["itens"] == [] and r["total"] == 0.0
