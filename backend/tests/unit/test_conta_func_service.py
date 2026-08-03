"""Testes unitários de Contas x Funcionário (Financeiro > Fluxo de Caixa,
ver services/conta_func_service.py e PENDENCIAS.md > "Contas x
Funcionário") — cursor falso, mesmo padrão dos outros services desta área."""
import services.conta_func_service as svc


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

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestGetVinculo:
    def test_lista_contas_e_vinculadas(self, monkeypatch):
        contas_rows = [{"codigo": 1, "descricao": "CAIXA"}, {"codigo": 2, "descricao": "BANCO X"}]
        vinculo_rows = [{"conta": 2}]
        cur = FakeCursor(many=[contas_rows, vinculo_rows])
        _patch(monkeypatch, cur)
        r = svc._get_vinculo_sync("srv", "bd", 10)
        assert r["success"] is True
        assert r["contas"] == [{"codigo": 1, "descricao": "CAIXA"}, {"codigo": 2, "descricao": "BANCO X"}]
        assert r["vinculadas"] == [2]

    def test_falha_conexao(self, monkeypatch):
        def boom(*a, **k):
            raise Exception("timeout")
        monkeypatch.setattr(svc, "_open_conn", boom)
        r = svc._get_vinculo_sync("srv", "bd", 10)
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


class TestSalvarVinculo:
    def test_funcionario_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._salvar_vinculo_sync("srv", "bd", 999, [1, 2])
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_substitui_todos_os_vinculos(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._salvar_vinculo_sync("srv", "bd", 10, [1, 2, 3])
        assert r["success"] is True
        assert r["qtd"] == 3
        assert conn.committed is True
        delete_q = [q for q, p in cur.queries if q.strip().startswith("DELETE")]
        insert_qs = [(q, p) for q, p in cur.queries if q.strip().startswith("INSERT")]
        assert len(delete_q) == 1
        assert len(insert_qs) == 3
        assert insert_qs[0][1] == (1, 10)

    def test_lista_vazia_so_apaga_vinculos_antigos(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._salvar_vinculo_sync("srv", "bd", 10, [])
        assert r["success"] is True
        assert r["qtd"] == 0
        assert conn.committed is True
        insert_qs = [q for q, p in cur.queries if q.strip().startswith("INSERT")]
        assert insert_qs == []


class TestListVisiveis:
    def test_master_ve_todas_ativas_ignorando_funcionario(self, monkeypatch):
        rows = [{"codigo": 1, "descricao": "CAIXA", "ContaPrincipalPainel": True}]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_visiveis_sync("srv", "bd", funcionario=None, is_master=True)
        assert r["success"] is True
        assert r["items"] == [{"codigo": 1, "descricao": "CAIXA", "conta_principal_painel": True}]
        # não filtrou por conta_func — só uma query, sem JOIN
        assert "conta_func" not in cur.queries[0][0]

    def test_funcionario_sem_vinculo_nao_ve_nenhuma_conta(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_visiveis_sync("srv", "bd", funcionario=10, is_master=False)
        assert r["success"] is True
        assert r["items"] == []
        assert "conta_func" in cur.queries[0][0]

    def test_sem_funcionario_e_sem_master_devolve_vazio_sem_query(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._list_visiveis_sync("srv", "bd", funcionario=None, is_master=False)
        assert r["success"] is True
        assert r["items"] == []
        assert cur.queries == []

    def test_funcionario_com_vinculo_ve_so_as_suas_contas(self, monkeypatch):
        rows = [{"codigo": 5, "descricao": "BANCO Y", "ContaPrincipalPainel": False}]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_visiveis_sync("srv", "bd", funcionario=10, is_master=False)
        assert r["items"] == [{"codigo": 5, "descricao": "BANCO Y", "conta_principal_painel": False}]
        query, params = cur.queries[0]
        assert "JOIN conta_func" in query
        assert params == (10,)
