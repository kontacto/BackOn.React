"""Testes UNITÁRIOS de pedidos_service — foco no que foi adicionado nesta
rodada: Data/Hora de Entrega, checkbox "Pedido Entregue" (auto-save,
FrmManPedBar.frm Check88_Click) e os filtros do painel "Pedidos Abertos"
(Mesa/Balcão/Entrega/Comanda, Data de Entrega, Ordenar por)."""
import services.pedidos_service as svc
from models.schemas import PedidoEntregueRequest, PedidosListRequest, FecharRequest, FormaPagSimplesRequest


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
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(tipos_cliente=[10, 20]))
        select_q, params = cur.queries[-1]
        assert "c.cliente_forn IN (%s,%s)" in select_q
        assert 10 in params and 20 in params

    def test_data_entrega_filtra_previsao_entrega(self, monkeypatch):
        cur = FakeCursor(one=[{"c": 0}], many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pedidos_sync(_list_req(data_entrega="2026-07-20"))
        select_q, params = cur.queries[-1]
        assert "p.previsao_entrega <= %s" in select_q
        assert "2026-07-20" in params

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
