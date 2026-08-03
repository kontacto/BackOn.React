"""Testes UNITÁRIOS do motor CNAB Bradesco (Fase 2a) — ver
services/cnab_bradesco_service.py e PENDENCIAS.md > "Bancos (Cadastro de
Cobrança / Boleto / CNAB)" > "Fase 2a". Round trip completo (remessa 240
chars/linha + retorno com baixa) já validado ao vivo contra GERDELL/
BARESTELA nesta sessão — estes testes cobrem regras/validação com cursor
falso, mesmo padrão de test_bancos_service.py."""
from datetime import date

import services.cnab_bradesco_service as svc


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


BANCO_ROW = {
    "cod": 1, "codigo": 237, "agencia": 1234, "dv_agencia": "5",
    "contacorrente": 98765, "dv_contacorrente": "4", "dv_agencia_conta": "3",
    "carteira": 9, "cod_transmissao": "1234567", "descr_arquivo": "BRADESCO",
    "especie_doc": 2, "aceite": "N", "codigo_protesto": 1, "dias_protesto": 5,
    "codigo_baixa": 1, "dias_baixa": 60, "Multa_Atraso_Pag": 0, "mora_dia_pag": 0,
    "numero_boleto": 0, "remessa": 0, "integracao_api": False,
}

TITULO = {
    "codigo": 10, "duplicata": 555, "desmembramento": 0, "dt_vencimento": date(2026, 8, 3),
    "valor": 250.75, "dt_emissao": date(2026, 7, 24), "num_parcelas": 1, "valor_desc": 0,
    "dt_vencimento_desc": None, "num_doc_cliente": 555, "cliente": 1990, "conta_cedente": 98765,
}


class TestModulo11Bradesco:
    def test_resto_zero(self):
        # combinação conhecida por dar resto 0 (DAC = "0")
        assert svc._modulo_11_bradesco("0" * 14, 7) == "0"

    def test_valores_validos(self):
        for dac in (svc._modulo_11_bradesco("00900000000000001", 7),):
            assert dac in [str(n) for n in range(10)] + ["P"]


class TestHelpers:
    def test_n_zero_pad(self):
        assert svc._n(42, 5) == "00042"
        assert svc._n(None, 3) == "000"

    def test_n_trunca_a_direita(self):
        assert svc._n(123456, 3) == "456"

    def test_a_pad_e_trunca(self):
        assert svc._a("abc", 5) == "abc  "
        assert svc._a("abcdefgh", 5) == "abcde"
        assert svc._a(None, 3) == "   "


class TestMontarRegistrosLargura:
    """Cada registro tem que somar EXATAMENTE 240 chars (CNAB240 Febraban) —
    conferido também ao vivo contra GERDELL/BARESTELA nesta sessão."""

    def test_header_arquivo_240(self):
        linha = svc._montar_header_arquivo_240(BANCO_ROW, "12345678000199", "EMPRESA TESTE LTDA", 1)
        assert len(linha) == 240
        assert linha.startswith("2370000")

    def test_header_lote_240(self):
        linha = svc._montar_header_lote_240(BANCO_ROW, "12345678000199", "EMPRESA TESTE LTDA", 1, "24072026")
        assert len(linha) == 240

    def test_segmento_p_240(self):
        linha = svc._montar_segmento_p_240(BANCO_ROW, TITULO, 1, 1)
        assert len(linha) == 240
        assert "000000098765" in linha  # conta corrente do banco

    def test_segmento_q_240(self):
        cliente_row = {"codigo": 1990, "nome": "CLIENTE TESTE", "cgc_cpf": "12345678000199"}
        endereco_row = {"endereco": "RUA TESTE", "numero": "100", "complemento": "", "bairro": "CENTRO", "cidade": "SAO PAULO", "uf": "SP", "cep": "01000000"}
        linha = svc._montar_segmento_q_240(cliente_row, endereco_row, 2)
        assert len(linha) == 240

    def test_segmento_q_240_sem_endereco(self):
        cliente_row = {"codigo": 1990, "nome": "CLIENTE TESTE", "cgc_cpf": "12345678901"}
        linha = svc._montar_segmento_q_240(cliente_row, None, 2)
        assert len(linha) == 240

    def test_segmento_r_240_com_multa(self):
        linha = svc._montar_segmento_r_240(10.0, date(2026, 8, 3), 3)
        assert linha is not None
        assert len(linha) == 240

    def test_segmento_r_240_sem_multa_retorna_none(self):
        assert svc._montar_segmento_r_240(0, date(2026, 8, 3), 3) is None

    def test_trailer_lote_240(self):
        assert len(svc._montar_trailer_lote_240(5)) == 240

    def test_trailer_240(self):
        assert len(svc._montar_trailer_240(10)) == 240


class TestGerarRemessaValidacoes:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_banco_nao_e_bradesco(self, monkeypatch):
        cur = FakeCursor(one=[{**BANCO_ROW, "codigo": 341}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Bradesco" in r["message"]

    def test_bloqueia_com_integracao_api_ligada(self, monkeypatch):
        cur = FakeCursor(one=[{**BANCO_ROW, "integracao_api": True}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "API" in r["message"]

    def test_sem_titulos_pendentes(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": "12345678000199", "rz_social": "EMPRESA TESTE"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Nenhum título" in r["message"]

    def test_titulos_selecionados_nenhum_pendente_mensagem_especifica(self, monkeypatch):
        # Mensagem diferente quando o usuário selecionou títulos na grade
        # (Geração de Boletos, aba Geração/Envio) mas nenhum deles ainda
        # está pendente — não confundir com "banco sem título nenhum".
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": "12345678000199", "rz_social": "EMPRESA TESTE"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1, titulos=[10, 11])
        assert r["success"] is False
        assert "selecionados" in r["message"]

    def test_titulos_selecionados_filtram_a_query(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": "12345678000199", "rz_social": "EMPRESA TESTE"}], many=[[]])
        _patch(monkeypatch, cur)
        svc._gerar_remessa_sync("srv", "bd", 1, titulos=[10, 11])
        titulos_query, titulos_params = cur.queries[-1]
        assert "drv.codigo IN (%s,%s)" in titulos_query
        assert titulos_params == (237, 10, 11)


class TestProcessarRetornoValidacoes:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 999, "conteudo qualquer")
        assert r["success"] is False

    def test_ignora_linhas_curtas_ou_tipo_diferente(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "2" + " " * 399 + "\ncurta")
        assert r["success"] is True
        assert r["ignorados"] == 2

    def test_ocorrencia_02_confirma_sem_baixar(self, monkeypatch):
        linha = list(" " * 400)
        linha[0] = "1"
        linha[108:110] = list("02")
        cur = FakeCursor(one=[dict(BANCO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "".join(linha))
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["baixados"] == 0

    def test_ocorrencia_06_titulo_nao_encontrado(self, monkeypatch):
        linha = list(" " * 400)
        linha[0] = "1"
        linha[62:70] = list("00000001")
        linha[108:110] = list("06")
        cur = FakeCursor(one=[dict(BANCO_ROW), None])  # banco, depois duplicata nao encontrada
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "".join(linha))
        assert r["success"] is True
        assert r["nao_encontrados"] == ["1"]
        assert r["baixados"] == 0

    def test_ocorrencia_06_baixa_titulo(self, monkeypatch):
        linha = list(" " * 400)
        linha[0] = "1"
        linha[62:70] = list("00000001")
        linha[108:110] = list("06")
        linha[110:116] = list("240726")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"codigo": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "".join(linha))
        assert r["success"] is True
        assert r["baixados"] == 1
        assert conn.committed is True
        assert "UPDATE duplicata_rec_venc SET situacao='PG'" in cur.queries[-1][0]

    def test_ocorrencia_06_ja_baixado_e_idempotente(self, monkeypatch):
        linha = list(" " * 400)
        linha[0] = "1"
        linha[62:70] = list("00000001")
        linha[108:110] = list("06")
        cur = FakeCursor(one=[dict(BANCO_ROW), {"codigo": 10, "situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "".join(linha))
        assert r["success"] is True
        assert r["baixados"] == 0
