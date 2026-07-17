"""Testes unitários de os_service — combobox simples 'Forma de Pagamento'
do cabeçalho (grava direto ao trocar, não só no Gravar normal). Mesmo
achado/raciocínio de `test_pedidos_service.py::TestSetFormaPagSimples`,
só a tabela/coluna muda (`os.forma_pagamento`)."""
import services.os_service as svc
from models.schemas import FormaPagSimplesRequest


class FakeCursor:
    def __init__(self, one=None, rowcount=1):
        self._one = list(one or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return []

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


def _forma_pag_req(**over):
    base = dict(servidor="srv", banco="bd", forma_pag="DI", usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return FormaPagSimplesRequest(**base)


class TestSetFormaPagSimples:
    def test_grava_com_os_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 55)
        assert r["success"] is True
        update_q, params = cur.queries[-1]
        assert "UPDATE os SET forma_pagamento=%s WHERE codigo=%s" == update_q
        assert params == ("DI", 55)

    def test_bloqueia_os_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 55)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"].lower()

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()
