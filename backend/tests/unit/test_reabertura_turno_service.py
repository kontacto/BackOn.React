"""Testes UNITÁRIOS de Reabertura de Turno (Posto de Combustível)."""
from datetime import date

import services.reabertura_turno_service as svc


class FakeCursor:
    def __init__(self, one=None, rowcount=1):
        self._one = list(one or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

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


def _controle(turno_movimento=1, qtd_turnos=2):
    return {"data_movimento": date(2026, 6, 18), "turno_movimento": turno_movimento, "qtd_turnos": qtd_turnos}


class TestModuloDesativado:
    def test_reabrir_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd")
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestReabrirComMock:
    def test_nada_pra_reabrir(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, _controle(turno_movimento=2), _controle(turno_movimento=2), _controle(turno_movimento=2), None])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd")
        assert r["success"] is False and "nenhum fechamento" in r["message"].lower()
        assert conn.committed is False

    def test_reabre_turno_mesmo_dia(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, _controle(turno_movimento=2), _controle(turno_movimento=2), _controle(turno_movimento=2), {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd")
        assert r["success"] is True
        assert r["cruzou_dia"] is False
        assert r["turno_reaberto"] == 1
        assert conn.committed is True
        assert any("UPDATE controle SET turno_movimento" in q for q, _ in cur.queries)
        assert not any("data_movimento" in q for q, _ in cur.queries if "UPDATE controle SET" in q)

    def test_reabre_cruzando_dia(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, _controle(turno_movimento=1, qtd_turnos=2), _controle(turno_movimento=1, qtd_turnos=2), _controle(turno_movimento=1, qtd_turnos=2), {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd")
        assert r["success"] is True
        assert r["cruzou_dia"] is True
        assert r["turno_reaberto"] == 2
        assert conn.committed is True
        assert any("DELETE FROM FECHAMENTO_TURNO" in q for q, _ in cur.queries)
        assert any("data_movimento=%s, turno_movimento=%s" in q for q, _ in cur.queries)
