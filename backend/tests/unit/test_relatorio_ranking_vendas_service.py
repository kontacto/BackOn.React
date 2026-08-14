"""Testes unitários de Ranking de Vendas — réplica de
`Geral\\FrmRkgCliPro.frm`, generalizada pra Pedido/O.S. (ver docstring do
service pro raciocínio completo)."""
import services.relatorio_ranking_vendas_service as svc


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
        r = svc._ranking_vendas_sync("srv", "bd", "", "2026-08-07", "produto", "valor", 10, None, None, True)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_modo_cliente(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "cliente", "valor", 10, None, None, True)
        query, params = cur.queries[-1]
        assert "pv.cliente" in query and "cli.nome" in query

    def test_modo_vendedor(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "vendedor", "valor", 10, None, None, True)
        query, params = cur.queries[-1]
        assert "pv.vendedor" in query and "i.vendedor" in query

    def test_filtro_fabricante_so_afeta_pecas(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "produto", "valor", 10, None, 5, True)
        query, params = cur.queries[-1]
        assert "pe.fornecedor = %s" in query
        assert 5 in params


class TestResultado:
    def test_ordena_por_valor_e_limita_top_n(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "P1", "nome": "Produto 1", "qtd": 1.0, "valor": 10.0},
            {"codigo": "P2", "nome": "Produto 2", "qtd": 5.0, "valor": 100.0},
            {"codigo": "P3", "nome": "Produto 3", "qtd": 2.0, "valor": 50.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "produto", "valor", 2, None, None, True)
        assert r["success"] is True
        assert len(r["itens"]) == 2
        assert r["itens"][0]["codigo"] == "P2"
        assert r["itens"][0]["posicao"] == 1
        assert r["totais"]["registros"] == 3

    def test_ordena_por_qtd(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "P1", "nome": "Produto 1", "qtd": 1.0, "valor": 999.0},
            {"codigo": "P2", "nome": "Produto 2", "qtd": 5.0, "valor": 1.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "produto", "qtd", 10, None, None, True)
        assert r["itens"][0]["codigo"] == "P2"

    def test_agrega_duas_linhas_mesmo_codigo(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "P1", "nome": "Produto 1", "qtd": 1.0, "valor": 10.0},
            {"codigo": "P1", "nome": "Produto 1", "qtd": 1.0, "valor": 10.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "produto", "valor", 10, None, None, True)
        assert len(r["itens"]) == 1
        assert r["itens"][0]["valor"] == 20.0

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._ranking_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", "produto", "valor", 10, None, None, True)
        assert r["itens"] == []
        assert r["totais"]["valor"] == 0.0
