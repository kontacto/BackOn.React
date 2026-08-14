"""Testes unitários do Resumo de Venda — réplica de `FrmRelFec.frm`,
generalizado pra Pedido/OS (não Comanda). Cobre montagem da query
(filtros/parâmetros) e a agregação por nível em Python."""
import services.relatorio_resumo_venda_service as svc


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
        r = svc._resumo_venda_sync("srv", "bd", "", "2026-08-07", None)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_query_cobre_pedido_e_os_produto_e_servico(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._resumo_venda_sync("srv", "bd", "2026-01-01", "2026-01-31", None)
        assert r["success"] is True
        query, _ = cur.queries[-1]
        assert "pedido_venda_prod" in query and "os_produto" in query
        assert "JOIN pecas pe" in query and "JOIN servicos sv" in query
        assert "vendedor" not in query

    def test_filtro_vendedor_aplicado_nas_duas_fontes(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._resumo_venda_sync("srv", "bd", "2026-01-01", "2026-01-31", vendedor=9)
        query, params = cur.queries[-1]
        assert "pv.vendedor = %s" in query
        assert "i.vendedor = %s" in query
        assert params.count(9) == 4  # 4 branches (pedido P/S, os P/S), cada um recebe o filtro


class TestAgregacaoPorNivel:
    def test_soma_por_combinacao_de_nivel_entre_fontes(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"nivel1": "001", "nivel2": "002", "nivel3": "", "nivel4": "", "nivel5": "", "venda": 100.0, "custo": 40.0},
            {"nivel1": "001", "nivel2": "002", "nivel3": "", "nivel4": "", "nivel5": "", "venda": 50.0, "custo": 10.0},
            {"nivel1": "003", "nivel2": "", "nivel3": "", "nivel4": "", "nivel5": "", "venda": 200.0, "custo": 150.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._resumo_venda_sync("srv", "bd", "2026-01-01", "2026-01-31", None)
        assert r["success"] is True
        assert len(r["niveis"]) == 2
        n1 = next(n for n in r["niveis"] if n["codigo"] == "001002")
        assert n1["venda"] == 150.0 and n1["custo"] == 50.0 and n1["margem"] == 100.0
        n2 = next(n for n in r["niveis"] if n["codigo"] == "003")
        assert n2["venda"] == 200.0 and n2["margem"] == 50.0
        assert r["totais"]["venda"] == 350.0
        assert r["totais"]["custo"] == 200.0
        assert r["totais"]["margem"] == 150.0

    def test_nivel_sem_classificacao_vira_codigo_vazio(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"nivel1": "", "nivel2": "", "nivel3": "", "nivel4": "", "nivel5": "", "venda": 10.0, "custo": 5.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._resumo_venda_sync("srv", "bd", "2026-01-01", "2026-01-31", None)
        assert r["niveis"][0]["codigo"] == ""

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._resumo_venda_sync("srv", "bd", "2026-01-01", "2026-01-31", None)
        assert r["success"] is True
        assert r["niveis"] == []
        assert r["totais"]["margem_pct"] == 0.0

    def test_venda_zero_nao_quebra_margem_pct(self, monkeypatch):
        cur = FakeCursor(rows=[{"nivel1": "001", "nivel2": "", "nivel3": "", "nivel4": "", "nivel5": "", "venda": 0.0, "custo": 0.0}])
        _patch(monkeypatch, cur)
        r = svc._resumo_venda_sync("srv", "bd", "2026-01-01", "2026-01-31", None)
        assert r["niveis"][0]["margem_pct"] == 0.0
