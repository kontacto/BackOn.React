"""Testes UNITÁRIOS de Pedido Completo (Fase A — cabeçalho, itens/kits, Fechar/Cancelar)."""
from datetime import date

import services.pedido_completo_service as svc
from models.schemas import FecharRequest, ItemSaveRequest, PedidoCompletoSaveRequest


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
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


def _pedido_req(**over):
    base = dict(servidor="srv", banco="bd", cliente=10, vendedor=20, forma_pag="001",
                validade=None, previsao_entrega=None, local_entrega="", infoentrega="",
                num_ped_cliente="", obs="", area_atuacao=None,
                usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return PedidoCompletoSaveRequest(**base)


def _item_req(**over):
    base = dict(servidor="srv", banco="bd", produto="P100", qtd=1, valor_unitario=None,
                complemento="", desconto=0, desconto_pct=0, acrescimo=0,
                usuario_codigo=-2, funcao=None, classe=1, plataforma="web")
    base.update(over)
    return ItemSaveRequest(**base)


def _fechar_req(**over):
    base = dict(servidor="srv", banco="bd", classe=1, master=False, usuario_alteracao=1, plataforma="web")
    base.update(over)
    return FecharRequest(**base)


PECA_ROW = {
    "codigo": "100", "descricao": "Produto Teste", "codigo_fab": "FAB100",
    "valor": 50.0, "uni": "UN", "custo_reposicao": 30.0,
    "controla_num_serie": False, "aceita_desconto": 1,
}


class TestGetPedidoCompleto:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_completo_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_encontrado_mapeia_campos_novos(self, monkeypatch):
        row = {
            "pedido": 1, "cliente": 10, "data": date(2026, 7, 14), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "obs", "situacao": "A",
            "total": 150.0, "NOME_CLIENTE": "Fulano", "TELEFONE_CLIENTE": "119999",
            "area_atuacao": 1, "forma_pag": "001", "local_entrega": "Rua X",
            "previsao_entrega": date(2026, 7, 20), "num_ped_cliente": "PC-1",
            "infoentrega": "Portão azul", "cliente_nome": "Fulano", "cliente_cgc": "123",
            "vendedor_nome": "Vendedor", "area_descricao": "Área", "forma_pag_descricao": "Dinheiro",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_completo_sync("srv", "bd", 1)
        assert r["success"] is True
        p = r["pedido"]
        assert p["forma_pag"] == "001" and p["forma_pag_descricao"] == "Dinheiro"
        assert p["local_entrega"] == "Rua X" and p["infoentrega"] == "Portão azul"
        assert p["num_ped_cliente"] == "PC-1" and p["previsao_entrega"] == "2026-07-20"
        assert p["editavel"] is True


class TestSavePedidoCompleto:
    def test_criar_cliente_inativo_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "C"}])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(), None)
        assert r["success"] is False and "situação" in r["message"].lower()

    def test_criar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "Cliente Teste", "tel": "1199999999"},
            {"pedido": 777},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(), None)
        assert r["success"] is True and r["pedido"] == 777
        insert_q = cur.queries[-1][0]
        assert "forma_pag" in insert_q and "previsao_entrega" in insert_q and "num_ped_cliente" in insert_q

    def test_atualizar_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(), 555)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_atualizar_cancelado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(), 555)
        assert r["success"] is False and "não pode ser alterado" in r["message"]

    def test_atualizar_aberto_permite_tudo(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"nome": "X", "tel": "Y"}], rowcount=1)
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(cliente=99), 555)
        assert r["success"] is True
        update_q = cur.queries[-1][0]
        assert "cliente=%s" in update_q and "local_entrega=%s" in update_q

    def test_atualizar_fechado_so_vendedor_forma_pag(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"nome": "X", "tel": "Y"}], rowcount=1)
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(), 555)
        assert r["success"] is True
        update_q = cur.queries[-1][0]
        assert "vendedor=%s, forma_pag=%s" in update_q
        assert "cliente=%s" not in update_q


class TestAddItemCompleto:
    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(), 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_pedido_fechado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(), 1)
        assert r["success"] is False and "não pode ser alterado" in r["message"]

    def test_produto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None, None, None, None, None])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="X404"), 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_quantidade_invalida(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(PECA_ROW)])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(qtd=0), 1)
        assert r["success"] is False and "quantidade" in r["message"].lower()

    def test_nao_aceita_desconto_bloqueia(self, monkeypatch):
        row = dict(PECA_ROW, aceita_desconto=0)
        cur = FakeCursor(one=[{"situacao": "A"}, row], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(desconto=5), 1)
        assert r["success"] is False and "desconto" in r["message"].lower()

    def test_item_simples_sucesso(self, monkeypatch):
        cur = FakeCursor(
            # None extra = checagem de Taxa de Serviço existente (sincroniza_taxa_servico_apos_alteracao) — não há.
            one=[{"situacao": "A"}, dict(PECA_ROW), {"codauto": 501}, None, {"total": 250.0}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(qtd=2), 1)
        assert r["success"] is True and r["kit"] is False
        assert r["codautos"] == [501] and r["total"] == 250.0

    def test_kit_expande_em_varias_linhas(self, monkeypatch):
        principal = dict(PECA_ROW, codigo="KIT1", codigo_fab="KITFAB")
        comp1 = {"vinculado": "P200", "qtd": 2, "valor_no_kit": 15.0, "descricao_no_kit": "Componente A"}
        comp2 = {"vinculado": "P300", "qtd": 1, "valor_no_kit": None, "descricao_no_kit": None}
        sub1 = dict(PECA_ROW, codigo="P200", descricao="Peça 200", valor=10.0, custo_reposicao=5.0)
        sub2 = dict(PECA_ROW, codigo="P300", descricao="Peça 300", valor=20.0, custo_reposicao=8.0)
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, principal,
                sub1, {"codauto": 601},
                sub2, {"codauto": 602},
                # None extra = checagem de Taxa de Serviço existente (sincroniza_taxa_servico_apos_alteracao) — não há.
                None, {"total": 999.0},
            ],
            many=[[comp1, comp2]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="KIT1", qtd=3), 1)
        assert r["success"] is True and r["kit"] is True
        assert r["codautos"] == [601, 602] and r["total"] == 999.0
        insert_queries = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod")]
        assert len(insert_queries) == 2
        assert "Produto_composto" in insert_queries[0]

    def test_kit_componente_nao_encontrado_faz_rollback(self, monkeypatch):
        principal = dict(PECA_ROW, codigo="KIT1")
        comp1 = {"vinculado": "P404", "qtd": 1, "valor_no_kit": None, "descricao_no_kit": None}
        cur = FakeCursor(
            one=[{"situacao": "A"}, principal, None, None, None, None, None],
            many=[[comp1]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="KIT1"), 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()
        assert conn.rolled is True


class TestFecharPedidoCompleto:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._fechar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is False

    def test_situacao_invalida(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._fechar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is False and "não pode ser fechado" in r["message"]

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._fechar_pedido_completo_sync(_fechar_req(master=False, classe=1), 1)
        assert r["success"] is False and "permissão" in r["message"].lower()

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._fechar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is False and "pelo menos um" in r["message"].lower()

    def test_sucesso_baixa_estoque_e_fecha(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"ok": 1}],
            many=[[{"produto": "P1", "qtd_pedida": 2.0}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is True and r["situacao"] == "F"
        assert conn.committed is True
        assert any("SET situacao='F'" in q for q, _ in cur.queries)


class TestCancelarPedidoCompleto:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is False

    def test_situacao_invalida(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is False and "não pode ser cancelado" in r["message"]

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._cancelar_pedido_completo_sync(_fechar_req(master=False, classe=1), 1)
        assert r["success"] is False and "permissão" in r["message"].lower()

    def test_cancela_de_aberto_sem_estorno(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is True and r["situacao"] == "C"
        assert conn.committed is True
        assert not any("pecas" in q.lower() for q, _ in cur.queries)

    def test_cancela_de_fechado_estorna_estoque(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "F"}, {"ok": 1}],
            many=[[{"produto": "P1", "qtd_pedida": 2.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_completo_sync(_fechar_req(master=True), 1)
        assert r["success"] is True and r["situacao"] == "C"
        pecas_updates = [(q, p) for q, p in cur.queries if q.strip().upper().startswith("UPDATE PECAS")]
        assert len(pecas_updates) == 1
        assert pecas_updates[0][1] == (-2.0, -2.0, "P1")
