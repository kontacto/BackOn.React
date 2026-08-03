"""Testes unitários de Contas (Financeiro > Fluxo de Caixa, ver
services/contas_service.py e PENDENCIAS.md > "Contas") — cursor falso,
mesmo padrão dos outros services desta área."""
import services.contas_service as svc


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


CONTA_ROW = {
    "codigo": 1, "descricao": "CAIXA GERAL", "banco": "", "agencia": "", "numero": "",
    "saldo_inicial": 1000.0, "saldo_atual": 1500.0, "moeda": "Real", "tipo": 0,
    "situacao": "A", "ContaPrincipalPainel": True,
}


class TestListarContas:
    def test_lista_sem_busca(self, monkeypatch):
        cur = FakeCursor(many=[[dict(CONTA_ROW)]])
        _patch(monkeypatch, cur)
        r = svc._list_sync("srv", "bd", None)
        assert r["success"] is True
        assert r["items"][0]["descricao"] == "CAIXA GERAL"
        assert r["items"][0]["conta_principal_painel"] is True

    def test_busca_numerica_por_codigo(self, monkeypatch):
        cur = FakeCursor(many=[[dict(CONTA_ROW)]])
        _patch(monkeypatch, cur)
        svc._list_sync("srv", "bd", "1")
        assert "codigo=%s" in cur.queries[-1][0]

    def test_busca_texto_por_descricao(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_sync("srv", "bd", "caixa")
        assert "descricao LIKE %s" in cur.queries[-1][0]


class TestGetConta:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[dict(CONTA_ROW)])
        _patch(monkeypatch, cur)
        r = svc._get_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["saldo_atual"] == 1500.0


class TestSalvarConta:
    def test_sem_descricao_bloqueia(self, monkeypatch):
        r = svc._save_sync("srv", "bd", {"descricao": "  "})
        assert r["success"] is False

    def test_descricao_duplicada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 5}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {"descricao": "CAIXA GERAL"})
        assert r["success"] is False
        assert "Já existe" in r["message"]

    def test_cria_nova_conta_saldo_atual_igual_inicial(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 10}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {"descricao": "NOVA CONTA", "saldo_inicial": 500})
        assert r["success"] is True
        assert r["codigo"] == 10
        assert conn.committed is True
        insert_q, insert_p = cur.queries[1]
        assert "INSERT INTO Contas" in insert_q
        # Saldo_Inicial e Saldo_Atual gravados com o mesmo valor na criação
        assert insert_p[4] == 500.0 and insert_p[5] == 500.0

    def test_edita_sem_mudar_saldo_inicial_mantem_saldo_atual(self, monkeypatch):
        cur = FakeCursor(one=[None, {"saldo_inicial": 1000.0, "saldo_atual": 1500.0}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {"codigo": 1, "descricao": "CAIXA GERAL", "saldo_inicial": 1000})
        assert r["success"] is True
        assert r["ajuste_saldo"] is False
        assert r["saldo_atual_novo"] == 1500.0

    def test_edita_aumentando_saldo_inicial_desloca_saldo_atual(self, monkeypatch):
        cur = FakeCursor(one=[None, {"saldo_inicial": 1000.0, "saldo_atual": 1500.0}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {"codigo": 1, "descricao": "CAIXA GERAL", "saldo_inicial": 1200})
        assert r["success"] is True
        assert r["ajuste_saldo"] is True
        assert r["saldo_atual_novo"] == 1700.0  # 1500 + (1200-1000)

    def test_edita_diminuindo_saldo_inicial_desloca_saldo_atual(self, monkeypatch):
        cur = FakeCursor(one=[None, {"saldo_inicial": 1000.0, "saldo_atual": 1500.0}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {"codigo": 1, "descricao": "CAIXA GERAL", "saldo_inicial": 700})
        assert r["success"] is True
        assert r["saldo_atual_novo"] == 1200.0  # 1500 + (700-1000)

    def test_edita_conta_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {"codigo": 999, "descricao": "X"})
        assert r["success"] is False


class TestExcluirConta:
    def test_bloqueia_com_previsao(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "previsões" in r["message"]

    def test_bloqueia_com_movimentacao(self, monkeypatch):
        cur = FakeCursor(one=[None, {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "movimentações" in r["message"]

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[None, None])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
