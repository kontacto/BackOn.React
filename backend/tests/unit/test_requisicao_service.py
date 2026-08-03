"""Testes UNITÁRIOS de Requisição (Transações > Movimentações)."""
import services.requisicao_service as svc


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


class TestFindItem:
    def test_termo_vazio_nao_bate_no_banco(self, monkeypatch):
        conn = _patch(monkeypatch, FakeCursor())
        r = svc._find_item_sync("srv", "bd", "  ")
        assert r == {"success": True, "found": False}
        assert conn._c.queries == []

    def test_encontra_por_codigo_int(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo_int": "P001", "descricao": "Parafuso", "p_custo": 2.5, "qtd": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._find_item_sync("srv", "bd", "P001")
        assert r["success"] and r["found"] and r["tipo"] == "P"
        assert r["preco"] == 2.5 and r["estoque"] == 100.0

    def test_encontra_por_codigo_fab(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo_int": "P002", "descricao": "Porca", "p_custo": 1.0, "qtd": 5.0}])
        _patch(monkeypatch, cur)
        r = svc._find_item_sync("srv", "bd", "FAB-1")
        assert r["found"] and r["codigo"] == "P002"

    def test_fallback_para_servico(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None, {"codigo": "S01", "descricao": "Instalação", "valor_hora": 80.0}])
        _patch(monkeypatch, cur)
        r = svc._find_item_sync("srv", "bd", "S01")
        assert r["found"] and r["tipo"] == "S" and r["preco"] == 80.0 and r["estoque"] is None

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None, None])
        _patch(monkeypatch, cur)
        r = svc._find_item_sync("srv", "bd", "XXX")
        assert r["success"] and not r["found"]


class TestIncluirItemValidacoesSemBanco:
    def test_sem_produto(self):
        r = svc._incluir_item_sync("srv", "bd", None, "desc", "", 1, 1, 1)
        assert not r["success"] and "produto" in r["message"].lower()

    def test_qtd_invalida(self):
        r = svc._incluir_item_sync("srv", "bd", None, "desc", "P1", 0, 1, 1)
        assert not r["success"] and "quantidade" in r["message"].lower()

    def test_preco_negativo(self):
        r = svc._incluir_item_sync("srv", "bd", None, "desc", "P1", 1, -1, 1)
        assert not r["success"] and "preço" in r["message"].lower()


class TestIncluirItemComBanco:
    def test_cria_requisicao_nova_e_inclui_item(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10}, {"ok": 1}, {"cod": 55}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", None, "Descrição teste", "P001", 3, 10.0, 1)
        assert r["success"] and r["codigo"] == 10 and r["cod_item"] == 55
        assert conn.committed
        assert "insert into requisicao" in cur.queries[0][0].lower()

    def test_requisicao_existente_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "", "P001", 3, 10.0, 1)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_requisicao_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 999, "", "P001", 3, 10.0, 1)
        assert not r["success"]

    def test_produto_nao_cadastrado_bloqueia_e_faz_rollback(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "", "XXX", 3, 10.0, 1)
        assert not r["success"] and "cadastrado" in r["message"].lower()
        assert conn.rolled

    def test_inclui_item_em_requisicao_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"cod": 77}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "", "P001", 2, 5.0, 1)
        assert r["success"] and r["codigo"] == 10 and r["cod_item"] == 77
        assert conn.committed


class TestExcluirItem:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert not r["success"]

    def test_requisicao_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"requisicao": 10, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"requisicao": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        assert "delete from rec_prod" in cur.queries[-1][0].lower()


class TestFecharRequisicao:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._fechar_requisicao_sync("srv", "bd", 1, 1)
        assert not r["success"]

    def test_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._fechar_requisicao_sync("srv", "bd", 1, 1)
        assert not r["success"]

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._fechar_requisicao_sync("srv", "bd", 1, 1)
        assert not r["success"] and "item" in r["message"].lower()

    def test_fecha_baixa_estoque_e_grava_movimentacao(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}],
            many=[[{"prod": "P001", "qtd": 5.0, "p_unit": 10.0}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_requisicao_sync("srv", "bd", 10, 1)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update pecas set qtd = qtd - " in joined
        assert "insert into movimentacao" in joined
        assert "'s07'" in joined and "'rq'" in joined
        assert "update requisicao set situacao='f'" in joined


class TestReabrirRequisicao:
    def test_nao_fechada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "nfe": None}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_requisicao_sync("srv", "bd", 10)
        assert not r["success"]

    def test_com_nfe_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F", "nfe": 123}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_requisicao_sync("srv", "bd", 10)
        assert not r["success"] and "nfe" in r["message"].lower()

    def test_reabre_devolve_estoque_e_remove_movimentacao(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "F", "nfe": None}],
            many=[[{"prod": "P001", "qtd": 5.0}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_requisicao_sync("srv", "bd", 10)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update pecas set qtd = qtd + " in joined
        assert "delete from movimentacao" in joined
        assert "situacao='a'" in joined


class TestCancelarRequisicao:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_requisicao_sync("srv", "bd", 10)
        assert not r["success"]

    def test_ja_cancelada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_requisicao_sync("srv", "bd", 10)
        assert not r["success"]

    def test_cancela_aberta_sem_devolver_estoque(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_requisicao_sync("srv", "bd", 10)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update pecas" not in joined
        assert "situacao='c'" in joined

    def test_cancela_fechada_devolve_estoque(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "F"}],
            many=[[{"prod": "P001", "qtd": 5.0}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_requisicao_sync("srv", "bd", 10)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update pecas set qtd = qtd + " in joined
