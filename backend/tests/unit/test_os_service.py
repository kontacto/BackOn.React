"""Testes unitários de os_service — combobox simples 'Forma de Pagamento'
do cabeçalho (grava direto ao trocar, não só no Gravar normal). Mesmo
achado/raciocínio de `test_pedidos_service.py::TestSetFormaPagSimples`,
só a tabela/coluna muda (`os.forma_pagamento`). Também cobre Faturar O.S.
(`_faturar_os_sync`, 2026-07-21 — pré-requisito do Gestor de Comandas) e a
bifurcação de faturamento Garantia×Cliente (2026-08-02)."""
import services.os_service as svc
from models.schemas import FormaPagSimplesRequest, FecharRequest, FaturarOSRequest, OSSaveRequest


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


def _forma_pag_req(**over):
    base = dict(servidor="srv", banco="bd", forma_pag="DI", usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return FormaPagSimplesRequest(**base)


class TestSetFormaPagSimples:
    def test_grava_com_os_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 55)
        assert r["success"] is True
        update_q, params = cur.queries[-1]
        assert "UPDATE os SET forma_pagamento=%s WHERE codigo=%s" == update_q
        assert params == ("DI", 55)

    def test_bloqueia_os_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 55)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"].lower()

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._set_forma_pag_simples_sync(_forma_pag_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()


def _faturar_req(**over):
    base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
    base.update(over)
    return FaturarOSRequest(**base)


class TestFaturarOS:
    """Faturar O.S. (`_faturar_os_sync`) — pré-requisito do Gestor de
    Comandas (2026-07-21): gera Comanda/movimentação/COMANDA_OS igual ao
    Pedido Bar, mas SEMPRE exige a OS já Fechada (sem o atalho "fecha e
    fatura junto" do Pedido Bar — O.S. nunca teve isso). Estes testes cobrem
    o caso comum (só itens Cliente paga, `situacao=0`) — a bifurcação
    Garantia×Cliente (itens `situacao<>0`) está em
    `TestFaturarOSBifurcacaoGarantia` logo abaixo."""

    def test_fatura_com_sucesso_gera_comanda_e_marca_pg(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 150.0, "area_atuacao": 2}
        itens = [
            {"codigo_interno": "P001", "quant": 2.0, "p_venda": 50.0, "custo_os": 30.0, "vendedor": 20},
            {"codigo_interno": "S001", "quant": 1.0, "p_venda": 50.0, "custo_os": 0.0, "vendedor": 21},
        ]
        # fetchone(): os_row, _recalc_os_total->{valor:150}, totais por
        # bloco (só cliente pendente), {comanda:501}, _is_peca(P001)->achou,
        # _is_peca(S001)->não achou
        cur = FakeCursor(
            one=[
                os_row, {"valor": 150.0}, {"total_cliente": 150.0, "total_garantia": 0.0},
                {"comanda": 501}, {"ok": 1}, None,
            ],
            many=[itens],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is True
        assert r["situacao"] == "PG"
        assert r["comanda"] == 501
        assert r["comanda_garantia"] is None
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any("INSERT INTO COMANDA_OS" in q for q in queries)
        assert any("UPDATE os SET situacao='PG'" in q for q in queries)
        # Reservado_os só é liberado pra peça (P001) — S001 não existe em pecas.
        reservado_updates = [p for q, p in cur.queries if "SET reservado_os" in q]
        assert reservado_updates == [(2.0, "P001")]
        assert sum(1 for q in queries if "INSERT INTO movimentacao" in q) == 2
        # Vendedor por item (não um vendedor único de cabeçalho, diferente do Pedido).
        mov_params = [p for q, p in cur.queries if "INSERT INTO movimentacao" in q]
        assert mov_params[0][4] == 20  # vendedor do item P001
        assert mov_params[1][4] == 21  # vendedor do item S001
        # Bloco cliente não marca `faturado` (a O.S. inteira já vira PG).
        assert not any("SET faturado=1" in q for q in queries)

    def test_fatura_recalcula_valor_ignorando_os_valor_desatualizado(self, monkeypatch):
        """os.valor pode ficar desatualizado (0/errado) se a O.S. veio do
        legado ou de algum outro processo que não passou por
        `_recalc_os_total` — ver PENDENCIAS.md > "O.S. Completa" > "Risco
        identificado". Faturar precisa somar os_produto de novo em vez de
        confiar cegamente na coluna `valor`."""
        # os.valor=0 (desatualizado/errado) — a soma real dos itens é 200.
        os_row = {"situacao": "F", "cliente": 10, "valor": 0.0, "area_atuacao": 2}
        itens = [{"codigo_interno": "P001", "quant": 2.0, "p_venda": 100.0, "custo_os": 60.0, "vendedor": 20}]
        cur = FakeCursor(
            one=[os_row, {"valor": 200.0}, {"total_cliente": 200.0, "total_garantia": 0.0}, {"comanda": 700}, {"ok": 1}],
            many=[itens],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is True
        comanda_insert = [p for q, p in cur.queries if q.startswith("INSERT INTO comanda")][0]
        assert comanda_insert[1] == 200.0  # valor_venda usa o total recalculado, não o os.valor=0 cru
        assert any(q.startswith("UPDATE os SET valor") for q, _ in cur.queries)

    def test_bloqueia_os_aberta_exige_fechar_primeiro(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "cliente": 10, "valor": 100.0, "area_atuacao": 2}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert "feche a os" in r["message"].lower()

    def test_bloqueia_os_ja_faturada_sem_garantia_pendente(self, monkeypatch):
        os_row = {"situacao": "PG", "cliente": 10, "valor": 100.0, "area_atuacao": 2}
        cur = FakeCursor(one=[os_row, {"valor": 100.0}, {"total": 0.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert "já faturada" in r["message"].lower()

    def test_bloqueia_os_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C", "cliente": 10, "valor": 100.0, "area_atuacao": 2}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert "não pode ser faturada" in r["message"].lower()

    def test_os_nao_encontrada_ao_faturar(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 100.0, "area_atuacao": 2}
        cur = FakeCursor(one=[os_row])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(master=False, classe=2), 55)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_tela_os_comp_checa_permissao_propria(self, monkeypatch):
        """A O.S. Completa chama a MESMA função passando tela="OS_COMP" —
        confirma que a checagem de permissão usa esse catálogo, não "OS"
        (mesmo padrão já coberto pro Pedido Completo)."""
        os_row = {"situacao": "F", "cliente": 10, "valor": 0.0, "area_atuacao": 2}
        cur = FakeCursor(
            one=[os_row, {"ok": 1}, {"valor": 0.0}, {"total_cliente": 100.0, "total_garantia": 0.0}, {"comanda": 900}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(master=False, classe=3), 55, tela="OS_COMP")
        assert r["success"] is True
        perm_query = [p for q, p in cur.queries if "FROM permissoes" in q][0]
        assert perm_query[2] == "OS_COMP"
        assert perm_query[3] == "FATURAR"


class TestFaturarOSBifurcacaoGarantia:
    """Bifurcação de faturamento Garantia×Cliente (`Command2_Click`/
    `GeraComanda`, `FrmTraOsNew.frm`, 2026-08-02) — itens `situacao=0`
    (Cliente paga) e `situacao<>0` (Garantia/Interno/Contrato) viram
    Comandas separadas, cada bloco com sua própria forma de pagamento."""

    def test_ambos_blocos_pendentes_sem_escolha_pede_needs_choice(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 300.0, "area_atuacao": 2}
        cur = FakeCursor(one=[os_row, {"valor": 300.0}, {"total_cliente": 200.0, "total_garantia": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert r["needs_choice"] is True
        assert r["total_cliente"] == 200.0
        assert r["total_garantia"] == 100.0

    def test_bucket_invalido_e_tratado_como_ambiguo(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 300.0, "area_atuacao": 2}
        cur = FakeCursor(one=[os_row, {"valor": 300.0}, {"total_cliente": 200.0, "total_garantia": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(faturar_bucket="xyz"), 55)
        assert r["success"] is False
        assert r["needs_choice"] is True

    def test_escolhe_cliente_fatura_so_esse_bloco(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 300.0, "area_atuacao": 2}
        cur = FakeCursor(
            one=[os_row, {"valor": 300.0}, {"total_cliente": 200.0, "total_garantia": 100.0}, {"comanda": 601}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(faturar_bucket="cliente"), 55)
        assert r["success"] is True
        assert r["comanda"] == 601
        assert r["comanda_garantia"] is None
        assert any(q.startswith("UPDATE os SET situacao='PG'") for q, _ in cur.queries)
        assert not any("SET faturado=1" in q for q, _ in cur.queries)

    def test_escolhe_garantia_sem_forma_pagamento_definida_bloqueia(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 300.0, "area_atuacao": 2, "forma_pagamento_garantia": None}
        cur = FakeCursor(one=[os_row, {"valor": 300.0}, {"total_cliente": 200.0, "total_garantia": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(faturar_bucket="garantia"), 55)
        assert r["success"] is False
        assert "forma de pagamento de garantia" in r["message"].lower()

    def test_escolhe_garantia_fatura_e_marca_faturado_nos_itens(self, monkeypatch):
        os_row = {
            "situacao": "F", "cliente": 10, "valor": 300.0, "area_atuacao": 2,
            "forma_pagamento_garantia": "DI",
        }
        itens_garantia = [
            {"cod_os_prod": 9, "codigo_interno": "P002", "quant": 1.0, "p_venda": 100.0, "custo_os": 50.0, "vendedor": 22},
        ]
        cur = FakeCursor(
            one=[os_row, {"valor": 300.0}, {"total_cliente": 200.0, "total_garantia": 100.0}, {"comanda": 602}, {"ok": 1}],
            many=[itens_garantia],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(faturar_bucket="garantia"), 55)
        assert r["success"] is True
        assert r["comanda"] is None
        assert r["comanda_garantia"] == 602
        faturado_updates = [p for q, p in cur.queries if "SET faturado=1" in q]
        assert faturado_updates == [(9,)]

    def test_escolhe_ambos_gera_2_comandas(self, monkeypatch):
        os_row = {
            "situacao": "F", "cliente": 10, "valor": 300.0, "area_atuacao": 2,
            "forma_pagamento_garantia": "DI",
        }
        itens_cliente = [{"codigo_interno": "P001", "quant": 1.0, "p_venda": 200.0, "custo_os": 100.0, "vendedor": 20}]
        itens_garantia = [
            {"cod_os_prod": 9, "codigo_interno": "P002", "quant": 1.0, "p_venda": 100.0, "custo_os": 50.0, "vendedor": 22},
        ]
        cur = FakeCursor(
            one=[
                os_row, {"valor": 300.0}, {"total_cliente": 200.0, "total_garantia": 100.0},
                {"comanda": 701}, {"ok": 1}, {"comanda": 702}, {"ok": 1},
            ],
            many=[itens_cliente, itens_garantia],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(faturar_bucket="ambos"), 55)
        assert r["success"] is True
        assert r["comanda"] == 701
        assert r["comanda_garantia"] == 702
        assert sum(1 for q, _ in cur.queries if q.startswith("INSERT INTO comanda")) == 2
        assert sum(1 for q, _ in cur.queries if "INSERT INTO COMANDA_OS" in q) == 2

    def test_so_garantia_pendente_fatura_automaticamente_sem_pedir_escolha(self, monkeypatch):
        """Sem ambiguidade (bloco cliente zerado) — decide sozinha, sem
        `needs_choice`, igual ao ramo "só garantia" do legado (que também
        marca a O.S. como PG mesmo sem nenhum item Cliente paga)."""
        os_row = {
            "situacao": "F", "cliente": 10, "valor": 100.0, "area_atuacao": 2,
            "forma_pagamento_garantia": "DI",
        }
        itens_garantia = [
            {"cod_os_prod": 5, "codigo_interno": "S001", "quant": 1.0, "p_venda": 100.0, "custo_os": 0.0, "vendedor": 21},
        ]
        cur = FakeCursor(
            one=[os_row, {"valor": 100.0}, {"total_cliente": 0.0, "total_garantia": 100.0}, {"comanda": 801}, None],
            many=[itens_garantia],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is True
        assert r["comanda"] is None
        assert r["comanda_garantia"] == 801
        assert r["situacao"] == "PG"
        assert any(q.startswith("UPDATE os SET situacao='PG'") for q, _ in cur.queries)

    def test_so_garantia_pendente_sem_forma_pagamento_bloqueia(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 100.0, "area_atuacao": 2, "forma_pagamento_garantia": None}
        cur = FakeCursor(one=[os_row, {"valor": 100.0}, {"total_cliente": 0.0, "total_garantia": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert "forma de pagamento de garantia" in r["message"].lower()

    def test_sem_itens_pendentes_em_nenhum_bloco_bloqueia(self, monkeypatch):
        os_row = {"situacao": "F", "cliente": 10, "valor": 0.0, "area_atuacao": 2}
        cur = FakeCursor(one=[os_row, {"valor": 0.0}, {"total_cliente": 0.0, "total_garantia": 0.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert "a serem faturados" in r["message"].lower()

    def test_ja_paga_fatura_garantia_pendente_incluida_depois(self, monkeypatch):
        """O.S. já Faturada (PG) — itens de Garantia/Interno/Contrato
        incluídos DEPOIS do primeiro faturamento (`faturado=0`) ainda podem
        ser faturados numa passada nova, sem reabrir a O.S."""
        os_row = {
            "situacao": "PG", "cliente": 10, "valor": 100.0, "area_atuacao": 2,
            "forma_pagamento_garantia": "DI",
        }
        itens_garantia = [
            {"cod_os_prod": 11, "codigo_interno": "P003", "quant": 1.0, "p_venda": 50.0, "custo_os": 20.0, "vendedor": 23},
        ]
        cur = FakeCursor(
            one=[os_row, {"valor": 100.0}, {"total": 50.0}, {"comanda": 901}, {"ok": 1}],
            many=[itens_garantia],
        )
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is True
        assert r["comanda_garantia"] == 901
        assert r["situacao"] == "PG"
        faturado_updates = [p for q, p in cur.queries if "SET faturado=1" in q]
        assert faturado_updates == [(11,)]
        # já estava PG — não repete a transição de situação.
        assert not any(q.startswith("UPDATE os SET situacao='PG'") for q, _ in cur.queries)

    def test_ja_paga_sem_forma_pagamento_garantia_bloqueia(self, monkeypatch):
        os_row = {
            "situacao": "PG", "cliente": 10, "valor": 100.0, "area_atuacao": 2,
            "forma_pagamento_garantia": None,
        }
        cur = FakeCursor(one=[os_row, {"valor": 100.0}, {"total": 50.0}])
        _patch(monkeypatch, cur)
        r = svc._faturar_os_sync(_faturar_req(), 55)
        assert r["success"] is False
        assert "forma de pagamento de garantia" in r["message"].lower()


class TestReabrirOS:
    """Reabrir O.S. (`_reabrir_os_sync`) — funcionalidade NOVA, sem
    precedente em nenhuma versão da O.S. até agora (nem Mobile). Só F->A
    (mesmo raciocínio do Pedido: o legado só habilita o botão nesse
    estado). NÃO reverte estoque — diferente do Pedido, o Fechar de O.S.
    não movimenta estoque (a reserva acontece na inclusão do item, só o
    Faturar libera), então Reabrir não tem nada pra estornar."""

    def _req(self, **over):
        base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
        base.update(over)
        return FecharRequest(**base)

    def test_reabre_os_fechada_sem_mexer_em_estoque(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(), 55)
        assert r["success"] is True
        assert r["situacao"] == "A"
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any("UPDATE os SET situacao='A'" in q for q in queries)
        assert not any("os_produto" in q for q in queries)

    def test_bloqueia_situacao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(), 55)
        assert r["success"] is False
        assert "reaberta" in r["message"].lower()

    def test_bloqueia_situacao_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(), 55)
        assert r["success"] is False

    def test_bloqueia_situacao_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(), 55)
        assert r["success"] is False

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(master=False, classe=2), 55)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_tela_os_comp_checa_permissao_propria(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}, {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_os_sync(self._req(master=False, classe=3), 55, tela="OS_COMP")
        assert r["success"] is True
        perm_query = [p for q, p in cur.queries if "FROM permissoes" in q][0]
        assert perm_query[2] == "OS_COMP"
        assert perm_query[3] == "REABRIR"


class TestCancelarOS:
    """Cancelar O.S. (`_cancelar_os_sync`) — funcionalidade NOVA. A/F->C
    (nunca Paga). SEMPRE estorna a reserva de estoque dos itens
    não-cancelados via `_mover_estoque` delta negativo — diferente do
    Pedido (que só estorna se estava Fechado), a reserva da O.S. acontece
    na INCLUSÃO do item, não no Fechar, então tanto faz a O.S. estar
    Aberta ou Fechada: sempre há reserva pra estornar."""

    def _req(self, **over):
        base = dict(servidor="srv", banco="bd", classe=1, master=True, usuario_alteracao=1, plataforma="web")
        base.update(over)
        return FecharRequest(**base)

    def test_cancela_os_aberta_estorna_pecas(self, monkeypatch):
        itens = [
            {"codigo_interno": "P001", "quant": 2.0},
            {"codigo_interno": "S001", "quant": 1.0},
        ]
        # fetchone(): situacao, depois _is_peca(P001)->achou, _is_peca(S001)->não achou
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}, None], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(), 55)
        assert r["success"] is True
        assert r["situacao"] == "C"
        assert conn.committed is True
        queries = [q for q, _ in cur.queries]
        assert any("UPDATE os SET situacao='C'" in q for q in queries)
        estorno = [p for q, p in cur.queries if "SET qtd = ISNULL" in q]
        assert estorno == [(-2.0, -2.0, "P001")]  # delta negativo: qtd += 2, reservado_os -= 2

    def test_cancela_os_fechada_tambem_estorna(self, monkeypatch):
        itens = [{"codigo_interno": "P002", "quant": 3.0}]
        cur = FakeCursor(one=[{"situacao": "F"}, {"ok": 1}], many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(), 55)
        assert r["success"] is True
        assert conn.committed is True
        estorno = [p for q, p in cur.queries if "SET qtd = ISNULL" in q]
        assert estorno == [(-3.0, -3.0, "P002")]

    def test_bloqueia_os_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(), 55)
        assert r["success"] is False
        assert "cancelada" in r["message"].lower()

    def test_bloqueia_os_ja_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(), 55)
        assert r["success"] is False

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(master=False, classe=2), 55)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()

    def test_acao_default_reaproveita_permissao_situacao(self, monkeypatch):
        """`acao` default é "SITUACAO" — mesma permissão de Fechar/Reabrir,
        evita exigir reconcessão numa ação nova (mesmo raciocínio já usado
        pro Pedido Completo)."""
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(master=False, classe=3), 55)
        assert r["success"] is True
        perm_query = [p for q, p in cur.queries if "FROM permissoes" in q][0]
        assert perm_query[3] == "SITUACAO"

    def test_tela_os_comp_checa_permissao_propria(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._cancelar_os_sync(self._req(master=False, classe=3), 55, tela="OS_COMP")
        assert r["success"] is True
        perm_query = [p for q, p in cur.queries if "FROM permissoes" in q][0]
        assert perm_query[2] == "OS_COMP"


class TestSalvarOSAreaAtuacao:
    """Réplica de `VerificaAreaAtuacao` — bloqueia nova O.S. quando o
    funcionário logado não está vinculado à Área de Atuação selecionada.
    Ver PENDENCIAS.md > "MDI Principal (VB6)"."""

    def _os_req(self, **over):
        base = dict(servidor="srv", banco="bd", cliente=10, usuario_alteracao=5, classe=1, plataforma="web")
        base.update(over)
        return OSSaveRequest(**base)

    def test_funcionario_sem_area_permitida_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"STATUS_CLIENTE": "A"}, {"descricao": "Oficina"}],
            many=[[{"area": 1}, {"area": 2}]],
        )
        _patch(monkeypatch, cur)
        r = svc._save_os_sync(self._os_req(area_atuacao=9), None)
        assert r["success"] is False
        assert "Oficina" in r["message"]


class TestSalvarOSChassiObrigatorio:
    """`controle.exige_chassi_os` — bloqueia gravar O.S. do segmento Oficina
    sem Chassi. Ver `_chassi_obrigatorio_ok` (pedido_common.py) e
    PENDENCIAS.md > "O.S. — Chassi obrigatório (Oficina)"."""

    def _os_req(self, **over):
        base = dict(servidor="srv", banco="bd", cliente=10, usuario_alteracao=5, classe=1, plataforma="web")
        base.update(over)
        return OSSaveRequest(**base)

    def test_oficina_com_flag_ligado_e_chassi_vazio_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"STATUS_CLIENTE": "A"},
                {"CONTROLA_ABERTURA_DIA": True},
                {"Oficina": True},
                {"exige_chassi_os": True},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._save_os_sync(self._os_req(chassi=""), None)
        assert r["success"] is False
        assert "Chassi" in r["message"]

    def test_oficina_com_flag_ligado_e_chassi_preenchido_libera(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"STATUS_CLIENTE": "A"},
                {"CONTROLA_ABERTURA_DIA": True},
                {"novo": 501},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._save_os_sync(self._os_req(chassi="9BW1234567890ABCD"), None)
        assert r["success"] is True

    def test_sem_modulo_oficina_libera_mesmo_com_chassi_vazio(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"STATUS_CLIENTE": "A"},
                {"CONTROLA_ABERTURA_DIA": True},
                {"Oficina": False},
                {"novo": 502},
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._save_os_sync(self._os_req(chassi=""), None)
        assert r["success"] is True
