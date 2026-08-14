"""Testes unitários de Movimentação de Itens — réplica de
`FrmRelMovCli.frm`, simplificada pra ler `movimentacao` direto (ver
docstring do service pro raciocínio completo)."""
import services.relatorio_movimentacao_itens_service as svc


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
        r = svc._movimentacao_itens_sync("srv", "bd", "", "2026-08-07", None, None, None, None, None)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_sem_filtros_extra_so_periodo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        query, params = cur.queries[-1]
        assert "m.codigo_int = %s" not in query
        assert params == ["2026-01-01", "2026-01-31"] or params == ("2026-01-01", "2026-01-31")

    def test_filtro_produto(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", "P001", None, None, None, None)
        query, params = cur.queries[-1]
        assert "m.codigo_int = %s" in query
        assert "P001" in params

    def test_filtro_tipo_csv(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "S01,E01", None, None, None)
        query, params = cur.queries[-1]
        assert "m.tipo IN (%s,%s)" in query
        assert "S01" in params and "E01" in params

    def test_filtro_entrada_saida(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, "S", None, None)
        query, params = cur.queries[-1]
        assert "LEFT(m.tipo,1) = %s" in query
        assert "S" in params

    def test_filtro_origem_csv(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, "RQ,MV", None)
        query, params = cur.queries[-1]
        assert "m.serie_nf IN (%s,%s)" in query
        assert "RQ" in params and "MV" in params


class TestResultado:
    def test_calcula_valor_e_origem_label(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "id_mov": 1, "data": "2026-01-05", "tipo": "S01", "tipo_desc": "Venda",
            "codigo_int": "P001", "produto_descricao": "Parafuso", "qtd": 2.0, "p_unit": 10.0,
            "num_nf": 55, "serie_nf": "CM", "vendedor_nome": "Zé",
        }])
        _patch(monkeypatch, cur)
        r = svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        assert r["success"] is True
        item = r["itens"][0]
        assert item["valor"] == 20.0
        assert item["origem_label"] == "Venda"
        assert r["totais"]["valor"] == 20.0

    def test_origem_desconhecida_usa_o_proprio_codigo(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "id_mov": 1, "data": "2026-01-05", "tipo": "S01", "tipo_desc": "Venda",
            "codigo_int": "P001", "produto_descricao": "Parafuso", "qtd": 1.0, "p_unit": 1.0,
            "num_nf": None, "serie_nf": "XX", "vendedor_nome": None,
        }])
        _patch(monkeypatch, cur)
        r = svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        assert r["itens"][0]["origem_label"] == "XX"
        assert r["itens"][0]["vendedor_nome"] == "—"

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._movimentacao_itens_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        assert r["itens"] == []
        assert r["totais"]["valor"] == 0.0
