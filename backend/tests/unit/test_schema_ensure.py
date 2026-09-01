"""Testes unitários de `services/schema_ensure.py::ensure_auto_close_off` —
ver docstring da função pro achado real que motivou (timeout intermitente
no BackOn VB6 de um cliente, causado por AUTO_CLOSE ligado por padrão no
SQL Server Express)."""
import services.schema_ensure as svc


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append(q)

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.autocommit_calls = []

    def cursor(self, as_dict=False):
        return self._c

    def autocommit(self, status):
        self.autocommit_calls.append(status)


def _reset_cache():
    svc._AUTO_CLOSE_JA_GARANTIDO.clear()


class TestEnsureAutoCloseOff:
    def test_desliga_quando_ligado(self):
        _reset_cache()
        cur = FakeCursor(one=[{"is_auto_close_on": True}, {"db": "BD_REVENDA"}])
        conn = FakeConn(cur)
        svc.ensure_auto_close_off(conn, "srv", "bd")
        alter = [q for q in cur.queries if q.startswith("ALTER DATABASE")]
        assert alter == ["ALTER DATABASE [BD_REVENDA] SET AUTO_CLOSE OFF"]
        # liga autocommit só pra essa instrução, devolve pro estado anterior em seguida.
        assert conn.autocommit_calls == [True, False]

    def test_nao_mexe_quando_ja_desligado(self):
        _reset_cache()
        cur = FakeCursor(one=[{"is_auto_close_on": False}])
        conn = FakeConn(cur)
        svc.ensure_auto_close_off(conn, "srv", "bd")
        assert not any(q.startswith("ALTER DATABASE") for q in cur.queries)
        assert conn.autocommit_calls == []

    def test_escapa_colchete_no_nome_do_banco(self):
        _reset_cache()
        cur = FakeCursor(one=[{"is_auto_close_on": True}, {"db": "BD]MALUCO"}])
        conn = FakeConn(cur)
        svc.ensure_auto_close_off(conn, "srv", "bd")
        alter = [q for q in cur.queries if q.startswith("ALTER DATABASE")][0]
        assert alter == "ALTER DATABASE [BD]]MALUCO] SET AUTO_CLOSE OFF"

    def test_cacheado_por_processo_nao_roda_de_novo(self):
        _reset_cache()
        cur = FakeCursor(one=[{"is_auto_close_on": True}, {"db": "BD_REVENDA"}])
        conn = FakeConn(cur)
        svc.ensure_auto_close_off(conn, "srv", "bd")
        svc.ensure_auto_close_off(conn, "srv", "bd")  # 2ª chamada — cache já garantido, nada roda
        alter = [q for q in cur.queries if q.startswith("ALTER DATABASE")]
        assert len(alter) == 1

    def test_falha_isolada_nao_propaga(self):
        _reset_cache()

        class ExplodingCursor(FakeCursor):
            def execute(self, q, p=None):
                raise RuntimeError("boom")

        conn = FakeConn(ExplodingCursor())
        svc.ensure_auto_close_off(conn, "srv", "bd")  # não deve levantar
