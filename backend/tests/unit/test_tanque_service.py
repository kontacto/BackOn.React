"""Testes UNITÁRIOS de Tanques (Posto de Combustível)."""
import services.tanque_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


MODULO_ON = {"Posto": 1}
MODULO_OFF = {"Posto": 0}


class TestValidacoesSemBanco:
    def test_tanque_obrigatorio(self):
        r = svc._save_sync("srv", "bd", tanque=None, capacidade=1000, combustivel=1)
        assert r["success"] is False and "tanque" in r["message"].lower()

    def test_capacidade_obrigatoria(self):
        r = svc._save_sync("srv", "bd", tanque=1, capacidade=None, combustivel=1)
        assert r["success"] is False and "capacidade" in r["message"].lower()

    def test_combustivel_obrigatorio(self):
        r = svc._save_sync("srv", "bd", tanque=1, capacidade=1000, combustivel=None)
        assert r["success"] is False and "combust" in r["message"].lower()


class TestModuloDesativado:
    def test_save_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", tanque=1, capacidade=1000, combustivel=1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestSaveComMock:
    def test_combustivel_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", tanque=1, capacidade=1000, combustivel=99)
        assert r["success"] is False and "combust" in r["message"].lower()
        assert conn.committed is False

    def test_insere_novo(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", tanque=1, capacidade=1000, combustivel=1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO tanque" in q for q, _ in cur.queries)

    def test_atualiza_existente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", tanque=1, capacidade=2000, combustivel=2)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE tanque" in q for q, _ in cur.queries)


class TestDeleteComMock:
    def test_bloqueia_com_bomba_vinculada(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "bombas" in r["message"].lower()
        assert conn.committed is False

    def test_exclui_sem_vinculos(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None, None, None], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_exclui_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None, None, None], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False
