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


@pytest.fixture(autouse=True)
def _sem_contingencia(monkeypatch):
    # Contingência NFe (conectada 2026-08-20) — mockada sem contingência
    # aberta por padrão, mesmo racional do fixture acima.
    monkeypatch.setattr(svc.contingencia_nfe_service, "contingencia_aberta_sync", lambda cur: None)


@pytest.fixture(autouse=True)
def _tp_amb_producao(monkeypatch):
    # Ambiente NFe (controle_aux.ambiente_nfe, 2026-08-20) — antes
    # hardcodado "1" (produção); agora resolvido em runtime. Mockado "1"
    # por padrão (mesmo racional dos fixtures acima).
    monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")


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
    "peso_bruto": None, "peso_liquido": None, "paga_frete": None,
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
        "protocolo_sefaz": "999", "dh_recbto": "2026-08-24T10:00:00-03:00",
        "xml": "<x/>", "situacao": "A", "cstat": "100",
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
        cur = FakeCursor(one=[{"num_nf": None}, {"soma_iss": False}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_itens_rascunho_sync("srv", "bd", 1, [{"codigo_int": "P001", "qtd": 1}])
        assert r["success"] is True
        assert conn.committed is True

    def test_save_itens_zera_iss_quando_soma_iss_desligado(self, monkeypatch):
        """Achado real, `NFe\\frmtranfe.frm:5612-5615` (`CmdOk_Click`):
        `controle.soma_iss=False` zera ISS de todo item, mesmo que o
        frontend tenha mandado um valor."""
        cur = FakeCursor(one=[{"num_nf": None}, {"soma_iss": False}])
        _patch(monkeypatch, cur)
        r = svc._save_itens_rascunho_sync(
            "srv", "bd", 1, [{"codigo_int": "P001", "qtd": 1, "base_iss": 100.0, "valor_iss": 5.0}],
        )
        assert r["success"] is True
        insert = next(q for q in cur.queries if q[0].startswith("INSERT INTO nf_aux_itens"))
        idx_base_iss = svc._ITEM_CAMPOS_AUX.index("base_iss")
        idx_valor_iss = svc._ITEM_CAMPOS_AUX.index("valor_iss")
        # params = (codigo, *valores) — +1 de deslocamento pelo `codigo`.
        assert insert[1][1 + idx_base_iss] == 0
        assert insert[1][1 + idx_valor_iss] == 0

    def test_save_itens_preserva_iss_quando_soma_iss_ligado(self, monkeypatch):
        cur = FakeCursor(one=[{"num_nf": None}, {"soma_iss": True}])
        _patch(monkeypatch, cur)
        r = svc._save_itens_rascunho_sync(
            "srv", "bd", 1, [{"codigo_int": "P001", "qtd": 1, "base_iss": 100.0, "valor_iss": 5.0}],
        )
        assert r["success"] is True
        insert = next(q for q in cur.queries if q[0].startswith("INSERT INTO nf_aux_itens"))
        idx_base_iss = svc._ITEM_CAMPOS_AUX.index("base_iss")
        idx_valor_iss = svc._ITEM_CAMPOS_AUX.index("valor_iss")
        assert insert[1][1 + idx_base_iss] == 100.0
        assert insert[1][1 + idx_valor_iss] == 5.0


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


class TestCalcularPisCofinsItem:
    """Achado real 2026-08-22 (reauditoria > Simplificações, item 4):
    `taxas.CST_TRIB_PIS`/`CST_TRIB_COFINS` vazio (82/82 linhas em ARGEN
    TESTE) não significa "sem PIS/COFINS" (CST 07/R$0,00, comportamento
    antigo) — o legado cai pro cadastro do produto/serviço
    (`SetaPisCofins`+`LancaPisCofins`, `NFe\\frmtranfe.frm:8811/8311`).
    2670/2681 produtos de ARGEN TESTE têm valor real só nesse caminho."""

    def test_caminho_a_usa_taxa_quando_cst_preenchido(self):
        taxa = {"CST_TRIB_PIS": "01", "ALQT_TRIB_PIS": 1.65, "CST_TRIB_COFINS": "01", "ALQT_TRIB_COFINS": 7.6}
        r = svc._calcular_pis_cofins_item(taxa, {}, 100.0)
        assert r == {
            "cst_pis": "01", "base_pis": 100.0, "alqt_pis": 1.65, "valor_pis": 1.65,
            "cst_cofins": "01", "base_cofins": 100.0, "alqt_cofins": 7.6, "valor_cofins": 7.6,
        }

    def test_caminho_a_com_aliquota_zero_zera_a_propria_base(self):
        taxa = {"CST_TRIB_PIS": "07", "ALQT_TRIB_PIS": 0, "CST_TRIB_COFINS": "01", "ALQT_TRIB_COFINS": 7.6}
        r = svc._calcular_pis_cofins_item(taxa, {}, 100.0)
        assert r["base_pis"] == 0.0
        assert r["valor_pis"] == 0.0
        # Divergência deliberada da fonte (ver docstring da função): COFINS
        # não é afetado pela base do PIS ter zerado — no legado, a variável
        # `basepiscofins` compartilhada faria isso zerar também (bug de
        # reuso de variável, não regra tributária real).
        assert r["base_cofins"] == 100.0
        assert r["valor_cofins"] == 7.6

    def test_caminho_b_usa_cadastro_do_produto_quando_taxas_vazio(self):
        # Caso real de ARGEN TESTE: taxas.CST_TRIB_PIS vazio, produto com
        # tributacao_pis=99/perc_valor_pis=0.30 (Outras Operações).
        taxa = {"CST_TRIB_PIS": "", "CST_TRIB_COFINS": ""}
        produto = {"tributacao_pis": 99, "perc_valor_pis": 0.30, "tributacao_cofins": 99, "perc_valor_cofins": 1.25}
        r = svc._calcular_pis_cofins_item(taxa, produto, 100.0)
        assert r["cst_pis"] == "99"
        assert r["valor_pis"] == 0.3
        assert r["cst_cofins"] == "99"
        assert r["valor_cofins"] == 1.25

    def test_caminho_b_so_um_cst_vazio_ja_cai_pro_produto(self):
        # `Trim(TaxaCstPis)<>"" And Trim(TaxaCstCofins)<>""` — os DOIS
        # precisam estar preenchidos pro Caminho A, não é por-imposto.
        taxa = {"CST_TRIB_PIS": "01", "ALQT_TRIB_PIS": 1.65, "CST_TRIB_COFINS": ""}
        produto = {"tributacao_pis": 99, "perc_valor_pis": 0.30, "tributacao_cofins": 99, "perc_valor_cofins": 1.25}
        r = svc._calcular_pis_cofins_item(taxa, produto, 100.0)
        assert r["cst_pis"] == "99"  # não "01" — caiu inteiro pro Caminho B
        assert r["valor_pis"] == 0.3

    def test_caminho_b_aplica_reducao_de_base(self):
        taxa = {"CST_TRIB_PIS": "", "CST_TRIB_COFINS": "", "REDUCAO_BASE_PIS_COFINS": 50}
        produto = {"tributacao_pis": 99, "perc_valor_pis": 10.0, "tributacao_cofins": 99, "perc_valor_cofins": 10.0}
        r = svc._calcular_pis_cofins_item(taxa, produto, 100.0)
        assert r["base_pis"] == 50.0
        assert r["valor_pis"] == 5.0

    def test_caminho_b_tributacao_zero_vira_cst_06(self):
        taxa = {"CST_TRIB_PIS": "", "CST_TRIB_COFINS": ""}
        produto = {"tributacao_pis": 0, "perc_valor_pis": 5.0, "tributacao_cofins": 0, "perc_valor_cofins": 5.0}
        r = svc._calcular_pis_cofins_item(taxa, produto, 100.0)
        assert r["cst_pis"] == "06"
        assert r["valor_pis"] == 0.0
        assert r["cst_cofins"] == "06"
        assert r["valor_cofins"] == 0.0

    def test_caminho_b_produto_nao_encontrado_vira_cst_06(self):
        # `_resolver_item_produto_sync` devolve dict SEM as chaves de PIS/
        # COFINS quando nem pecas nem servicos casam — mesmo efeito do
        # `Tbp.RecordCount<1` do legado.
        taxa = {"CST_TRIB_PIS": "", "CST_TRIB_COFINS": ""}
        produto = {"descricao": "P999", "ncm": "", "unidade": "UN", "cod_icms": "", "origem": 0}
        r = svc._calcular_pis_cofins_item(taxa, produto, 100.0)
        assert r["cst_pis"] == "06"
        assert r["cst_cofins"] == "06"


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
                PRODUTO_ROW, None,  # produto (item) + protocolo_st
                {"codigo": 555},  # INSERT n_fiscal
                {"id": 900},  # INSERT n_fiscal_itens (OUTPUT INSERTED.id)
            ],
            many=[[ITEM_AUX_ROW], []],
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
        # Achado 2026-08-24 (mesmo bug já corrigido no MDF-e 2026-08-23):
        # `dh_recbto` cru do SEFAZ (com offset "-03:00") quebra numa coluna
        # DATETIME — precisa chegar como `datetime` NAIVE já convertido.
        insert_nf = next(q for q in cur.queries if "INSERT INTO n_fiscal (" in q[0])
        import datetime as _dt
        dh_param = next(p for p in insert_nf[1] if isinstance(p, _dt.datetime))
        assert dh_param == _dt.datetime(2026, 8, 24, 10, 0, 0)

    def test_sucesso_persiste_colunas_difal_no_item(self, monkeypatch):
        # Achado 2026-08-28 ("persistir DIFAL"): as 4 colunas de rateio
        # DIFAL (já existentes em n_fiscal_itens, já lidas por
        # apuracao_fiscal_service.py::_calc_difal) nunca eram gravadas
        # pelas notas emitidas por este service — Apuração Fiscal (modo
        # DIFAL) mostrava zerado mesmo com o XML correto.
        tributos_difal = {**TRIBUTOS_ROW, "aliquota_interestadual": 12.0, "aliquota_interna_destino": 18.0, "percentual_origem": 0.0, "fundo_pobreza": 2.0}
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch, tributos=tributos_difal)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        insert_item = [q for q in cur.queries if "INSERT INTO n_fiscal_itens" in q[0]][0]
        assert "aliquota_interestadual" in insert_item[0]
        assert "aliquota_interna_destino" in insert_item[0]
        assert "percentual_origem" in insert_item[0]
        assert "fundo_pobreza" in insert_item[0]
        assert 12.0 in insert_item[1]
        assert 18.0 in insert_item[1]
        assert 2.0 in insert_item[1]

    def test_item_com_cfop_proprio_sobrepoe_cabecalho_no_xml(self, monkeypatch):
        # Achado real 2026-08-24: `n_fiscal_itens.cod_fiscal` já era
        # gravado por item (rascunho/persistência sempre suportaram),
        # mas o XML transmitido usava SEMPRE o CFOP de cabeçalho pra todo
        # item, ignorando esse valor -- divergência real entre o que
        # ficava salvo (correto) e o que ia pro SEFAZ (sempre o
        # cabeçalho). Item com cod_fiscal próprio tem que sobrepor.
        item_com_cfop_proprio = {**ITEM_AUX_ROW, "cod_fiscal": "6108"}
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[item_com_cfop_proprio], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": "2026-08-24T10:00:00-03:00",
                "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["itens_resolvidos"][0]["cfop"] == "6108"  # não CAB_ROW["cfop"]="5102"

    def test_item_sem_cfop_proprio_usa_cabecalho_no_xml(self, monkeypatch):
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],  # cod_fiscal=None
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": "2026-08-24T10:00:00-03:00",
                "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["itens_resolvidos"][0]["cfop"] == CAB_ROW["cfop"]  # "5102"

    def test_contingencia_aberta_e_repassada_pro_emitir_e_grava_situacao_g(self, monkeypatch):
        # Conectado 2026-08-20 — antes desta rodada, contingência aberta
        # nunca era consultada nem repassada pro emitir_nfe_sync.
        cont_row = {
            "data_inicio": "2026-08-20", "hora_inicio": "10:00:00",
            "motivo": "SEFAZ fora do ar" + "x" * 10, "tipo_contingencia": 5,
        }
        monkeypatch.setattr(svc.contingencia_nfe_service, "contingencia_aberta_sync", lambda cur: cont_row)
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        conn = _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": None, "dh_recbto": None, "xml": "<x/>", "situacao": "G", "cstat": None,
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["contingencia"] == cont_row
        insert_n_fiscal = next(q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal ("))
        assert "G" in insert_n_fiscal[1]
        assert conn.committed is True

    def test_ibs_cbs_calculado_antes_de_emitir_e_gravado_estruturado(self, monkeypatch):
        # Regressão 2026-08-20 (mesmo dia — mesmo princípio corrigido em
        # nfe_agrupada_service.py): IBS/CBS deixou de ser calculado depois
        # da promoção (só em colunas estruturadas, sem entrar no XML
        # transmitido) e passou a ser calculado junto com o resto da
        # tributação, embutido no XML original assinado.
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        conn = _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        monkeypatch.setattr(
            svc.ibs_cbs_service, "resolver_taxa_nfce_para_ibs_cbs_sync",
            lambda cur, **kw: {"cst_ibs_uf": "000"},
        )
        ibs_cbs_item = {
            "xml_item": "<IBSCBS>item</IBSCBS>",
            "cst_ibs_uf": "000", "classtrib_ibs_uf": "000", "base_ibs_uf": 100.0, "alqt_ibs_uf": 0.1, "valor_ibs_uf": 0.1,
            "cst_ibs_municipio": "000", "classtrib_ibs_municipio": "000", "base_ibs_municipio": 100.0,
            "alqt_ibs_municipio": 0.1, "valor_ibs_municipio": 0.1,
            "cst_cbs": "000", "classtrib_cbs": "000", "base_cbs": 100.0, "alqt_cbs": 0.1, "valor_cbs": 0.1,
        }
        monkeypatch.setattr(svc.ibs_cbs_service, "calcular_item_ibs_cbs", lambda **kw: ibs_cbs_item)
        monkeypatch.setattr(svc.ibs_cbs_service, "calcular_totais_ibs_cbs", lambda itens: {"xml_totais": "<IBSCBSTot>totais</IBSCBSTot>"})
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": None, "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["ibs_cbs_totais_xml"] == "<IBSCBSTot>totais</IBSCBSTot>"
        assert capturado["itens_resolvidos"][0]["ibs_cbs_xml"] == "<IBSCBS>item</IBSCBS>"
        insert_n_fiscal = next(q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal ("))
        assert "<IBSCBSTot>totais</IBSCBSTot>" in insert_n_fiscal[1]
        assert any(q[0].startswith("UPDATE n_fiscal_itens SET CST_IBS_UF") for q in cur.queries)
        assert conn.committed is True

    def test_paga_frete_do_rascunho_e_repassado_pro_emissor_e_gravado_em_n_fiscal(self, monkeypatch):
        """Achado real 2026-08-21 (reauditoria): `paga_frete` é um campo
        real (`n_fiscal.paga_frete`, smallint), lido de verdade pelo motor
        de emissão pra montar `<modFrete>` — precisa ser lido de `nf_aux`
        (via `_CAB_CAMPOS_AUX`) e repassado tanto pra `emitir_nfe_sync`
        quanto pra `n_fiscal` promovido, não só usado num dos dois."""
        cab_com_frete = {**CAB_ROW, "paga_frete": 2}
        cur = FakeCursor(
            one=[
                cab_com_frete, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        conn = _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": None, "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["paga_frete"] == 2
        insert_n_fiscal = next(q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal ("))
        assert 2 in insert_n_fiscal[1]
        assert conn.committed is True

    def test_transportador_veiculo_volumes_do_rascunho_repassados_e_gravados(self, monkeypatch):
        """Achado real 2026-08-22 (varredura de simplificações): `nf_aux`
        já capturava cnpj_transportadora/placa/motorista/volumes/
        especie_volume/peso_bruto/peso_liquido desde 2026-08-20 (Fase 1),
        mas nada disso nunca chegava ao XML nem à `n_fiscal` promovida —
        ficava só armazenado, sem uso real. `cnpj_transportadora` não tem
        nome/IE em `nf_aux` — resolvido best-effort via `fornecedor`."""
        cab_com_transp = {
            **CAB_ROW, "cnpj_transportadora": "12345678000100", "placa": "ABC1234",
            "motorista": "JOAO", "volumes": 2, "especie_volume": "CAIXA",
            "peso_bruto": 10.5, "peso_liquido": 9.8,
        }
        cur = FakeCursor(
            one=[
                cab_com_transp, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"nome": "TRANSPORTADORA X", "inscr_est": "ISENTO"},
                {"codigo": 555},
                {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        conn = _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": None, "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["transportador"] == {"cgc_cpf": "12345678000100", "nome": "TRANSPORTADORA X", "ie": "ISENTO"}
        assert capturado["veiculo"] == {"placa": "ABC1234"}
        assert capturado["volumes"] == {"qtd": 2, "especie": "CAIXA", "peso_bruto": 10.5, "peso_liquido": 9.8}
        insert_n_fiscal = next((q, p) for q, p in cur.queries if q.startswith("INSERT INTO n_fiscal ("))
        assert "12345678000100" in insert_n_fiscal[1]
        assert "ABC1234" in insert_n_fiscal[1]

    def test_sem_cnpj_transportadora_nao_consulta_fornecedor(self, monkeypatch):
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None,
                {"codigo": 555}, {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": None, "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)
        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert capturado["transportador"] is None
        assert not any("FROM fornecedor WHERE" in q[0] for q in cur.queries)

    def test_falha_emissao_nao_grava_nfiscal(self, monkeypatch):
        cur = FakeCursor(
            one=[CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"}, PRODUTO_ROW, None],
            many=[[ITEM_AUX_ROW]],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", lambda cur, **kw: {"success": False, "message": "SEFAZ recusou"})

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is False
        assert not any("INSERT INTO n_fiscal (" in q[0] for q in cur.queries)

    def test_atualiza_est_soma_quando_mov_entrada(self, monkeypatch):
        # Achado real 2026-08-24 (Leandro): baixa/reposicao de estoque
        # acontece apos a emissao, dependendo do flag tipo_mov.atualiza_est.
        # mov comecando com E (Entrada, ex. E25 "Entrada de Devolucao") SOMA
        # em pecas.qtd quando atualiza_est == S.
        cab_entrada = {**CAB_ROW, "mov": "E25"}
        cur = FakeCursor(
            one=[
                cab_entrada, {"codigo": "E25", "origem_destino": "C", "atualiza_est": "S"}, CONTROLE_ROW,
                {"descricao": "Entrada de Devolucao"}, PRODUTO_ROW, None,
                {"codigo": 555}, {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        upd = next(q for q in cur.queries if q[0].startswith("UPDATE pecas SET qtd = qtd + "))
        assert upd[1] == (ITEM_AUX_ROW["qtd"], ITEM_AUX_ROW["codigo_int"])
        assert not any(q[0].startswith("UPDATE pecas SET qtd = qtd - ") for q in cur.queries)

    def test_atualiza_est_subtrai_quando_mov_saida(self, monkeypatch):
        # mov S01 (Saida) SUBTRAI de pecas.qtd quando atualiza_est == S.
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C", "atualiza_est": "S"}, CONTROLE_ROW,
                {"descricao": "Venda"}, PRODUTO_ROW, None,
                {"codigo": 555}, {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        upd = next(q for q in cur.queries if q[0].startswith("UPDATE pecas SET qtd = qtd - "))
        assert upd[1] == (ITEM_AUX_ROW["qtd"], ITEM_AUX_ROW["codigo_int"])
        assert not any(q[0].startswith("UPDATE pecas SET qtd = qtd + ") for q in cur.queries)

    def test_sem_atualiza_est_nao_mexe_em_estoque(self, monkeypatch):
        # atualiza_est vazio/diferente de S -- nenhuma UPDATE em pecas.
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C", "atualiza_est": "N"}, CONTROLE_ROW,
                {"descricao": "Venda"}, PRODUTO_ROW, None,
                {"codigo": 555}, {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert not any(q[0].startswith("UPDATE pecas SET qtd") for q in cur.queries)

    def test_vinculo_devolucao_atualiza_nfe_apos_emissao(self, monkeypatch):
        # Achado real 2026-08-24 (frmtranfe.frm:4453) -- depois de
        # confirmar o Codigo_NF, devolucao_itens.Nfe e atualizado pra
        # apontar pra ele, fechando o ciclo Devolucao -> NF-e.
        cab_devolucao = {**CAB_ROW, "mov": "E25", "ids_devolucao_origem": "10,11"}
        cur = FakeCursor(
            one=[
                cab_devolucao, {"codigo": "E25", "origem_destino": "C", "atualiza_est": "S"}, CONTROLE_ROW,
                {"descricao": "Entrada de Devolucao"}, PRODUTO_ROW, None,
                {"codigo": 777}, {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        upd = next(q for q in cur.queries if q[0].startswith("UPDATE devolucao_itens SET Nfe="))
        assert upd[1] == (777, 10, 11)

    def test_sem_ids_devolucao_origem_nao_atualiza_devolucao_itens(self, monkeypatch):
        cur = FakeCursor(
            one=[
                CAB_ROW, {"codigo": "S01", "origem_destino": "C"}, CONTROLE_ROW, {"descricao": "Venda"},
                PRODUTO_ROW, None, {"codigo": 555}, {"id": 900},
            ],
            many=[[ITEM_AUX_ROW], []],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_avulsa_sync("srv", "bd", codigo=1, master=True)
        assert r["success"] is True
        assert not any("UPDATE devolucao_itens SET Nfe=" in q[0] for q in cur.queries)


class TestImportarDevolucaoSync:
    """_importar_devolucao_sync -- achado real 2026-08-24 (rastreio de
    Command14_Click/FrmManDev.frm + ImportaDevolucao/frmtranfe.frm): a
    fonte sempre importa um ARRAY de id_devolucao (VetDevolucao),
    consolidando 1+ devolucoes (possivelmente de comandas diferentes, mas
    sempre do MESMO cliente) numa unica NF-e. Substitui a 1a versao desta
    funcao, que so aceitava 1 id (nao servia pro caso real, ver
    PENDENCIAS.md > "Gestor de Devolucao")."""

    def _dev_row(self, id_devolucao, codmov=1, num_nf=100, codigo_int="P001", qtd=2.0, p_unit=50.0):
        return {
            "id_devolucao": id_devolucao, "CodMov": codmov, "Qtd_Devolvida": qtd,
            "codigo_int": codigo_int, "p_unit": p_unit, "num_nf": num_nf,
        }

    def test_lista_vazia_bloqueia(self, monkeypatch):
        r = svc._importar_devolucao_sync("srv", "bd", [])
        assert r["success"] is False
        assert "nenhuma devolucao" in r["message"].lower() or "nenhuma devolução" in r["message"].lower()

    def test_ids_nao_encontrados_bloqueia_com_lista(self, monkeypatch):
        cur = FakeCursor(many=[[self._dev_row(10)]])
        _patch(monkeypatch, cur)
        r = svc._importar_devolucao_sync("srv", "bd", [10, 99])
        assert r["success"] is False
        assert "99" in r["message"]

    def test_devolucoes_de_clientes_diferentes_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"cliente": 1}, {"cliente": 2}],
            many=[[self._dev_row(10, codmov=1, num_nf=100), self._dev_row(11, codmov=2, num_nf=200)]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_devolucao_sync("srv", "bd", [10, 11])
        assert r["success"] is False
        assert "clientes diferentes" in r["message"].lower()

    def test_sucesso_consolida_multiplas_devolucoes_mesmo_cliente(self, monkeypatch):
        # DEST_OK.uf = "RJ"; controle.uf também "RJ" -> uf_dev = "RJ"
        # (mesma UF da empresa, ver achado do descompasso Destino=UF do
        # cliente vs Destino=UF da empresa/'XX' corrigido 2026-08-24).
        cur = FakeCursor(
            one=[
                {"cliente": 1}, {"cliente": 1},  # cliente de cada comanda (2 num_nf distintos)
                {"uf": "RJ"},  # controle.uf (empresa)
                {"CFOP": "1202", "Tipo_Mov": "E25"},  # header cfg (Destino='RJ')
                {"CFOP": "1202"}, {"CFOP": "1202"},  # cfop por item (cod_icms '00', 2 itens)
            ],
            many=[[self._dev_row(10, codmov=1, num_nf=100), self._dev_row(11, codmov=2, num_nf=200, codigo_int="P002", qtd=1.0, p_unit=30.0)]],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        monkeypatch.setattr(svc, "_resolver_item_produto_sync", lambda cur, cod: {"descricao": f"Produto {cod}", "ncm": "1", "unidade": "UN", "cod_icms": "00", "origem": 0})

        r = svc._importar_devolucao_sync("srv", "bd", [10, 11])
        assert r["success"] is True
        assert r["header"]["fornecedor"] == 1
        assert r["header"]["ids_devolucao_origem"] == "10,11"
        assert len(r["itens"]) == 2
        assert r["itens"][0]["codigo_int"] == "P001"
        assert r["itens"][0]["cod_fiscal"] == "1202"
        assert r["itens"][1]["codigo_int"] == "P002"

    def test_uf_dev_resolve_para_xx_quando_cliente_e_de_outro_estado(self, monkeypatch):
        # Achado real 2026-08-24: devolucao_config.Destino nunca guarda o
        # UF literal do cliente -- só a UF da própria empresa ou 'XX'.
        # Cliente de MG (fora da empresa, que é RJ) tem que resolver pra
        # Destino='XX', nunca Destino='MG' (bug real da versão anterior,
        # que bloqueava toda devolução interestadual).
        dest_mg = {**DEST_OK, "destinatario": {**DEST_OK["destinatario"], "uf": "MG"}}
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_destinatario_cliente_sync", lambda cur, pessoa: dest_mg)
        cur = FakeCursor(
            one=[
                {"cliente": 1},
                {"uf": "RJ"},  # controle.uf (empresa) -- diferente do cliente (MG)
                {"CFOP": "2202", "Tipo_Mov": "E25"},  # header cfg (Destino='XX')
                {"CFOP": "2202"},
            ],
            many=[[self._dev_row(10)]],
        )
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_item_produto_sync", lambda cur, cod: {"descricao": "Produto", "ncm": "1", "unidade": "UN", "cod_icms": "00", "origem": 0})

        r = svc._importar_devolucao_sync("srv", "bd", [10])
        assert r["success"] is True
        # a query do header cfg tem que ter usado Destino='XX', não 'MG'
        header_cfg_query = [p for q, p in cur.queries if "devolucao_config" in q and "Cod_Icms" not in q][0]
        assert header_cfg_query == ("XX",)
        assert r["header"]["cfop"] == "2202"

    def test_sem_config_devolucao_pra_uf_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cliente": 1}, {"uf": "RJ"}, None], many=[[self._dev_row(10)]])
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        r = svc._importar_devolucao_sync("srv", "bd", [10])
        assert r["success"] is False
        assert "configuração de devolução" in r["message"].lower() or "configuracao de devolucao" in r["message"].lower()

    def test_sem_config_por_cod_icms_bloqueia_item_a_item(self, monkeypatch):
        # Header tem config (Destino='RJ'), mas o item tem um cod_icms sem
        # linha correspondente em devolucao_config -- bloqueia com
        # mensagem clara em vez de importar silenciosamente sem o item
        # (o legado, via INNER JOIN, simplesmente omitia; decisão
        # consciente de não replicar esse silêncio).
        cur = FakeCursor(
            one=[
                {"cliente": 1},
                {"uf": "RJ"},
                {"CFOP": "1202", "Tipo_Mov": "E25"},
                None,  # cfop por item -- cod_icms sem config
            ],
            many=[[self._dev_row(10)]],
        )
        _patch(monkeypatch, cur)
        _mock_destinatario_ok(monkeypatch)
        monkeypatch.setattr(svc, "_resolver_item_produto_sync", lambda cur, cod: {"descricao": "Produto", "ncm": "1", "unidade": "UN", "cod_icms": "9", "origem": 0})

        r = svc._importar_devolucao_sync("srv", "bd", [10])
        assert r["success"] is False
        assert "cód. icms" in r["message"].lower() or "cod. icms" in r["message"].lower() or "9" in r["message"]
