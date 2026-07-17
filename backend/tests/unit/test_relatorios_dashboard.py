"""Testes do dashboard (Tela Principal) — foco na regra de data por
situação: 'Faturado' usa a data do Faturar (comanda.data); Aberto/Fechado/
Cancelado usam a data de criação do pedido (pedido_venda.data); 'Todos'
usa a UNIÃO das duas (Faturado por comanda.data, os demais por
pedido_venda.data) — sem isso "Todos" podia ficar menor que "Faturado"
sozinho. Ver `relatorios_service._dashboard_sync` — pedido explícito do
usuário, 2026-07-16."""
import services.relatorios_service as svc


class SqlFakeCursor:
    """Cursor fake que só registra as queries executadas — todas retornam
    vazio (fetchone()->{} / fetchall()->[]), suficiente pra inspecionar o
    SQL montado sem precisar simular dado real."""

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


class SubstringFakeCursor:
    """Cursor fake que casa por substring da última query (mesmo padrão de
    `test_fechamento_caixa_service.py`) — usado só pra testar o
    `situacao`/`situacao_label` da lista de movimento, sem precisar
    simular as outras 2 queries (totais)."""

    def __init__(self):
        self._last_q = ""
        self._rules: list[tuple[str, list]] = []

    def when(self, substr: str, rows: list) -> "SubstringFakeCursor":
        self._rules.append((substr, rows))
        return self

    def execute(self, q, p=None):
        self._last_q = q

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else {}

    def fetchall(self):
        for substr, rows in self._rules:
            if substr in self._last_q:
                return rows
        return []

    def close(self):
        pass


class TestMovimentoSituacao:
    def test_pedido_situacao_e_label(self, monkeypatch):
        cur = SubstringFakeCursor().when(
            "SELECT TOP 50 pv.pedido, pv.situacao",
            [{"pedido": 17606, "situacao": "PG", "cliente": "Fulano", "valor": 197.0, "vendedor_nome": ""}],
        )
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        out = svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao=None)
        ped = next(m for m in out["movimento"] if m["tipo"] == "PED")
        assert ped["situacao"] == "PG"
        assert ped["situacao_label"] == "Faturado"

    def test_os_situacao_e_label(self, monkeypatch):
        cur = SubstringFakeCursor().when(
            "SELECT TOP 50 i.os AS doc",
            [{"doc": 55, "situacao": "A", "cliente": "Beltrano", "valor": 80.0}],
        )
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        out = svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao=None)
        os_row = next(m for m in out["movimento"] if m["tipo"] == "OS")
        assert os_row["situacao"] == "A"
        assert os_row["situacao_label"] == "Aberto"


class TestDashboardDataPorSituacao:
    def test_faturado_usa_comanda_data(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao="PG")
        pedido_queries = [q for q, _ in cur.queries if "FROM pedido_venda pv" in q]
        assert len(pedido_queries) == 2  # totais + movimento
        for q in pedido_queries:
            assert "COMANDA_PED" in q
            assert "cm.data" in q
            assert "CAST(pv.data AS DATE) = %s" not in q

    def test_aberto_usa_pedido_data(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao="A")
        pedido_queries = [q for q, _ in cur.queries if "FROM pedido_venda pv" in q]
        assert len(pedido_queries) == 2
        for q in pedido_queries:
            assert "COMANDA_PED" not in q
            assert "CAST(pv.data AS DATE) = %s" in q

    def test_sem_situacao_usa_uniao(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao=None)
        pedido_queries = [(q, p) for q, p in cur.queries if "FROM pedido_venda pv" in q]
        assert len(pedido_queries) == 2
        for q, p in pedido_queries:
            assert "LEFT JOIN COMANDA_PED" in q
            assert "cm.data" in q
            assert "CAST(pv.data AS DATE) = %s" in q
            assert p[0] == "2026-07-16" and p[1] == "2026-07-16"  # data_iso usado 2x (união)

    def test_fechado_usa_pedido_data(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao="F")
        pedido_queries = [q for q, _ in cur.queries if "FROM pedido_venda pv" in q]
        for q in pedido_queries:
            assert "COMANDA_PED" not in q

    def test_cancelado_usa_pedido_data(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao="C")
        pedido_queries = [q for q, _ in cur.queries if "FROM pedido_venda pv" in q]
        for q in pedido_queries:
            assert "COMANDA_PED" not in q

    def test_data_iso_e_parametro_em_ambas_queries(self, monkeypatch):
        cur = SqlFakeCursor()
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        svc._dashboard_sync("srv", "bd", None, "2026-07-16", situacao="PG")
        pedido_queries = [p for q, p in cur.queries if "FROM pedido_venda pv" in q]
        for p in pedido_queries:
            assert p[0] == "2026-07-16"
