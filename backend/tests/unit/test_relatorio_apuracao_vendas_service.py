"""Testes unitários do Apuração de Vendas - DRE (Fase 1) — réplica de
`FrmRelAPV.frm`. Cobre a montagem da query (filtros/parâmetros) e a
agregação por mês em Python (5 categorias -> total/custo/margem)."""
import services.relatorio_apuracao_vendas_service as svc


class FakeCursor:
    def __init__(self, cod_servico_contrato="S999", rows=None):
        self._cod = [{"cod_servico_contrato": cod_servico_contrato}]
        self._rows = rows or []
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._cod.pop(0) if self._cod else None

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestValidacao:
    def test_periodo_obrigatorio(self):
        r = svc._apuracao_vendas_sync("srv", "bd", "", "2026-08-07", None, None, None, None, None)
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_usa_cod_servico_contrato_da_controle(self, monkeypatch):
        cur = FakeCursor(cod_servico_contrato="S123", rows=[])
        _patch(monkeypatch, cur)
        r = svc._apuracao_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        assert r["success"] is True
        query, params = cur.queries[-1]
        assert params[0] == "S123"
        assert "movimentacao" in query and "os_produto" in query and "pedido_venda_prod" in query

    def test_filtros_opcionais_nao_aplicados_por_padrao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._apuracao_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        query, _ = cur.queries[-1]
        assert "cli.regiao" not in query
        assert "cli.segmento" not in query
        assert "i.vendedor" not in query
        assert "pv.vendedor" not in query

    def test_filtros_opcionais_aplicados_quando_informados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._apuracao_vendas_sync(
            "srv", "bd", "2026-01-01", "2026-01-31",
            vendedor=7, regiao=2, segmento="001", rota=3, tipo_cliente=1,
        )
        query, params = cur.queries[-1]
        assert "cli.regiao = %s" in query
        assert "cli.segmento = %s" in query
        assert "cli.rota = %s" in query
        assert "cli.cliente_forn = %s" in query
        assert "m.vendedor = %s" in query
        assert "i.vendedor = %s" in query
        assert "pv.vendedor = %s" in query
        assert 7 in params and 2 in params and "001" in params and 3 in params and 1 in params


class TestAgregacaoPorMes:
    def test_agrupa_categorias_por_mes_e_calcula_totais(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"categoria": "CONTRATO", "ano": 2026, "mes": 1, "total": 100.0, "custo": 0.0},
            {"categoria": "OS_PRODUTO", "ano": 2026, "mes": 1, "total": 200.0, "custo": 80.0},
            {"categoria": "PEDIDO_SERVICO", "ano": 2026, "mes": 2, "total": 500.0, "custo": 100.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._apuracao_vendas_sync("srv", "bd", "2026-01-01", "2026-02-28", None, None, None, None, None)
        assert r["success"] is True
        assert len(r["meses"]) == 2
        jan, fev = r["meses"]
        assert jan["ano"] == 2026 and jan["mes"] == 1
        assert jan["contratos"] == 100.0
        assert jan["produtos_os"] == 200.0
        assert jan["total"] == 300.0
        assert jan["custo"] == 80.0
        assert jan["margem"] == 220.0
        assert round(jan["margem_pct"], 2) == round((220.0 / 300.0) * 100, 2)
        assert fev["mes"] == 2 and fev["venda_servicos"] == 500.0 and fev["total"] == 500.0
        assert r["totais"]["total"] == 800.0
        assert r["totais"]["custo"] == 180.0
        assert r["totais"]["margem"] == 620.0

    def test_sem_resultados_retorna_listas_vazias(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._apuracao_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        assert r["success"] is True
        assert r["meses"] == []
        assert r["totais"]["total"] == 0.0
        assert r["totais"]["margem_pct"] == 0.0

    def test_mes_sem_venda_total_zero_nao_quebra_margem_pct(self, monkeypatch):
        cur = FakeCursor(rows=[{"categoria": "CONTRATO", "ano": 2026, "mes": 1, "total": 0.0, "custo": 0.0}])
        _patch(monkeypatch, cur)
        r = svc._apuracao_vendas_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None, None, None, None)
        assert r["meses"][0]["margem_pct"] == 0.0
