"""Testes do filtro "Projeto" no Relatório de Pedidos e no Relatório de
Descontos & Margem — Gestor de Projetos Fase 4 (recurso extra, sem
equivalente no legado). Ver PENDENCIAS.md > "Gestor de Projetos" > "Fase
4"."""
import services.relatorios_service as svc


class SqlFakeCursor:
    """Cursor fake que só registra as queries executadas — mesmo padrão de
    `test_relatorios_dashboard.py::SqlFakeCursor`."""

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


class TestRelatorioPedidosFiltroProjeto:
    def test_sem_projeto_nao_filtra(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_pedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None)
        assert not any("projetos_documentos" in q for q, _ in cur.queries)

    def test_com_projeto_filtra_pelo_vinculo(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_pedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, 42)
        primeira_q, primeiros_params = cur.queries[0]
        assert "projetos_documentos" in primeira_q
        assert "tipo_doc='PED'" in primeira_q
        assert 42 in primeiros_params


class TestRelatorioDescMargemFiltroProjeto:
    def test_sem_projeto_nao_filtra(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_desc_margem_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None)
        assert not any("projetos_documentos" in q for q, _ in cur.queries)

    def test_com_projeto_filtra_pelo_vinculo(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        svc._relatorio_desc_margem_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, 42)
        q, params = cur.queries[0]
        assert "projetos_documentos" in q
        assert "tipo_doc='PED'" in q
        assert 42 in params
