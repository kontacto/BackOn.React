"""Testes UNITÁRIOS de Contatos (_save_sync/_delete_sync).

Mesmo padrão de test_clientes_service.py / test_entrada_saida_caixa_service.py:
cursor/conexão falsos (monkeypatch em _open_conn), sem banco real.
"""
import services.contatos_service as svc


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


def _args(**over):
    base = dict(
        codigo=None, data="2026-07-12", cliente="Fulano de Tal", telefone="1199990000",
        telefone_2=None, tipo_cliente=1, contato="Ciclano", profissional=3,
        data_prev=None, hora_prev=None, obs=None, e_mail=None, endereco=None,
        bairro=None, indicacao=None,
    )
    base.update(over)
    return base


class TestValidacoesSemBanco:
    def test_data_obrigatoria(self):
        r = svc._save_sync("srv", "bd", **_args(data=None))
        assert r["success"] is False and "data" in r["message"].lower()

    def test_cliente_obrigatorio(self):
        r = svc._save_sync("srv", "bd", **_args(cliente="   "))
        assert r["success"] is False and "cliente" in r["message"].lower()

    def test_tipo_cliente_obrigatorio(self):
        r = svc._save_sync("srv", "bd", **_args(tipo_cliente=None))
        assert r["success"] is False and "tipo de cliente" in r["message"].lower()

    def test_profissional_obrigatorio(self):
        r = svc._save_sync("srv", "bd", **_args(profissional=None))
        assert r["success"] is False and "profissional" in r["message"].lower()


class TestSaveComMock:
    def test_insere_novo_contato(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 501}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args())
        assert r["success"] is True
        assert r["codigo"] == 501
        assert conn.committed is True
        assert any("INSERT INTO contatos" in q for q, _ in cur.queries)

    def test_edita_contato_existente_via_update_preserva_codigo(self, monkeypatch):
        # Regra preservada do legado (delete+reinsert) é INTENCIONALMENTE
        # substituída por um UPDATE de verdade — o codigo não pode mudar.
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args(codigo=999))
        assert r["success"] is True
        assert r["codigo"] == 999
        assert conn.committed is True
        assert any("UPDATE contatos" in q for q, _ in cur.queries)
        assert not any("DELETE FROM contatos" in q for q, _ in cur.queries)
        assert not any("INSERT INTO contatos" in q for q, _ in cur.queries)

    def test_edita_contato_inexistente(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", **_args(codigo=999))
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False


class TestDeleteComMock:
    def test_exclui_contato(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_exclui_contato_inexistente(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False
