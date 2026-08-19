"""Testes UNITÁRIOS de Pedido Completo (Fase A — cabeçalho, itens/kits, Fechar/Cancelar/
Faturar/Reabrir/Dividir/Entregue/Tipo)."""
import asyncio
from datetime import date

import services.pedido_completo_service as svc
from models.schemas import (
    FecharRequest, ItemSaveRequest, PedidoCompletoSaveRequest,
    DividirPedidoRequest, PedidoEntregueRequest,
)


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

    def test_mapeia_tipo_hora_entrega_e_pedido_entregue(self, monkeypatch):
        """Campos trazidos do Pedido Bar 2026-07-20 (Tipo/hora_entrega/
        Pedido Entregue) — mesma tabela, mesmo mapeamento."""
        row = {
            "pedido": 1, "cliente": 10, "data": date(2026, 7, 14), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A",
            "total": 0.0, "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "forma_pag": "", "local_entrega": "", "previsao_entrega": None, "num_ped_cliente": "",
            "infoentrega": "", "hora_entrega": "14:30:00", "pedido_entregue": 1, "tipo": 3,
            "tipo_descricao": "ENTREGA",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_completo_sync("srv", "bd", 1)
        p = r["pedido"]
        assert p["hora_entrega"] == "14:30:00"
        assert p["pedido_entregue"] is True
        assert p["tipo"] == 3 and p["tipo_descricao"] == "ENTREGA"


class TestSavePedidoCompleto:
    def test_criar_cliente_inativo_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"STATUS_CLIENTE": "C"}])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(), None)
        assert r["success"] is False and "situação" in r["message"].lower()

    def test_criar_funcionario_sem_area_permitida_bloqueia(self, monkeypatch):
        """Réplica de `VerificaAreaAtuacao` — ver PENDENCIAS.md > "MDI
        Principal (VB6)"."""
        cur = FakeCursor(
            one=[{"STATUS_CLIENTE": "A"}, {"descricao": "Oficina"}],
            many=[[{"area": 1}, {"area": 2}]],
        )
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(usuario_alteracao=5, area_atuacao=9), None)
        assert r["success"] is False
        assert "Oficina" in r["message"]

    def test_criar_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"CONTROLA_ABERTURA_DIA": True},
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

    def test_cliente_reservado_sobrescreve_tipo_pedido(self, monkeypatch):
        """Mesma regra do Pedido Bar (`_resolve_tipo_pedido`, pedido_common.py)
        — cliente MESA/COMANDA/BALCÃO sempre grava o próprio tipo
        (cliente_forn), ignorando o que foi selecionado no combobox "Tipo"
        da tela. Trazida ao Pedido Geral 2026-07-20."""
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"CONTROLA_ABERTURA_DIA": True},
            {"nome": "MESA 5", "fantasia": "MESA 5", "cliente_forn": 7, "tel": ""},
            {"pedido": 777},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_completo_sync(_pedido_req(tipo=2), None)
        assert r["success"] is True
        insert_params = cur.queries[-1][1]
        assert insert_params[13] == 7  # tipo_final sobrescrito pro tipo do cliente, não o `tipo=2` pedido

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


class TestAddItemCompletoNumSerie:
    """Fase B — `PECAS.controla_num_serie` (padrão `CmbNDS`/`FrmNDS`), ver
    PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: número de série"."""

    def test_sem_cod_num_serie_bloqueia(self, monkeypatch):
        row = dict(PECA_ROW, controla_num_serie=True)
        cur = FakeCursor(one=[{"situacao": "A"}, row])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(), 1)
        assert r["success"] is False and "número de série" in r["message"].lower()

    def test_num_serie_invalido_ou_indisponivel_bloqueia(self, monkeypatch):
        row = dict(PECA_ROW, controla_num_serie=True)
        cur = FakeCursor(one=[{"situacao": "A"}, row, None])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(cod_num_serie=77), 1)
        assert r["success"] is False and "não está mais disponível" in r["message"]

    def test_sucesso_forca_qtd_1_e_grava_fk(self, monkeypatch):
        row = dict(PECA_ROW, controla_num_serie=True)
        cur = FakeCursor(
            one=[{"situacao": "A"}, row, {"codigo": 77}, {"codauto": 501}, None, {"total": 100.0}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        # qtd=5 solicitada, mas controla_num_serie sempre força 1 (mesma
        # regra do `Campo(4) = 1` em `Campo_LostFocus` do legado).
        r = svc._add_item_completo_sync(_item_req(qtd=5, cod_num_serie=77), 1)
        assert r["success"] is True and r["codautos"] == [501]
        insert_q, insert_p = next(
            (q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod")
        )
        assert "cod_num_serie" in insert_q
        assert insert_p[2] == 1  # qtd_pedida forçada pra 1
        assert insert_p[10] == 77  # cod_num_serie (índice mudou com os campos de m² acrescentados depois dele)


PECA_ROW_M2 = dict(PECA_ROW, uni="M2")

CONFIG_M2_ROW = {
    "m2_area_minima_padrao": True,
    "m2_area_minima_modelado": False,
    "m2_area_minima_engenharia": False,
    "m2_area_minima_modelado_engenharia": False,
    "m2_area_minima_comum_lapidacao": False,
    "m2_area_minima_comum_sem_lapidacao": False,
    "metro_quadrado_minima_metragem": 0.25,
    "vidro_controla_cabeca_chapa": False,
}


class TestAddItemCompletoM2:
    """Fase B — módulo Metro Quadrado (`pecas.uni` M2/ML/M3 +
    `controle_configuracao.metro_quadrado`), ver PENDENCIAS.md >
    "Transações" > "Pedido Geral — Metro Quadrado"."""

    def test_sem_tipo_preco_ou_dimensoes_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(PECA_ROW_M2), {"metro_quadrado": True}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(), 1)
        assert r["success"] is False and "dimens" in r["message"].lower()

    def test_tipo_preco_invalido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(PECA_ROW_M2), {"metro_quadrado": True}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(tipo_preco_m2=9, comprimento=1, largura=1), 1)
        assert r["success"] is False and "inválido" in r["message"].lower()

    def test_preco_do_tipo_nao_cadastrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, dict(PECA_ROW_M2), {"metro_quadrado": True}, {"preco": 0}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(tipo_preco_m2=1, comprimento=1, largura=1), 1)
        assert r["success"] is False and "não está cadastrado" in r["message"]

    def test_sucesso_calcula_area_e_dobra_no_preco(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(PECA_ROW_M2), {"metro_quadrado": True}, {"preco": 50.0},
                dict(CONFIG_M2_ROW), {"codauto": 501}, None, {"total": 100.0},
            ],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        # comprimento=2, largura=1 -> área = 2 (dimensões "redondas", sem
        # resto que dispare o arredondamento de ArredondaPBox).
        r = svc._add_item_completo_sync(_item_req(tipo_preco_m2=0, comprimento=2, largura=1), 1)
        assert r["success"] is True and r["codautos"] == [501]
        insert_q, insert_p = next(
            (q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod")
        )
        assert "comprimento" in insert_q and "area_venda" in insert_q
        # p_venda/p_normal = preço do tipo (50) x área (2) = 100 — decisão
        # de dobrar a área dentro do preço unitário, ver PENDENCIAS.md.
        assert insert_p[3] == 100.0 and insert_p[4] == 100.0
        assert insert_p[11] == 2.0 and insert_p[12] == 1.0 and insert_p[13] == 2.0  # comprimento/largura/area_venda

    def test_area_minima_aplicada_quando_flag_do_tipo_ativa(self, monkeypatch):
        cfg = dict(CONFIG_M2_ROW, metro_quadrado_minima_metragem=5.0)  # piso alto
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(PECA_ROW_M2), {"metro_quadrado": True}, {"preco": 10.0},
                cfg, {"codauto": 501}, None, {"total": 50.0},
            ],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        # área real = 2x1 = 2, menor que o piso 5 — tipo 0 (Padrão) tem
        # m2_area_minima_padrao=True em CONFIG_M2_ROW, então o piso se aplica.
        r = svc._add_item_completo_sync(_item_req(tipo_preco_m2=0, comprimento=2, largura=1), 1)
        assert r["success"] is True
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod"))
        assert insert_p[3] == 50.0  # 10 (preço) x 5.0 (piso), não 10x2=20

    def test_modulo_desligado_usa_preco_normal_sem_area(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(PECA_ROW_M2), {"metro_quadrado": False},
                {"codauto": 501}, None, {"total": 50.0},
            ],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(valor_unitario=50.0), 1)
        assert r["success"] is True
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod"))
        assert insert_p[3] == 50.0  # preço cheio, sem multiplicar por área
        assert insert_p[11] is None  # comprimento não gravado — produto não passou pelo caminho m²

    def test_produto_nao_m2_ignora_campos_dimensao(self, monkeypatch):
        # unidade "UN" (PECA_ROW original) — mesmo com módulo ligado, não
        # entra no caminho m² (réplica do `If uni = M2/ML/M3` do legado).
        cur = FakeCursor(
            one=[{"situacao": "A"}, dict(PECA_ROW), {"codauto": 501}, None, {"total": 50.0}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(valor_unitario=50.0), 1)
        assert r["success"] is True
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod"))
        assert insert_p[3] == 50.0 and insert_p[11] is None


class TestUpdateItemCompletoM2:
    """`_update_item_completo_sync` reconhece item m² já gravado
    (`comprimento`/`largura` não-nulos na linha) e recalcula a área ao
    editar — item normal segue exatamente o comportamento antigo de
    `itens_service.update_item`. Ver PENDENCIAS.md > "Transações" >
    "Pedido Geral — Metro Quadrado"."""

    def test_item_normal_atualiza_como_antes(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"produto": "P100", "comprimento": None, "largura": None}, {"total": 80.0}],
        )
        _patch(monkeypatch, cur)
        r = svc._update_item_completo_sync(_item_req(qtd=2, valor_unitario=40.0), 1, 501)
        assert r["success"] is True and r["total"] == 80.0
        update_q, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod"))
        assert "comprimento=%s" in update_q
        assert update_p[1] == 40.0  # p_normal = valor_unitario, sem recálculo de área

    def test_item_m2_sem_tipo_ou_dimensoes_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"produto": "P100", "comprimento": 1.0, "largura": 1.0}],
        )
        _patch(monkeypatch, cur)
        r = svc._update_item_completo_sync(_item_req(), 1, 501)
        assert r["success"] is False and "dimens" in r["message"].lower()

    def test_item_m2_recalcula_area_ao_editar(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, {"produto": "P100", "comprimento": 1.0, "largura": 1.0},
                {"preco": 50.0}, {"controla_num_serie": False}, dict(CONFIG_M2_ROW),
                {"total": 100.0},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._update_item_completo_sync(_item_req(tipo_preco_m2=0, comprimento=2, largura=1), 1, 501)
        assert r["success"] is True and r["total"] == 100.0
        update_p = next(p for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod"))
        # preço do tipo (50) x área recalculada (2x1=2) = 100
        assert update_p[1] == 100.0

    def test_item_nao_encontrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._update_item_completo_sync(_item_req(), 1, 999)
        assert r["success"] is False and "não encontrado" in r["message"].lower()


class TestListItensCompletoEnriquecido:
    """`list_itens_completo` reaproveita `itens_service._list_itens_sync`
    (mockado aqui) e só acrescenta `num_serie` — não duplica a query base."""

    def test_sem_itens_nao_chama_enriquecimento(self, monkeypatch):
        monkeypatch.setattr(svc, "_list_itens_bar_shared", lambda *a, **k: {"success": True, "items": []})
        called = {"n": 0}
        def _boom(*a, **k):
            called["n"] += 1
            raise AssertionError("não deveria abrir conexão sem itens")
        monkeypatch.setattr(svc, "_open_conn", _boom)
        r = svc._list_itens_completo_sync("srv", "bd", 1)
        assert r["success"] is True and r["items"] == []
        assert called["n"] == 0

    def test_enriquece_item_com_num_serie(self, monkeypatch):
        base = {"success": True, "items": [{"codauto": 501, "produto": "100"}, {"codauto": 502, "produto": "200"}]}
        monkeypatch.setattr(svc, "_list_itens_bar_shared", lambda *a, **k: base)
        cur = FakeCursor(many=[[{"codauto": 501, "num_serie": "NS-0001"}]])
        _patch(monkeypatch, cur)
        r = svc._list_itens_completo_sync("srv", "bd", 1)
        assert r["success"] is True
        by_codauto = {it["codauto"]: it for it in r["items"]}
        assert by_codauto[501]["num_serie"] == "NS-0001"
        assert "num_serie" not in by_codauto[502]


class TestAddItemCompletoClinica:
    """Fase B — módulo Clínica: item de Serviço vira N linhas agendáveis
    (qtd_pedida=1 cada) ao incluir, quando o módulo está ativo. Ver
    PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
    (Agendamento)"."""

    SERVICO_ROW = {"codigo": "S100", "descricao": "Consulta", "valor": 80.0}

    def test_clinica_ativa_desdobra_em_n_linhas(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(self.SERVICO_ROW), {"servicos": 1}, {"CLINICA": 1},
                {"codauto": 501}, {"codauto": 502}, {"codauto": 503},
                # None extra = checagem de Taxa de Serviço existente (sincroniza_taxa_servico_apos_alteracao) — não há.
                None, {"total": 240.0},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="S100", qtd=3), 1)
        assert r["success"] is True
        assert r["clinica_split"] is True and r["kit"] is False
        assert r["codautos"] == [501, 502, 503]
        insert_calls = [(q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO pedido_venda_prod")]
        assert len(insert_calls) == 3
        for query, _ in insert_calls:
            # qtd_pedida vai como literal "1" na própria query (não é parâmetro
            # bindado) — mesma linha em todas as N inserções.
            assert "(%s,%s,1,%s" in query

    def test_clinica_desligada_nao_desdobra(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(self.SERVICO_ROW), {"servicos": 1}, {"CLINICA": 0},
                {"codauto": 501}, None, {"total": 80.0},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="S100", qtd=3), 1)
        assert r["success"] is True and r["clinica_split"] is False
        assert r["codautos"] == [501]

    def test_assistencia_ativa_desdobra_em_n_linhas(self, monkeypatch):
        """Módulo Assistência liga o MESMO comportamento de desdobramento
        que Clínica — mesma tela/fluxo, user-directed 2026-07-28 ("é só
        chamar a tela"). Ver `_modulo_agenda_ativo` (pedido_common.py)."""
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, dict(self.SERVICO_ROW), {"servicos": 1},
                {"CLINICA": 0, "Assistencia": 1},
                {"codauto": 501}, {"codauto": 502}, {"codauto": 503},
                None, {"total": 240.0},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="S100", qtd=3), 1)
        assert r["success"] is True
        assert r["clinica_split"] is True and r["kit"] is False
        assert r["codautos"] == [501, 502, 503]

    def test_quantidade_fracionaria_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, dict(self.SERVICO_ROW), {"servicos": 1}, {"CLINICA": 1}])
        _patch(monkeypatch, cur)
        r = svc._add_item_completo_sync(_item_req(produto="S100", qtd=2.5), 1)
        assert r["success"] is False and "inteiro" in r["message"].lower()


class TestListItensCompletoEnriquecidoAgendamento:
    """Enriquecimento com dados de agendamento (Fase B — módulo Clínica) —
    mesmo padrão de `num_serie`, sem duplicar a query base."""

    def test_enriquece_item_com_agendamento(self, monkeypatch):
        base = {"success": True, "items": [{"codauto": 501, "produto": "S100"}, {"codauto": 502, "produto": "S100"}]}
        monkeypatch.setattr(svc, "_list_itens_bar_shared", lambda *a, **k: base)
        cur = FakeCursor(many=[
            [],  # num_serie — nenhum
            [],  # dimensão m² — nenhum
            [{
                "codauto": 501, "codagenda": 900, "data": date(2026, 8, 1), "hora_ini": "14:00:00",
                "situacao_atendimento": "Confirmado", "profissional": "MARIA", "funcionario": 10,
            }],
        ])
        _patch(monkeypatch, cur)
        r = svc._list_itens_completo_sync("srv", "bd", 1)
        assert r["success"] is True
        by_codauto = {it["codauto"]: it for it in r["items"]}
        assert by_codauto[501]["agendamento"]["data"] == "2026-08-01"
        assert by_codauto[501]["agendamento"]["hora_ini"] == "14:00"
        assert by_codauto[501]["agendamento"]["profissional"] == "MARIA"
        # Regressão: código do funcionário (não só o nome) — usado pra levar
        # o usuário da tela do Pedido pra Agenda daquele profissional/data
        # (user-directed 2026-07-28).
        assert by_codauto[501]["agendamento"]["funcionario"] == 10
        assert "agendamento" not in by_codauto[502]


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
    """Cancelar/Faturar/Reabrir/Dividir do Pedido Completo NÃO duplicam a
    lógica do Pedido Bar — `pedido_completo_service` reaproveita
    literalmente as mesmas funções de `pedidos_service` (mesma tabela
    `pedido_venda`), só passando `tela="PEDIDO_COMP"` (`acao="SITUACAO"`
    pro Cancelar especificamente, ver docstring de
    `pedidos_service._cancelar_pedido_sync`). A regra de negócio em si já
    está coberta pelos testes de `test_pedidos_service.py`
    (`TestCancelarPedido`/`TestFaturarPedido`/`TestReabrirPedido`/
    `TestDividirPedido`) — aqui só confirmamos que a delegação passa os
    parâmetros certos, sem reabrir toda a bateria de cenários de novo."""

    def test_cancelar_delega_com_tela_pedido_comp_e_acao_situacao(self, monkeypatch):
        chamada = {}

        async def fake_cancelar(req, pedido, tela, acao):
            chamada["args"] = (req, pedido, tela, acao)
            return {"success": True, "situacao": "C"}

        monkeypatch.setattr(svc, "_cancelar_pedido_bar_shared", fake_cancelar)
        req = _fechar_req(master=True)
        r = asyncio.run(svc.cancelar_pedido_completo(req, 1))
        assert r["success"] is True and r["situacao"] == "C"
        assert chamada["args"] == (req, 1, "PEDIDO_COMP", "SITUACAO")

    def test_faturar_delega_com_tela_pedido_comp_e_exige_fechado(self, monkeypatch):
        """Diferença de regra confirmada pelo usuário, 2026-07-20: diferente
        do Pedido Bar, o Pedido Geral só pode faturar pedido já Fechado —
        `exigir_fechado=True` precisa ser repassado pra função compartilhada."""
        chamada = {}

        async def fake_faturar(req, pedido, tela, exigir_fechado=False):
            chamada["args"] = (req, pedido, tela, exigir_fechado)
            return {"success": True, "situacao": "PG"}

        monkeypatch.setattr(svc, "_faturar_pedido_bar_shared", fake_faturar)
        req = _fechar_req(master=True)
        r = asyncio.run(svc.faturar_pedido_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "PEDIDO_COMP", True)

    def test_reabrir_delega_com_tela_pedido_comp(self, monkeypatch):
        chamada = {}

        async def fake_reabrir(req, pedido, tela):
            chamada["args"] = (req, pedido, tela)
            return {"success": True, "situacao": "A"}

        monkeypatch.setattr(svc, "_reabrir_pedido_bar_shared", fake_reabrir)
        req = _fechar_req(master=True)
        r = asyncio.run(svc.reabrir_pedido_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "PEDIDO_COMP")

    def test_dividir_delega_com_tela_pedido_comp(self, monkeypatch):
        chamada = {}

        async def fake_dividir(req, pedido, tela):
            chamada["args"] = (req, pedido, tela)
            return {"success": True, "novos_pedidos": [2]}

        monkeypatch.setattr(svc, "_dividir_pedido_bar_shared", fake_dividir)
        req = DividirPedidoRequest(
            servidor="srv", banco="bd", grupos=[], classe=1, master=True,
            usuario_alteracao=1, plataforma="web",
        )
        r = asyncio.run(svc.dividir_pedido_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1, "PEDIDO_COMP")

    def test_entregue_delega_sem_parametros_extra(self, monkeypatch):
        chamada = {}

        async def fake_entregue(req, pedido):
            chamada["args"] = (req, pedido)
            return {"success": True, "entregue": True}

        monkeypatch.setattr(svc, "_toggle_entregue_bar_shared", fake_entregue)
        req = PedidoEntregueRequest(servidor="srv", banco="bd", entregue=True, usuario_alteracao=1, classe=1, plataforma="web")
        r = asyncio.run(svc.toggle_entregue_completo(req, 1))
        assert r["success"] is True
        assert chamada["args"] == (req, 1)
