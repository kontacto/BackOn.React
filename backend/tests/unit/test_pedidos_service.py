"""Testes UNITÁRIOS de pedidos_service — foco no que foi adicionado nesta
rodada: Data/Hora de Entrega, checkbox "Pedido Entregue" (auto-save,
FrmManPedBar.frm Check88_Click) e os filtros do painel "Pedidos Abertos"
(Mesa/Balcão/Entrega/Comanda, Data de Entrega, Ordenar por)."""
import services.pedidos_service as svc
from models.schemas import (
    PedidoEntregueRequest, PedidosListRequest, FecharRequest, FormaPagSimplesRequest,
    DividirPedidoRequest, DividirPedidoGrupo, DividirPedidoItem, QtdPessoasRequest,
    PedidoSaveRequest,
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


def _entregue_req(**over):
    base = dict(servidor="srv", banco="bd", entregue=True, usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return PedidoEntregueRequest(**base)


def _list_req(**over):
    base = dict(servidor="srv", banco="bd")
    base.update(over)
    return PedidosListRequest(**base)


class TestListPedidosFiltrosPedidosAbertos:
    """Filtros do painel "Pedidos Abertos" do Pedido Bar (FrmManPedBar.frm)
    — Mesa/Balcão/Entrega/Comanda filtram por cliente.cliente_forn (tipo do
    CLIENTE, não um tipo de pedido), Data de Entrega filtra
    previsao_entrega<=X, Ordenar por muda o ORDER BY."""

    def test_tipos_cliente_filtra_por_cliente_forn(self, monkeypatch):
        # Filtra pelo tipo do PEDIDO, caindo pro tipo do cliente quando o
        # pedido não tem tipo próprio — pedido explícito do usuário,
        # 2026-07-18.
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(tipos_cliente=[10, 20]))
        select_q, params = cur.queries[-1]
        assert "COALESCE(NULLIF(p.tipo, 0), c.cliente_forn) IN (%s,%s)" in select_q
        assert 10 in params and 20 in params

    def test_data_entrega_filtra_previsao_entrega(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(data_entrega="2026-07-20"))
        select_q, params = cur.queries[-1]
        assert "p.previsao_entrega <= %s" in select_q
        assert "2026-07-20" in params

    def test_data_ini_e_fim_tem_excecao_pra_fiado_aberto(self, monkeypatch):
        # Pedido tipo FIADO ainda Aberto nunca é escondido pelo filtro de
        # data — a tela sempre carrega com o filtro do dia atual, e um
        # fiado pode ter sido aberto há semanas. Pedido explícito do
        # usuário, 2026-07-18.
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(data_ini="2026-07-18", data_fim="2026-07-18"))
        select_q, params = cur.queries[-1]
        assert "(p.data >= %s OR (p.situacao = 'A' AND (SELECT descricao FROM tipo_cliente wt " \
            "WHERE wt.codigo = COALESCE(NULLIF(p.tipo, 0), c.cliente_forn)) = 'FIADO'))" in select_q
        assert "(p.data <= %s OR (p.situacao = 'A' AND (SELECT descricao FROM tipo_cliente wt " \
            "WHERE wt.codigo = COALESCE(NULLIF(p.tipo, 0), c.cliente_forn)) = 'FIADO'))" in select_q
        assert "2026-07-18" in params

    def test_ordenar_por_abertura(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(ordenar_por="abertura"))
        select_q, _ = cur.queries[-1]
        assert "ORDER BY p.data, p.hora_aberto" in select_q

    def test_ordenar_por_tipo(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(ordenar_por="tipo"))
        select_q, _ = cur.queries[-1]
        assert "ORDER BY tc.descricao, c.nome" in select_q

    def test_ordenar_por_cliente(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(ordenar_por="cliente"))
        select_q, _ = cur.queries[-1]
        assert "ORDER BY c.nome" in select_q

    def test_sem_ordenar_por_mantem_comportamento_atual(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req())
        select_q, _ = cur.queries[-1]
        assert "ORDER BY p.pedido DESC" in select_q

    def test_sem_filtros_nao_gera_where_de_tipo_ou_entrega(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req())
        select_q, _ = cur.queries[-1]
        assert "cliente_forn IN" not in select_q
        assert "previsao_entrega <=" not in select_q


class TestBuscaPorCodigoDoCliente:
    def test_search_inclui_codigo_do_cliente(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(search="42"))
        select_q, params = cur.queries[-1]
        assert "CAST(c.codigo AS NVARCHAR(20)) LIKE %s" in select_q
        assert "%42%" in params


class TestToggleEntregue:
    def test_marca_entregue_true(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._toggle_entregue_sync(_entregue_req(entregue=True), 1)
        assert r["success"] is True and r["entregue"] is True
        assert conn.committed is True
        update_params = cur.queries[0][1]
        assert update_params == (1, 1)

    def test_marca_entregue_false(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        _patch(monkeypatch, cur)
        r = svc._toggle_entregue_sync(_entregue_req(entregue=False), 1)
        assert r["success"] is True and r["entregue"] is False
        update_params = cur.queries[0][1]
        assert update_params == (0, 1)

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._toggle_entregue_sync(_entregue_req(), 999)
        assert r["success"] is False and "não encontrado" in r["message"].lower()
        assert conn.rolled is True


class TestFaturarPedido:
    """Faturar Pedido (FrmManPedBar.frm, Command111_Click) — só a parte
    não-fiscal: gera Comanda, libera reservado das peças, grava
    movimentação e marca situação PG. Sem NFC-e (ver PENDENCIAS.md)."""

    def _req(self, **over):
        base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
        base.update(over)
        return FecharRequest(**base)

    def test_fatura_com_sucesso_gera_comanda_e_marca_pg(self, monkeypatch):
        pedido_row = {"situacao": "F", "cliente": 10, "total": 150.0, "area_atuacao": 2, "vendedor": 20, "forma_pag": "001"}
        itens = [
            {"produto": "P001", "qtd_pedida": 2.0, "p_venda": 50.0, "custo_ped": 30.0},
            {"produto": "S001", "qtd_pedida": 1.0, "p_venda": 50.0, "custo_ped": 0.0},
        ]
        cur = FakeCursor(one=[pedido_row, {"comanda": 501}, {"ok": 1}, None], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._faturar_pedido_sync(self._req(), 77)
        assert r["success"] is True
        assert r["situacao"] == "PG"
        assert r["comanda"] == 501
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any("INSERT INTO COMANDA_PED" in q for q in queries)
        assert any("UPDATE pedido_venda SET situacao='PG'" in q for q in queries)
        # Reservado só é liberado pra peça (P001) — S001 não existe em pecas.
        reservado_updates = [p for q, p in cur.queries if "SET reservado" in q]
        assert reservado_updates == [(2.0, "P001")]
        assert sum(1 for q in queries if "INSERT INTO movimentacao" in q) == 2

    def test_pedido_aberto_fecha_e_fatura_automaticamente(self, monkeypatch):
        """Pedido explícito do usuário: Faturar Pedido não exige clicar em
        Fechar Pedido antes — se ainda estiver Aberto, fecha (mesma rotina
        do endpoint /fechar, via `_fechar_pedido_itens`) e já emenda o
        faturamento, num clique só. `_fechar_pedido_itens` é mockado aqui —
        seu próprio comportamento (validação/ajuste de forma de pagamento
        via `_fecha_fpag_dav`) tem teste dedicado em
        test_pedido_common_forma_pagamento.py; este teste cobre só o
        controle de fluxo de `_faturar_pedido_sync` (repassa os args certos,
        segue pro faturamento quando ok)."""
        pedido_row = {"situacao": "A", "cliente": 10, "total": 100.0, "area_atuacao": 2, "vendedor": 20, "forma_pag": "001"}
        itens_faturar = [{"produto": "P001", "qtd_pedida": 2.0, "p_venda": 50.0, "custo_ped": 30.0}]
        cur = FakeCursor(one=[pedido_row, {"comanda": 501}, {"ok": 1}], many=[itens_faturar])
        conn = _patch(monkeypatch, cur)
        chamada = {}

        def fake_fechar_itens(cur_arg, pedido_arg, subtotal_arg, forma_arg):
            chamada["args"] = (pedido_arg, subtotal_arg, forma_arg)
            return None  # sucesso — não bloqueia

        monkeypatch.setattr(svc, "_fechar_pedido_itens", fake_fechar_itens)
        r = svc._faturar_pedido_sync(self._req(), 77)
        assert r["success"] is True
        assert r["situacao"] == "PG"
        assert r["situacao_antes"] == "A"
        assert r["comanda"] == 501
        assert conn.committed is True
        assert chamada["args"] == (77, 100.0, "001")
        queries = [q for q, _ in cur.queries]
        assert any("UPDATE pedido_venda SET situacao='PG'" in q for q in queries)

    def test_pedido_aberto_propaga_erro_do_fechamento_automatico(self, monkeypatch):
        """Se `_fechar_pedido_itens` bloquear (forma de pagamento divergente,
        sem itens, etc.), `_faturar_pedido_sync` propaga o erro sem tentar
        gerar a Comanda."""
        pedido_row = {"situacao": "A", "cliente": 10, "total": 100.0, "area_atuacao": 2, "vendedor": 20, "forma_pag": "001"}
        cur = FakeCursor(one=[pedido_row])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_fechar_pedido_itens", lambda *a: "Informar a Forma de Pagamento corretamente!")
        r = svc._faturar_pedido_sync(self._req(), 77)
        assert r["success"] is False
        assert "forma de pagamento" in r["message"].lower()
        assert not any("INSERT INTO comanda" in q for q, _ in cur.queries)

    def test_pedido_aberto_sem_itens_bloqueia_fechamento_automatico(self, monkeypatch):
        pedido_row = {"situacao": "A", "cliente": 10, "total": 0, "area_atuacao": 0, "vendedor": 0, "forma_pag": "001"}
        cur = FakeCursor(one=[pedido_row], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._faturar_pedido_sync(self._req(), 77)
        assert r["success"] is False
        assert "inclua pelo menos" in r["message"].lower()

    def test_bloqueia_situacao_invalida(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C", "cliente": 10, "total": 0, "area_atuacao": 0, "vendedor": 0, "forma_pag": "001"}])
        _patch(monkeypatch, cur)
        r = svc._faturar_pedido_sync(self._req(), 77)
        assert r["success"] is False
        assert "não pode ser faturado" in r["message"].lower()

    def test_bloqueia_se_ja_faturado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG", "cliente": 10, "total": 0, "area_atuacao": 0, "vendedor": 0, "forma_pag": "001"}])
        _patch(monkeypatch, cur)
        r = svc._faturar_pedido_sync(self._req(), 77)
        assert r["success"] is False
        assert "já faturado" in r["message"].lower()

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._faturar_pedido_sync(self._req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestCancelarPedido:
    """Cancelar Pedido (FrmManPedBar.frm, Command9_Click) — só Aberto/Fechado
    podem ser cancelados; se estava Fechado, reverte a baixa de estoque que
    o Fechar tinha feito (`_mover_estoque` com delta negativo)."""

    def _req(self, **over):
        base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
        base.update(over)
        return FecharRequest(**base)

    def test_cancela_pedido_aberto_nao_estorna_estoque(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_sync(self._req(), 77)
        assert r["success"] is True
        assert r["situacao"] == "C"
        assert r["situacao_antes"] == "A"
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any("UPDATE pedido_venda SET situacao='C'" in q for q in queries)
        assert not any("pedido_venda_prod" in q for q in queries)

    def test_cancela_pedido_fechado_estorna_so_pecas(self, monkeypatch):
        itens = [
            {"produto": "P001", "qtd_pedida": 2.0},
            {"produto": "S001", "qtd_pedida": 1.0},
        ]
        # fetchone(): situacao, depois _is_peca(P001)->achou, _is_peca(S001)->não achou
        cur = FakeCursor(one=[{"situacao": "F"}, {"ok": 1}, None], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_sync(self._req(), 77)
        assert r["success"] is True
        assert r["situacao_antes"] == "F"
        assert conn.committed is True
        estorno = [p for q, p in cur.queries if "SET qtd = ISNULL" in q]
        assert estorno == [(-2.0, -2.0, "P001")]  # delta negativo: qtd += 2, reservado -= 2

    def test_bloqueia_situacao_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_sync(self._req(), 77)
        assert r["success"] is False
        assert "cancelados" in r["message"].lower()

    def test_bloqueia_situacao_ja_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_sync(self._req(), 77)
        assert r["success"] is False

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._cancelar_pedido_sync(self._req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestReabrirPedido:
    """Reabrir Pedido (FrmManPedBar.frm, cmdReabrir_Click) — só Fechado pode
    ser reaberto (volta pra Aberto); sempre reverte a baixa de estoque que
    o Fechar tinha feito (`_mover_estoque` com delta negativo)."""

    def _req(self, **over):
        base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
        base.update(over)
        return FecharRequest(**base)

    def test_reabre_pedido_fechado_estorna_so_pecas(self, monkeypatch):
        itens = [
            {"produto": "P001", "qtd_pedida": 2.0},
            {"produto": "S001", "qtd_pedida": 1.0},
        ]
        # fetchone(): situacao, depois _is_peca(P001)->achou, _is_peca(S001)->não achou
        cur = FakeCursor(one=[{"situacao": "F"}, {"ok": 1}, None], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_pedido_sync(self._req(), 77)
        assert r["success"] is True
        assert r["situacao"] == "A"
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any("UPDATE pedido_venda SET situacao='A'" in q for q in queries)
        estorno = [p for q, p in cur.queries if "SET qtd = ISNULL" in q]
        assert estorno == [(-2.0, -2.0, "P001")]  # delta negativo: qtd += 2, reservado -= 2

    def test_bloqueia_situacao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_pedido_sync(self._req(), 77)
        assert r["success"] is False
        assert "reabertos" in r["message"].lower()

    def test_bloqueia_situacao_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_pedido_sync(self._req(), 77)
        assert r["success"] is False

    def test_bloqueia_situacao_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_pedido_sync(self._req(), 77)
        assert r["success"] is False

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._reabrir_pedido_sync(self._req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestDividirPedido:
    """Dividir Pedido — funcionalidade nova (sem precedente no VB6, ver
    docstring de `_dividir_pedido_sync`). Divide um pedido Aberto em N
    pedidos novos sob o mesmo cliente, movendo itens (quantidade inteira ou
    fracionária — mesma mecânica pra "dividir por valor" um item
    indivisível)."""

    def _req(self, grupos, **over):
        base = dict(
            servidor="srv", banco="bd", grupos=grupos,
            classe=1, master=True, usuario_alteracao=1, plataforma="web",
        )
        base.update(over)
        return DividirPedidoRequest(**base)

    def _grupo(self, *pares):
        return DividirPedidoGrupo(itens=[DividirPedidoItem(codauto=c, qtd=q) for c, q in pares])

    def _header(self, situacao="A"):
        return {
            "situacao": situacao, "cliente": 10, "vendedor": 20, "area_atuacao": 2,
            "forma_pag": "001", "obs": "", "NOME_CLIENTE": "M15", "TELEFONE_CLIENTE": "",
            "LOCALIZACAO": 5,
        }

    def test_divide_parte_de_um_item_mantem_original_aberto(self, monkeypatch):
        itens = [
            {"codauto": 1, "produto": "P001", "qtd_pedida": 4.0, "p_venda": 10.0, "p_normal": 10.0,
             "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 5.0, "descricao_produto": "", "unidade_pedido": "UN"},
            {"codauto": 2, "produto": "P002", "qtd_pedida": 1.0, "p_venda": 20.0, "p_normal": 20.0,
             "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 8.0, "descricao_produto": "", "unidade_pedido": "UN"},
        ]
        cur = FakeCursor(
            one=[self._header(), {"pedido": 501}, None, None, {"total": 20.0}, {"total": 40.0}],
            many=[itens],
        )
        conn = _patch(monkeypatch, cur)
        req = self._req([self._grupo((1, 2.0))])
        r = svc._dividir_pedido_sync(req, 77)
        assert r["success"] is True
        assert r["novos_pedidos"] == [501]
        assert r["original_cancelado"] is False
        assert conn.committed is True

        queries = [q for q, _ in cur.queries]
        assert any("INSERT INTO pedido_venda " in q for q in queries)
        insert_item_q, insert_item_p = next((q, p) for q, p in cur.queries if "INSERT INTO pedido_venda_prod" in q)
        assert insert_item_p[:3] == (501, "P001", 2.0)  # pedido novo, produto, qtd movida
        # Referência ao pedido original gravada em num_ped_cliente (última coluna do INSERT).
        insert_pedido_p = next(p for q, p in cur.queries if q.startswith("INSERT INTO pedido_venda "))
        assert insert_pedido_p[-1] == "77"
        # Item parcialmente movido vira UPDATE (resta 2.0), não DELETE.
        update_restante = [p for q, p in cur.queries if q.startswith("UPDATE pedido_venda_prod SET qtd_pedida=")]
        assert (2.0, 1) in update_restante
        assert (1.0, 2) in update_restante
        assert not any(q.startswith("DELETE FROM pedido_venda_prod WHERE codauto=") for q, _ in cur.queries)

    def test_divide_tudo_de_um_item_unico_cancela_original(self, monkeypatch):
        itens = [
            {"codauto": 1, "produto": "P001", "qtd_pedida": 2.0, "p_venda": 10.0, "p_normal": 10.0,
             "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 5.0, "descricao_produto": "", "unidade_pedido": "UN"},
        ]
        cur = FakeCursor(
            one=[self._header(), {"pedido": 501}, None, None, {"total": 20.0}],
            many=[itens],
        )
        conn = _patch(monkeypatch, cur)
        req = self._req([self._grupo((1, 2.0))])
        r = svc._dividir_pedido_sync(req, 77)
        assert r["success"] is True
        assert r["original_cancelado"] is True
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any(q.startswith("DELETE FROM pedido_venda_prod WHERE codauto=") for q in queries)
        assert any("UPDATE pedido_venda SET situacao='C'" in q for q in queries)

    def test_divide_quantidade_fracionaria_para_valor(self, monkeypatch):
        """1 unidade indivisível dividida em 4 partes iguais (qtd=0.25 cada) —
        mesma mecânica de qtd inteira, só com fração."""
        itens = [
            {"codauto": 1, "produto": "P900", "qtd_pedida": 1.0, "p_venda": 40.0, "p_normal": 40.0,
             "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 20.0, "descricao_produto": "", "unidade_pedido": "UN"},
        ]
        cur = FakeCursor(
            one=[
                self._header(), {"pedido": 501}, {"pedido": 502}, {"pedido": 503},
                None,                    # sincroniza(pedido original)
                None, {"total": 10.0},   # sincroniza(501), recalc_total(501)
                None, {"total": 10.0},   # sincroniza(502), recalc_total(502)
                None, {"total": 10.0},   # sincroniza(503), recalc_total(503)
                {"total": 10.0},         # recalc_total(pedido original)
            ],
            many=[itens],
        )
        _patch(monkeypatch, cur)
        req = self._req([self._grupo((1, 0.25)), self._grupo((1, 0.25)), self._grupo((1, 0.25))])
        r = svc._dividir_pedido_sync(req, 77)
        assert r["success"] is True
        assert r["novos_pedidos"] == [501, 502, 503]
        # 0.75 movido no total, resta 0.25 no pedido original — não zera, não cancela.
        assert r["original_cancelado"] is False

    def test_bloqueia_quantidade_excede_original(self, monkeypatch):
        itens = [
            {"codauto": 1, "produto": "P001", "qtd_pedida": 1.0, "p_venda": 10.0, "p_normal": 10.0,
             "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 5.0, "descricao_produto": "", "unidade_pedido": "UN"},
        ]
        cur = FakeCursor(one=[self._header()], many=[itens])
        _patch(monkeypatch, cur)
        req = self._req([self._grupo((1, 5.0))])
        r = svc._dividir_pedido_sync(req, 77)
        assert r["success"] is False
        assert "exceder" in r["message"].lower()

    def test_bloqueia_item_de_outro_pedido(self, monkeypatch):
        cur = FakeCursor(one=[self._header()], many=[[]])
        _patch(monkeypatch, cur)
        req = self._req([self._grupo((999, 1.0))])
        r = svc._dividir_pedido_sync(req, 77)
        assert r["success"] is False
        assert "não pertence" in r["message"].lower()

    def test_bloqueia_dividir_taxa_de_servico(self, monkeypatch):
        itens = [
            {"codauto": 9, "produto": "S002", "qtd_pedida": 1.0, "p_venda": 5.0, "p_normal": 5.0,
             "desconto": 0.0, "acrescimo": 0.0, "custo_ped": 0.0, "descricao_produto": "", "unidade_pedido": "UN"},
        ]
        cur = FakeCursor(one=[self._header()], many=[itens])
        _patch(monkeypatch, cur)
        req = self._req([self._grupo((9, 1.0))])
        r = svc._dividir_pedido_sync(req, 77)
        assert r["success"] is False
        assert "taxa de serviço" in r["message"].lower()

    def test_bloqueia_dividir_pedido_que_ja_e_filho(self, monkeypatch):
        """Um pedido filho de uma distribuição (referência numérica aponta
        pro original) não pode ser distribuído de novo — evita cadeia de
        múltiplos níveis. Pedido explícito do usuário, 2026-07-17."""
        header_filho = {**self._header(), "num_ped_cliente": "10334"}
        cur = FakeCursor(one=[header_filho])
        _patch(monkeypatch, cur)
        req = self._req([self._grupo((1, 1.0))])
        r = svc._dividir_pedido_sync(req, 10336)
        assert r["success"] is False
        assert "já é resultado de uma distribuição" in r["message"]

    def test_bloqueia_sem_grupos(self, monkeypatch):
        cur = FakeCursor(one=[self._header()])
        _patch(monkeypatch, cur)
        r = svc._dividir_pedido_sync(self._req([]), 77)
        assert r["success"] is False
        assert "ao menos um grupo" in r["message"].lower()

    def test_bloqueia_situacao_nao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[self._header(situacao="F")])
        _patch(monkeypatch, cur)
        r = svc._dividir_pedido_sync(self._req([self._grupo((1, 1.0))]), 77)
        assert r["success"] is False
        assert "aberto" in r["message"].lower()

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._dividir_pedido_sync(self._req([self._grupo((1, 1.0))]), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestGetPedidoRetornaCamposEntrega:
    def test_mapeia_previsao_hora_entregue(self, monkeypatch):
        from datetime import date
        row = {
            "pedido": 1, "cliente": 10, "data": date(2026, 7, 16), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A", "total": 0,
            "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "previsao_entrega": date(2026, 7, 20), "hora_entrega": "18:30:00", "pedido_entregue": 1,
            "cliente_nome": "Fulano", "cliente_cgc": "", "vendedor_nome": "V", "area_descricao": "",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_sync("srv", "bd", 1)
        assert r["success"] is True
        p = r["pedido"]
        assert p["previsao_entrega"] == "2026-07-20"
        assert p["hora_entrega"] == "18:30:00"
        assert p["pedido_entregue"] is True

    def test_sem_previsao_entrega_retorna_none(self, monkeypatch):
        from datetime import date
        row = {
            "pedido": 1, "cliente": 10, "data": date(2026, 7, 16), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A", "total": 0,
            "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "previsao_entrega": None, "hora_entrega": None, "pedido_entregue": 0,
            "cliente_nome": "Fulano", "cliente_cgc": "", "vendedor_nome": "V", "area_descricao": "",
        }
        cur = FakeCursor(one=[row])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_sync("srv", "bd", 1)
        p = r["pedido"]
        assert p["previsao_entrega"] is None
        assert p["hora_entrega"] == ""
        assert p["pedido_entregue"] is False

    def test_lista_pedidos_relacionados_visto_da_raiz(self, monkeypatch):
        """Visto a partir do pedido ORIGINAL (raiz de uma divisão): lista os
        filhos criados por "Dividir Pedido", rastreados via
        num_ped_cliente=str(pedido) — mostrados junto pra permitir abrir/
        faturar cada um (pedido explícito do usuário, 2026-07-17)."""
        from datetime import date
        row = {
            "pedido": 77, "cliente": 10, "data": date(2026, 7, 17), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A", "total": 36.0,
            "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "previsao_entrega": None, "hora_entrega": None, "pedido_entregue": 0,
            "cliente_nome": "Fulano", "cliente_cgc": "", "vendedor_nome": "V", "area_descricao": "",
            "num_ped_cliente": None,
        }
        filhos = [
            {"pedido": 501, "situacao": "A", "total": 20.0},
            {"pedido": 502, "situacao": "PG", "total": 15.0},
        ]
        cur = FakeCursor(one=[row], many=[filhos])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_sync("srv", "bd", 77)
        p = r["pedido"]
        assert p["pedidos_relacionados"] == [
            {"pedido": 501, "situacao": "A", "situacao_label": "Aberto", "total": 20.0},
            {"pedido": 502, "situacao": "PG", "situacao_label": "Faturado", "total": 15.0},
        ]
        select_q, params = cur.queries[-1]
        assert params == ("77", 77, 77)

    def test_lista_pedidos_relacionados_visto_de_um_filho(self, monkeypatch):
        """Visto a partir de um pedido FILHO (tem `num_ped_cliente` apontando
        pra um número): a raiz da consulta é a original (77), não o próprio
        filho (501) — assim a lista fica a mesma não importa qual pedido da
        divisão está aberto na tela, mantendo a referência da mesa visível
        até o fechamento total de todos eles."""
        from datetime import date
        row = {
            "pedido": 501, "cliente": 10, "data": date(2026, 7, 17), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A", "total": 20.0,
            "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "previsao_entrega": None, "hora_entrega": None, "pedido_entregue": 0,
            "cliente_nome": "Fulano", "cliente_cgc": "", "vendedor_nome": "V", "area_descricao": "",
            "num_ped_cliente": "77",
        }
        relacionados = [
            {"pedido": 77, "situacao": "A", "total": 16.0},
            {"pedido": 502, "situacao": "PG", "total": 15.0},
        ]
        cur = FakeCursor(one=[row], many=[relacionados])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_sync("srv", "bd", 501)
        p = r["pedido"]
        assert p["referencia"] == "77"
        assert p["pedidos_relacionados"] == [
            {"pedido": 77, "situacao": "A", "situacao_label": "Aberto", "total": 16.0},
            {"pedido": 502, "situacao": "PG", "situacao_label": "Faturado", "total": 15.0},
        ]
        select_q, params = cur.queries[-1]
        assert params == ("77", 77, 501)  # raiz=77 (da referência), exclui o próprio 501

    def test_sem_pedidos_relacionados_lista_vazia(self, monkeypatch):
        from datetime import date
        row = {
            "pedido": 1, "cliente": 10, "data": date(2026, 7, 16), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A", "total": 0,
            "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "previsao_entrega": None, "hora_entrega": None, "pedido_entregue": 0,
            "cliente_nome": "Fulano", "cliente_cgc": "", "vendedor_nome": "V", "area_descricao": "",
        }
        cur = FakeCursor(one=[row], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_sync("srv", "bd", 1)
        assert r["pedido"]["pedidos_relacionados"] == []


def _forma_pag_req(**over):
    base = dict(servidor="srv", banco="bd", forma_pag="CC", usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return FormaPagSimplesRequest(**base)


class TestSetFormaPagSimples:
    """Combobox simples 'Forma de Pagamento' do cabeçalho — grava direto ao
    trocar (não só no Gravar normal). Achado 2026-07-16: sem isso, o
    usuário selecionava a forma na tela e o backend nunca via a mudança se
    ele clicasse em "Faturar Pedido" antes de "Gravar" — Faturar bloqueava
    com "Defina a Forma de Pagamento do Pedido!" mesmo com uma forma já
    "selecionada" visualmente."""

    def test_grava_com_pedido_aberto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 17605)
        assert r["success"] is True
        update_q, params = cur.queries[-1]
        assert "UPDATE pedido_venda SET forma_pag=%s WHERE pedido=%s" == update_q
        assert params == ("CC", 17605)

    def test_grava_com_pedido_fechado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 17605)
        assert r["success"] is True

    def test_bloqueia_pedido_faturado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 17605)
        assert r["success"] is False
        assert "não pode ser alterado" in r["message"].lower()

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_limpar_forma_pagamento(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(forma_pag=""), 17605)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert params == (None, 17605)


def _qtd_pessoas_req(**over):
    base = dict(servidor="srv", banco="bd", qtd_pessoas=4, usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return QtdPessoasRequest(**base)


class TestSetQtdPessoas:
    """Painel de Pedidos (Mesa/Comanda/Balcão) — quantidade de pessoas,
    grava direto no card (mesmo raciocínio de TestSetFormaPagSimples)."""

    def test_grava_com_pedido_aberto(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._set_qtd_pessoas_sync(_qtd_pessoas_req(), 17605)
        assert r["success"] is True
        update_q, params = cur.queries[-1]
        assert "UPDATE pedido_venda SET qtd_pessoas=%s WHERE pedido=%s" == update_q
        assert params == (4, 17605)

    def test_grava_com_pedido_fechado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._set_qtd_pessoas_sync(_qtd_pessoas_req(), 17605)
        assert r["success"] is True

    def test_bloqueia_pedido_faturado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._set_qtd_pessoas_sync(_qtd_pessoas_req(), 17605)
        assert r["success"] is False
        assert "não pode ser alterado" in r["message"].lower()

    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._set_qtd_pessoas_sync(_qtd_pessoas_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_zero_ou_none_grava_null(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._set_qtd_pessoas_sync(_qtd_pessoas_req(qtd_pessoas=0), 17605)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert params == (None, 17605)


class TestListEGetExpoemLocalizacaoEQtdPessoas:
    """Painel de Pedidos — Localização e Qtd. Pessoas precisam aparecer
    tanto na listagem (cards) quanto na leitura de um pedido só."""

    def test_list_expoe_localizacao_e_qtd_pessoas(self, monkeypatch):
        row = {
            "pedido": 1, "data": None, "validade": None, "situacao": "A", "total": 50.0,
            "cliente": 10, "cliente_nome": "Cliente X", "cliente_fantasia": "",
            "vendedor": 20, "vendedor_nome": "Vend", "hora_aberto": "10:00:00",
            "tipo_cliente_descricao": "MESA", "localizacao_descricao": "Mesa 5", "qtd_pessoas": 4,
        }
        cur = FakeCursor(one=[{"c": 1}], many=[[row]])
        _patch(monkeypatch, cur)
        r = svc._list_pedidos_sync(_list_req())
        item = r["items"][0]
        assert item["localizacao_descricao"] == "Mesa 5"
        assert item["qtd_pessoas"] == 4

    def test_list_qtd_pessoas_none_quando_nao_informado(self, monkeypatch):
        row = {
            "pedido": 1, "data": None, "validade": None, "situacao": "A", "total": 50.0,
            "cliente": 10, "cliente_nome": "Cliente X", "cliente_fantasia": "",
            "vendedor": 20, "vendedor_nome": "Vend", "hora_aberto": "10:00:00",
            "tipo_cliente_descricao": "", "localizacao_descricao": "", "qtd_pessoas": None,
        }
        cur = FakeCursor(one=[{"c": 1}], many=[[row]])
        _patch(monkeypatch, cur)
        r = svc._list_pedidos_sync(_list_req())
        assert r["items"][0]["qtd_pessoas"] is None

    def test_get_expoe_qtd_pessoas(self, monkeypatch):
        from datetime import date
        row = {
            "pedido": 1, "cliente": 10, "data": date(2026, 7, 17), "validade": None,
            "vendedor": 20, "hora_aberto": "10:00:00", "obs": "", "situacao": "A", "total": 0,
            "NOME_CLIENTE": "", "TELEFONE_CLIENTE": "", "area_atuacao": None,
            "previsao_entrega": None, "hora_entrega": None, "pedido_entregue": 0,
            "cliente_nome": "Fulano", "cliente_cgc": "", "vendedor_nome": "V", "area_descricao": "",
            "qtd_pessoas": 6,
        }
        cur = FakeCursor(one=[row], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._get_pedido_sync("srv", "bd", 1)
        assert r["pedido"]["qtd_pessoas"] == 6


def _pedido_save_req(**over):
    base = dict(servidor="srv", banco="bd", cliente=10, vendedor=2, usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return PedidoSaveRequest(**base)


class TestSalvarPedidoCampoTipo:
    """Combobox "Tipo" do Pedido Bar (pedido_venda.tipo) — separado do tipo
    do CLIENTE (cliente.cliente_forn). Cliente reservado Mesa/Comanda/
    Balcão sempre trava o pedido no próprio tipo, ignorando o que foi
    pedido; fora isso, o tipo pedido é livre. Pedido explícito do usuário,
    2026-07-18."""

    def test_cliente_reservado_mesa_ignora_tipo_pedido_e_usa_o_proprio(self, monkeypatch):
        # Detecção é pelo NOME FANTASIA (mesmo critério de texto de
        # `clientes_service._cliente_mesa_ou_comanda`), não pelo tipo
        # resolvido via cliente_forn — um cliente comum com cliente_forn=1
        # (Mesa) mas fantasia normal NÃO trava (ver teste
        # `test_cliente_tipo_mesa_mas_nao_reservado_aceita_tipo_pedido`).
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "M7", "fantasia": "MESA 7", "cliente_forn": 1, "tel": ""},
            {"pedido": 500},
        ])
        _patch(monkeypatch, cur)
        # Tenta forçar tipo=4 (Entrega) num cliente reservado Mesa — deve
        # ser ignorado, o pedido grava o tipo do próprio cliente (1).
        r = svc._save_pedido_sync(_pedido_save_req(cliente=10, tipo=4), None)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert 1 in params
        assert 4 not in params

    def test_cliente_comanda_reservado_tambem_trava_proprio_tipo(self, monkeypatch):
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "C3", "fantasia": "COMANDA 3", "cliente_forn": 3, "tel": ""},
            {"pedido": 501},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_sync(_pedido_save_req(cliente=11, tipo=4), None)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert 3 in params
        assert 4 not in params

    def test_cliente_balcao_reservado_tambem_trava_proprio_tipo(self, monkeypatch):
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "BALCAO", "fantasia": "BALCÃO", "cliente_forn": 2, "tel": ""},
            {"pedido": 504},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_sync(_pedido_save_req(cliente=15, tipo=4), None)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert 2 in params
        assert 4 not in params

    def test_cliente_tipo_mesa_mas_nao_reservado_aceita_tipo_pedido(self, monkeypatch):
        # Cliente REAL (fantasia comum) cujo cliente_forn aponta pra Mesa —
        # não é um placeholder físico, então o tipo do pedido fica livre
        # (exemplo do usuário: "um cliente do tipo mesa pode ser adicionado
        # na lista como entrega, o tipo dele não muda, mas o tipo de
        # pedido será entrega").
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "Fulano da Silva", "fantasia": "", "cliente_forn": 1, "tel": ""},
            {"pedido": 505},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_sync(_pedido_save_req(cliente=16, tipo=4), None)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert 4 in params

    def test_cliente_entrega_aceita_tipo_pedido_diferente(self, monkeypatch):
        # Cliente do tipo Entrega pode ser lançado como Comanda na lista —
        # o tipo do CLIENTE não muda, só o do PEDIDO.
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "Cliente Real", "fantasia": "", "cliente_forn": 4, "tel": ""},
            {"pedido": 502},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_sync(_pedido_save_req(cliente=12, tipo=3), None)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert 3 in params

    def test_sem_tipo_informado_e_cliente_nao_reservado_fica_nulo(self, monkeypatch):
        cur = FakeCursor(one=[
            {"STATUS_CLIENTE": "A"},
            {"nome": "Cliente Real", "fantasia": "", "cliente_forn": None, "tel": ""},
            {"pedido": 503},
        ])
        _patch(monkeypatch, cur)
        r = svc._save_pedido_sync(_pedido_save_req(cliente=13), None)
        assert r["success"] is True
        _, params = cur.queries[-1]
        assert None in params

    def test_update_tambem_aplica_regra_do_tipo(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"situacao": "A"},
                {"nome": "M1", "fantasia": "MESA 1", "cliente_forn": 1, "tel": ""},
            ],
            rowcount=1,
        )
        _patch(monkeypatch, cur)
        r = svc._save_pedido_sync(_pedido_save_req(cliente=14, tipo=4), 700)
        assert r["success"] is True
        update_q, params = cur.queries[-1]
        assert "UPDATE pedido_venda SET" in update_q
        assert "tipo=%s" in update_q
        assert 1 in params
        assert 4 not in params
