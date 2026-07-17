"""Testes UNITÁRIOS de Clientes x Cilindro (Fase 2 do módulo Cilindros)."""
import services.cilindro_cliente_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
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


class TestSaveVinculo:
    def test_sem_cliente(self):
        r = svc._save_vinculo_sync("srv", "bd", 0, 10)
        assert r["success"] is False and "cliente" in r["message"].lower()

    def test_sem_cilindro(self):
        r = svc._save_vinculo_sync("srv", "bd", 5, 0)
        assert r["success"] is False and "cilindro" in r["message"].lower()

    def test_cilindro_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_vinculo_sync("srv", "bd", 5, 10)
        assert r["success"] is False and "cilindro" in r["message"].lower()

    def test_cliente_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 10}, None])
        _patch(monkeypatch, cur)
        r = svc._save_vinculo_sync("srv", "bd", 5, 10)
        assert r["success"] is False and "cliente" in r["message"].lower()

    def test_cria_vinculo_novo(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 10}, {"codigo": 5}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_vinculo_sync("srv", "bd", 5, 10)
        assert r["success"] is True
        assert r["cilindro"] == 10
        assert conn.committed is True

    def test_nao_duplica_vinculo_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 10}, {"codigo": 5}, {"cilindro": 10}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_vinculo_sync("srv", "bd", 5, 10)
        assert r["success"] is True
        # não deveria ter feito INSERT (nem commit) — o vínculo já existia
        assert not any("INSERT" in (q or "") for q, _ in cur.queries)
        assert conn.committed is False


class TestDeleteVinculo:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_vinculo_sync("srv", "bd", 5, 10)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_exclui(self, monkeypatch):
        cur = FakeCursor(one=[{"cilindro": 10}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_vinculo_sync("srv", "bd", 5, 10)
        assert r["success"] is True
        assert conn.committed is True
