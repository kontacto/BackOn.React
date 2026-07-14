"""Testes UNITÁRIOS de Aferições/Despesas (Posto de Combustível)."""
from datetime import date

import services.afericao_abastecimento_service as svc


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


def _abastecimento(status="PENDENTE", valor=100.0, volume=50.0, ponto=1, posicao=1, turno=1):
    return {
        "ponto": ponto, "posicao": posicao, "combustivel": 1, "valor": valor, "volume": volume,
        "data": date(2026, 6, 18), "turno": turno, "status_abastecimento": status,
        "valor_despesa": 0.0,
    }


class TestValidacoesSemBanco:
    def test_sem_selecao(self):
        r = svc._aferir_sync("srv", "bd", nums=[], lancar_despesa=False, motivo="", usuario=1)
        assert r["success"] is False and "nenhum" in r["message"].lower()

    def test_mais_de_10(self):
        r = svc._aferir_sync("srv", "bd", nums=list(range(11)), lancar_despesa=False, motivo="", usuario=1)
        assert r["success"] is False and "10" in r["message"]


class TestModuloDesativado:
    def test_aferir_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._aferir_sync("srv", "bd", nums=[1], lancar_despesa=False, motivo="", usuario=1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False

    def test_reverter_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._reverter_sync("srv", "bd", 1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestAferirComMock:
    def test_afere_um_sem_despesa(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, _abastecimento(), {"codigo": 5}])
        conn = _patch(monkeypatch, cur)
        r = svc._aferir_sync("srv", "bd", nums=[1], lancar_despesa=False, motivo="ok", usuario=1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("status_abastecimento='AFERIÇÃO'" in q for q, _ in cur.queries)
        assert any("UPDATE mov_bomba SET afericao" in q for q, _ in cur.queries)

    def test_ignora_ja_aferido(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, _abastecimento(status="AFERIÇÃO")])
        conn = _patch(monkeypatch, cur)
        r = svc._aferir_sync("srv", "bd", nums=[1], lancar_despesa=False, motivo="", usuario=1)
        assert r["success"] is False and "nenhum" in r["message"].lower()
        assert conn.committed is False


class TestReverterComMock:
    def test_reverte_com_sucesso(self, monkeypatch):
        row = _abastecimento(status="AFERIÇÃO")
        row["valor_despesa"] = 20.0
        cur = FakeCursor(one=[MODULO_ON, row, {"codigo": 5}])
        conn = _patch(monkeypatch, cur)
        r = svc._reverter_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("status_abastecimento='PENDENTE'" in q for q, _ in cur.queries)
        assert any("UPDATE mov_bomba SET afericao=ISNULL(afericao,0)-%s" in q for q, _ in cur.queries)

    def test_reverte_nao_aferido(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, _abastecimento(status="PENDENTE")])
        conn = _patch(monkeypatch, cur)
        r = svc._reverter_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrada" in r["message"].lower()
        assert conn.committed is False
