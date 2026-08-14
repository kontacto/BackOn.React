"""Testes do filtro `situacao` em CSV (uma ou mais situações) no Relatório
de Pedidos e no Relatório de OS — adicionado 2026-08-07 pra cobrir
"Pedidos Pendentes"/"O.S. Não Faturadas" (Painel de Relatórios > Pré
Venda) sem precisar de telas dedicadas. Ver PENDENCIAS.md > "Painel de
Relatórios (VB6)" > "Pré Venda"."""
import services.relatorios_service as svc


class SqlFakeCursor:
    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return {}

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self, as_dict=True):
        return self._cur

    def close(self):
        pass


class TestRelatorioPedidosSituacaoMulti:
    def test_sem_situacao_nao_filtra(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_pedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None)
        assert not any("pv.situacao IN" in q for q, _ in cur.queries)

    def test_situacao_unica_ainda_funciona(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_pedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "A", None)
        q, p = cur.queries[0]
        assert "pv.situacao IN (%s)" in q
        assert "A" in p

    def test_situacao_csv_pendentes(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_pedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "A,F", None)
        q, p = cur.queries[0]
        assert "pv.situacao IN (%s,%s)" in q
        assert "A" in p and "F" in p

    def test_situacao_all_nao_filtra(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_pedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "all", None)
        assert not any("pv.situacao IN" in q for q, _ in cur.queries)


class TestRelatorioOsSituacaoMulti:
    def test_sem_situacao_nao_filtra(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_os_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert not any("o.situacao IN" in q for q, _ in cur.queries)

    def test_situacao_csv_nao_faturadas(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_os_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "A,F")
        q, p = cur.queries[0]
        assert "o.situacao IN (%s,%s)" in q
        assert "A" in p and "F" in p

    def test_situacao_unica_ainda_funciona(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_os_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "PG")
        q, p = cur.queries[0]
        assert "o.situacao IN (%s)" in q
        assert "PG" in p
