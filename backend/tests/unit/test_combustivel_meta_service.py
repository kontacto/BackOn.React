"""Testes UNITÁRIOS de Metas de Combustível (Posto de Combustível).

Mesmo padrão de test_contatos_service.py / test_equipamentos_service.py:
cursor/conexão falsos (monkeypatch em _open_conn), sem banco real.
"""
import services.combustivel_meta_service as svc


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
    def test_mes_obrigatorio_invalido(self):
        r = svc._save_meta_sync("srv", "bd", grupo=1, ano=2026, mes=13, meta=100)
        assert r["success"] is False and "mês" in r["message"].lower()

    def test_mes_zero_invalido(self):
        r = svc._save_meta_sync("srv", "bd", grupo=1, ano=2026, mes=0, meta=100)
        assert r["success"] is False and "mês" in r["message"].lower()

    def test_ano_invalido(self):
        r = svc._save_meta_sync("srv", "bd", grupo=1, ano=1999, mes=1, meta=100)
        assert r["success"] is False and "ano" in r["message"].lower()

    def test_grupo_obrigatorio(self):
        r = svc._save_meta_sync("srv", "bd", grupo=None, ano=2026, mes=1, meta=100)
        assert r["success"] is False and "grupo" in r["message"].lower()


class TestModuloDesativado:
    def test_list_grupos_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        _patch(monkeypatch, cur)
        r = svc._list_grupos_sync("srv", "bd")
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert r["items"] == []

    def test_list_metas_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        _patch(monkeypatch, cur)
        r = svc._list_metas_sync("srv", "bd")
        assert r["success"] is False and "desativado" in r["message"].lower()

    def test_save_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._save_meta_sync("srv", "bd", grupo=1, ano=2026, mes=1, meta=100)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False

    def test_delete_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_meta_sync("srv", "bd", grupo=1, ano=2026, mes=1)
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestSaveComMock:
    def test_grupo_nao_encontrado(self, monkeypatch):
        # 1a fetchone = módulo ativo; 2a fetchone = grupo (não encontrado, None)
        cur = FakeCursor(one=[MODULO_ON, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_meta_sync("srv", "bd", grupo=99, ano=2026, mes=1, meta=100)
        assert r["success"] is False and "grupo" in r["message"].lower()
        assert conn.committed is False

    def test_insere_meta_nova(self, monkeypatch):
        # módulo ativo, grupo existe, meta ainda não existe (None)
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_meta_sync("srv", "bd", grupo=1, ano=2026, mes=7, meta=15000)
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO combustivel_meta" in q for q, _ in cur.queries)
        assert not any("UPDATE combustivel_meta" in q for q, _ in cur.queries)

    def test_atualiza_meta_existente(self, monkeypatch):
        # módulo ativo, grupo existe, meta já existe
        cur = FakeCursor(one=[MODULO_ON, {"ok": 1}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_meta_sync("srv", "bd", grupo=1, ano=2026, mes=7, meta=20000)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE combustivel_meta" in q for q, _ in cur.queries)
        assert not any("INSERT INTO combustivel_meta" in q for q, _ in cur.queries)


class TestDeleteComMock:
    def test_exclui_meta(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_meta_sync("srv", "bd", grupo=1, ano=2026, mes=7)
        assert r["success"] is True
        assert conn.committed is True

    def test_exclui_meta_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_meta_sync("srv", "bd", grupo=1, ano=2026, mes=7)
        assert r["success"] is False and "não encontrada" in r["message"]
        assert conn.committed is False
        assert conn.rolled is True
