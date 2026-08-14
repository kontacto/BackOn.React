"""Testes unitários do Checkout (venda direta — migração de FrmPafOFF.frm).

Cobre as regras de negócio da Fase 1 (núcleo): abrir venda, adicionar item
(preço/limite de desconto por função + bypass por autorização), cancelar
item, desconto geral, fechar venda com múltiplas formas de pagamento
(gravação fiel nas tabelas `comanda_*`, incluindo a divergência real de
schema de `comanda_financiado.valor_pago`), validação de parcelamento de
cartão (`Cartao_Verifica_Parcelamento`) e cancelar venda.

E a Fase 2: importar Pedido/O.S. como DAV (`Insere_Dav`) — itens marcados
com `tipo_dav` não podem ser cancelados individualmente, e cancelar a venda
inteira reverte o Pedido/O.S. de origem de volta pra Fechado + re-reserva o
estoque desses itens (em vez de decrementar `pecas.qtd` de novo).

E a Fase 3: `_get_venda_sync` expõe os dados que o recibo de impressão
precisa (CPF/CNPJ do cliente, nome do atendente — sempre nome_guerra —,
descrição da forma de pagamento e troco)."""
from datetime import datetime

import services.checkout_service as svc
from models.schemas import (
    CheckoutAbrirRequest, CheckoutItemRequest, CheckoutCancelarItemRequest,
    CheckoutDescontoGeralRequest, CheckoutFecharRequest, CheckoutFormaPagamentoItem,
    CheckoutCancelarVendaRequest, CheckoutImportarDavRequest,
    CheckoutImportarAbastecimentoRequest, CheckoutImportarAgendamentoRequest,
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


def _abrir_req(**over):
    base = dict(servidor="srv", banco="bd", atendente=1, cliente=99, master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutAbrirRequest(**base)


def _item_req(**over):
    base = dict(servidor="srv", banco="bd", codigo="S001", qtd=1, vendedor=1, funcao=3,
                desconto_percentual=0, acrescimo_percentual=0, autorizado_por=None,
                master=True, usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutItemRequest(**base)


def _cancel_item_req(**over):
    base = dict(servidor="srv", banco="bd", autorizado_por=None, master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutCancelarItemRequest(**base)


def _desc_geral_req(**over):
    base = dict(servidor="srv", banco="bd", desconto_percentual=10, funcao=3,
                autorizado_por=None, master=True, usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutDescontoGeralRequest(**base)


def _fechar_req(formas, **over):
    base = dict(servidor="srv", banco="bd", formas=formas, master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutFecharRequest(**base)


def _cancelar_venda_req(**over):
    base = dict(servidor="srv", banco="bd", motivo="Teste", master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutCancelarVendaRequest(**base)


def _importar_dav_req(**over):
    base = dict(servidor="srv", banco="bd", tipo_dav="PED", documento=100, master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutImportarDavRequest(**base)


def _importar_abastecimento_req(**over):
    base = dict(servidor="srv", banco="bd", num_abastecimento=555, vendedor=1, master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutImportarAbastecimentoRequest(**base)


def _importar_agendamento_req(**over):
    base = dict(servidor="srv", banco="bd", codagenda=777, vendedor=1, master=True,
                usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return CheckoutImportarAgendamentoRequest(**base)


PECA_ROW = {
    "codigo": "P001", "descricao": "Produto X", "codigo_fab": "P001", "valor": 50.0,
    "uni": "UN", "custo_reposicao": 30.0, "controla_num_serie": False, "aceita_desconto": True,
}
SERVICO_ROW = {"codigo": "S001", "descricao": "Serviço X", "valor": 100.0}


class TestBuscarProdutoPesoVariavel:
    """Automação Comercial (2026-08-10) — `_buscar_produto_sync` decodifica
    código de barras de peso variável (EAN-13, prefixo "2") antes de resolver
    o produto, e expõe `peso_variado`/`peso_kg` na resposta. Isola do resto
    da cadeia de resolução (já coberta em outros testes) via monkeypatch dos
    colaboradores — mais robusto do que contar fetchone() em sequência por
    uma cadeia de 4-5 funções internas."""

    # Mesmo código válido de test_pedido_common_balanca.py: prefixo "2" +
    # código produto "00123" + peso "00500" (500g) + dígito extra + dígito
    # verificador EAN-13.
    CODIGO_BARRAS_PESO_VARIAVEL = "2001230050009"

    def _stub_colaboradores(self, monkeypatch, resolve_fn):
        monkeypatch.setattr(svc, "_resolve_produto_completo", resolve_fn)
        monkeypatch.setattr(svc, "_preco_promocional", lambda *a, **k: None)
        monkeypatch.setattr(svc, "_preco_por_qtd", lambda *a, **k: None)
        monkeypatch.setattr(svc, "_limites_desconto", lambda *a, **k: {"desc_g": 0, "desc_s": 0, "desc_v": 0})

    def test_decodifica_e_resolve_pelo_codigo_embutido(self, monkeypatch):
        cur = FakeCursor(one=[{"qtd": 10.0}])
        _patch(monkeypatch, cur)
        codigos_resolvidos = []

        def fake_resolve(cur, codigo):
            codigos_resolvidos.append(codigo)
            return {
                "tipo": "P", "codigo": "00123", "cod_fab": "FAB1", "descricao": "Banana Prata",
                "valor": 6.5, "unidade": "KG", "custo": 3.0, "peso_variado": True,
            }

        self._stub_colaboradores(monkeypatch, fake_resolve)

        r = svc._buscar_produto_sync("srv", "bd", self.CODIGO_BARRAS_PESO_VARIAVEL, 1)

        assert r["success"] is True
        # Resolveu pelo código EMBUTIDO no código de barras, não pelo código
        # de barras cru de 13 dígitos.
        assert codigos_resolvidos == ["00123"]
        assert r["peso_variado"] is True
        assert r["peso_kg"] == 0.5

    def test_codigo_normal_nao_decodifica(self, monkeypatch):
        cur = FakeCursor(one=[{"qtd": 10.0}])
        _patch(monkeypatch, cur)
        codigos_resolvidos = []

        def fake_resolve(cur, codigo):
            codigos_resolvidos.append(codigo)
            return {
                "tipo": "S", "codigo": "S001", "cod_fab": "S001", "descricao": "Serviço X",
                "valor": 100.0, "unidade": "HR", "custo": 100.0, "peso_variado": False,
            }

        self._stub_colaboradores(monkeypatch, fake_resolve)

        r = svc._buscar_produto_sync("srv", "bd", "S001", 1)

        assert codigos_resolvidos == ["S001"]  # código normal, sem decodificação
        assert r["peso_variado"] is False
        assert r["peso_kg"] is None


class TestAbrirVenda:
    def test_cria_comanda_situacao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 501}])
        conn = _patch(monkeypatch, cur)
        result = svc._abrir_venda_sync(_abrir_req())
        assert result["success"] is True
        assert result["comanda"] == 501
        insert_q = cur.queries[0][0]
        assert "INSERT INTO comanda" in insert_q
        assert "'A'" in insert_q  # situacao já nasce Aberta
        assert conn.committed is True


class TestAddItem:
    def test_adiciona_servico_sem_desconto(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, SERVICO_ROW, {"emite_nf_comanda": False}, {"desc_g": 10, "desc_s": 15, "desc_v": 5},
                 {"id_mov": 55}, None, {"total": 100.0}],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(codigo="S001", qtd=1), comanda=1)
        assert result == {"success": True, "id_mov": 55, "valor_venda": 100.0}
        assert conn.committed is True
        # Serviço não é peça — nenhum UPDATE de estoque deve ter sido emitido.
        assert not any("UPDATE pecas" in q for q, _ in cur.queries)

    def test_bloqueia_desconto_acima_do_limite_do_vendedor(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, PECA_ROW, {"emite_nf_comanda": False}, {"agora": datetime(2026, 1, 1)}, None,
                 {"desc_g": 20, "desc_s": 15, "desc_v": 10}],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(codigo="P001", qtd=2, desconto_percentual=20, funcao=3), comanda=1)
        assert result["success"] is False
        assert "permitido" in result["message"].lower()
        assert conn.committed is False

    def test_autorizado_por_libera_desconto_acima_do_limite(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, PECA_ROW, {"emite_nf_comanda": False}, {"agora": datetime(2026, 1, 1)}, None,
                 {"desc_g": 20, "desc_s": 15, "desc_v": 10}, {"id_mov": 77}, {"ok": 1}, {"total": 80.0}],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(
            _item_req(codigo="P001", qtd=2, desconto_percentual=20, funcao=3, autorizado_por=9), comanda=1,
        )
        assert result["success"] is True
        assert result["id_mov"] == 77
        assert conn.committed is True
        assert any("INSERT INTO comanda_desconto" in q for q, _ in cur.queries)

    def test_bloqueia_fora_da_situacao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(), comanda=1)
        assert result["success"] is False
        assert "fechada" in result["message"].lower()


class TestAddItemTaxaNfce:
    """Checagem de Taxa (taxas_nfce) ao adicionar item — réplica de
    `RetornaDadosProduto`/`Campo_Validate` (FrmPafOFF.frm), rastreada ao
    vivo 2026-08-06. Gateada por `controle.emite_nf_comanda` — decisão
    explícita do usuário de NÃO replicar a inconsistência do legado (lá
    roda sempre, incondicional; aqui só quando a empresa emite NF direto)."""

    def test_bloqueia_item_sem_taxa_cadastrada_quando_emite_nf_comanda(self, monkeypatch):
        peca = {**PECA_ROW, "cod_icms": "0"}
        cur = FakeCursor(one=[
            {"situacao": "A"}, peca, {"emite_nf_comanda": True}, {"uf": "RJ"}, None,
        ])
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(codigo="P001", qtd=1), comanda=1)
        assert result["success"] is False
        assert "Tabela de Taxas" in result["message"]
        assert conn.committed is False
        taxa_q, taxa_p = next(q for q in cur.queries if "taxas_nfce" in q[0])
        assert "Tipo_Mov='S01'" in taxa_q
        assert taxa_p == ("RJ", "0")

    def test_permite_item_quando_taxa_cadastrada(self, monkeypatch):
        peca = {**PECA_ROW, "cod_icms": "0"}
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, peca, {"emite_nf_comanda": True}, {"uf": "RJ"}, {"ok": 1},
                {"agora": datetime(2026, 1, 1)}, None,
                {"desc_g": 20, "desc_s": 15, "desc_v": 10},
                {"id_mov": 90}, {"ok": 1}, {"total": 50.0},
            ],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(codigo="P001", qtd=1), comanda=1)
        assert result["success"] is True
        assert conn.committed is True

    def test_nao_verifica_taxa_quando_emite_nf_comanda_desligado(self, monkeypatch):
        peca = {**PECA_ROW, "cod_icms": "0"}
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, peca, {"emite_nf_comanda": False},
                {"agora": datetime(2026, 1, 1)}, None,
                {"desc_g": 20, "desc_s": 15, "desc_v": 10},
                {"id_mov": 91}, {"ok": 1}, {"total": 60.0},
            ],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(codigo="P001", qtd=1), comanda=1)
        assert result["success"] is True
        assert conn.committed is True
        assert not any("taxas_nfce" in q for q, _ in cur.queries)

    def test_produto_sem_cod_icms_nunca_bloqueia_mesmo_com_emite_nf_comanda(self, monkeypatch):
        # PECA_ROW não tem chave "cod_icms" — _linha_peca_completo devolve
        # "" (get() retorna None -> strip vazio), e _verifica_taxa_nfce
        # trata string vazia como "sem crivo" (mesmo raciocínio de outros
        # campos fiscais opcionais no projeto).
        cur = FakeCursor(
            one=[
                {"situacao": "A"}, PECA_ROW, {"emite_nf_comanda": True},
                {"agora": datetime(2026, 1, 1)}, None,
                {"desc_g": 20, "desc_s": 15, "desc_v": 10},
                {"id_mov": 92}, {"ok": 1}, {"total": 70.0},
            ],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._add_item_sync(_item_req(codigo="P001", qtd=1), comanda=1)
        assert result["success"] is True
        assert conn.committed is True
        assert not any("taxas_nfce" in q for q, _ in cur.queries)


class TestCancelarItem:
    def test_devolve_estoque_e_recalcula_total(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo_int": "P001", "qtd": 2.0}, {"ok": 1}, {"total": 50.0}])
        conn = _patch(monkeypatch, cur)
        result = svc._cancelar_item_sync(_cancel_item_req(), comanda=1, id_mov=10)
        assert result == {"success": True, "valor_venda": 50.0}
        assert conn.committed is True
        estoque_q, estoque_p = next(q for q in cur.queries if "UPDATE pecas" in q[0])
        # UPDATE faz `qtd = qtd - %s` — delta NEGATIVO aqui devolve estoque (-(-2.0) = +2.0).
        assert estoque_p == (-2.0, "P001")


class TestDescontoGeral:
    def test_redistribui_percentual_entre_itens(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"desconto_pdv_gerente": 30, "desconto_pdv_supervisor": 20, "desconto_pdv_vendedor": 10},
                 {"total": 117.0}],
            many=[[{"id_mov": 1, "codigo_int": "P001", "qtd": 2.0, "p_unit": 50.0},
                   {"id_mov": 2, "codigo_int": "P002", "qtd": 1.0, "p_unit": 30.0}]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._desconto_geral_sync(_desc_geral_req(desconto_percentual=10, funcao=3), comanda=1)
        assert result == {"success": True, "valor_venda": 117.0}
        assert conn.committed is True
        updates = [p for q, p in cur.queries if q.startswith("UPDATE movimentacao SET p_unit")]
        assert updates == [(45.0, 1), (27.0, 2)]  # 10% de desconto em cada item

    def test_bloqueia_acima_do_limite_sem_autorizacao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"desconto_pdv_gerente": 30, "desconto_pdv_supervisor": 20, "desconto_pdv_vendedor": 10}])
        _patch(monkeypatch, cur)
        result = svc._desconto_geral_sync(_desc_geral_req(desconto_percentual=50, funcao=3), comanda=1)
        assert result["success"] is False
        assert "permitido" in result["message"].lower()


class TestVerificaParcelamentoCartao:
    def test_modo_administradora_ok_quando_configuracao_existe(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        ok, erro = svc._verifica_parcelamento_cartao(cur, "001", 5, "A", 1)
        assert ok is True and erro is None

    def test_modo_administradora_bloqueia_sem_configuracao(self, monkeypatch):
        cur = FakeCursor(one=[None])
        ok, erro = svc._verifica_parcelamento_cartao(cur, "001", 5, "A", 1)
        assert ok is False
        assert "não cadastrada" in erro

    def test_modo_loja_bloqueia_parcela_nao_cadastrada(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_cartoes_configuracao": 8}, None])
        ok, erro = svc._verifica_parcelamento_cartao(cur, "001", 5, "L", 12)
        assert ok is False
        assert "não cadastrada" in erro

    def test_modo_loja_ok_quando_parcela_cadastrada(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_cartoes_configuracao": 8}, {"ok": 1}])
        ok, erro = svc._verifica_parcelamento_cartao(cur, "001", 5, "L", 3)
        assert ok is True and erro is None


class TestFecharVenda:
    def test_bloqueia_quando_falta_valor(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=40.0)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "Falta" in result["message"]

    def test_fecha_com_dinheiro_grava_comanda_dinheiro_e_situacao_pg(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}])
        conn = _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=100.0)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert result["troco"] == 0
        assert any("comanda_dinheiro" in q for q, _ in cur.queries)
        assert any("situacao='PG'" in q for q, _ in cur.queries)
        assert conn.committed is True

    def test_calcula_troco_quando_pago_maior_que_devido(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=150.0)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert result["troco"] == 50.0
        assert any("TROCO_COMANDA" in q for q, _ in cur.queries)

    def test_cartao_credito_nao_exige_mais_administradora_e_parcelador(self, monkeypatch):
        """Crivo de Administradora/Parcelador desativado nesta versão — pedido
        explícito do usuário, 2026-08-06 ("não fazer o crivo da administradora
        e parcelador nessa versão"). Fecha normalmente mesmo sem os dois."""
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}])
        conn = _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="CC", forma_pag="002", valor=100.0)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert conn.committed is True

    def test_cartao_credito_valida_parcelamento_e_grava_financiado_com_valor_pago(self, monkeypatch):
        """Confirma a divergência de schema real do legado: `comanda_financiado`
        usa a coluna `valor_pago` (não `valor_pag`, diferente de
        `pedido_venda_financiado`/`os_financiado`)."""
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="FI", forma_pag="003", valor=100.0)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        insert_q = next(q for q, _ in cur.queries if "comanda_financiado" in q)
        assert "valor_pago" in insert_q
        assert "valor_pag" not in insert_q.replace("valor_pago", "")


class TestFecharVendaValeDevolucao:
    """Vale de Devolução usado como companheiro de DI/DU/VA — ao portador,
    sem duplicidade na mesma venda, e com a assimetria real do legado: só
    DU/VA geram vale residual quando o valor usado é menor que o saldo."""

    def test_di_consome_vale_integralmente_sem_residual_mesmo_com_sobra(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 60.0},
            {"codvale": 55, "cliente": 10, "valor": 100.0, "situacao": "A"},
        ])
        conn = _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=60.0, codigo_vale_devolucao=55)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert conn.committed is True
        assert any("UPDATE vale_devolucao SET situacao='F'" in q for q, _ in cur.queries)
        assert any("INSERT INTO comanda_vale_devolucao" in q for q, _ in cur.queries)
        # DI nunca gera vale residual, mesmo havendo sobra (100 - 60 = 40).
        assert not any(q.startswith("INSERT INTO vale_devolucao") for q, _ in cur.queries)

    def test_va_parcial_gera_vale_residual_com_saldo_restante(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 60.0},
            {"codvale": 55, "cliente": 10, "valor": 100.0, "situacao": "A"},
        ])
        conn = _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="VA", forma_pag="004", valor=60.0, codigo_vale_devolucao=55)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert conn.committed is True
        residual_q, residual_p = next(q for q in cur.queries if q[0].startswith("INSERT INTO vale_devolucao"))
        assert residual_p[0] == 10  # mesmo cliente do vale original (ao portador, clonado)
        assert residual_p[1] == 40.0  # 100 - 60

    def test_du_parcial_gera_vale_residual(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 30.0},
            {"codvale": 55, "cliente": 10, "valor": 100.0, "situacao": "A"},
        ])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DU", forma_pag="005", valor=30.0, codigo_vale_devolucao=55)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert any(q.startswith("INSERT INTO vale_devolucao") for q, _ in cur.queries)

    def test_bloqueia_vale_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}, None])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=100.0, codigo_vale_devolucao=999)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "não encontrado" in result["message"]

    def test_bloqueia_vale_ja_utilizado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"codvale": 55, "cliente": 10, "valor": 100.0, "situacao": "F"},
        ])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=100.0, codigo_vale_devolucao=55)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "já foi utilizado" in result["message"]

    def test_bloqueia_vale_cancelado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"codvale": 55, "cliente": 10, "valor": 100.0, "situacao": "C"},
        ])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=100.0, codigo_vale_devolucao=55)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "cancelado" in result["message"]

    def test_bloqueia_valor_maior_que_saldo_do_vale(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"codvale": 55, "cliente": 10, "valor": 40.0, "situacao": "A"},
        ])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=100.0, codigo_vale_devolucao=55)]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "maior que o saldo" in result["message"]

    def test_bloqueia_mesmo_vale_usado_duas_vezes_na_mesma_venda(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"codvale": 55, "cliente": 10, "valor": 100.0, "situacao": "A"},
        ])
        _patch(monkeypatch, cur)
        formas = [
            CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=50.0, codigo_vale_devolucao=55),
            CheckoutFormaPagamentoItem(tipo="DI", forma_pag="001", valor=50.0, codigo_vale_devolucao=55),
        ]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "já foi usado nesta mesma venda" in result["message"]


class TestFecharVendaCartaoPresente:
    """Cartão Presente — tipo `CP` novo (sem forma_pag própria), resgate
    tudo-ou-nada ao portador, gera cartão residual com o saldo restante
    (mesma mecânica do Vale de Devolução, sem a assimetria de tipo já que
    Cartão Presente não tem um tipo `DI`/`DU`/`VA` próprio — decisão
    explícita do usuário, "TEM QUE SER FIEL AO LEGADO" aplicada ao análogo
    mais próximo, já que o legado nunca implementou resgate de verdade)."""

    def test_resgate_total_sem_residual(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"pecas_cartao_presente_auto": 9, "codigo_int": "CARTAO01"},
            {"comanda_cartao_presente_auto": 77, "valor_venda": 100.0},
        ])
        conn = _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=100.0, codigo_cartao_presente="ABC123")]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert conn.committed is True
        assert any(
            "UPDATE comanda_cartao_presente SET situacao='F'" in q and p == (77,)
            for q, p in cur.queries
        )
        resgate_q, resgate_p = next(q for q in cur.queries if "comanda_cartao_presente_resgate" in q[0] and q[0].startswith("INSERT"))
        assert resgate_p == (1, 77, 100.0)
        # Sem sobra (100 - 100 = 0) — nenhum cartão residual deve ser criado.
        assert not any(q.startswith("INSERT INTO pecas_cartao_presente") for q, _ in cur.queries)

    def test_resgate_parcial_gera_cartao_residual(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 60.0},
            {"pecas_cartao_presente_auto": 9, "codigo_int": "CARTAO01"},
            {"comanda_cartao_presente_auto": 77, "valor_venda": 100.0},
            {"pecas_cartao_presente_auto": 88},
        ])
        conn = _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=60.0, codigo_cartao_presente="ABC123")]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is True
        assert conn.committed is True
        novo_cartao_q, novo_cartao_p = next(q for q in cur.queries if q[0].startswith("INSERT INTO pecas_cartao_presente"))
        assert novo_cartao_p[0] == "CARTAO01"
        assert novo_cartao_p[1] == "ABC123-R77"
        vinculo_q, vinculo_p = next(q for q in cur.queries if q[0].startswith("INSERT INTO comanda_cartao_presente ") or q[0].startswith("INSERT INTO comanda_cartao_presente\n"))
        assert vinculo_p == (1, 88, 40.0)

    def test_bloqueia_cartao_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0}, None])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=100.0, codigo_cartao_presente="ZZZ")]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "não encontrado" in result["message"]

    def test_bloqueia_cartao_ja_resgatado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"pecas_cartao_presente_auto": 9, "codigo_int": "X"}, None,
        ])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=100.0, codigo_cartao_presente="X")]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "já foi resgatado" in result["message"]

    def test_bloqueia_valor_maior_que_saldo_do_cartao(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"pecas_cartao_presente_auto": 9, "codigo_int": "X"},
            {"comanda_cartao_presente_auto": 77, "valor_venda": 50.0},
        ])
        _patch(monkeypatch, cur)
        formas = [CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=100.0, codigo_cartao_presente="X")]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "maior que o saldo" in result["message"]

    def test_bloqueia_mesmo_cartao_usado_duas_vezes_na_mesma_venda(self, monkeypatch):
        cur = FakeCursor(one=[
            {"situacao": "A"}, {"c": 1}, {"valor_venda": 100.0},
            {"pecas_cartao_presente_auto": 9, "codigo_int": "Y"},
            {"comanda_cartao_presente_auto": 77, "valor_venda": 100.0},
        ])
        _patch(monkeypatch, cur)
        formas = [
            CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=50.0, codigo_cartao_presente="Y"),
            CheckoutFormaPagamentoItem(tipo="CP", forma_pag="", valor=50.0, codigo_cartao_presente="Y"),
        ]
        result = svc._fechar_venda_sync(_fechar_req(formas), comanda=1)
        assert result["success"] is False
        assert "já foi usado nesta mesma venda" in result["message"]


class TestCancelarVenda:
    def test_marca_situacao_cancelada_e_devolve_estoque(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"ok": 1}, None],
            many=[[{"codigo_int": "P001", "qtd": 2.0}, {"codigo_int": "S001", "qtd": 1.0}]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._cancelar_venda_sync(_cancelar_venda_req(), comanda=1)
        assert result == {"success": True}
        assert conn.committed is True
        assert any("cancelamento" in q for q, _ in cur.queries)
        assert any("situacao='C'" in q for q, _ in cur.queries)

    def test_reverte_pedido_e_os_de_itens_importados_via_dav(self, monkeypatch):
        """Item direto: devolve pecas.qtd. Item de Pedido importado ("P"):
        re-reserva `reservado`, sem tocar `qtd`. Item de O.S. importado
        ("O"), serviço: nem entra em `_is_peca` (retorna None -> sem UPDATE).
        Além disso, reverte `pedido_venda`/`os` pra Fechado e remove os
        vínculos `COMANDA_PED`/`comanda_os`."""
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"ok": 1}, {"ok": 1}, None],
            many=[[
                {"codigo_int": "P002", "qtd": 1.0, "tipo_dav": ""},
                {"codigo_int": "P001", "qtd": 2.0, "tipo_dav": "P"},
                {"codigo_int": "S001", "qtd": 1.0, "tipo_dav": "O"},
            ]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._cancelar_venda_sync(_cancelar_venda_req(), comanda=1)
        assert result == {"success": True}
        assert conn.committed is True
        direto_q, direto_p = next(q for q in cur.queries if "UPDATE pecas SET qtd" in q[0])
        assert direto_p == (-1.0, "P002")
        reserva_q, reserva_p = next(q for q in cur.queries if "reservado = ISNULL(reservado,0)" in q[0])
        assert reserva_p == (-2.0, "P001")
        assert not any("reservado_os" in q for q, _ in cur.queries if "UPDATE pecas" in q)
        assert any("pedido_venda SET situacao='F'" in q for q, _ in cur.queries)
        assert any("os SET situacao='F'" in q for q, _ in cur.queries)
        assert any(q.startswith("DELETE FROM COMANDA_PED") for q, _ in cur.queries)
        assert any(q.startswith("DELETE FROM comanda_os") for q, _ in cur.queries)


class TestCancelarItemBloqueiaDav:
    def test_bloqueia_cancelamento_de_item_importado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo_int": "P001", "qtd": 2.0, "tipo_dav": "P"}])
        _patch(monkeypatch, cur)
        result = svc._cancelar_item_sync(_cancel_item_req(), comanda=1, id_mov=10)
        assert result["success"] is False
        assert "importada" in result["message"].lower()

    def test_permite_cancelar_item_direto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo_int": "P001", "qtd": 2.0, "tipo_dav": ""}, {"ok": 1}, {"total": 50.0}])
        conn = _patch(monkeypatch, cur)
        result = svc._cancelar_item_sync(_cancel_item_req(), comanda=1, id_mov=10)
        assert result["success"] is True
        assert conn.committed is True


class TestListDavPendentes:
    def test_lista_pedidos_fechados(self, monkeypatch):
        cur = FakeCursor(
            many=[[{"documento": 100, "data": "2026-08-06", "valor": 150.0, "cliente_nome": "MARIA"}]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_dav_pendentes_sync("srv", "bd", "PED")
        assert result["success"] is True
        assert result["items"][0]["documento"] == 100
        assert "pedido_venda" in cur.queries[0][0]
        assert "situacao = 'F'" in cur.queries[0][0]

    def test_lista_os_fechadas(self, monkeypatch):
        cur = FakeCursor(
            many=[[{"documento": 200, "data": "2026-08-06", "valor": 80.0, "cliente_nome": "JOÃO"}]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_dav_pendentes_sync("srv", "bd", "OS")
        assert result["success"] is True
        assert result["items"][0]["documento"] == 200
        assert "FROM os o" in cur.queries[0][0]

    def test_bloqueia_tipo_invalido(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        result = svc._list_dav_pendentes_sync("srv", "bd", "XXX")
        assert result["success"] is False
        assert "inválido" in result["message"].lower()


class TestImportarDav:
    def test_pedido_precisa_estar_fechado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"situacao": "A", "cliente": 1, "area_atuacao": 0, "vendedor": 1}])
        _patch(monkeypatch, cur)
        result = svc._importar_dav_sync(_importar_dav_req(tipo_dav="PED", documento=100), comanda=1)
        assert result["success"] is False
        assert "Fechado" in result["message"]

    def test_importa_itens_do_pedido_libera_reservado_e_fatura(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"},
                {"situacao": "F", "cliente": 50, "area_atuacao": 0, "vendedor": 7},
                {"id_mov": 200},
                {"ok": 1},  # _is_peca dentro de _liberar_reservado
                {"total": 90.0},
            ],
            many=[[{
                "codauto": 1, "produto": "P001", "qtd": 2.0, "p_unit": 45.0,
                "preco_bruto": 50.0, "desconto": 5.0, "acrescimo": 0.0,
            }]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._importar_dav_sync(_importar_dav_req(tipo_dav="PED", documento=100), comanda=1)
        assert result == {"success": True, "valor_venda": 90.0, "itens_importados": 1}
        assert conn.committed is True
        mov_q, mov_p = next(q for q in cur.queries if q[0].startswith("INSERT INTO movimentacao"))
        assert "tipo_dav" in mov_q
        assert "P" in mov_p  # letra do DAV (Pedido)
        assert any("comanda_desconto" in q for q, _ in cur.queries)
        assert any(q[0].startswith("INSERT INTO COMANDA_PED") for q in cur.queries)
        assert any("pedido_venda SET situacao='PG'" in q for q, _ in cur.queries)
        assert any(q == ("UPDATE comanda SET cliente=%s WHERE comanda=%s", (50, 1)) for q in cur.queries)

    def test_os_ja_vinculada_a_outra_comanda_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"comanda": 55}])
        _patch(monkeypatch, cur)
        result = svc._importar_dav_sync(_importar_dav_req(tipo_dav="OS", documento=200), comanda=1)
        assert result["success"] is False
        assert "vinculada" in result["message"].lower()

    def test_importa_itens_da_os_bloco_cliente(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"},
                None,  # não vinculada a nenhuma comanda ainda
                {"situacao": "F", "cliente": 60, "area_atuacao": 0},
                {"id_mov": 300},
                None,  # _is_peca -> serviço, não é peça
                {"total": 100.0},
            ],
            many=[[{
                "cod_os_prod": 5, "produto": "S001", "qtd": 1.0, "p_unit": 100.0,
                "preco_bruto": 100.0, "desconto": 0.0, "acrescimo": 0.0, "vendedor": 9,
            }]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._importar_dav_sync(_importar_dav_req(tipo_dav="OS", documento=200), comanda=1)
        assert result == {"success": True, "valor_venda": 100.0, "itens_importados": 1}
        assert conn.committed is True
        assert any(q[0].startswith("INSERT INTO comanda_os") for q in cur.queries)
        assert any("os SET situacao='PG'" in q for q, _ in cur.queries)


class TestGetVenda:
    """`_get_venda_sync` — Fase 3 (recibo): expõe CPF/CNPJ do cliente, nome
    do atendente (nome_guerra), descrição da forma de pagamento e troco."""

    def test_expoe_dados_completos_pro_recibo(self, monkeypatch):
        cab = {
            "comanda": 1, "data": "2026-08-05", "situacao": "PG", "valor_venda": 100.0,
            "cliente": 50, "atendente": 7, "area_atuacao": 0,
            "cliente_nome": "Fulano de Tal", "cliente_fantasia": None,
            "cliente_cgc_cpf": "12345678900", "atendente_nome": "Zé",
        }
        itens_rows = [{
            "id_mov": 1, "codigo_int": "P001", "qtd": 2.0, "p_unit": 45.0, "vendedor": 7,
            "tipo_dav": "", "COD_AUTO_DAV": 0, "descricao_p": "Produto X", "descricao_s": None,
            "desconto": 5.0, "preco_bruto_desc": 50.0, "acrescimo": 0.0, "preco_bruto_acr": None,
        }]
        formas_di = [{"sequencia": 1, "forma_pag": "001", "descricao": "Dinheiro", "valor": 100.0}]
        cur = FakeCursor(
            one=[cab, {"troco": 5.0}],
            many=[itens_rows, [], [], formas_di, [], [], [], [], [], [], []],
        )
        _patch(monkeypatch, cur)
        result = svc._get_venda_sync("srv", "bd", 1)
        assert result["success"] is True
        assert result["cliente_cgc_cpf"] == "12345678900"
        assert result["atendente_nome"] == "Zé"
        assert result["troco"] == 5.0
        assert result["formas_pagamento"] == [
            {"tipo": "DI", "sequencia": 1, "forma_pag": "001", "descricao": "Dinheiro", "valor": 100.0}
        ]
        assert result["itens"][0]["preco_bruto"] == 50.0


class TestCancelarVendaBloqueiaJaFechada:
    def test_bloqueia_venda_ja_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        result = svc._cancelar_venda_sync(_cancelar_venda_req(), comanda=1)
        assert result["success"] is False
        assert "Gestor de Comandas" in result["message"]


class TestListAbastecimentosPendentes:
    def test_lista_com_modulo_ativo(self, monkeypatch):
        cur = FakeCursor(
            one=[{"Posto": 1}],
            many=[[{"num": 555, "descricao": "GASOLINA COMUM", "preco_un": 5.9, "volume": 20.0, "valor": 118.0}]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_abastecimentos_pendentes_sync("srv", "bd")
        assert result["success"] is True
        assert result["items"][0]["num"] == 555

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"Posto": 0}])
        _patch(monkeypatch, cur)
        result = svc._list_abastecimentos_pendentes_sync("srv", "bd")
        assert result["success"] is False
        assert result["items"] == []
        assert "desativado" in result["message"].lower()


class TestImportarAbastecimento:
    def test_importa_com_sucesso_e_marca_emitido(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"Posto": 1},
                {"situacao": "A"},
                {"codigo_int": "COMB01", "preco_un": 5.9, "volume": 20.0, "status_abastecimento": "PENDENTE"},
                {"id_mov": 900},
                {"total": 118.0},
            ],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._importar_abastecimento_sync(_importar_abastecimento_req(), comanda=1)
        assert result == {"success": True, "id_mov": 900, "valor_venda": 118.0}
        assert conn.committed is True
        mov_q, mov_p = next(q for q in cur.queries if q[0].startswith("INSERT INTO movimentacao"))
        assert "tipo_dav" in mov_q
        assert "ABA" in mov_p
        assert any(
            q == ("UPDATE abastecimento SET status_abastecimento='EMITIDO CF' WHERE num=%s", (555,))
            for q in cur.queries
        )
        # Não decrementa pecas.qtd — combustível já saiu fisicamente do tanque.
        assert not any("UPDATE pecas SET qtd" in q for q, _ in cur.queries)

    def test_bloqueia_ja_emitido(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"Posto": 1},
                {"situacao": "A"},
                {"codigo_int": "COMB01", "preco_un": 5.9, "volume": 20.0, "status_abastecimento": "EMITIDO CF"},
            ],
        )
        _patch(monkeypatch, cur)
        result = svc._importar_abastecimento_sync(_importar_abastecimento_req(), comanda=1)
        assert result["success"] is False
        assert "outra venda" in result["message"].lower()

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"Posto": 0}])
        _patch(monkeypatch, cur)
        result = svc._importar_abastecimento_sync(_importar_abastecimento_req(), comanda=1)
        assert result["success"] is False
        assert "desativado" in result["message"].lower()


class TestListAgendamentosPendentes:
    def test_lista_com_modulo_ativo(self, monkeypatch):
        cur = FakeCursor(
            one=[{"CLINICA": 1, "Assistencia": 0}],
            many=[[{"codagenda": 777, "cliente_nome": "MARIA", "servico_descricao": "Corte", "valor": 50.0}]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_agendamentos_pendentes_sync("srv", "bd")
        assert result["success"] is True
        assert result["items"][0]["codagenda"] == 777

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 0, "Assistencia": 0}])
        _patch(monkeypatch, cur)
        result = svc._list_agendamentos_pendentes_sync("srv", "bd")
        assert result["success"] is False
        assert result["items"] == []


class TestImportarAgendamento:
    def test_importa_com_sucesso_e_grava_vinculo(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"CLINICA": 1, "Assistencia": 0},
                {"situacao": "A"},
                {"servico": "SERV01", "valor": 50.0, "situacao_atendimento": "Confirmado", "situacao_caixa": "A"},
                None,  # agenda_comanda ainda não faturado
                {"id_mov": 950},
                {"total": 50.0},
            ],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._importar_agendamento_sync(_importar_agendamento_req(), comanda=1)
        assert result == {"success": True, "id_mov": 950, "valor_venda": 50.0}
        assert conn.committed is True
        mov_q, mov_p = next(q for q in cur.queries if q[0].startswith("INSERT INTO movimentacao"))
        assert "tipo_dav" in mov_q
        assert "AGE" in mov_p
        assert any(
            q == ("INSERT INTO agenda_comanda (codagenda, codcomanda, situacao_atendimento, ID_MOVIMENTACAO) "
                  "VALUES (%s,%s,%s,%s)", (777, 1, "Confirmado", 950))
            for q in cur.queries
        )
        assert any(q == ("UPDATE AGENDA SET situacao_caixa='P' WHERE codagenda=%s", (777,)) for q in cur.queries)
        # Não troca o cliente da venda automaticamente (diferente do legado).
        assert not any("UPDATE comanda SET cliente" in q for q, _ in cur.queries)

    def test_bloqueia_ja_faturado(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"CLINICA": 1, "Assistencia": 0},
                {"situacao": "A"},
                {"servico": "SERV01", "valor": 50.0, "situacao_atendimento": "Confirmado", "situacao_caixa": "P"},
            ],
        )
        _patch(monkeypatch, cur)
        result = svc._importar_agendamento_sync(_importar_agendamento_req(), comanda=1)
        assert result["success"] is False
        assert "já foi faturado" in result["message"]

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"CLINICA": 0, "Assistencia": 0}])
        _patch(monkeypatch, cur)
        result = svc._importar_agendamento_sync(_importar_agendamento_req(), comanda=1)
        assert result["success"] is False


class TestCancelarItemBloqueiaOrigemAbaAge:
    def test_bloqueia_cancelamento_de_item_abastecimento(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo_int": "COMB01", "qtd": 20.0, "tipo_dav": "ABA"}])
        _patch(monkeypatch, cur)
        result = svc._cancelar_item_sync(_cancel_item_req(), comanda=1, id_mov=10)
        assert result["success"] is False

    def test_bloqueia_cancelamento_de_item_agendamento(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo_int": "SERV01", "qtd": 1.0, "tipo_dav": "AGE"}])
        _patch(monkeypatch, cur)
        result = svc._cancelar_item_sync(_cancel_item_req(), comanda=1, id_mov=10)
        assert result["success"] is False


class TestCancelarVendaReverteAbastecimentoEAgendamento:
    def test_reverte_abastecimento_e_agendamento(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}],
            many=[[
                {"codigo_int": "COMB01", "qtd": 20.0, "tipo_dav": "ABA", "COD_AUTO_DAV": 555},
                {"codigo_int": "SERV01", "qtd": 1.0, "tipo_dav": "AGE", "COD_AUTO_DAV": 777},
            ]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._cancelar_venda_sync(_cancelar_venda_req(), comanda=1)
        assert result == {"success": True}
        assert conn.committed is True
        assert any(
            q == ("UPDATE abastecimento SET status_abastecimento='PENDENTE' WHERE num=%s", (555,))
            for q in cur.queries
        )
        assert any(q == ("DELETE FROM agenda_comanda WHERE codagenda=%s", (777,)) for q in cur.queries)
        assert any(q == ("UPDATE AGENDA SET situacao_caixa='A' WHERE codagenda=%s", (777,)) for q in cur.queries)
