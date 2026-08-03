"""Testes unitários do motor CNAB Banco do Brasil (Fase 2a — só retorno, ver
services/cnab_bb_service.py e PENDENCIAS.md). Mesmo padrão de cursor falso
já usado pelos outros motores desta fase — leitura idêntica à do Santander
(ver test_cnab_santander_service.py), só muda o código Febraban do banco."""
from datetime import date

import services.cnab_bb_service as svc


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


BANCO_ROW = {"cod": 1, "codigo": 1, "contacorrente": 54321}


def _segmento_t(nosso_numero: str, ocorrencia: str) -> str:
    linha = list(" " * 240)
    linha[7] = "3"
    linha[13] = "T"
    linha[15:17] = list(ocorrencia)
    linha[40:53] = list(nosso_numero.zfill(13))
    return "".join(linha)


def _segmento_u(acrescimos_centavos: int, descontos_centavos: int, valor_pago_centavos: int, data_pg: str, data_credito: str) -> str:
    linha = list(" " * 240)
    linha[7] = "3"
    linha[13] = "U"
    linha[17:32] = list(str(acrescimos_centavos).zfill(15))
    linha[32:47] = list(str(descontos_centavos).zfill(15))
    linha[47:62] = list("0".zfill(15))
    linha[92:107] = list(str(valor_pago_centavos).zfill(15))
    linha[137:145] = list(data_pg)
    linha[145:153] = list(data_credito)
    return "".join(linha)


class TestHelpers:
    def test_parse_valor(self):
        assert svc._parse_valor_cnab("0000000018000") == 180.0

    def test_parse_data(self):
        assert svc._parse_data_ddmmyyyy("21072026") == date(2026, 7, 21)


class TestProcessarRetorno:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 999, "conteudo")
        assert r["success"] is False

    def test_ocorrencia_diferente_de_baixa_confirma(self, monkeypatch):
        t = _segmento_t("1", "02")
        u = _segmento_u(0, 0, 18000, "21072026", "21072026")
        cur = FakeCursor(one=[dict(BANCO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, t + "\n" + u)
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["baixados"] == 0

    def test_ocorrencia_06_titulo_nao_encontrado(self, monkeypatch):
        t = _segmento_t("1", "06")
        u = _segmento_u(0, 0, 18000, "21072026", "21072026")
        cur = FakeCursor(one=[dict(BANCO_ROW), None])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, t + "\n" + u)
        assert r["success"] is True
        assert r["nao_encontrados"] == ["1"]

    def test_ocorrencia_06_baixa_titulo(self, monkeypatch):
        t = _segmento_t("1", "06")
        u = _segmento_u(390, 0, 18390, "21072026", "21072026")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"codigo": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, t + "\n" + u)
        assert r["success"] is True
        assert r["baixados"] == 1
        assert conn.committed is True

    def test_ocorrencia_06_ja_baixado_idempotente(self, monkeypatch):
        t = _segmento_t("1", "06")
        u = _segmento_u(0, 0, 18000, "21072026", "21072026")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"codigo": 10, "situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, t + "\n" + u)
        assert r["success"] is True
        assert r["baixados"] == 0


class TestGerarRemessa:
    def test_nao_implementado(self, monkeypatch):
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não foi implementada" in r["message"]
