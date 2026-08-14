"""Testes unitários de Itens por Funcionário — réplica de
`Geral\\FrmRelVenFun.frm`, generalizada pra Pedido/O.S. (ver docstring do
service pro raciocínio completo)."""
import services.relatorio_itens_funcionario_service as svc


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
        r = svc._itens_funcionario_sync("srv", "bd", "", "2026-08-07", "vendedor", None, True)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_modo_vendedor_usa_pedido(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._itens_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None, True)
        query, params = cur.queries[-1]
        assert "pedido_venda_prod" in query and "pv.vendedor" in query
        assert "os_produto" not in query

    def test_modo_executor_usa_os(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._itens_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "executor", None, True)
        query, params = cur.queries[-1]
        assert "os_produto" in query and "i.executor" in query
        assert "pedido_venda_prod" not in query

    def test_filtro_funcionario(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._itens_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", 42, True)
        query, params = cur.queries[-1]
        assert "pv.vendedor = %s" in query
        assert 42 in params

    def test_sem_considerar_servicos_exclui(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._itens_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None, False)
        query, params = cur.queries[-1]
        assert "sv.codigo IS NULL" in query


class TestResultado:
    def test_agrega_e_totaliza(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"func_codigo": 1, "func_nome": "Zé", "qtd": 3.0, "valor": 30.0},
            {"func_codigo": 2, "func_nome": "Maria", "qtd": 2.0, "valor": 50.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None, True)
        assert r["success"] is True
        assert len(r["funcionarios"]) == 2
        assert r["totais"]["valor"] == 80.0
        assert r["totais"]["qtd"] == 5.0

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._itens_funcionario_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", None, True)
        assert r["funcionarios"] == []
        assert r["totais"]["valor"] == 0.0
