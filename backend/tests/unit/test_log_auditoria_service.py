"""Testes UNITÁRIOS do log de auditoria — cobre principalmente a migração
idempotente da tabela `log_auditoria` (`_ensure_log_auditoria_table`),
adicionada depois de uma base de teste (sem esse schema, não legado) fazer
`registrar_log` falhar em silêncio (best-effort) e o card de Alertas de
Estoque reportar "Curva ABC nunca foi gerada" mesmo já tendo sido gerada."""
import services.log_auditoria_service as svc


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
        self.rolled_back = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestEnsureLogAuditoriaTable:
    def test_ddl_e_idempotente_com_if_not_exists(self):
        assert "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'log_auditoria')" in svc._DDL_LOG_AUDITORIA
        assert "CREATE TABLE log_auditoria" in svc._DDL_LOG_AUDITORIA


class TestRegistrarLogGaranteTabela:
    def test_cria_tabela_antes_do_insert(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        svc._registrar_log_sync(
            "srv", "bd", tela="CURVA_ABC", comando="GERAR", usuario=1, classe=1,
        )
        assert len(cur.queries) == 2
        assert "CREATE TABLE log_auditoria" in cur.queries[0][0]
        assert "INSERT INTO log_auditoria" in cur.queries[1][0]
        assert conn.committed is True

    def test_falha_no_insert_nao_propaga(self, monkeypatch):
        class RaisingCursor(FakeCursor):
            def execute(self, q, p=None):
                super().execute(q, p)
                if "INSERT INTO log_auditoria" in q:
                    raise Exception("boom")

        cur = RaisingCursor()
        _patch(monkeypatch, cur)
        # Não deve levantar exceção — best-effort.
        svc._registrar_log_sync("srv", "bd", tela="CURVA_ABC", comando="GERAR")


class TestListLogsGaranteTabela:
    def test_cria_tabela_antes_de_listar(self, monkeypatch):
        cur = FakeCursor(one=[{"n": 0}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_logs_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert "CREATE TABLE log_auditoria" in cur.queries[0][0]
