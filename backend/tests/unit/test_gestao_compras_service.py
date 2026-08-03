"""Testes UNITÁRIOS de Gestão de Compras > Ressuprimento."""
from datetime import date

import services.gestao_compras_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
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

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestListCurvas:
    def test_retorna_valores_distintos(self, monkeypatch):
        cur = FakeCursor(many=[
            [{"curva_abc": "A"}, {"curva_abc": "B"}, {"curva_abc": "C"}],
            [{"curva_abc_fin": "A"}, {"curva_abc_fin": "B"}],
        ])
        _patch(monkeypatch, cur)
        r = svc._list_curvas_sync("srv", "bd")
        assert r["success"]
        assert r["curva_abc"] == ["A", "B", "C"]
        assert r["curva_abc_fin"] == ["A", "B"]


class TestListRessuprimento:
    def test_sem_filtros_traz_so_situacao_ativa(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd")
        q, params = cur.queries[-1]
        assert "WHERE p.situacao = 'A' ORDER BY" in q
        assert params == ()

    def test_filtro_curva_abc_e_fin(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd", curva_abc="A", curva_abc_fin="B")
        q, params = cur.queries[-1]
        assert "p.curva_abc = %s" in q and "p.curva_abc_fin = %s" in q
        assert params == ("A", "B")

    def test_filtro_fornecedor(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd", fornecedor=42)
        q, params = cur.queries[-1]
        assert "pecas_fornecedor" in q
        assert 42 in params

    def test_filtro_nivel_chunks_de_3(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd", nivel="001002")
        q, params = cur.queries[-1]
        assert "p.nivel1 = %s" in q and "p.nivel2 = %s" in q
        assert params == ("001", "002")

    def test_filtros_abaixo_minimo_ressuprimento_acima_maximo(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync(
            "srv", "bd", abaixo_minimo=True, abaixo_ressuprimento=True, acima_maximo=True,
        )
        q, _ = cur.queries[-1]
        assert "p.qtd < p.estoque_minimo" in q
        assert "p.qtd < p.estoque_ressuprimento" in q
        assert "p.qtd > p.estoque_maximo AND p.estoque_maximo <> 0" in q

    def test_calcula_previsao_mes_e_dias(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "curva_abc": "A", "curva_abc_fin": "A", "codigo_fab": "F1", "codigo_int": "P1",
            "descricao": "Produto 1", "qtd": 300.0, "cmm": 30.0,
            "estoque_minimo": 10.0, "estoque_ressuprimento": 20.0, "estoque_maximo": 500.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._list_ressuprimento_sync("srv", "bd")
        assert r["success"]
        item = r["items"][0]
        # cmm=30/mes -> 1/dia; qtd=300 -> 300 dias, 10 meses
        assert item["prev_dia"] == 300
        assert item["prev_mes"] == 10

    def test_qtd_negativa_zera_previsao(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "curva_abc": "", "curva_abc_fin": "", "codigo_fab": "", "codigo_int": "P1",
            "descricao": "Produto 1", "qtd": -5.0, "cmm": 30.0,
            "estoque_minimo": 10.0, "estoque_ressuprimento": 20.0, "estoque_maximo": 0.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._list_ressuprimento_sync("srv", "bd")
        item = r["items"][0]
        assert item["prev_dia"] == 0 and item["prev_mes"] == 0

    def test_consumo_zero_nao_divide_por_zero(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "curva_abc": "", "curva_abc_fin": "", "codigo_fab": "", "codigo_int": "P1",
            "descricao": "Produto 1", "qtd": 50.0, "cmm": 0,
            "estoque_minimo": 10.0, "estoque_ressuprimento": 20.0, "estoque_maximo": 0.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._list_ressuprimento_sync("srv", "bd")
        item = r["items"][0]
        assert item["prev_dia"] == 0 and item["prev_mes"] == 0

    def test_order_by_estoque(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_ressuprimento_sync("srv", "bd", order_by="estoque")
        q, _ = cur.queries[-1]
        assert "ORDER BY p.qtd, p.descricao" in q


class TestUltimasCompras:
    def test_calcula_valor_unit_e_impostos_unit(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "num_nf": 123, "data_mov": date(2026, 5, 1), "fantasia": "Forn. X",
            "qtd": 10.0, "qtd_un_compra": 2.0, "valor_total": 200.0,
            "valor_ipi": 10.0, "seguro": 0.0, "frete": 5.0, "despesas": 0.0,
            "valor_sub": 0.0, "valor_iss": 0.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._ultimas_compras_sync("srv", "bd", "P1")
        assert r["success"]
        item = r["items"][0]
        # qtd_total = 10*2 = 20; valor_unit = 200/20 = 10; impostos = 15/20 = 0.75
        assert item["qtd"] == 20.0
        assert item["valor_unit"] == 10.0
        assert item["impostos_unit"] == 0.75
        assert item["fornecedor"] == "Forn. X"

    def test_filtra_mov_e01_e_situacao_ativa(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._ultimas_compras_sync("srv", "bd", "P1")
        q, params = cur.queries[-1]
        assert "nf.mov = 'E01'" in q and "nf.situacao = 'A'" in q
        assert params == ("P1",)

    def test_qtd_zero_nao_divide_por_zero(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "num_nf": 1, "data_mov": None, "fantasia": "F",
            "qtd": 0.0, "qtd_un_compra": 1.0, "valor_total": 0.0,
            "valor_ipi": 0.0, "seguro": 0.0, "frete": 0.0, "despesas": 0.0,
            "valor_sub": 0.0, "valor_iss": 0.0,
        }]])
        _patch(monkeypatch, cur)
        r = svc._ultimas_compras_sync("srv", "bd", "P1")
        item = r["items"][0]
        assert item["valor_unit"] == 0 and item["impostos_unit"] == 0
