"""Testes unitários de Movimentações por Nível — réplica de
`frmrelvenlojas.frm` (nome real, sem o conceito de "filiais" da caption
enganosa — ver docstring do service)."""
import services.relatorio_movimentacao_nivel_service as svc


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
    def test_tipo_obrigatorio(self):
        r = svc._movimentacao_nivel_sync("srv", "bd", "", "2026-01-01", "2026-01-31")
        assert r["success"] is False and "tipo" in r["message"].lower()

    def test_periodo_obrigatorio(self):
        r = svc._movimentacao_nivel_sync("srv", "bd", "S01", "", "2026-01-31")
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_filtra_por_tipo_e_periodo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._movimentacao_nivel_sync("srv", "bd", "S01", "2026-01-01", "2026-01-31")
        query, params = cur.queries[-1]
        assert "m.tipo = %s" in query
        assert params == ("S01", "2026-01-01", "2026-01-31")


class TestAgregacao:
    def test_agrupa_por_nivel(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"nivel1": "001", "nivel2": "", "nivel3": "", "nivel4": "", "nivel5": "", "qtd": 10.0, "valor": 100.0},
            {"nivel1": "002", "nivel2": "", "nivel3": "", "nivel4": "", "nivel5": "", "qtd": 5.0, "valor": 50.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._movimentacao_nivel_sync("srv", "bd", "S01", "2026-01-01", "2026-01-31")
        assert r["success"] is True
        assert len(r["itens"]) == 2
        assert r["totais"]["qtd"] == 15.0 and r["totais"]["valor"] == 150.0

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._movimentacao_nivel_sync("srv", "bd", "S01", "2026-01-01", "2026-01-31")
        assert r["itens"] == []
        assert r["totais"]["valor"] == 0.0
