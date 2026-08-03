"""Testes UNITÁRIOS de Cotação de Compra (Transações > Gestão de Compras)."""
import services.cotacao_compra_service as svc


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


class TestFindProduto:
    def test_termo_vazio_nao_bate_no_banco(self, monkeypatch):
        conn = _patch(monkeypatch, FakeCursor())
        r = svc._find_produto_sync("srv", "bd", "  ")
        assert r == {"success": True, "found": False}
        assert conn._c.queries == []

    def test_encontra_por_codigo_int_com_ultima_compra(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo_int": "P001", "descricao": "Parafuso", "custo_medio": 2.0, "qtd": 100.0},
            {"data_mov": "2026-01-10", "qtd": 5.0, "qtd_un_compra": 1.0, "valor_total": 12.50},
        ])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "P001")
        assert r["success"] and r["found"]
        assert r["custo_medio"] == 2.0 and r["estoque"] == 100.0
        assert r["ultima_compra_valor"] == 2.5

    def test_encontra_sem_historico_de_compra(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo_int": "P001", "descricao": "Parafuso", "custo_medio": 2.0, "qtd": 100.0},
            None,
        ])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "P001")
        assert r["found"] and r["ultima_compra_valor"] is None

    def test_encontra_por_codigo_fab(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo_int": "P002", "descricao": "Porca", "custo_medio": 1.0, "qtd": 5.0}, None])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "FAB-1")
        assert r["found"] and r["codigo"] == "P002"

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "XXX")
        assert r["success"] and not r["found"]


class TestIncluirItemValidacoesSemBanco:
    def test_sem_produto(self):
        r = svc._incluir_item_sync("srv", "bd", None, "desc", "", 1, 1)
        assert not r["success"] and "produto" in r["message"].lower()

    def test_qtd_invalida(self):
        r = svc._incluir_item_sync("srv", "bd", None, "desc", "P1", 0, 1)
        assert not r["success"] and "quantidade" in r["message"].lower()


class TestIncluirItemComBanco:
    def test_cria_cotacao_nova_e_inclui_item(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10}, {"ok": 1}, {"cod": 55}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", None, "Cotação teste", "P001", 3, 1)
        assert r["success"] and r["codigo"] == 10 and r["cod_item"] == 55
        assert conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "insert into cotacao_compra (" in joined

    def test_cotacao_existente_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "", "P001", 3, 1)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_cotacao_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 999, "", "P001", 3, 1)
        assert not r["success"]

    def test_produto_nao_cadastrado_bloqueia_e_faz_rollback(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "", "XXX", 3, 1)
        assert not r["success"] and "cadastrado" in r["message"].lower()
        assert conn.rolled

    def test_inclui_item_em_cotacao_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"cod": 77}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "", "P001", 2, 1)
        assert r["success"] and r["codigo"] == 10 and r["cod_item"] == 77
        assert conn.committed


class TestExcluirItem:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert not r["success"]

    def test_cotacao_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cotacao": 10, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"cotacao": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "delete from cotacao_compra_resposta" in joined
        assert "delete from cotacao_compra_item" in joined


class TestIncluirRespostaValidacoesSemBanco:
    def test_sem_fornecedor(self):
        r = svc._incluir_resposta_sync("srv", "bd", 1, 0, 10.0, None, None, None)
        assert not r["success"] and "fornecedor" in r["message"].lower()

    def test_valor_invalido(self):
        r = svc._incluir_resposta_sync("srv", "bd", 1, 5, 0, None, None, None)
        assert not r["success"] and "valor" in r["message"].lower()


class TestIncluirRespostaComBanco:
    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._incluir_resposta_sync("srv", "bd", 1, 5, 10.0, None, None, None)
        assert not r["success"]

    def test_cotacao_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._incluir_resposta_sync("srv", "bd", 1, 5, 10.0, None, None, None)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_fornecedor_nao_cadastrado_bloqueia_e_faz_rollback(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1, "situacao": "A"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_resposta_sync("srv", "bd", 1, 5, 10.0, None, None, None)
        assert not r["success"] and "cadastrado" in r["message"].lower()
        assert conn.rolled

    def test_inclui_resposta_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1, "situacao": "A"}, {"ok": 1}, {"cod": 99}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_resposta_sync("srv", "bd", 1, 5, 10.0, "Marca X", "5 dias", "30 dias")
        assert r["success"] and r["cod_resposta"] == 99
        assert conn.committed


class TestExcluirResposta:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_resposta_sync("srv", "bd", 1)
        assert not r["success"]

    def test_cotacao_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cotacao_item": 1, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._excluir_resposta_sync("srv", "bd", 1)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_exclui_com_sucesso_e_limpa_vencedor(self, monkeypatch):
        cur = FakeCursor(one=[{"cotacao_item": 1, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_resposta_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update cotacao_compra_item set fornecedor_vencedor=null" in joined
        assert "delete from cotacao_compra_resposta" in joined


class TestMarcarVencedor:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._marcar_vencedor_sync("srv", "bd", 1)
        assert not r["success"]

    def test_cotacao_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cotacao_item": 1, "fornecedor": 3, "valor_unit": 10.0, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._marcar_vencedor_sync("srv", "bd", 1)
        assert not r["success"] and "aberta" in r["message"].lower()

    def test_marca_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"cotacao_item": 1, "fornecedor": 3, "valor_unit": 10.0, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._marcar_vencedor_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update cotacao_compra_item set fornecedor_vencedor=" in joined


class TestFinalizarCotacao:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._finalizar_cotacao_sync("srv", "bd", 1)
        assert not r["success"]

    def test_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._finalizar_cotacao_sync("srv", "bd", 1)
        assert not r["success"]

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._finalizar_cotacao_sync("srv", "bd", 1)
        assert not r["success"] and "item" in r["message"].lower()

    def test_finaliza_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._finalizar_cotacao_sync("srv", "bd", 10)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update cotacao_compra set situacao='f'" in joined


class TestReabrirCotacao:
    def test_nao_finalizada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_cotacao_sync("srv", "bd", 10)
        assert not r["success"]

    def test_reabre_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_cotacao_sync("srv", "bd", 10)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "situacao='a'" in joined


class TestCancelarCotacao:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_cotacao_sync("srv", "bd", 10)
        assert not r["success"]

    def test_ja_cancelada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_cotacao_sync("srv", "bd", 10)
        assert not r["success"]

    def test_cancela_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_cotacao_sync("srv", "bd", 10)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "situacao='c'" in joined
