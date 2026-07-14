"""Testes UNITÁRIOS de Telemarketing (_save_contato_sync/_get_cliente_sync/
_list_selecionar_sync).

Mesmo padrão de test_contatos_service.py / test_equipamentos_service.py:
cursor/conexão falsos (monkeypatch em _open_conn), sem banco real.
"""
import services.telemarketing_service as svc


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


class TestSaveContatoValidacoes:
    def test_cliente_obrigatorio(self):
        r = svc._save_contato_sync("srv", "bd", 0, "Ligou perguntando sobre pedido", None, 3)
        assert r["success"] is False and "cliente" in r["message"].lower()

    def test_texto_obrigatorio(self):
        r = svc._save_contato_sync("srv", "bd", 10, "   ", None, 3)
        assert r["success"] is False and "texto" in r["message"].lower()


class TestSaveContatoComMock:
    def test_grava_sem_agendamento(self, monkeypatch):
        # 1) SELECT historico (existente) 2) SELECT nome_guerra
        cur = FakeCursor(one=[{"historico": "Entrada antiga"}, {"nome_guerra": "CARLOS"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_contato_sync("srv", "bd", 10, "Cliente confirmou interesse", None, 3)
        assert r["success"] is True
        assert conn.committed is True
        assert "Cliente confirmou interesse" in r["historico"]
        assert "Entrada antiga" in r["historico"]
        assert "CARLOS" in r["historico"]
        # sem agendamento -> UPDATE que zera DATA_AGENDAMENTO_TELEMARKETING
        assert any("DATA_AGENDAMENTO_TELEMARKETING=NULL" in q for q, _ in cur.queries)

    def test_grava_com_agendamento(self, monkeypatch):
        cur = FakeCursor(one=[{"historico": ""}, {"nome_guerra": "ADRIANA"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_contato_sync("srv", "bd", 10, "Vai ligar de volta", "2026-08-01", 5)
        assert r["success"] is True
        assert conn.committed is True
        # Formato dd-mm-aaaa pedido pelo usuário (o valor cru é ISO, vindo
        # do <input type=date> do frontend) — não deixar o ISO vazar pro
        # texto exibido no histórico.
        assert "Contato agendado para o dia 01-08-2026" in r["historico"]
        assert "2026-08-01" not in r["historico"]
        # a coluna DATA_AGENDAMENTO_TELEMARKETING continua recebendo o ISO
        # (formato que o SQL Server espera), só o TEXTO do histórico muda.
        agend_q, agend_p = next(
            (q, p) for q, p in cur.queries if "DATA_AGENDAMENTO_TELEMARKETING=%s" in q
        )
        assert "2026-08-01" in agend_p
        assert any(
            "DATA_AGENDAMENTO_TELEMARKETING=%s" in q and "FUNCIONARIO_AGENDAMENTO_TELEMARKETING=%s" in q
            for q, _ in cur.queries
        )

    def test_cliente_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_contato_sync("srv", "bd", 999, "texto", None, 3)
        assert r["success"] is False and "não encontrado" in r["message"]
        assert conn.committed is False


class TestGetCliente:
    def test_cliente_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_cliente_sync("srv", "bd", 999)
        assert r["success"] is False and "não encontrado" in r["message"]


class TestListSelecionar:
    def test_query_aplica_filtros_basicos(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._list_selecionar_sync("srv", "bd", {
            "dia_contato": 2, "cliente_termo": "fulano", "cgc_cpf": "123",
            "bairro": "Centro", "situacao": "A",
        })
        assert r["success"] is True
        query, params = cur.queries[-1]
        assert "c.dia_contato = %s" in query
        assert "c.nome LIKE %s" in query  # termo não-numérico -> LIKE por nome
        assert "cliente_end" in query  # filtro de bairro via subquery
        assert 2 in params

    def test_termo_numerico_filtra_por_codigo(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        svc._list_selecionar_sync("srv", "bd", {"cliente_termo": "1583"})
        query, params = cur.queries[-1]
        assert "c.codigo = %s" in query
        assert 1583 in params
