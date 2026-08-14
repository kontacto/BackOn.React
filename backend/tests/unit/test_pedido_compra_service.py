"""Testes UNITÁRIOS de Pedido de Compra (Transações > Gestão de Compras)."""
import services.pedido_compra_service as svc

FISCAL_VAZIO = {
    "qtd_un_compra": 1, "base_icms": 0, "valor_icms": 0, "base_ipi": 0, "alqt_ipi": 0,
    "valor_ipi": 0, "base_sub": 0, "valor_sub": 0, "base_iss": 0, "valor_iss": 0,
    "frete": 0, "seguro": 0, "despesas": 0, "desconto": 0,
}


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []
        self._last_query = ""

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_query = q

    def fetchone(self):
        # `_modulo_curva_abc_ativo` (pedido_common.py) roda antes da lógica
        # real de toda função deste service — devolve "módulo ligado" sem
        # consumir da fila `_one` (reservada pras queries de negócio de
        # cada teste; nenhum teste deste arquivo cobre o cenário "módulo
        # desligado").
        if "Curva_abc" in self._last_query:
            return {"Curva_abc": True}
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

    def test_encontra_por_codigo_int(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo_int": "P001", "descricao": "Parafuso", "custo_medio": 2.0, "qtd": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "P001")
        assert r["success"] and r["found"] and r["custo_medio"] == 2.0 and r["estoque"] == 100.0

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "XXX")
        assert r["success"] and not r["found"]


class TestFindFornecedorInfo:
    def test_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"nome": "Fornecedor Um", "fantasia": "F1", "prazo_pgto": 30}])
        _patch(monkeypatch, cur)
        r = svc._find_fornecedor_info_sync("srv", "bd", 5)
        assert r["success"] and r["found"] and r["prazo_pgto"] == 30

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._find_fornecedor_info_sync("srv", "bd", 999)
        assert r["success"] and not r["found"]


class TestGravarCabecalhoValidacoesSemBanco:
    def test_sem_fornecedor(self):
        r = svc._gravar_cabecalho_sync("srv", "bd", None, "2026-07-18", 0, None, None, None, None, None, None, None, 0, 1)
        assert not r["success"] and "fornecedor" in r["message"].lower()

    def test_sem_data(self):
        r = svc._gravar_cabecalho_sync("srv", "bd", None, "", 5, None, None, None, None, None, None, None, 0, 1)
        assert not r["success"] and "data" in r["message"].lower()


class TestGravarCabecalhoComBanco:
    def test_cria_pedido_novo(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"codigo": 10}, {"resumo": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._gravar_cabecalho_sync("srv", "bd", None, "2026-07-18", 5, "PF-1", 30, "Boleto", "João", "Transp X", None, "Obs", 0, 1)
        assert r["success"] and r["codigo"] == 10
        assert conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "insert into pedido (" in joined

    def test_pedido_existente_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._gravar_cabecalho_sync("srv", "bd", 10, "2026-07-18", 5, None, None, None, None, None, None, None, 0, 1)
        assert not r["success"] and "aberto" in r["message"].lower()

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._gravar_cabecalho_sync("srv", "bd", 999, "2026-07-18", 5, None, None, None, None, None, None, None, 0, 1)
        assert not r["success"]

    def test_fornecedor_nao_cadastrado_bloqueia_e_faz_rollback(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._gravar_cabecalho_sync("srv", "bd", None, "2026-07-18", 5, None, None, None, None, None, None, None, 0, 1)
        assert not r["success"] and "cadastrado" in r["message"].lower()
        assert conn.rolled

    def test_atualiza_pedido_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._gravar_cabecalho_sync("srv", "bd", 10, "2026-07-18", 5, None, None, None, None, None, None, None, 0, 1)
        assert r["success"] and r["codigo"] == 10 and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "update pedido set" in joined


class TestIncluirItemValidacoesSemBanco:
    def test_sem_produto(self):
        r = svc._incluir_item_sync("srv", "bd", 10, "", 1, 1, FISCAL_VAZIO)
        assert not r["success"] and "produto" in r["message"].lower()

    def test_qtd_invalida(self):
        r = svc._incluir_item_sync("srv", "bd", 10, "P1", 0, 1, FISCAL_VAZIO)
        assert not r["success"] and "quantidade" in r["message"].lower()

    def test_preco_negativo(self):
        r = svc._incluir_item_sync("srv", "bd", 10, "P1", 1, -1, FISCAL_VAZIO)
        assert not r["success"] and "preço" in r["message"].lower()


class TestIncluirItemComBanco:
    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 999, "P1", 1, 10.0, FISCAL_VAZIO)
        assert not r["success"]

    def test_pedido_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "P1", 1, 10.0, FISCAL_VAZIO)
        assert not r["success"] and "aberto" in r["message"].lower()

    def test_produto_nao_cadastrado_bloqueia_e_faz_rollback(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "XXX", 1, 10.0, FISCAL_VAZIO)
        assert not r["success"] and "cadastrado" in r["message"].lower()
        assert conn.rolled

    def test_inclui_item_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"SEQUENCIA_PEDIDO_ITENS": 5}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_item_sync("srv", "bd", 10, "P1", 2, 15.0, FISCAL_VAZIO)
        assert r["success"] and r["seq"] == 5 and conn.committed


class TestEditarItem:
    def test_qtd_invalida(self):
        r = svc._editar_item_sync("srv", "bd", 1, 0, 10.0, FISCAL_VAZIO)
        assert not r["success"]

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._editar_item_sync("srv", "bd", 1, 2, 10.0, FISCAL_VAZIO)
        assert not r["success"]

    def test_pedido_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._editar_item_sync("srv", "bd", 1, 2, 10.0, FISCAL_VAZIO)
        assert not r["success"] and "aberto" in r["message"].lower()

    def test_edita_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._editar_item_sync("srv", "bd", 1, 3, 12.5, FISCAL_VAZIO)
        assert r["success"] and conn.committed
        assert "update pedido_itens set" in cur.queries[-1][0].lower()


class TestExcluirItem:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert not r["success"]

    def test_pedido_nao_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10, "situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert not r["success"] and "aberto" in r["message"].lower()

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_item_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        assert "delete from pedido_itens" in cur.queries[-1][0].lower()


class TestAprovar:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._aprovar_sync("srv", "bd", 10, None)
        assert not r["success"]

    def test_rejeitado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._aprovar_sync("srv", "bd", 10, None)
        assert not r["success"] and "rejeitados" in r["message"].lower()

    def test_ja_aprovado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._aprovar_sync("srv", "bd", 10, None)
        assert not r["success"] and "já está aprovado" in r["message"].lower()

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._aprovar_sync("srv", "bd", 10, None)
        assert not r["success"] and "item" in r["message"].lower()

    def test_aprova_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, {"resumo": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._aprovar_sync("srv", "bd", 10, "João")
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "situacao='f'" in joined


class TestRejeitar:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._rejeitar_sync("srv", "bd", 10, None)
        assert not r["success"]

    def test_ja_rejeitado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._rejeitar_sync("srv", "bd", 10, None)
        assert not r["success"] and "já foi rejeitado" in r["message"].lower()

    def test_aprovado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._rejeitar_sync("srv", "bd", 10, None)
        assert not r["success"] and "reabra" in r["message"].lower()

    def test_rejeita_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"resumo": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._rejeitar_sync("srv", "bd", 10, None)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "situacao='c'" in joined


class TestReabrir:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd", 10, None)
        assert not r["success"]

    def test_rejeitado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd", 10, None)
        assert not r["success"] and "rejeitados" in r["message"].lower()

    def test_ja_aberto_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd", 10, None)
        assert not r["success"] and "já está aberto" in r["message"].lower()

    def test_reabre_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"resumo": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd", 10, None)
        assert r["success"] and conn.committed
        joined = " ".join(q for q, _ in cur.queries).lower()
        assert "situacao='a'" in joined
