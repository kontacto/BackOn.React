"""Testes UNITÁRIOS de Fechamento de Turno (Posto de Combustível)."""
from datetime import date

import services.fechamento_turno_service as svc


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


def _controle(data_movimento=None, turno_movimento=1, qtd_turnos=2):
    return {
        "data_movimento": data_movimento or date(2026, 6, 18),
        "turno_movimento": turno_movimento,
        "qtd_turnos": qtd_turnos,
    }


class TestModuloDesativado:
    def test_fechar_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", usuario=1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestFecharComMock:
    def test_bloqueia_se_dia_ja_fechado(self, monkeypatch):
        # data_movimento, turno_movimento, qtd_turnos, depois SELECT controle_turno (ultimo turno) -> encontrado
        cur = FakeCursor(one=[
            MODULO_ON,
            _controle(turno_movimento=1, qtd_turnos=2),
            _controle(turno_movimento=1, qtd_turnos=2),
            _controle(turno_movimento=1, qtd_turnos=2),
            {"ok": 1},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", usuario=1)
        assert r["success"] is False and "já foram fechados" in r["message"]
        assert conn.committed is False

    def test_bloqueia_com_abastecimento_pendente(self, monkeypatch):
        cur = FakeCursor(one=[
            MODULO_ON,
            _controle(turno_movimento=1, qtd_turnos=2),
            _controle(turno_movimento=1, qtd_turnos=2),
            _controle(turno_movimento=1, qtd_turnos=2),
            None,  # controle_turno do último turno -> não fechado ainda
            None,  # controle_turno_horario -> sem horário configurado
            {"ok": 1},  # abastecimento pendente
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", usuario=1)
        assert r["success"] is False and "pendentes" in r["message"].lower()
        assert conn.committed is False

    def test_fecha_turno_intermediario(self, monkeypatch):
        cur = FakeCursor(one=[
            MODULO_ON,
            _controle(turno_movimento=1, qtd_turnos=2),
            _controle(turno_movimento=1, qtd_turnos=2),
            _controle(turno_movimento=1, qtd_turnos=2),
            None,  # nao fechado
            None,  # sem horario
            None,  # sem pendente
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", usuario=1)
        assert r["success"] is True
        assert r["dia_fechado"] is False
        assert r["novo_turno"] == 2
        assert conn.committed is True
        assert any("INSERT INTO controle_turno" in q for q, _ in cur.queries)
        assert not any("FECHAMENTO_TURNO" in q for q, _ in cur.queries)

    def test_fecha_ultimo_turno_avanca_dia(self, monkeypatch):
        cur = FakeCursor(one=[
            MODULO_ON,
            _controle(turno_movimento=2, qtd_turnos=2),
            _controle(turno_movimento=2, qtd_turnos=2),
            _controle(turno_movimento=2, qtd_turnos=2),
            None,  # nao fechado
            None,  # sem horario
            None,  # sem pendente
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_sync("srv", "bd", usuario=1)
        assert r["success"] is True
        assert r["dia_fechado"] is True
        assert r["novo_turno"] == 1
        assert conn.committed is True
        assert any("INSERT INTO FECHAMENTO_TURNO" in q for q, _ in cur.queries)
