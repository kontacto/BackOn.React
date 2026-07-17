"""Testes unitários dos helpers de Forma de Pagamento em pedido_common.py —
réplica de `Fecha_FPAG_Dav`/`TotalizaDav`/`QtdFormas` (FormaPagamentoDAV.bas)
e do lançamento manual/automático (FrmForPag.frm). Cobre Pedido (PED) e O.S.
(OS) via o mesmo `DavPagamento` — tela genérica no legado, confirmada pelo
usuário 2026-07-16 ("esse frm de forma de pagto atende pedido bar, pedido
geral e o.s.")."""
import services.pedido_common as pc


class SqlFakeCursor:
    """Cursor fake que responde por CASAMENTO DE SUBSTRING no SQL da última
    query executada, não por ordem de chamada — necessário porque as
    funções testadas aqui disparam várias queries parecidas em loop (uma
    por tabela de forma de pagamento, 8 tabelas). Sem regra casada,
    fetchone()->None / fetchall()->[] (equivalente a "tabela vazia")."""

    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self._last_q = ""
        self._one_rules: list[tuple[str, object]] = []
        self._many_rules: list[tuple[str, object]] = []

    def when_one(self, substr: str, value) -> "SqlFakeCursor":
        self._one_rules.append((substr, value))
        return self

    def when_many(self, substr: str, value) -> "SqlFakeCursor":
        self._many_rules.append((substr, value))
        return self

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_q = q

    def fetchone(self):
        for substr, val in self._one_rules:
            if substr in self._last_q:
                return val
        return None

    def fetchall(self):
        for substr, val in self._many_rules:
            if substr in self._last_q:
                return val
        return []

    def close(self):
        pass


def _dav(tipo=pc.DAV_PED, documento=77, valor=100.0, forma_padrao="") -> pc.DavPagamento:
    return pc.DavPagamento(tipo=tipo, documento=documento, situacao="A", valor=valor, forma_padrao=forma_padrao)


class TestTotalizaDav:
    def test_soma_as_8_tabelas_ped(self):
        cur = (
            SqlFakeCursor()
            .when_one("pedido_venda_dinheiro", {"s": 50.0})
            .when_one("pedido_venda_cartao", {"s": 30.0})
        )
        total = pc._totaliza_dav(cur, _dav())
        assert total == 80.0

    def test_sem_nenhuma_forma_lancada_retorna_zero(self):
        cur = SqlFakeCursor()
        assert pc._totaliza_dav(cur, _dav()) == 0.0

    def test_usa_tabelas_os_quando_tipo_os(self):
        cur = SqlFakeCursor().when_one("os_dinheiro", {"s": 20.0})
        total = pc._totaliza_dav(cur, _dav(tipo=pc.DAV_OS, documento=5))
        assert total == 20.0
        # Confirma que consultou a tabela de OS (fk=os), não pedido_venda.
        assert any("os_dinheiro" in q and "WHERE os=" in q for q, _ in cur.queries)


class TestQtdFormas:
    def test_conta_linhas_de_todas_as_tabelas(self):
        cur = (
            SqlFakeCursor()
            .when_one("pedido_venda_dinheiro", {"c": 1})
            .when_one("pedido_venda_cheque", {"c": 2})
        )
        assert pc._qtd_formas(cur, _dav()) == 3

    def test_zero_quando_nada_lancado(self):
        cur = SqlFakeCursor()
        assert pc._qtd_formas(cur, _dav()) == 0


class TestUnicaFormaExistente:
    def test_uma_linha_retorna_tipo_e_sequencia(self):
        cur = SqlFakeCursor().when_many("pedido_venda_dinheiro", [{"sequencia": 10}])
        assert pc._unica_forma_existente(cur, _dav()) == ("DI", 10)

    def test_duas_linhas_em_tabelas_diferentes_retorna_none(self):
        cur = (
            SqlFakeCursor()
            .when_many("pedido_venda_dinheiro", [{"sequencia": 10}])
            .when_many("pedido_venda_cartao", [{"sequencia": 11}])
        )
        assert pc._unica_forma_existente(cur, _dav()) is None

    def test_nenhuma_linha_retorna_none(self):
        cur = SqlFakeCursor()
        assert pc._unica_forma_existente(cur, _dav()) is None


class TestFechaFpagDav:
    """Réplica de `Fecha_FPAG_Dav` — ver Command111_Click (FrmManPedBar.frm)
    e o próprio `.bas`."""

    def test_total_ja_bate_nao_faz_nada(self):
        cur = SqlFakeCursor().when_one("pedido_venda_dinheiro", {"s": 100.0})
        erro = pc._fecha_fpag_dav(cur, _dav(valor=100.0))
        assert erro is None
        assert not any("UPDATE" in q or "INSERT" in q for q, _ in cur.queries)

    def test_uma_forma_diverge_corrige_automaticamente(self):
        cur = (
            SqlFakeCursor()
            .when_one("SELECT SUM(valor_pago)", {"s": 80.0})  # total lançado != 100
            .when_many("pedido_venda_dinheiro", [{"sequencia": 5}])
        )
        erro = pc._fecha_fpag_dav(cur, _dav(valor=100.0))
        assert erro is None
        update_q = [
            (q, p) for q, p in cur.queries
            if q.startswith("UPDATE pedido_venda_dinheiro") and "valor_pago" in q
        ]
        assert update_q == [("UPDATE pedido_venda_dinheiro SET valor_pago=%s WHERE sequencia=%s", (100.0, 5))]

    def test_zero_formas_com_padrao_lanca_automaticamente(self):
        cur = SqlFakeCursor().when_one("forma_pagamento WHERE codigo", {"tipo": "DI"})
        erro = pc._fecha_fpag_dav(cur, _dav(valor=100.0, forma_padrao="001"))
        assert erro is None
        assert any(
            q.startswith("INSERT INTO pedido_venda_dinheiro") and p == (77, "001", 100.0)
            for q, p in cur.queries
        )

    def test_zero_formas_sem_padrao_nao_bloqueia_aqui(self):
        """Fecha_FPAG_Dav sozinho não bloqueia — quem decide a mensagem
        "Defina a Forma de Pagamento" é o chamador (`_fechar_pedido_itens`/
        `_fechar_os_sync`), só quando valor > 0."""
        cur = SqlFakeCursor()
        erro = pc._fecha_fpag_dav(cur, _dav(valor=100.0, forma_padrao=""))
        assert erro is None

    def test_duas_formas_divergentes_bloqueia(self):
        cur = (
            SqlFakeCursor()
            .when_one("SELECT SUM(valor_pago)", {"s": 60.0})
            .when_many("pedido_venda_dinheiro", [{"sequencia": 5}])
            .when_many("pedido_venda_cartao", [{"sequencia": 6}])
            .when_one("COUNT(*) AS c FROM pedido_venda_dinheiro", {"c": 1})
            .when_one("COUNT(*) AS c FROM pedido_venda_cartao", {"c": 1})
        )
        erro = pc._fecha_fpag_dav(cur, _dav(valor=100.0))
        assert erro == "Informar a Forma de Pagamento corretamente!"

    def test_usa_tabelas_os_quando_tipo_os(self):
        """Mesma lógica, tabelas os_* — confirma o compartilhamento real
        entre Pedido e O.S. (mesmo Type_FormaPagPedOS do legado)."""
        cur = SqlFakeCursor().when_one("os_dinheiro WHERE os=", {"s": 100.0})
        erro = pc._fecha_fpag_dav(cur, _dav(tipo=pc.DAV_OS, documento=9, valor=100.0))
        assert erro is None


class TestInsereDuplicataParcelada:
    def test_com_prazos_cadastrados_rateia_por_percentual(self):
        cur = SqlFakeCursor().when_many(
            "forma_pag_prazo",
            [{"prazo": 30, "percentual": 60.0}, {"prazo": 60, "percentual": 40.0}],
        )
        pc._insere_duplicata_parcelada(cur, _dav(documento=77), "002", 100.0)
        inserts = [(q, p) for q, p in cur.queries if q.startswith("INSERT INTO pedido_venda_duplicata")]
        assert len(inserts) == 2
        assert inserts[0][1] == (77, "002", 60.0, 30)
        assert inserts[1][1] == (77, "002", 40.0, 60)

    def test_sem_prazo_cadastrado_insere_parcela_unica(self):
        cur = SqlFakeCursor()  # forma_pag_prazo vazio (fetchall default [])
        pc._insere_duplicata_parcelada(cur, _dav(documento=77), "002", 150.0)
        inserts = [(q, p) for q, p in cur.queries if q.startswith("INSERT INTO pedido_venda_duplicata")]
        assert len(inserts) == 1
        assert inserts[0][1] == (77, "002", 150.0)

    def test_ultima_parcela_absorve_arredondamento(self):
        cur = SqlFakeCursor().when_many(
            "forma_pag_prazo",
            [{"prazo": 10, "percentual": 33.33}, {"prazo": 20, "percentual": 33.33}, {"prazo": 30, "percentual": 33.34}],
        )
        pc._insere_duplicata_parcelada(cur, _dav(documento=1), "003", 100.0)
        inserts = [p for q, p in cur.queries if q.startswith("INSERT INTO pedido_venda_duplicata")]
        valores = [p[2] for p in inserts]
        assert round(sum(valores), 2) == 100.0
