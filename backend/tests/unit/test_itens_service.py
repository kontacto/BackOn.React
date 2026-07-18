"""Testes UNITÁRIOS de itens_service — inclusão/listagem de itens do Pedido,
com foco na gravação/leitura de data_inclusao_item/hora_inclusao_item e no
botão "Incluir Tx Serviço" do Pedido Bar."""
import services.itens_service as svc
from models.schemas import ItemSaveRequest, TaxaServicoRequest


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


def _item_req(**over):
    base = dict(servidor="srv", banco="bd", produto="P100", qtd=1, valor_unitario=None,
                complemento="", desconto=0, desconto_pct=0, acrescimo=0,
                usuario_codigo=-2, funcao=None, classe=1, plataforma="web")
    base.update(over)
    return ItemSaveRequest(**base)


PECA_ROW = {
    "codigo": "100", "descricao": "Produto Teste", "codigo_fab": "FAB100",
    "valor": 50.0, "uni": "UN", "custo_reposicao": 30.0,
    "controla_num_serie": False, "aceita_desconto": 1,
}


class TestBloqueiaAdicionarTaxaServicoManualmente:
    """Nunca pode haver 2 linhas de Taxa de Serviço (S002) no mesmo
    pedido — o fluxo genérico de adicionar item bloqueia o código
    reservado, só o botão dedicado (`_add_taxa_servico_sync`) pode
    incluir/atualizar essa linha."""

    def test_add_item_bloqueia_produto_s002(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(produto="S002"), 1)
        assert r["success"] is False
        assert "Tx Serviço" in r["message"]

    def test_add_item_bloqueia_produto_s002_minusculo(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(produto="s002"), 1)
        assert r["success"] is False
        assert "Tx Serviço" in r["message"]

    def test_add_item_outro_servico_continua_permitido(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(PECA_ROW), {"codauto": 1}, None, {"total": 50.0}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(produto="S010"), 1)
        assert r["success"] is True


class TestAddItemSincronizaTaxaServicoExistente:
    """Se o pedido já tem uma linha de Taxa de Serviço, incluir um novo item
    (produto ou serviço) recalcula e atualiza o valor dela automaticamente —
    pedido explícito do usuário, 2026-07-15."""

    def test_novo_item_atualiza_taxa_servico_existente(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, dict(PECA_ROW), {"codauto": 5},
            {"codauto": 900},  # já existe linha S002
            {"s": 150.0},      # subtotal recalculado (exclui S002) após o novo item
            {"total": 165.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(), 1)
        assert r["success"] is True
        update_params = next(
            p for q, p in cur.queries
            if q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=1")
        )
        assert update_params == (15.0, 15.0, 900)

    def test_novo_item_sem_taxa_servico_nao_gera_update_extra(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, dict(PECA_ROW), {"codauto": 5},
            None,  # nenhuma linha S002 existente
            {"total": 50.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(), 1)
        assert r["success"] is True
        assert not any(
            q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=1") for q, _ in cur.queries
        )


class TestUpdateItemTaxaServicoQtdFixa:
    """Taxa de Serviço (S002) só pode ter 1 unidade — editar a quantidade
    dessa linha pra qualquer outro valor é bloqueado."""

    def test_bloqueia_alterar_qtd_da_taxa_servico(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"produto": "S002"}])
        _patch(monkeypatch, cur)
        r = svc._update_item_sync(_item_req(qtd=2), 1, 900)
        assert r["success"] is False
        assert "1 unidade" in r["message"]

    def test_permite_manter_qtd_1_da_taxa_servico(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"produto": "S002"}, {"total": 55.0}],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._update_item_sync(_item_req(qtd=1, valor_unitario=10), 1, 900)
        assert r["success"] is True

    def test_outro_item_pode_ter_qtd_alterada_livremente(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"produto": "P100"}, {"total": 250.0}],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._update_item_sync(_item_req(qtd=5, valor_unitario=50), 1, 500)
        assert r["success"] is True


class TestEnsureHoraInclusaoItemCol:
    def test_add_item_dispara_migracao_idempotente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(PECA_ROW), {"codauto": 1}, None, {"total": 50.0}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(), 1)
        assert r["success"] is True
        joined = " ".join(q[0] for q in cur.queries)
        assert "IF NOT EXISTS" in joined and "hora_inclusao_item" in joined
        assert "ALTER TABLE pedido_venda_prod ADD hora_inclusao_item" in joined

    def test_list_itens_dispara_migracao_idempotente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        assert r["success"] is True
        joined = " ".join(q[0] for q in cur.queries)
        assert "ALTER TABLE pedido_venda_prod ADD hora_inclusao_item" in joined


class TestAddItemGravaHoraInclusao:
    def test_insert_grava_data_e_hora_inclusao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(PECA_ROW), {"codauto": 1}, None, {"total": 50.0}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_item_req(), 1)
        assert r["success"] is True
        insert_q = next(q for q, _ in cur.queries if q.startswith("INSERT INTO pedido_venda_prod"))
        assert "data_inclusao_item" in insert_q
        assert "hora_inclusao_item" in insert_q
        assert "CONVERT(NVARCHAR(8), GETDATE(), 108)" in insert_q


class TestListItensRetornaDataHoraInclusao:
    def test_mapeia_data_hora_inclusao_no_item(self, monkeypatch):
        from datetime import date
        row = {
            "codauto": 1, "produto": "100", "qtd_pedida": 2, "p_venda": 45.0, "p_normal": 50.0,
            "desconto": 5.0, "acrescimo": 0, "descricao_produto": "", "unidade_pedido": "UN",
            "data_inclusao_item": date(2026, 7, 15), "hora_inclusao_item": "14:30:05",
            "peca_desc": "Produto Teste", "peca_fab": "FAB100", "serv_desc": None,
        }
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[row]])
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        assert r["success"] is True
        item = r["items"][0]
        assert item["data_inclusao"] == "2026-07-15"
        assert item["hora_inclusao"] == "14:30:05"

    def test_item_sem_hora_inclusao_grava_string_vazia(self, monkeypatch):
        row = {
            "codauto": 1, "produto": "100", "qtd_pedida": 2, "p_venda": 45.0, "p_normal": 50.0,
            "desconto": 5.0, "acrescimo": 0, "descricao_produto": "", "unidade_pedido": "UN",
            "data_inclusao_item": None, "hora_inclusao_item": None,
            "peca_desc": "Produto Teste", "peca_fab": "FAB100", "serv_desc": None,
        }
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[row]])
        _patch(monkeypatch, cur)
        r = svc._list_itens_sync("srv", "bd", 1)
        item = r["items"][0]
        assert item["data_inclusao"] is None
        assert item["hora_inclusao"] == ""

    def test_taxa_de_servico_sempre_ordenada_por_ultimo(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_itens_sync("srv", "bd", 1)
        select_q, params = next(
            (q, p) for q, p in cur.queries if q.startswith("SELECT i.codauto")
        )
        assert "ORDER BY CASE WHEN i.produto=%s THEN 1 ELSE 0 END, i.codauto" in select_q
        assert params[-1] == svc.TAXA_SERVICO_CODIGO


def _taxa_req(**over):
    base = dict(servidor="srv", banco="bd", usuario_codigo=-2, classe=1, plataforma="web")
    base.update(over)
    return TaxaServicoRequest(**base)


ITEM_ROW = {
    "produto": "P001", "qtd_pedida": 2.0, "p_venda": 10.0, "p_normal": 10.0,
    "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 5.0, "descricao_produto": "", "unidade_pedido": "UN",
}


class TestDeleteItemDevolveParaPedidoOriginal:
    """Excluir um item de um pedido FILHO (criado por "Distribuir"/Dividir
    Pedido) devolve o item pro pedido original em vez de só descartar —
    pedido explícito do usuário, 2026-07-17."""

    def test_devolve_somando_em_linha_existente_do_mesmo_produto(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"},          # _check_pedido_aberto(pedido filho)
                dict(ITEM_ROW),              # item sendo excluído
                {"num_ped_cliente": "77"},   # referencia do pedido filho
                {"situacao": "A"},           # _check_pedido_aberto(original=77)
                {"codauto": 900, "qtd_pedida": 3.0},  # linha já existente do mesmo produto no original
                None,                         # sincroniza_taxa(pedido filho) -> sem S002
                {"total": 0.0},              # recalc_total(pedido filho)
                None,                         # sincroniza_taxa(original) -> sem S002
                {"total": 50.0},             # recalc_total(original)
            ],
            rowcount=1,
        )
        conn = _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 501, 20232)
        assert r["success"] is True
        assert r["devolvido_para"] == 77
        assert conn.committed is True
        soma_q, soma_p = next((q, p) for q, p in cur.queries if q.startswith("UPDATE pedido_venda_prod SET qtd_pedida="))
        assert soma_p == (5.0, 900)  # 3.0 (já no original) + 2.0 (devolvido)
        assert not any("INSERT INTO pedido_venda_prod" in q for q, _ in cur.queries)

    def test_devolve_criando_nova_linha_quando_produto_nao_existe_no_original(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(ITEM_ROW), {"num_ped_cliente": "77"}, {"situacao": "A"},
                None,  # nenhuma linha existente do produto no original
                None, {"total": 0.0}, None, {"total": 20.0},
            ],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 501, 20232)
        assert r["success"] is True
        assert r["devolvido_para"] == 77
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.startswith("INSERT INTO pedido_venda_prod"))
        assert insert_p[:3] == (77, "P001", 2.0)

    def test_nao_devolve_taxa_de_servico(self, monkeypatch):
        item_taxa = {**ITEM_ROW, "produto": "S002"}
        cur = FakeCursor(
            one=[{"situacao": "A"}, item_taxa, None, {"total": 0.0}],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 501, 20232)
        assert r["success"] is True
        assert r["devolvido_para"] is None
        assert not any("INSERT INTO pedido_venda_prod" in q or q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=") for q, _ in cur.queries)

    def test_nao_devolve_quando_pedido_nao_e_filho(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, dict(ITEM_ROW), {"num_ped_cliente": None}, None, {"total": 0.0}],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 1, 1)
        assert r["success"] is True
        assert r["devolvido_para"] is None

    def test_nao_devolve_quando_original_nao_esta_mais_aberto(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(ITEM_ROW), {"num_ped_cliente": "77"},
                {"situacao": "PG"},  # original já foi faturado — não devolve
                None, {"total": 0.0},
            ],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 501, 20232)
        assert r["success"] is True
        assert r["devolvido_para"] is None
        assert not any("INSERT INTO pedido_venda_prod" in q or q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=") for q, _ in cur.queries)

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 999, 1)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_bloqueia_pedido_nao_aberto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 1, 1)
        assert r["success"] is False
        assert "não pode ser alterado" in r["message"]

    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 1, 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestAddTaxaServico:
    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_pedido_nao_aberto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is False and "não pode ser alterado" in r["message"]

    def test_servico_s002_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is False and "S002" in r["message"]

    def test_bloqueia_quando_pedido_sem_itens(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"descricao": "Taxa de Serviço"}, {"c": 0}])
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is False
        assert "item" in r["message"].lower()

    def test_primeira_inclusao_insere_nova_linha(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"descricao": "Taxa de Serviço"}, {"c": 1}, {"s": 50.0}, {"codauto": 800}, {"total": 55.0}],
            many=[[]],  # nenhuma linha S002 existente
        )
        conn = _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is True
        assert r["valor"] == 5.0
        assert r["atualizado"] is False
        assert conn.committed is True
        insert_q = next(q for q, _ in cur.queries if q.startswith("INSERT INTO pedido_venda_prod"))
        params = next(p for q, p in cur.queries if q.startswith("INSERT INTO pedido_venda_prod"))
        assert svc.TAXA_SERVICO_CODIGO in params
        assert not any(q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=1") for q, _ in cur.queries)

    def test_ja_incluido_atualiza_linha_existente_sem_pedir_confirmacao(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"descricao": "Taxa de Serviço"}, {"c": 1}, {"s": 100.0}, {"total": 110.0}],
            many=[[{"codauto": 900}]],  # já existe uma linha S002
        )
        conn = _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is True
        assert r["valor"] == 10.0
        assert r["atualizado"] is True
        assert r["codauto"] == 900
        assert conn.committed is True
        update_params = next(
            p for q, p in cur.queries if q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=1")
        )
        assert update_params == (10.0, 10.0, 900)
        assert not any(q.startswith("INSERT INTO pedido_venda_prod") for q, _ in cur.queries)

    def test_subtotal_exclui_a_propria_taxa_ja_incluida(self, monkeypatch):
        # 2º clique não deve compor 10% em cima do valor de taxa já lançado —
        # a query de subtotal já filtra produto<>S002, então isso é
        # verificado indiretamente: valor recalculado bate com o subtotal
        # "puro" retornado pelo fake, não um valor maior.
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"descricao": "Taxa de Serviço"}, {"c": 1}, {"s": 100.0}, {"total": 110.0}],
            many=[[{"codauto": 900}]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["valor"] == 10.0
        subtotal_q = next(q for q, _ in cur.queries if "SUM(qtd_pedida*p_venda)" in q)
        assert "produto<>%s" in subtotal_q

    def test_valor_e_10_por_cento_do_subtotal_arredondado(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"descricao": "Taxa de Serviço"}, {"c": 1}, {"s": 33.333}, {"codauto": 1}, {"total": 36.67}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["valor"] == 3.33

    def test_multiplas_linhas_existentes_sao_consolidadas(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"descricao": "Taxa de Serviço"}, {"c": 1}, {"s": 100.0}, {"total": 110.0}],
            many=[[{"codauto": 900}, {"codauto": 901}]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_taxa_servico_sync(_taxa_req(), 1)
        assert r["success"] is True
        assert r["codauto"] == 900
        delete_q = next(q for q, _ in cur.queries if q.startswith("DELETE FROM pedido_venda_prod WHERE codauto IN"))
        assert "901" in delete_q
