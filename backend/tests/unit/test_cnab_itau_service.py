"""Testes unitários do motor CNAB Itaú (Fase 2a — remessa+retorno, ver
services/cnab_itau_service.py e PENDENCIAS.md). Mesmo padrão de cursor
falso já usado pelos outros motores desta fase — a remessa é validada
contra um arquivo real colado pelo usuário (golden file), ver
TestRemessaArquivoReal abaixo."""
from datetime import date

import services.cnab_itau_service as svc


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


BANCO_ROW = {"cod": 1, "codigo": 341, "contacorrente": 98765}


def _linha_detalhe(nosso_numero: str, ocorrencia: str, data_ocorrencia="210726",
                    desconto=0, valor_pago=0, juros=0) -> str:
    linha = list(" " * 400)
    linha[0] = "1"
    linha[85:93] = list(nosso_numero.zfill(8))
    linha[108:110] = list(ocorrencia)
    linha[110:116] = list(data_ocorrencia)
    linha[240:253] = list(str(int(desconto * 100)).zfill(13))
    linha[253:266] = list(str(int(valor_pago * 100)).zfill(13))
    linha[266:279] = list(str(int(juros * 100)).zfill(13))
    return "".join(linha)


HEADER = "02RETORNO01COBRANCA" + " " * 380


class TestProcessarRetorno:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 999, "conteudo")
        assert r["success"] is False

    def test_cabecalho_invalido(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._processar_retorno_sync("srv", "bd", 1, "conteudo sem cabecalho valido")
        assert r["success"] is False
        assert "cabeçalho" in r["message"]

    def test_ocorrencia_02_confirma_sem_baixar(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)])
        _patch(monkeypatch, cur)
        conteudo = HEADER + "\n" + _linha_detalhe("1", "02")
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["confirmados"] == 1
        assert r["baixados"] == 0

    def test_ocorrencia_06_titulo_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), None])
        _patch(monkeypatch, cur)
        conteudo = HEADER + "\n" + _linha_detalhe("1", "06")
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["nao_encontrados"] == ["1"]
        assert r["baixados"] == 0

    def test_ocorrencia_06_baixa_titulo(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"codigo": 10, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        conteudo = HEADER + "\n" + _linha_detalhe("1", "06", valor_pago=180.0)
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["baixados"] == 1
        assert conn.committed is True
        assert "UPDATE duplicata_rec_venc SET situacao='PG'" in cur.queries[-1][0]

    def test_ocorrencia_06_ja_baixado_idempotente(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"codigo": 10, "situacao": "PG"}])
        _patch(monkeypatch, cur)
        conteudo = HEADER + "\n" + _linha_detalhe("1", "06")
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["baixados"] == 0

    def test_ocorrencia_desconhecida_ignorada(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW)])
        _patch(monkeypatch, cur)
        conteudo = HEADER + "\n" + _linha_detalhe("1", "17")
        r = svc._processar_retorno_sync("srv", "bd", 1, conteudo)
        assert r["success"] is True
        assert r["ignorados"] == 1
        assert r["confirmados"] == 0
        assert r["baixados"] == 0


REAL_HEADER = (
    "01REMESSA01COBRANCA       810000118804        RACING LUB DO BRASIL IMP. EXP.341BANCO ITAU SA  240726"
    + " " * 294 + "000001"
)
REAL_DETALHE = (
    "10205083080000100810000118804    0000127973                   001491580000000000000109                     "
    "I0148325     21082600000001079403410000001N240726579300000000005400000000000000000000000000000000000000000000000"
    "207663084000192JUNIOR E HUGO MOTO PECAS LTDA           RUA CEARA, 95, LJ A                     "
    "PRAÇA DA BAN20270160RIO DE JANEIRO RJ                                  00000000 000002"
)
REAL_TRAILER = "9" + " " * 393 + "000003"

BANCO_ROW_REMESSA = {
    "agencia": 8100, "contacorrente": 11880, "dv_agencia_conta": "4", "carteira": 109, "cod_carteira": "I",
    "especie_doc": 1, "aceite": "N", "instr_cobranca_1": 57, "instr_cobranca_2": 93, "mora_dia_pag": 0.5,
}
TITULO_REAL = {
    "codigo": 127973, "duplicata": 48325, "desmembramento": 0, "dt_vencimento": date(2026, 8, 21),
    "valor": 1079.40, "dt_emissao": date(2026, 7, 24), "num_doc_cliente": 48325, "num_parcelas": 1,
}
CLIENTE_REAL = {"nome": "JUNIOR E HUGO MOTO PECAS LTDA", "cgc_cpf": "07663084000192"}
ENDERECO_REAL = {
    "endereco": "RUA CEARA, 95, LJ A", "numero": None, "complemento": "",
    "bairro": "PRAÇA DA BAN", "cep": "20270160", "cidade": "RIO DE JANEIRO", "uf": "RJ",
}
CGC_EMPRESA_REAL = "05083080000100"


class TestRemessaArquivoReal:
    """Regressão contra remessa real do Itaú (cliente RACING LUB DO BRASIL,
    título da JUNIOR E HUGO MOTO PECAS LTDA) colada pelo usuário 2026-07-24 —
    ver docstring do módulo. Cada linha tem que bater byte a byte."""

    def test_header_bate_com_arquivo_real(self):
        linha = svc._montar_header_400(8100, 11880, "4", "RACING LUB DO BRASIL IMP. EXP.", 1)
        assert len(linha) == 400
        assert linha == REAL_HEADER

    def test_detalhe_bate_com_arquivo_real(self):
        linha = svc._montar_detalhe_400(BANCO_ROW_REMESSA, CGC_EMPRESA_REAL, TITULO_REAL, CLIENTE_REAL, ENDERECO_REAL, 149158, 2)
        assert len(linha) == 400
        assert linha == REAL_DETALHE

    def test_trailer_bate_com_arquivo_real(self):
        linha = svc._montar_trailer_400(3)
        assert len(linha) == 400
        assert linha == REAL_TRAILER

    def test_detalhe_sem_endereco(self):
        linha = svc._montar_detalhe_400(BANCO_ROW_REMESSA, CGC_EMPRESA_REAL, TITULO_REAL, CLIENTE_REAL, None, 149158, 2)
        assert len(linha) == 400


class TestGerarRemessaValidacoes:
    def test_banco_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_banco_nao_e_itau(self, monkeypatch):
        cur = FakeCursor(one=[{**BANCO_ROW, "codigo": 237}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Itaú" in r["message"]

    def test_bloqueia_com_integracao_api_ligada(self, monkeypatch):
        cur = FakeCursor(one=[{**BANCO_ROW, "integracao_api": True}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "API" in r["message"]

    def test_sem_titulos_pendentes(self, monkeypatch):
        cur = FakeCursor(one=[dict(BANCO_ROW), {"cgc": "05083080000100", "rz_social": "EMPRESA TESTE"}])
        _patch(monkeypatch, cur)
        r = svc._gerar_remessa_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Nenhum título" in r["message"]
