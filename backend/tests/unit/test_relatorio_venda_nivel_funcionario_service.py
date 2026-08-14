"""Testes unitários de Venda por Vendedor × Nível — réplica de
`Kontacto\\frmrelvennivfun.frm` (ver docstring do service pro raciocínio
completo)."""
import services.relatorio_venda_nivel_funcionario_service as svc


class FakeCursor:
    def __init__(self, rows=None, lookup=None):
        self._rows = rows or []
        self._lookup = lookup
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._lookup

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
        r = svc._venda_nivel_funcionario_sync("srv", "bd", "", "2026-08-07", "vendedor", None)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_modo_vendedor_usa_pedido(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None)
        query, params = cur.queries[-1]
        assert "pedido_venda_prod" in query and "pv.pedido" in query
        assert "os_produto" not in query

    def test_modo_executor_usa_os(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "executor", None)
        query, params = cur.queries[-1]
        assert "os_produto" in query and "custo_os" in query
        assert "pedido_venda_prod" not in query

    def test_filtro_funcionario_aplica_no_modo_certo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", 42)
        query, params = cur.queries[-1]
        assert "pv.vendedor = %s" in query
        assert 42 in params

        cur2 = FakeCursor(rows=[])
        _patch(monkeypatch, cur2)
        svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "executor", 42)
        query2, params2 = cur2.queries[-1]
        assert "i.executor = %s" in query2
        assert 42 in params2

    def test_filtro_funcionario_busca_nome(self, monkeypatch):
        cur = FakeCursor(rows=[], lookup={"nome": "Zé"})
        _patch(monkeypatch, cur)
        r = svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", 42)
        assert r["func_nome"] == "Zé"


class TestResultado:
    def test_agrega_por_nivel_e_calcula_margem(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"nivel1": "001", "nivel2": "002", "nivel3": "", "nivel4": "", "nivel5": "", "venda": 100.0, "custo": 60.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None)
        assert r["success"] is True
        assert len(r["niveis"]) == 1
        assert r["niveis"][0]["margem"] == 40.0
        assert r["totais"]["margem_pct"] == 40.0

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._venda_nivel_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None)
        assert r["niveis"] == []
        assert r["totais"]["venda"] == 0.0
