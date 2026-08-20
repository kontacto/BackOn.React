"""Testes de `nfe_avulsa_service.py` ("Gerar NFe" — NF-e Avulsa) — ver
PENDENCIAS.md > "NF-e Avulsa" pro racional completo.

Nenhum teste fala com o SEFAZ nem usa certificado real —
`nfe_emissao_service.emitir_nfe_sync`/`_resolver_tributacao_sync` e
`nfe_fiscal_common.resolver_destinatario_*` são sempre mockados (já têm
cobertura própria em seus arquivos de teste); o foco aqui é a lógica de
rascunho→promoção em si (validações, PIS/COFINS só na emissão, IBS/CBS
gravado nas colunas estruturadas)."""
import pytest

import services.nfe_avulsa_service as svc


@pytest.fixture(autouse=True)
def _modulo_nfe_ativo(monkeypatch):
    # Módulo "NFe" (controle_aux.nfe_ws, 2026-08-20) — checado em runtime;
    # mockado True por padrão pra não exigir mais uma linha no FakeCursor
    # de todo teste já existente (nenhum testa módulo desligado).
    monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: True)


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
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


DEST_OK = {
    "success": True,
    "destinatario": {
        "cgc_cpf": "12345678000199", "nome": "CLIENTE TESTE", "endereco": "RUA TESTE", "numero": "100",
        "bairro": "CENTRO", "cidade": "RIO DE JANEIRO", "uf": "RJ", "cep": "20000000",
        "cod_municipio_ibge": "3304557", "ie": None, "indIEDest": "9",
    },
    "consumidor_final": True, "simples_nacional_cliente": False,
}

CAB_ROW = {
    "codigo": 1, "num_nf": None, "cod_fiscal": None, "fornecedor": 10, "mov": "S01", "cfop": "5102",
    "data": "2026-08-20", "data_mov": "2026-08-20", "data_saida": None, "hora_saida": None,
    "valor_total": 100.0, "base_icms": 0, "valor_icms": 0, "base_ipi": 0, "valor_ipi": 0,
    "base_iss": 0, "valor_iss": 0, "base_sub": 0, "valor_sub": 0,
    "frete": 0, "seguro": 0, "despesas": 0, "desconto": 0, "prazo": None,
    "BASE_FCP": 0, "VALOR_FCP": 0, "ALQT_FCP": 0, "BASE_FCP_RETIDO": 0, "VALOR_FCP_RETIDO": 0, "ALQT_FCP_RETIDO": 0,
    "BASE_FCP_ST": 0, "VALOR_FCP_ST": 0, "ALQT_FCP_ST": 0,
    "cnpj_transportadora": None, "placa": None, "motorista": None, "volumes": None, "especie_volume": None,
    "peso_bruto": None, "peso_liquido": None,
}

ITEM_AUX_ROW = {
    "id_nf_aux": 1, "codigo_int": "P001", "cod_fiscal": None, "tributacao": "102",
    "qtd": 2.0, "p_unit": 50.0, "desconto": 0, "desconto_perc": 0, "valor_total": 100.0,
    "alqt_icms": 18.0, "reducao_base_icms": 0, "base_icms": 100.0, "valor_icms": 18.0,
    "base_ipi": 0, "alqt_ipi": 0, "valor_ipi": 0,
    "base_sub": 0, "valor_sub": 0, "base_iss": 0, "valor_iss": 0,
    "frete": 0, "seguro": 0, "despesas": 0, "obs_item_nf": None,
}

CONTROLE_ROW = {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE", "numero_nf": 100, "serie_nf": "1"}

PRODUTO_ROW = {"descricao": "Produto Teste", "ncm": "12345678", "unidade": "UN", "cod_icms": "00", "origem": 0}

TRIBUTOS_ROW = {"cfop_livro": "5102", "ALQT_TRIB_PIS": 1.65, "CST_TRIB_PIS": "01", "ALQT_TRIB_COFINS": 7.6, "CST_TRIB_COFINS": "01"}


def _mock_destinatario_ok(monkeypatch, fornecedor=False):
    alvo = "resolver_destinatario_fornecedor_sync" if fornecedor else "resolver_destinatario_cliente_sync"
    monkeypatch.setattr(svc.nfe_fiscal_common, alvo, lambda cur, pessoa: DEST_OK)


def _mock_tributacao_ok(monkeypatch, tributos=TRIBUTOS_ROW):
    monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda cur, **kw: tributos)


def _mock_ibs_cbs_sem(monkeypatch):
    monkeypatch.setattr(svc.ibs_cbs_service, "resolver_taxa_nfce_para_ibs_cbs_sync", lambda cur, **kw: None)


def _mock_emissao_ok(monkeypatch):
    resultado = {
        "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
        "protocolo_sefaz": "999", "dh_recbto": None, "xml": "<x/>", "situacao": "A", "cstat": "100",
    }
    monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", lambda cur, **kw: resultado)
    return resultado


class TestRascunho:
    def test_novo_rascunho(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 42}])
        conn = _patch(monkeypatch, cur)
        r = svc._novo_rascunho_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert r["codigo"] == 42
        assert conn.committed is True

    def test_get_rascunho_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_rascunho_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_get_rascunho_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[CAB_ROW], many=[[ITEM_AUX_ROW], []])
        _patch(monkeypatch, cur)
        r = svc._get_rascunho_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["promovida"] is False
        assert len(r["itens"]) == 1

    def test_save_cabecalho_bloqueia_ja_promovida(self, monkeypatch):
        cur = FakeCursor(one=[{"num_nf": 555}])
        _patch(monkeypatch, cur)
        r = svc._save_cabecalho_rascunho_sync("srv", "bd", 1, {"fornecedor": 10})
        assert r["success"] is False
        assert "já foi emitida" in r["message"].lower()

    def test_save_cabecalho_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"num_nf": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_rascunho_sync("srv", "bd", 1, {"fornecedor": 10, "mov": "S01"})
        assert r["success"] is True
        assert conn.committed is True

    def test_save_itens_bloqueia_sem_codigo(self):
        r = svc._save_itens_rascunho_sync("srv", "bd", 1, [{"codigo_int": "", "qtd": 1}])
        assert r["success"] is False

    def test_save_itens_bloqueia_sem_qtd(self):
        r = svc._save_itens_rascunho_sync("srv", "bd", 1, [{"codigo_int": "P001", "qtd": 0}])
        assert r["success"] is False

    def test_save_itens_bloqueia_ja_promovida(self, monkeypatch):
        cur = FakeCursor(one=[{"num_nf": 555}])
        _patch(monkeypatch, cur)
        r = svc._save_itens_rascunho_sync("srv", "bd", 1, [{"codigo_int": "P001", "qtd": 1}])
        assert r["success"] is False
        assert "já foi emitida" in r["message"].lower()

    def test_save_itens_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"num_nf": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_itens_rascunho_sync("srv", "bd", 1, [{"codigo_int": "P001", "qtd": 1}])
        assert r["success"] is True
        assert conn.committed is True


class TestSugerirTributacao:
    def test_produto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._sugerir_tributacao_sync(
            "srv", "bd", codigo_int="P999", mov="S01", uf_destino="RJ",
            nao_contribuinte=True, simples_nacional_cliente=False, consumidor_final=True,
        )
        assert r["success"] is False

    def test_sem_tributacao_cadastrada(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_icms": "00"}, CONTROLE_ROW, None])
        _patch(monkeypatch, cur)
        _mock_tributacao_ok(monkeypatch, tributos=None)
        r = svc._sugerir_tributacao_sync(
            "srv", "bd", codigo_int="P001", mov="S01", uf_destino="RJ",
            nao_contribuinte=True, simples_nacional_cliente=False, consumidor_final=True,
        )
        assert r["success"] is False

    def test_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_icms": "00"}, CONTROLE_ROW, None])
        _patch(monkeypatch, cur)
        _mock_tributacao_ok(monkeypatch)
        r = svc._sugerir_tributacao_sync(
            "srv", "bd", codigo_int="P001", mov="S01", uf_destino="RJ",
            nao_contribuinte=True, simples_nacional_cliente=False, consumidor_final=True,
        )
        assert r["success"] is True
        assert r["sugestao"]["cfop_livro"] == "5102"


class TestEmitirNfeAvulsaSync:
    def test_bloqueia_sem_codigo(self):
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=0, master=True)
        assert r["success"] is False

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_rascunho_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_bloqueia_ja_promovida(self, monkeypatch):
        cur = FakeCursor(one=[{**CAB_ROW, "num_nf": 555}])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "já foi emitida" in r["message"].lower()

    def test_bloqueia_cabecalho_incompleto(self, monkeypatch):
        cab_incompleto = {**CAB_ROW, "cfop": None}
        cur = FakeCursor(one=[cab_incompleto])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "preencha" in r["message"].lower()

    def test_bloqueia_tipo_mov_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[CAB_ROW, None])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "movimentação" in r["message"].lower()

    def test_bloqueia_destinatario_invalido(self, monkeypatch):
        cur = FakeCursor(one=[CAB_ROW, {"codigo": "S01", "origem_destino": "C"}])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_destinatario_cliente_sync", lambda cur, p: {"success": False, "message": "Cliente sem endereço."})
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "endereço" in r["message"].lower()

    def test_usa_resolver_fornecedor_quando_origem_destino_f(self, monkeypatch):
        cur = FakeCursor(
            one=[CAB_ROW, {"codigo": "E01", "origem_destino": "F"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        chamou = {}

        def _fake(cur, pessoa):
            chamou["ok"] = True
            return {"success": False, "message": "Fornecedor sem endereço."}

        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_destinatario_fornecedor_sync", _fake)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert chamou.get("ok") is True
        assert r["success"] is False

    def test_bloqueia_sem_itens(self, monkeypatch):
        cur = FakeCursor(one=[CAB_ROW, {"codigo": "S01", "origem_destino": "C"}], many=[[]])
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "nada a emitir" in r["message"].lower()

    def test_bloqueia_sem_tributacao(self, monkeypatch):
        cur = FakeCursor(
            one=[CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"}, PRODUTO_ROW, None],
            many=[[ITEM_AUX_ROW]],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch, tributos=None)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert "tributação" in r["message"].lower()

    def test_sucesso_grava_tudo_e_marca_promovida(self, monkeypatch):
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,  # produto (item, passo 8a) + protocolo_st
                {"codigo": 555},  # INSERT n_fiscal
                PRODUTO_ROW,  # produto de novo (IBS/CBS, passo 14a)
            ],
            many=[[ITEM_AUX_ROW], [], [{"id": 900}]],
        )
        conn = _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        resultado_emissao = _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert r["nota_fisc"] == 555
        assert r["rascunho"] == 1
        assert conn.committed is True
        assert any("INSERT INTO n_fiscal (" in q[0] for q in cur.queries)
        assert any("INSERT INTO n_fiscal_itens" in q[0] for q in cur.queries)
        assert any("UPDATE nf_aux SET num_nf" in q[0] for q in cur.queries)
        assert any("UPDATE controle SET numero_nf" in q[0] for q in cur.queries)
        # PIS/COFINS calculado só na emissão — confere que o INSERT de item leva os valores da cascata mockada.
        insert_item = [q for q in cur.queries if "INSERT INTO n_fiscal_itens" in q[0]][0]
        assert 1.65 in insert_item[1]  # alqt_pis
        assert 7.6 in insert_item[1]  # alqt_cofins
        assert resultado_emissao["chave_acesso"] in [q[1] for q in cur.queries if "INSERT INTO n_fiscal (" in q[0]][0]

    def test_falha_emissao_nao_grava_nfiscal(self, monkeypatch):
        cur = FakeCursor(
            one=[CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"}, PRODUTO_ROW, None],
            many=[[ITEM_AUX_ROW]],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", lambda cur, **kw: {"success": False, "message": "SEFAZ recusou"})

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert not any("INSERT INTO n_fiscal (" in q[0] for q in cur.queries)
