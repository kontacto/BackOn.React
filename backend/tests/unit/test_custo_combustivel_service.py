"""Testes UNITÁRIOS de Custo de Combustível (Posto de Combustível).

Sem Incluir/Excluir (o legado `frmmancus.frm` não tem esses botões) —
só list + update.
"""
import services.custo_combustivel_service as svc


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
        r = svc._update_sync("srv", "bd", cod_cus=1, data="", entrada=0, saida=0, custo=0)
        assert r["success"] is False and "data" in r["message"].lower()


class TestModuloDesativado:
    def test_update_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._update_sync("srv", "bd", cod_cus=1, data="2026-07-13", entrada=100, saida=50, custo=4.5)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestUpdateComMock:
    def test_atualiza_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._update_sync("srv", "bd", cod_cus=1, data="2026-07-13", entrada=100, saida=50, custo=4.5)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE Custo_Combustivel" in q for q, _ in cur.queries)

    def test_atualiza_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._update_sync("srv", "bd", cod_cus=999, data="2026-07-13", entrada=0, saida=0, custo=0)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False
