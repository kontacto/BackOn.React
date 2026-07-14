"""Testes UNITÁRIOS de Combustíveis (Posto de Combustível)."""
import services.combustivel_service as svc


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


def _dados(**over):
    base = dict(descricao="GASOLINA COMUM", venda=5.99, venda2=0, codigo_automacao=None, indImport=None, cUFOrig=None, pOrig=0)
    base.update(over)
    return base


class TestValidacoesSemBanco:
    def test_codigo_invalido(self):
        r = svc._save_sync("srv", "bd", codigo=300, dados=_dados())
        assert r["success"] is False and "código" in r["message"].lower()

    def test_descricao_obrigatoria(self):
        r = svc._save_sync("srv", "bd", codigo=1, dados=_dados(descricao="  "))
        assert r["success"] is False and "descri" in r["message"].lower()

    def test_venda_obrigatoria(self):
        r = svc._save_sync("srv", "bd", codigo=1, dados=_dados(venda=None))
        assert r["success"] is False and "venda" in r["message"].lower()


class TestModuloDesativado:
    def test_save_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", codigo=1, dados=_dados())
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False

    def test_delete_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "desativado" in r["message"].lower()


class TestSaveComMock:
    def test_insere_novo(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", codigo=1, dados=_dados())
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO combustivel" in q for q, _ in cur.queries)
        # Custo nunca é gravado (dead code do legado, ver docstring do service)
        assert not any("custo" in q.lower() for q, _ in cur.queries)

    def test_atualiza_existente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", codigo=1, dados=_dados(venda=6.5))
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE combustivel" in q for q, _ in cur.queries)
        assert not any("custo" in q.lower() for q, _ in cur.queries)


class TestDeleteComMock:
    def test_bloqueia_com_movimentacao(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "vendas associadas" in r["message"].lower()
        assert conn.committed is False

    def test_exclui_sem_movimentacao(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_exclui_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, None], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False
