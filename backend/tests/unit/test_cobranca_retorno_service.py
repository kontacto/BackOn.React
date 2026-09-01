"""Testes unitários da pré-visualização/aplicação seletiva de retorno
(ver services/cobranca_retorno_service.py) — cursor falso, reaproveita os
`_parse_linhas` já testados em cada test_cnab_*_service.py."""
from datetime import date

import services.cnab_inter_service as cnab_inter
import services.cobranca_retorno_service as svc


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


def _linha_bradesco_06(nosso_numero="1"):
    linha = list(" " * 400)
    linha[0] = "1"
    linha[62:70] = list(nosso_numero.zfill(8))
    linha[108:110] = list("06")
    linha[110:116] = list("210726")
    return "".join(linha)


class TestPreviewRetorno:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 999, "conteudo")
        assert r["success"] is False

    def test_banco_sem_motor_implementado(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 999, "contacorrente": 1}])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, "conteudo")
        assert r["success"] is False
        assert "implementada só para" in r["message"]

    def test_bradesco_baixa_resolvida_com_dados_do_titulo(self, monkeypatch):
        banco_row = {"codigo": 237, "contacorrente": 98765}
        titulo_row = {
            "drv_codigo": 10, "situacao": "A", "dt_vencimento": date(2026, 8, 3),
            "valor_titulo": 250.75, "documento": 555, "cliente_nome": "CLIENTE TESTE",
        }
        cur = FakeCursor(one=[banco_row, titulo_row])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, _linha_bradesco_06())
        assert r["success"] is True
        assert len(r["itens_baixa"]) == 1
        item = r["itens_baixa"][0]
        assert item["drv_codigo"] == 10
        assert item["cliente_nome"] == "CLIENTE TESTE"
        assert item["ja_baixado"] is False

    def test_bradesco_titulo_nao_encontrado(self, monkeypatch):
        banco_row = {"codigo": 237, "contacorrente": 98765}
        cur = FakeCursor(one=[banco_row, None])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, _linha_bradesco_06())
        assert r["success"] is True
        assert r["itens_baixa"] == []
        assert r["nao_encontrados"] == ["1"]
        # Não encontrado ainda vira uma linha listável (não só uma contagem)
        # — dados do próprio arquivo (ocorrência/valor/data), sem drv_codigo
        # (não selecionável pra baixa, não existe título local pra atualizar).
        assert len(r["itens_nao_encontrados"]) == 1
        item = r["itens_nao_encontrados"][0]
        assert item["numero_boleto"] == "1"
        assert item["drv_codigo"] is None
        assert item["encontrado"] is False
        assert item["cliente_nome"] is None

    def test_bradesco_confirmacao_vira_contagem(self, monkeypatch):
        linha = list(" " * 400)
        linha[0] = "1"
        linha[108:110] = list("02")
        banco_row = {"codigo": 237, "contacorrente": 98765}
        cur = FakeCursor(one=[banco_row])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, "".join(linha))
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["itens_baixa"] == []

    def test_ja_baixado_marca_flag(self, monkeypatch):
        banco_row = {"codigo": 237, "contacorrente": 98765}
        titulo_row = {
            "drv_codigo": 10, "situacao": "PG", "dt_vencimento": date(2026, 8, 3),
            "valor_titulo": 250.75, "documento": 555, "cliente_nome": "CLIENTE TESTE",
        }
        cur = FakeCursor(one=[banco_row, titulo_row])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, _linha_bradesco_06())
        assert r["itens_baixa"][0]["ja_baixado"] is True


CNPJ_TESTE = "12345678000199"


def _linha_inter_02(codigo_interno="20621", numero_real="90820068271"):
    """Réplica da posição real do Inter pra ocorrência "02" (Confirmação
    de Título) — achado 2026-08-28 contra arquivo real da instalação
    "KONTACTO REAL": `codigo_interno` (Uso da Empresa, nosso controle) em
    [37:62], `numero_real` (Nosso Número do banco, ecoado) em [107:118]."""
    linha = list(" " * 400)
    linha[0] = "1"
    linha[1:3] = list("02")
    linha[3:17] = list(CNPJ_TESTE)
    linha[37:62] = list(codigo_interno.ljust(25))
    linha[89:91] = list("02")
    linha[107:118] = list(numero_real.rjust(11, "0"))
    return "".join(linha)


class TestPreviewRetornoInterConfirmacao:
    """Achado real 2026-08-28 — sem isso, nenhuma baixa futura de um
    boleto GERADO por este app (não pelo legado) jamais encontraria o
    título depois, porque `numero_boleto` ficaria travado no valor
    provisório pra sempre. Ver docstring do módulo/`cnab_inter_service.
    _parse_linhas`."""
    def _conteudo(self, linha: str) -> str:
        return "02RETORNO01COBRANCA" + " " * 380 + "\n" + linha

    def test_ocorrencia_02_grava_registrado_e_numero_real(self, monkeypatch):
        banco_row = {"codigo": cnab_inter.BANCO_INTER_CODIGO, "contacorrente": 318631490}
        cur = FakeCursor(one=[banco_row, {"cgc": CNPJ_TESTE}])
        conn = _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, self._conteudo(_linha_inter_02()))
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["registrados"] == 1
        assert conn.committed is True
        update = [p for q, p in cur.queries if q.startswith("UPDATE duplicata_rec_venc SET registrado=1")][0]
        assert update == (90820068271, 20621)

    def test_ocorrencia_03_nao_grava_nada(self, monkeypatch):
        """Entrada Rejeitada — o legado nunca chega a atribuir Nosso
        Número real pra esse caso (grava 0 no lugar); só contagem."""
        linha = _linha_inter_02(numero_real="0")
        linha = linha[:89] + "03" + linha[91:]
        banco_row = {"codigo": cnab_inter.BANCO_INTER_CODIGO, "contacorrente": 318631490}
        cur = FakeCursor(one=[banco_row, {"cgc": CNPJ_TESTE}])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, self._conteudo(linha))
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["registrados"] == 0
        assert not any(q.startswith("UPDATE duplicata_rec_venc SET registrado=1") for q, p in cur.queries)

    def test_outro_banco_nao_tenta_gravar_confirmacao(self, monkeypatch):
        """Bradesco/Santander/BB/Itaú ainda não têm essa extração — a
        confirmação continua só contagem pra eles, sem KeyError."""
        linha = list(" " * 400)
        linha[0] = "1"
        linha[108:110] = list("02")
        banco_row = {"codigo": 237, "contacorrente": 98765}
        cur = FakeCursor(one=[banco_row])
        _patch(monkeypatch, cur)
        r = svc._preview_retorno_sync("srv", "bd", 1, "".join(linha))
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["registrados"] == 0


class TestAplicarBaixas:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._aplicar_baixas_sync("srv", "bd", 999, [])
        assert r["success"] is False

    def test_aplica_baixa_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1}, {"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        item = {"drv_codigo": 10, "ocorrencia": "06", "data_pag": "2026-07-21", "valor_pago": 250.75, "juros": 0, "desconto": 0}
        r = svc._aplicar_baixas_sync("srv", "bd", 1, [item])
        assert r["success"] is True
        assert r["baixados"] == 1
        assert conn.committed is True
        assert "UPDATE duplicata_rec_venc SET situacao='PG'" in cur.queries[-1][0]

    def test_idempotente_ja_baixado(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1}, {"situacao": "PG"}])
        _patch(monkeypatch, cur)
        item = {"drv_codigo": 10, "ocorrencia": "06", "data_pag": "2026-07-21", "valor_pago": 250.75, "juros": 0, "desconto": 0}
        r = svc._aplicar_baixas_sync("srv", "bd", 1, [item])
        assert r["success"] is True
        assert r["baixados"] == 0
        assert r["ja_baixados"] == 1

    def test_grava_conta_quando_informada(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1}, {"situacao": "A"}])
        _patch(monkeypatch, cur)
        item = {"drv_codigo": 10, "ocorrencia": "06", "data_pag": "2026-07-21", "valor_pago": 250.75, "juros": 0, "desconto": 0}
        r = svc._aplicar_baixas_sync("srv", "bd", 1, [item], conta=5)
        assert r["success"] is True
        assert ", conta=%s" in cur.queries[-1][0]
        assert 5 in cur.queries[-1][1]
