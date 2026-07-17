"""Testes UNITÁRIOS do Borderô de Cilindros (Fase 3c do módulo Cilindros)."""
import services.bordero_service as svc


class FakeCursor:
    def __init__(self, many=None):
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._many.pop(0) if self._many else []

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


class TestBuildWhere:
    def test_sem_filtros(self):
        where, params = svc._build_where({})
        assert where == "1=1"
        assert params == []

    def test_tipo_viagem(self):
        where, params = svc._build_where({"tipo_viagem": 0})
        assert "v.tipo_viagem=%s" in where
        assert params == [0]

    def test_status_lista(self):
        where, params = svc._build_where({"status": ["AP", "APT"]})
        assert "vc.status_retorno IN (%s,%s)" in where
        assert params == ["AP", "APT"]

    def test_documento(self):
        where, params = svc._build_where({"documento": "OS123"})
        assert "os_saida=%s" in where
        assert params == ["OS123", "OS123", "OS123", "OS123"]

    def test_segmento_ignorado_para_fabrica(self):
        where, params = svc._build_where({"segmento": "01", "tipo_viagem": 1})
        assert "segmento" not in where


class TestListBordero:
    def test_agrupa_por_cliente_e_soma_subtotais(self, monkeypatch):
        rows = [
            {"codigo": 1, "cliente": 10, "cliente_nome": "Cliente A", "em_aberto": 1},
            {"codigo": 2, "cliente": 10, "cliente_nome": "Cliente A", "em_aberto": 0},
            {"codigo": 3, "cliente": 20, "cliente_nome": "Cliente B", "em_aberto": 1},
        ]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_bordero_sync("srv", "bd", {})
        assert r["success"] is True
        assert len(r["grupos"]) == 2
        grupo_a = r["grupos"][0]
        assert grupo_a["cliente"] == "Cliente A"
        assert grupo_a["saida"] == 2
        assert grupo_a["em_aberto"] == 1
        assert grupo_a["retorno"] == 1
        assert r["total"]["saida"] == 3
        assert r["total"]["em_aberto"] == 2

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_bordero_sync("srv", "bd", {})
        assert r["success"] is True
        assert r["grupos"] == []
        assert r["total"]["saida"] == 0

    def test_cliente_sem_nome_usa_codigo(self, monkeypatch):
        rows = [{"codigo": 1, "cliente": 99, "cliente_nome": None, "em_aberto": 0}]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_bordero_sync("srv", "bd", {})
        assert r["grupos"][0]["cliente"] == "#99"

    def test_filtro_em_aberto_true_adiciona_exists(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_bordero_sync("srv", "bd", {"em_aberto": True})
        q, _ = cur.queries[0]
        assert "EXISTS (SELECT 1 FROM Viagem_Retorno vry" in q
        assert "NOT EXISTS" not in q

    def test_filtro_em_aberto_false_adiciona_not_exists(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_bordero_sync("srv", "bd", {"em_aberto": False})
        q, _ = cur.queries[0]
        assert "NOT EXISTS (SELECT 1 FROM Viagem_Retorno vry" in q


class TestResumoBordero:
    def test_retorna_itens(self, monkeypatch):
        rows = [{"grupo_gas": "P123", "capacidade": 20, "pressao": 150, "padrao": "01", "descricao": "Cilindro X", "status": "AP", "total": 5}]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._resumo_bordero_sync("srv", "bd", {})
        assert r["success"] is True
        assert r["items"][0]["total"] == 5

    def test_erro_de_query_retorna_failure(self, monkeypatch):
        class BoomCursor(FakeCursor):
            def execute(self, q, p=None):
                raise RuntimeError("boom")
        _patch(monkeypatch, BoomCursor())
        r = svc._resumo_bordero_sync("srv", "bd", {})
        assert r["success"] is False
        assert "boom" in r["message"]
