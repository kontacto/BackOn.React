"""Testes UNITÁRIOS de Ilhas (Posto de Combustível)."""
import services.ilha_service as svc


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
    def test_data_obrigatoria(self):
        r = svc._save_sync("srv", "bd", data="", ilha=1, turno=1, funcionario=1)
        assert r["success"] is False and "data" in r["message"].lower()

    def test_ilha_obrigatoria(self):
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=None, turno=1, funcionario=1)
        assert r["success"] is False and "ilha" in r["message"].lower()

    def test_turno_obrigatorio(self):
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=None, funcionario=1)
        assert r["success"] is False and "turno" in r["message"].lower()

    def test_funcionario_obrigatorio(self):
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1, funcionario=None)
        assert r["success"] is False and "funcion" in r["message"].lower()


class TestModuloDesativado:
    def test_save_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1, funcionario=1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False

    def test_delete_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestSaveComMock:
    def test_ilha_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1, funcionario=1)
        assert r["success"] is False and "ilha" in r["message"].lower()
        assert conn.committed is False

    def test_funcionario_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1, funcionario=1)
        assert r["success"] is False and "funcion" in r["message"].lower()
        assert conn.committed is False

    def test_ja_cadastrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, {"ok": 1}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1, funcionario=1)
        assert r["success"] is False and "já existe" in r["message"].lower()
        assert conn.committed is False

    def test_inclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1, funcionario=1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO ilha" in q for q, _ in cur.queries)


class TestDeleteComMock:
    def test_exclui(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1)
        assert r["success"] is True
        assert conn.committed is True

    def test_exclui_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", data="2026-07-13", ilha=1, turno=1)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False
