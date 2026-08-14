"""Testes unitários de Estoque — réplica de `FrmRelPecNiv.frm`."""
import services.relatorio_estoque_service as svc


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
    def test_nivel_obrigatorio(self):
        r = svc._estoque_sync("srv", "bd", "", None)
        assert r["success"] is False and "nível" in r["message"].lower()


class TestQuery:
    def test_filtra_situacao_ativo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._estoque_sync("srv", "bd", "001", None)
        query, params = cur.queries[-1]
        assert "p.situacao = 'A'" in query
        assert "p.nivel1 = %s" in query
        assert params == ("001",)

    def test_nivel_composto_de_dois_segmentos(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._estoque_sync("srv", "bd", "001002", None)
        query, params = cur.queries[-1]
        assert "p.nivel1 = %s" in query and "p.nivel2 = %s" in query
        assert params == ("001", "002")

    def test_ordenacao_padrao_codigo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._estoque_sync("srv", "bd", "001", None)
        query, _ = cur.queries[-1]
        assert "ORDER BY p.codigo_int" in query

    def test_ordenacao_por_descricao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._estoque_sync("srv", "bd", "001", "descricao")
        query, _ = cur.queries[-1]
        assert "ORDER BY p.descricao" in query


class TestResultado:
    def test_monta_itens(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "codigo_int": "P001", "codigo_fab": "F1", "descricao": "Produto", "quant": 5.0,
            "custo_inventario": 10.0, "p_venda": 20.0, "area": "A1", "prateleira": "P1", "escaninho": "E1",
        }])
        _patch(monkeypatch, cur)
        r = svc._estoque_sync("srv", "bd", "001", None)
        assert r["success"] is True
        assert r["itens"][0]["quant"] == 5.0
        assert r["itens"][0]["area"] == "A1"

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._estoque_sync("srv", "bd", "001", None)
        assert r["itens"] == []
