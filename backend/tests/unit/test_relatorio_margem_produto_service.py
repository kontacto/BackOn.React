"""Testes unitários de Margem de Lucro (por produto) — réplica de
`Gilson Pneus\\FrmRelPecMLC.frm` (ver docstring do service pro raciocínio
completo)."""
import services.relatorio_margem_produto_service as svc


class FakeCursor:
    def __init__(self, controle_row=None, rows=None):
        self._controle_row = controle_row if controle_row is not None else {"cod_rel": ""}
        self._rows = rows or []
        self.queries = []
        self._n_execute = 0

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._n_execute += 1

    def fetchone(self):
        return self._controle_row

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


class TestNivelClause:
    def test_sem_nivel_nao_filtra(self):
        clauses, params = svc._nivel_clause(None)
        assert clauses == [] and params == []

    def test_nivel_um_bloco(self):
        clauses, params = svc._nivel_clause("001")
        assert clauses == ["nivel1 = %s"]
        assert params == ["001"]

    def test_nivel_tres_blocos(self):
        clauses, params = svc._nivel_clause("001002003")
        assert clauses == ["nivel1 = %s", "nivel2 = %s", "nivel3 = %s"]
        assert params == ["001", "002", "003"]


class TestCodRel:
    def test_cod_rel_i_usa_codigo_interno(self, monkeypatch):
        cur = FakeCursor(controle_row={"cod_rel": "I"}, rows=[])
        _patch(monkeypatch, cur)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["success"] is True
        assert r["codigo_label"] == "Cód. Interno"
        query, _ = cur.queries[-1]
        assert "codigo_int AS codigo" in query

    def test_cod_rel_f_usa_codigo_fabrica(self, monkeypatch):
        cur = FakeCursor(controle_row={"cod_rel": "F"}, rows=[])
        _patch(monkeypatch, cur)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["codigo_label"] == "Cód. Fábrica"
        query, _ = cur.queries[-1]
        assert "codigo_fab AS codigo" in query

    def test_cod_rel_vazio_default_fabrica(self, monkeypatch):
        cur = FakeCursor(controle_row={"cod_rel": None}, rows=[])
        _patch(monkeypatch, cur)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["codigo_label"] == "Cód. Fábrica"


class TestQuery:
    def test_filtra_situacao_ativa(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._margem_produto_sync("srv", "bd", None, "codigo")
        query, _ = cur.queries[-1]
        assert "situacao = 'A'" in query

    def test_filtro_nivel_aplicado(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._margem_produto_sync("srv", "bd", "001002", "codigo")
        query, params = cur.queries[-1]
        assert "nivel1 = %s" in query and "nivel2 = %s" in query
        assert list(params) == ["001", "002"]

    def test_ordenar_por_descricao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._margem_produto_sync("srv", "bd", None, "descricao")
        query, _ = cur.queries[-1]
        assert "ORDER BY descricao" in query

    def test_ordenar_por_codigo_default(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._margem_produto_sync("srv", "bd", None, "codigo")
        query, _ = cur.queries[-1]
        assert "ORDER BY codigo_fab" in query


class TestResultado:
    def test_agrega_e_totaliza(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "F1", "descricao": "Produto 1", "custo_reposicao": 10.0, "p_venda": 15.0},
            {"codigo": "F2", "descricao": "Produto 2", "custo_reposicao": 20.0, "p_venda": 25.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["success"] is True
        assert r["qtd_itens"] == 2
        assert r["total_custo"] == 30.0
        assert r["total_venda"] == 40.0
        assert r["itens"][0]["margem_pct"] == 50.0
        assert r["itens"][1]["margem_pct"] == 25.0
        # margem total sobre os somatórios, não média das margens individuais
        assert r["margem_total_pct"] == round((40.0 - 30.0) / 30.0 * 100, 2)

    def test_custo_zero_margem_none(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo": "F1", "descricao": "Produto Sem Custo", "custo_reposicao": 0.0, "p_venda": 15.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["itens"][0]["margem_pct"] is None

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["itens"] == []
        assert r["qtd_itens"] == 0
        assert r["margem_total_pct"] is None

    def test_erro_de_conexao(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("falha de conexão")
        monkeypatch.setattr(svc, "_open_conn", boom)
        r = svc._margem_produto_sync("srv", "bd", None, "codigo")
        assert r["success"] is False
        assert "Falha de conexão" in r["message"]
