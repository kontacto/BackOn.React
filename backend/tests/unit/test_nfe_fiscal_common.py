"""Testes de `nfe_fiscal_common.py` — resolvedores de destinatário
(cliente já coberto indiretamente via `test_nfe_agrupada_service.py`;
aqui o foco é o resolvedor de FORNECEDOR, novo em 2026-08-20 pra NF-e
Avulsa — ver PENDENCIAS.md > "NF-e Avulsa")."""
import services.nfe_fiscal_common as common


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])

    def execute(self, q, p=None):
        pass

    def fetchone(self):
        return self._one.pop(0) if self._one else None


class TestResolverDestinatarioFornecedorSync:
    def test_bloqueia_sem_fornecedor(self):
        cur = FakeCursor(one=[None])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is False
        assert "cpf/cnpj" in r["message"].lower()

    def test_bloqueia_documento_curto(self):
        cur = FakeCursor(one=[{"cgc_cpf": "123", "nome": "X", "fantasia": "", "inscr_est": ""}])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is False

    def test_cnpj_sem_endereco_comercial_bloqueia(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "12345678000199", "nome": "X", "fantasia": "", "inscr_est": ""},
            None,
        ])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is False
        assert "comercial" in r["message"].lower()

    def test_cpf_sem_endereco_bloqueia(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "98765432100", "nome": "X", "fantasia": "", "inscr_est": ""},
            None,
        ])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is False
        assert "endereço" in r["message"].lower()
        assert "comercial" not in r["message"].lower()

    def test_municipio_desconhecido_bloqueia(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "12345678000199", "nome": "X", "fantasia": "", "inscr_est": ""},
            {"endereco": "RUA X", "numero": "1", "bairro": "B", "cidade": "CIDADE INEXISTENTE", "uf": "XX", "cep": "00000000"},
        ])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is False
        assert "município" in r["message"].lower()

    def test_sucesso_cnpj_contribuinte(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "12345678000199", "nome": "RAZAO SOCIAL FORN", "fantasia": "FANTASIA FORN", "inscr_est": "1234567"},
            {"endereco": "RUA X", "numero": "1", "bairro": "B", "cidade": "RIO DE JANEIRO", "uf": "RJ", "cep": "20000000"},
        ])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is True
        assert r["destinatario"]["nome"] == "FANTASIA FORN"
        assert r["destinatario"]["ie"] == "1234567"
        assert r["destinatario"]["indIEDest"] == "1"
        assert r["consumidor_final"] is False
        assert r["simples_nacional_cliente"] is False

    def test_sucesso_cpf(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "98765432100", "nome": "FORNECEDOR PF", "fantasia": "", "inscr_est": ""},
            {"endereco": "RUA X", "numero": "1", "bairro": "B", "cidade": "RIO DE JANEIRO", "uf": "RJ", "cep": "20000000"},
        ])
        r = common.resolver_destinatario_fornecedor_sync(cur, 1)
        assert r["success"] is True
        assert r["destinatario"]["ie"] is None
        assert r["destinatario"]["indIEDest"] == "9"
