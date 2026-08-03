"""Testes unitários da Geração de Boletos (ver
services/geracao_boletos_service.py) — cursor falso, mesmo padrão dos
outros services desta área."""
from datetime import date

import services.geracao_boletos_service as svc


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


BANCO_ROW = {"codigo": 237, "Multa_Atraso_Pag": 2.0, "mora_dia_pag": 0.5, "tarifa_cobranca": 3.5}

TITULO_ROW = {
    "drv_codigo": 10, "dr_codigo": 5, "duplicata": 555, "cliente_codigo": 1990, "cliente_nome": "CLIENTE TESTE",
    "dt_emissao": date(2026, 7, 1), "dt_vencimento": date(2026, 8, 3), "valor": 100.0, "OUTROS_acres_pag": 0.0,
    "numero_boleto": 0, "registrado": False, "banco_cedente": 237, "desmembramento": 0, "num_parcelas": 1,
    "cobra_tarifa_bancaria": True,
}


class TestListarTitulos:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._listar_titulos_sync("srv", "bd", 999, {})
        assert r["success"] is False

    def test_lista_titulos_com_estimativas(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)], many=[[dict(TITULO_ROW)]])
        _patch(monkeypatch, cur)
        r = svc._listar_titulos_sync("srv", "bd", 1, {})
        assert r["success"] is True
        assert len(r["items"]) == 1
        item = r["items"][0]
        assert item["cliente_nome"] == "CLIENTE TESTE"
        assert item["taxa_bancaria"] == 3.5
        assert item["multa_atraso"] == 2.0  # 100 * 2% = 2.00
        assert item["multa_dia_atraso"] == 0.5  # 100 * 0.5% = 0.50
        assert item["valor_total"] == 103.5

    def test_sem_tarifa_quando_cliente_nao_cobra(self, monkeypatch):
        row = {**TITULO_ROW, "cobra_tarifa_bancaria": False}
        cur = FakeCursor(one=[dict(BANCO_ROW)], many=[[row]])
        _patch(monkeypatch, cur)
        r = svc._listar_titulos_sync("srv", "bd", 1, {})
        assert r["items"][0]["taxa_bancaria"] == 0.0
        assert r["items"][0]["valor_total"] == 100.0

    def test_filtro_so_sem_boleto_monta_where(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)], many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_titulos_sync("srv", "bd", 1, {"so_sem_boleto": True})
        sql = cur.queries[-1][0]
        assert "numero_boleto IS NULL OR drv.numero_boleto = 0" in sql

    def test_filtro_somente_registrados_monta_where(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)], many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_titulos_sync("srv", "bd", 1, {"somente_registrados": True})
        sql = cur.queries[-1][0]
        assert "drv.registrado = 1" in sql

    def test_filtro_cliente_codigo_busca_exata(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)], many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_titulos_sync("srv", "bd", 1, {"cliente_codigo": 1990})
        sql, params = cur.queries[-1]
        assert "c.codigo = %s" in sql
        assert 1990 in params

    def test_parcela_info_formatada_quando_multiplas_parcelas(self, monkeypatch):
        row = {**TITULO_ROW, "num_parcelas": 3, "desmembramento": 2}
        cur = FakeCursor(one=[dict(BANCO_ROW)], many=[[row]])
        _patch(monkeypatch, cur)
        r = svc._listar_titulos_sync("srv", "bd", 1, {})
        assert r["items"][0]["parcela_info"] == "2 de 3"
