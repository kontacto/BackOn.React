"""Testes UNITÁRIOS de Entrada/Saída de Caixa (_save_sync/_delete_sync).

Mesmo padrão de test_clientes_service.py: cursor/conexão falsos
(monkeypatch em _open_conn), validando resultado e queries emitidas —
sem banco real.
"""
import services.entrada_saida_caixa_service as svc


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


class TestValidacoesSemBanco:
    def test_tipo_invalido(self):
        r = svc._save_sync("srv", "bd", None, "X", 10, "desc", None, None, None, None, None, None, None, 1)
        assert r["success"] is False and "Entrada ou Saída" in r["message"]

    def test_valor_obrigatorio(self):
        r = svc._save_sync("srv", "bd", None, "E", 0, "desc", None, None, None, None, None, None, None, 1)
        assert r["success"] is False and "valor" in r["message"].lower()

    def test_descricao_obrigatoria(self):
        r = svc._save_sync("srv", "bd", None, "E", 10, "   ", None, None, None, None, None, None, None, 1)
        assert r["success"] is False and "descrição" in r["message"].lower()

    def test_conta_origem_destino_iguais(self):
        r = svc._save_sync("srv", "bd", None, "E", 10, "desc", None, 5, 5, None, None, None, None, 1)
        assert r["success"] is False and "não podem ser a mesma" in r["message"]


class TestResolveFavorecido:
    def test_encontra_existente(self):
        cur = FakeCursor(one=[{"codigo": 42}])
        cod = svc._resolve_favorecido_sync(cur, "ACME")
        assert cod == 42
        assert len(cur.queries) == 1

    def test_cria_se_nao_existir(self):
        cur = FakeCursor(one=[None, {"codigo": 99}])
        cod = svc._resolve_favorecido_sync(cur, "NOVO FAVORECIDO")
        assert cod == 99
        assert len(cur.queries) == 2
        assert "INSERT INTO favorecidos" in cur.queries[1][0]


class TestSaveComMock:
    def test_insert_novo_lancamento_sem_transferencia(self, monkeypatch):
        cur = FakeCursor(one=[
            {"transf_ent_sai_caixa": False},  # config
            {"codigo": 501},                  # INSERT ... OUTPUT INSERTED.codigo
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(
            "srv", "bd", None, "E", 35.0, "Compra de café", "01",
            None, None, None, None, None, None, 3,
        )
        assert r["success"] is True
        assert r["codigo"] == 501
        assert conn.committed is True
        assert any("INSERT INTO entrada_caixa" in q for q, _ in cur.queries)

    def test_transferencia_entre_contas_sobrepoe_classe(self, monkeypatch):
        cur = FakeCursor(one=[
            {"transf_ent_sai_caixa": True},   # config
            {"cod_movimentacao": None},       # SELECT cod_movimentacao (existe, não transferido)
            None,                              # favorecido não encontrado
            {"codigo": 77},                    # favorecido criado
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(
            "srv", "bd", 999, "S", 200.0, "Transferência entre contas", "01",
            10, 20, "Banco X", 5, 6, 7, 3,
        )
        assert r["success"] is True
        assert conn.committed is True
        ultima_query, ultimos_params = cur.queries[-1]
        assert "transferencia='2'" in ultima_query
        assert "sub_classe=0" in ultima_query
        # classe recebe o código da conta destino (20), não o `classe` passado (5) —
        # comportamento herdado do legado (FrmManESC), preservado de propósito.
        assert 20 in ultimos_params

    def test_bloqueia_alteracao_ja_transferido(self, monkeypatch):
        cur = FakeCursor(one=[
            {"transf_ent_sai_caixa": False},
            {"cod_movimentacao": 555},
            {"ok": 1},  # existe em movimentacoes
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(
            "srv", "bd", 999, "E", 50.0, "Tentando alterar", None,
            None, None, None, None, None, None, 3,
        )
        assert r["success"] is False
        assert "transferido" in r["message"]
        assert conn.committed is False

    def test_exige_conta_e_favorecido_quando_transf_ativo(self, monkeypatch):
        cur = FakeCursor(one=[{"transf_ent_sai_caixa": True}])
        _patch(monkeypatch, cur)
        r = svc._save_sync(
            "srv", "bd", None, "E", 50.0, "Sem conta", None,
            None, None, None, None, None, None, 3,
        )
        assert r["success"] is False and "conta" in r["message"].lower()


class TestDeleteComMock:
    def test_lancamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", "E", 1)
        assert r["success"] is False and "não encontrado" in r["message"]

    def test_bloqueia_exclusao_ja_transferido(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_movimentacao": 555}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", "S", 1)
        assert r["success"] is False and "transferido" in r["message"]
        assert conn.committed is False

    def test_exclui_quando_nao_transferido(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_movimentacao": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", "E", 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("DELETE FROM entrada_caixa" in q for q, _ in cur.queries)
