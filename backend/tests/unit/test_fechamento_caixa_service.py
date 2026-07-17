"""Testes unitários do Fechamento de Caixa — réplica de `frmFechaCaixa.frm`.

Cobre a decisão de arquitetura chave (ver docstring do módulo testado): a
agregação soma `pedido_venda_*`/`os_*` (via COMANDA_PED/comanda_os), não
`comanda_dinheiro`/etc. (tabelas que este app nunca escreve)."""
import services.fechamento_caixa_service as svc


class SqlFakeCursor:
    """Mesmo padrão de `test_pedido_common_forma_pagamento.py` — casamento
    por substring da última query, não por ordem de chamada (a função sob
    teste dispara uma query por tabela de forma de pagamento, em loop)."""

    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self._last_q = ""
        self._many_rules: list[tuple[str, object]] = []

    def when_many(self, substr: str, value) -> "SqlFakeCursor":
        self._many_rules.append((substr, value))
        return self

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_q = q

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def fetchall(self):
        # Casa pela regra de substring MAIS ESPECÍFICA (maior comprimento),
        # não a primeira registrada — necessário porque as cláusulas
        # NOT EXISTS de `_pedidos_faturados_sem_forma_pagamento_sync`
        # contêm "pedido_venda_dinheiro"/etc. como substring, que colidiria
        # com as regras (mais curtas) já registradas pra
        # `_resumo_forma_pagamento_sync` nos mesmos testes.
        matches = [(substr, val) for substr, val in self._many_rules if substr in self._last_q]
        if not matches:
            return []
        return max(matches, key=lambda m: len(m[0]))[1]

    def close(self):
        pass


class FakeConn:
    def __init__(self, cur: SqlFakeCursor):
        self._cur = cur

    def cursor(self, as_dict=True):
        return self._cur

    def close(self):
        pass


class TestResumoFormaPagamento:
    def test_soma_pedido_e_os_juntos_por_descricao(self):
        cur = (
            SqlFakeCursor()
            .when_many("pedido_venda_dinheiro", [{"descricao": "Dinheiro", "tipo": "DI", "nao_totaliza_caixa": False, "total": 100.0}])
            .when_many("pedido_venda_cartao", [{"descricao": "Cartão de Crédito", "tipo": "CC", "nao_totaliza_caixa": False, "total": 50.0}])
        )
        out = svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", None, "atendente", None, False)
        by_desc = {r["descricao"]: r for r in out}
        assert by_desc["Dinheiro"]["valor"] == 100.0
        assert by_desc["Cartão de Crédito"]["valor"] == 50.0

    def test_ignora_grupos_com_valor_zero(self):
        cur = SqlFakeCursor().when_many("pedido_venda_dinheiro", [{"descricao": "Dinheiro", "tipo": "DI", "nao_totaliza_caixa": False, "total": 0.0}])
        out = svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", None, "atendente", None, False)
        assert out == []

    def test_marca_nao_totaliza_caixa(self):
        cur = SqlFakeCursor().when_many("pedido_venda_vale", [{"descricao": "Vale Garantia", "tipo": "VA", "nao_totaliza_caixa": True, "total": 30.0}])
        out = svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", None, "atendente", None, False)
        assert out[0]["nao_totaliza_caixa"] is True

    def test_exibir_garantias_false_filtra_no_sql(self):
        cur = SqlFakeCursor()
        svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", None, "atendente", None, False)
        assert any("FORMA_PAG_GARANTIA" in q for q, _ in cur.queries)

    def test_exibir_garantias_true_nao_filtra_no_sql(self):
        cur = SqlFakeCursor()
        svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", None, "atendente", None, True)
        assert not any("FORMA_PAG_GARANTIA" in q for q, _ in cur.queries)

    def test_filtro_atendente_dav_usa_coluna_certa(self):
        cur = SqlFakeCursor()
        svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", 5, "atendente_dav", None, False)
        assert all("c.atendente_dav AS atend" in q for q, _ in cur.queries)

    def test_filtro_area_aplicado(self):
        cur = SqlFakeCursor()
        svc._resumo_forma_pagamento_sync(cur, "2026-07-01", "2026-07-31", None, "atendente", 3, False)
        assert all("x.area_atuacao = %s" in q for q, _ in cur.queries)
        assert all(3 in p for _, p in cur.queries)


class TestEntradasSaidas:
    def test_agrega_entradas_saidas_despesas(self):
        cur = (
            SqlFakeCursor()
            .when_many("FROM entrada_caixa", [{"descricao": "Suprimento", "total": 200.0}])
            .when_many("FROM saida_caixa", [{"descricao": "Sangria", "total": 80.0}])
            .when_many("FROM despesas", [{"tipo": 0, "total": 10.0}, {"tipo": 1, "total": 5.0}])
        )
        out = svc._entradas_saidas_sync(cur, "2026-07-01", "2026-07-31", None)
        assert out["total_entradas"] == 200.0
        assert out["total_saidas"] == 80.0
        assert out["despesas_com_comprovante"] == 10.0
        assert out["despesas_sem_comprovante"] == 5.0

    def test_sem_dados_retorna_zerado(self):
        cur = SqlFakeCursor()
        out = svc._entradas_saidas_sync(cur, "2026-07-01", "2026-07-31", None)
        assert out["entradas"] == []
        assert out["total_entradas"] == 0.0
        assert out["despesas_com_comprovante"] == 0.0

    def test_filtro_atendente_sempre_coluna_atendente_pura(self):
        cur = SqlFakeCursor()
        svc._entradas_saidas_sync(cur, "2026-07-01", "2026-07-31", 9)
        assert all("atendente = %s" in q for q, _ in cur.queries)


class TestPedidosSemFormaPagamento:
    def test_lista_pedidos_sem_nenhum_lancamento(self):
        cur = SqlFakeCursor().when_many(
            "JOIN pedido_venda pv ON pv.pedido = cp.ped",
            [{"pedido": 17606, "total": 197.0}],
        )
        out = svc._pedidos_faturados_sem_forma_pagamento_sync(cur, "2026-07-16", "2026-07-16", None, "atendente", None)
        assert out == [{"pedido": 17606, "valor": 197.0}]

    def test_sql_tem_not_exists_pras_8_tabelas(self):
        cur = SqlFakeCursor()
        svc._pedidos_faturados_sem_forma_pagamento_sync(cur, "2026-07-16", "2026-07-16", None, "atendente", None)
        q = cur.queries[0][0]
        for sufixo in ["dinheiro", "cheque", "cartao", "debito", "duplicata", "vale", "ticket", "financiado"]:
            assert f"pedido_venda_{sufixo}" in q

    def test_sem_lancamento_faltante_retorna_vazio(self):
        cur = SqlFakeCursor()
        out = svc._pedidos_faturados_sem_forma_pagamento_sync(cur, "2026-07-16", "2026-07-16", None, "atendente", None)
        assert out == []


class TestFechamentoCaixaSync:
    def test_totais_consolidados(self, monkeypatch):
        cur = (
            SqlFakeCursor()
            .when_many("pedido_venda_dinheiro", [{"descricao": "Dinheiro", "tipo": "DI", "nao_totaliza_caixa": False, "total": 300.0}])
            .when_many("FROM entrada_caixa", [{"descricao": "Suprimento", "total": 50.0}])
            .when_many("FROM saida_caixa", [{"descricao": "Sangria", "total": 20.0}])
            # substring mais específica que "pedido_venda_dinheiro" (que
            # também aparece dentro da cláusula NOT EXISTS desta query) —
            # ver comentário em SqlFakeCursor.fetchall.
            .when_many("SELECT cp.ped AS pedido", [])
        )
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        out = svc._fechamento_caixa_sync("srv", "bd", "2026-07-01", "2026-07-31", None, False, None, False)
        assert out["success"] is True
        assert out["subtotal_formas_pagamento"] == 300.0
        assert out["total_entradas"] == 50.0
        assert out["total_saidas"] == 20.0
        # 300 + 50 - 20 - 0 - 0
        assert out["total_caixa"] == 330.0
        assert out["resumo_tipo"][0]["tipo"] == "DI"
        assert out["resumo_tipo"][0]["percentual"] == 100.0

    def test_forma_nao_totaliza_caixa_fica_fora_do_subtotal_mas_no_resumo(self, monkeypatch):
        cur = (
            SqlFakeCursor()
            .when_many("pedido_venda_dinheiro", [{"descricao": "Dinheiro", "tipo": "DI", "nao_totaliza_caixa": False, "total": 100.0}])
            .when_many("pedido_venda_vale", [{"descricao": "Vale Garantia", "tipo": "VA", "nao_totaliza_caixa": True, "total": 40.0}])
            .when_many("SELECT cp.ped AS pedido", [])
        )
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        out = svc._fechamento_caixa_sync("srv", "bd", "2026-07-01", "2026-07-31", None, False, None, False)
        assert out["subtotal_formas_pagamento"] == 100.0
        assert out["total_recebimentos"] == 140.0
        tipos = {r["tipo"]: r for r in out["resumo_tipo"]}
        assert tipos["VA"]["valor"] == 40.0

    def test_expoe_pedidos_faturados_sem_forma_pagamento(self, monkeypatch):
        cur = (
            SqlFakeCursor()
            .when_many("pedido_venda_dinheiro", [{"descricao": "Dinheiro", "tipo": "DI", "nao_totaliza_caixa": False, "total": 492.70}])
            .when_many("JOIN pedido_venda pv ON pv.pedido = cp.ped", [{"pedido": 17606, "total": 197.0}])
        )
        monkeypatch.setattr(svc, "_open_conn", lambda servidor, banco: FakeConn(cur))
        out = svc._fechamento_caixa_sync("srv", "bd", "2026-07-16", "2026-07-16", None, False, None, False)
        assert out["pedidos_sem_forma_pagamento"] == [{"pedido": 17606, "valor": 197.0}]
        assert out["total_sem_forma_pagamento"] == 197.0

    def test_conexao_falha_retorna_erro(self, monkeypatch):
        def _boom(servidor, banco):
            raise RuntimeError("timeout")
        monkeypatch.setattr(svc, "_open_conn", _boom)
        out = svc._fechamento_caixa_sync("srv", "bd", "2026-07-01", "2026-07-31", None, False, None, False)
        assert out["success"] is False
