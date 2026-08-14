"""Testes unitários de Itens do Pedido — réplica de `FrmItePEd.frm`."""
import services.relatorio_itens_pedido_service as svc


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

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
        r = svc._itens_pedido_sync("srv", "bd", "", "2026-08-07")
        assert r["success"] is False and "período" in r["message"].lower()


class TestQuery:
    def test_filtra_situacao_fechado(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._itens_pedido_sync("srv", "bd", "2026-01-01", "2026-01-31")
        query, params = cur.queries[-1]
        assert "pv.situacao = 'F'" in query
        assert params == ("2026-01-01", "2026-01-31")


class TestAgregacao:
    def test_agrupa_por_codigo_fab_e_converte_compra(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo_fab": "ABC", "produto_descricao": "Parafuso", "un_compra": "CX", "qtd_un_compra": 100,
             "pedido": 10, "cliente_nome": "Cliente A", "qtd_pedida": 50.0},
            {"codigo_fab": "ABC", "produto_descricao": "Parafuso", "un_compra": "CX", "qtd_un_compra": 100,
             "pedido": 11, "cliente_nome": "Cliente B", "qtd_pedida": 150.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_pedido_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert r["success"] is True
        assert len(r["itens"]) == 1
        item = r["itens"][0]
        assert item["codigo_fab"] == "ABC"
        assert item["qtd_total"] == 200.0
        assert item["fator"] == 100
        # Fiel ao legado: Total Geral = TotQtd * QTD_UN_COMPRA (multiplicação, não divisão —
        # ver Command1_Click, FrmItePed.frm linha 158).
        assert item["qtd_compra"] == 20000.0
        assert len(item["pedidos"]) == 2
        assert item["pedidos"][0]["pedido"] == 10 and item["pedidos"][0]["qtd_pedida"] == 50.0

    def test_produtos_diferentes_nao_se_misturam(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo_fab": "A", "produto_descricao": "X", "un_compra": "UN", "qtd_un_compra": 1,
             "pedido": 1, "cliente_nome": "C1", "qtd_pedida": 1.0},
            {"codigo_fab": "B", "produto_descricao": "Y", "un_compra": "UN", "qtd_un_compra": 1,
             "pedido": 2, "cliente_nome": "C2", "qtd_pedida": 2.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_pedido_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert len(r["itens"]) == 2

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._itens_pedido_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert r["success"] is True
        assert r["itens"] == []

    def test_fator_zero_vira_um(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"codigo_fab": "A", "produto_descricao": "X", "un_compra": "UN", "qtd_un_compra": 0,
             "pedido": 1, "cliente_nome": "C1", "qtd_pedida": 5.0},
        ])
        _patch(monkeypatch, cur)
        r = svc._itens_pedido_sync("srv", "bd", "2026-01-01", "2026-01-31")
        assert r["itens"][0]["fator"] == 1
        assert r["itens"][0]["qtd_compra"] == 5.0
