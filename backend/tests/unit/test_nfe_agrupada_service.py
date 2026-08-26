"""Testes unitários de `nfe_agrupada_service.py` (Agrupar Comandas em NF-e)
— ver PENDENCIAS.md > "Agrupar Comandas em NF-e" pro racional completo.

**Importantíssimo**: nenhum teste aqui fala com o SEFAZ nem usa certificado
real — `nfe_emissao_service.emitir_nfe_sync` é sempre mockada (a emissão em
si já tem cobertura própria em `test_nfe_emissao_service.py`), assim como
`_resolver_tributacao_sync`/`resolver_taxa_nfce_para_ibs_cbs_sync` (também
já cobertas em seus próprios arquivos de teste) — aqui o foco é só a lógica
de agrupamento em si (validações, consolidação de itens, gravação)."""
import pytest

import services.nfe_agrupada_service as svc


@pytest.fixture(autouse=True)
def _modulo_nfe_ativo(monkeypatch):
    # Módulo "NFe" (controle_aux.nfe_ws, 2026-08-20) — checado em runtime;
    # mockado True por padrão pra não exigir mais uma linha no FakeCursor
    # de todo teste já existente (nenhum testa módulo desligado).
    monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: True)


@pytest.fixture(autouse=True)
def _sem_contingencia(monkeypatch):
    # Contingência NFe (conectada 2026-08-20) — mockada sem contingência
    # aberta por padrão, mesma razão do fixture acima: evita exigir mais
    # uma linha no FakeCursor de todo teste já existente (o caso "com
    # contingência aberta" é coberto por testes dedicados que sobrescrevem
    # este mock).
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


def _mock_emissao_ok(monkeypatch, **overrides):
    resultado = {
        "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
        "protocolo_sefaz": "135260000012345", "dh_recbto": "2026-08-19T10:00:00-03:00",
        "xml": "<NFe/>", "situacao": "A", "cstat": "100",
    }
    resultado.update(overrides)
    monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", lambda cur, **kw: resultado)
    return resultado


_SEM_OVERRIDE = object()


def _mock_tributacao_ok(monkeypatch, tributos=_SEM_OVERRIDE):
    valor = {"cfop_livro": "5102"} if tributos is _SEM_OVERRIDE else tributos
    monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda cur, **kw: valor)


def _mock_ibs_cbs_sem(monkeypatch):
    monkeypatch.setattr(svc.ibs_cbs_service, "resolver_taxa_nfce_para_ibs_cbs_sync", lambda cur, **kw: None)


ITEM_MOV = {
    "codigo_int": "P001", "descricao": "Produto Teste", "qtd": 2.0, "p_unit": 10.0,
    "cod_icms": "00", "origem": 0, "ncm": "12345678", "unidade": "UN", "controla_num_serie": False,
}
CONTROLE_ROW = {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE", "numero_nf": 100, "serie_nf": "1"}


class TestListComandasAgrupaveisSync:
    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._list_comandas_agrupaveis_sync("srv", "bd", cliente=1, classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_lista_basica(self, monkeypatch):
        linha = {
            "comanda": 10, "data": "2026-08-19", "valor_venda": 100.0,
            "tem_nfce": True, "ja_tem_nfe": False, "ja_tem_nfse": False,
            "tem_item_produto": True, "tem_item_servico": False,
        }
        cur = FakeCursor(many=[[linha]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_agrupaveis_sync("srv", "bd", cliente=1, master=True)
        assert r["success"] is True
        assert r["itens"] == [{
            "comanda": 10, "data": "2026-08-19", "valor_venda": 100.0,
            "tem_nfce": True, "ja_tem_nfe": False, "ja_tem_nfse": False,
            "tem_item_produto": True, "tem_item_servico": False,
        }]

    def test_falha_conexao(self, monkeypatch):
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        r = svc._list_comandas_agrupaveis_sync("srv", "bd", cliente=1, master=True)
        assert r["success"] is False


class TestResolverDestinatarioSync:
    def test_bloqueia_sem_cliente(self):
        cur = FakeCursor(one=[None])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is False
        assert "cpf/cnpj" in r["message"].lower()

    def test_bloqueia_documento_curto(self):
        cur = FakeCursor(one=[{"cgc_cpf": "123", "nome": "X", "fantasia": "", "inscr_est": "", "consumidor_final": True, "credita_icms": False}])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is False

    def test_cnpj_sem_endereco_comercial_bloqueia(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "12345678000199", "nome": "X", "fantasia": "", "inscr_est": "", "consumidor_final": True, "credita_icms": False},
            None,
        ])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is False
        assert "comercial" in r["message"].lower()

    def test_cpf_sem_endereco_bloqueia(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "98765432100", "nome": "X", "fantasia": "", "inscr_est": "", "consumidor_final": True, "credita_icms": False},
            None,
        ])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is False
        assert "endereço" in r["message"].lower()
        assert "comercial" not in r["message"].lower()

    def test_municipio_desconhecido_bloqueia(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "12345678000199", "nome": "X", "fantasia": "", "inscr_est": "", "consumidor_final": True, "credita_icms": False},
            {"endereco": "RUA X", "numero": "1", "bairro": "B", "cidade": "CIDADE INEXISTENTE", "uf": "XX", "cep": "00000000"},
        ])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is False
        assert "município" in r["message"].lower()

    def test_sucesso_cnpj_contribuinte(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "12345678000199", "nome": "RAZAO SOCIAL", "fantasia": "FANTASIA", "inscr_est": "1234567", "consumidor_final": False, "credita_icms": True},
            {"endereco": "RUA X", "numero": "1", "bairro": "B", "cidade": "RIO DE JANEIRO", "uf": "RJ", "cep": "20000000"},
        ])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is True
        assert r["destinatario"]["nome"] == "FANTASIA"
        assert r["destinatario"]["ie"] == "1234567"
        assert r["destinatario"]["indIEDest"] == "1"
        assert r["consumidor_final"] is False
        assert r["simples_nacional_cliente"] is True

    def test_sucesso_cpf(self):
        cur = FakeCursor(one=[
            {"cgc_cpf": "98765432100", "nome": "PESSOA FISICA", "fantasia": "", "inscr_est": "", "consumidor_final": True, "credita_icms": False},
            {"endereco": "RUA X", "numero": "1", "bairro": "B", "cidade": "RIO DE JANEIRO", "uf": "RJ", "cep": "20000000"},
        ])
        r = svc._resolver_destinatario_sync(cur, 1)
        assert r["success"] is True
        assert r["destinatario"]["ie"] is None
        assert r["destinatario"]["indIEDest"] == "9"


class TestEmitirNfeAgrupadaSync:
    def test_bloqueia_lista_vazia(self):
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[], master=True)
        assert r["success"] is False

    def test_bloqueia_modulo_nfe_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: False)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "módulo nfe" in r["message"].lower()

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(many=[[{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}]])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_bloqueia_comanda_nao_paga(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50},
            {"comanda": 2, "cliente": 10, "situacao": "A", "valor_venda": 50},
        ]])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is False
        assert "faturada" in r["message"].lower()

    def test_bloqueia_clientes_diferentes(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50},
            {"comanda": 2, "cliente": 20, "situacao": "PG", "valor_venda": 50},
        ]])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is False
        assert "mesmo cliente" in r["message"].lower()

    def test_bloqueia_comanda_sem_cliente(self, monkeypatch):
        cur = FakeCursor(many=[[{"comanda": 1, "cliente": None, "situacao": "PG", "valor_venda": 50}]])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "cliente" in r["message"].lower()

    def test_bloqueia_ja_agrupada(self, monkeypatch):
        cur = FakeCursor(many=[
            [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
            [{"comanda": 1}],
        ])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "já está" in r["message"].lower()

    def test_bloqueia_destinatario_invalido(self, monkeypatch):
        cur = FakeCursor(many=[
            [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
            [],
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: {"success": False, "message": "Cliente sem endereço."})
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "endereço" in r["message"].lower()

    def test_bloqueia_sem_itens_produto(self, monkeypatch):
        cur = FakeCursor(many=[
            [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
            [],
            [],
        ])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "nada a emitir" in r["message"].lower()

    def test_bloqueia_sem_tributacao(self, monkeypatch):
        cur = FakeCursor(
            many=[
                [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
                [],
                [dict(ITEM_MOV)],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None],
        )
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
        _mock_tributacao_ok(monkeypatch, tributos=None)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "tributação" in r["message"].lower()

    def test_consolida_itens_soma_mesmo_codigo_preco(self, monkeypatch):
        item1 = {**ITEM_MOV, "qtd": 2.0}
        item2 = {**ITEM_MOV, "qtd": 3.0}
        cur = FakeCursor(
            many=[
                [
                    {"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50},
                    {"comanda": 2, "cliente": 10, "situacao": "PG", "valor_venda": 50},
                ],
                [],
                [item1, item2],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None, {"codigo": 555}],
        )
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
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
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is True
        assert len(capturado["itens_resolvidos"]) == 1
        assert capturado["itens_resolvidos"][0]["qtd"] == 5.0
        assert conn.committed is True

    def test_contingencia_aberta_e_repassada_pro_emitir_e_grava_situacao_g(self, monkeypatch):
        # Conectado 2026-08-20 — antes desta rodada, contingência aberta
        # nunca era consultada nem repassada pro emitir_nfe_sync.
        cont_row = {
            "data_inicio": "2026-08-20", "hora_inicio": "10:00:00",
            "motivo": "SEFAZ fora do ar" + "x" * 10, "tipo_contingencia": 2,
        }
        monkeypatch.setattr(svc.contingencia_nfe_service, "contingencia_aberta_sync", lambda cur: cont_row)
        cur = FakeCursor(
            many=[
                [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
                [],
                [dict(ITEM_MOV)],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None, {"codigo": 555}],
        )
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
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
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is True
        assert capturado["contingencia"] == cont_row
        insert_n_fiscal = next(q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal ("))
        assert "G" in insert_n_fiscal[1]
        insert_comanda_nf = next(q for q in cur.queries if "INSERT INTO comanda_nf" in q[0])
        assert "G" in insert_comanda_nf[1]
        assert conn.committed is True

    def test_item_com_num_serie_nao_soma(self, monkeypatch):
        item1 = {**ITEM_MOV, "qtd": 1.0, "controla_num_serie": True}
        item2 = {**ITEM_MOV, "qtd": 1.0, "controla_num_serie": True}
        cur = FakeCursor(
            many=[
                [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
                [],
                [item1, item2],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None, None, {"codigo": 555}],
        )
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
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
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is True
        assert len(capturado["itens_resolvidos"]) == 2

    def test_sucesso_grava_nfiscal_itens_comandanf_e_atualiza_controle(self, monkeypatch):
        cur = FakeCursor(
            many=[
                [
                    {"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50},
                    {"comanda": 2, "cliente": 10, "situacao": "PG", "valor_venda": 50},
                ],
                [],
                [dict(ITEM_MOV)],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None, {"codigo": 555}],
        )
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_emissao_ok(monkeypatch)

        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is True
        assert r["nota_fisc"] == 555
        assert r["comandas"] == [1, 2]
        assert conn.committed is True
        assert any("INSERT INTO n_fiscal (" in q[0] for q in cur.queries)
        assert any("INSERT INTO n_fiscal_itens" in q[0] for q in cur.queries)
        comanda_nf_q = [q for q in cur.queries if "INSERT INTO comanda_nf" in q[0]]
        assert len(comanda_nf_q) == 1
        assert ", 3, " in comanda_nf_q[0][0]  # tipo=3 (novo, distinto de NFCe=1/NFSe=2)
        assert any("UPDATE controle SET numero_nf" in q[0] for q in cur.queries)
        # Achado 2026-08-24 (mesmo bug já corrigido no MDF-e 2026-08-23):
        # `dh_recbto` cru do SEFAZ (com offset "-03:00") quebra numa coluna
        # DATETIME — precisa chegar como `datetime` NAIVE já convertido.
        insert_nf = next(q for q in cur.queries if "INSERT INTO n_fiscal (" in q[0])
        import datetime as _dt
        dh_param = next(p for p in insert_nf[1] if isinstance(p, _dt.datetime))
        assert dh_param == _dt.datetime(2026, 8, 19, 10, 0, 0)

    def test_ibs_cbs_calculado_antes_de_emitir_sem_reescrever_xml(self, monkeypatch):
        # Regressão 2026-08-20 (mesmo dia): a versão anterior calculava
        # IBS/CBS DEPOIS de emitir e reescrevia n_fiscal.xml sem reassinar
        # — perdia a assinatura digital. Corrigido: IBS/CBS agora é
        # calculado junto com o resto da tributação, ANTES do emitir_nfe_
        # sync, embutido no XML que sai assinado — nenhum UPDATE de xml
        # depois do INSERT.
        cur = FakeCursor(
            many=[
                [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
                [],
                [dict(ITEM_MOV)],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None, {"codigo": 555}],
        )
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
        _mock_tributacao_ok(monkeypatch)
        monkeypatch.setattr(
            svc.ibs_cbs_service, "resolver_taxa_nfce_para_ibs_cbs_sync",
            lambda cur, **kw: {"cst_ibs_uf": "000", "aliq_ibs": 0.1},
        )
        monkeypatch.setattr(
            svc.ibs_cbs_service, "calcular_item_ibs_cbs",
            lambda **kw: {"xml_item": "<IBSCBS>item</IBSCBS>"},
        )
        monkeypatch.setattr(
            svc.ibs_cbs_service, "calcular_totais_ibs_cbs",
            lambda itens: {"xml_totais": "<IBSCBSTot>totais</IBSCBSTot>"},
        )
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 101, "serie": "1", "chave_acesso": "3" * 44,
                "protocolo_sefaz": "999", "dh_recbto": None, "xml": "<x/>", "situacao": "A", "cstat": "100",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", _fake_emitir)
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is True
        # IBS/CBS já chegou pronto no emitir_nfe_sync — embutido no XML original.
        assert capturado["ibs_cbs_totais_xml"] == "<IBSCBSTot>totais</IBSCBSTot>"
        assert capturado["itens_resolvidos"][0]["ibs_cbs_xml"] == "<IBSCBS>item</IBSCBS>"
        # Nenhum UPDATE em n_fiscal depois do INSERT — o xml gravado é
        # exatamente o que veio (assinado) de emitir_nfe_sync, nunca
        # reescrito.
        assert not any(q[0].startswith("UPDATE n_fiscal ") for q in cur.queries)
        insert_n_fiscal = next(q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal ("))
        assert "<IBSCBSTot>totais</IBSCBSTot>" in insert_n_fiscal[1]
        assert "<x/>" in insert_n_fiscal[1]

    def test_paga_frete_do_request_e_repassado_pro_emissor_e_gravado_em_n_fiscal(self, monkeypatch):
        """Achado real 2026-08-21 (reauditoria): `paga_frete` (Emitente/
        Destinatário/etc.) é o seletor real replicado de `FrmTraImpNFE.
        frm`'s `opFrete` — precisa chegar até `emitir_nfe_sync` (que monta
        `<modFrete>`) e até o `n_fiscal` promovido, não só um dos dois."""
        cur = FakeCursor(
            many=[
                [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
                [],
                [dict(ITEM_MOV)],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None, {"codigo": 555}],
        )
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
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
        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True, paga_frete=2)
        assert r["success"] is True
        assert capturado["paga_frete"] == 2
        insert_n_fiscal = next(q for q in cur.queries if q[0].startswith("INSERT INTO n_fiscal ("))
        assert 2 in insert_n_fiscal[1]

    def test_falha_emissao_nao_grava_nfiscal(self, monkeypatch):
        cur = FakeCursor(
            many=[
                [{"comanda": 1, "cliente": 10, "situacao": "PG", "valor_venda": 50}],
                [],
                [dict(ITEM_MOV)],
            ],
            one=[CONTROLE_ROW, {"ok": 1}, {"descricao": "Venda"}, None],
        )
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "_resolver_destinatario_sync", lambda cur, cliente: DEST_OK)
        _mock_tributacao_ok(monkeypatch)
        _mock_ibs_cbs_sem(monkeypatch)
        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfe_sync", lambda cur, **kw: {"success": False, "message": "SEFAZ recusou"})

        r = svc._emitir_nfe_agrupada_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert not any("INSERT INTO n_fiscal (" in q[0] for q in cur.queries)


ITEM_SERVICO_MOV = {
    "codigo_int": "S001", "descricao": "Mão de Obra", "cod_lista_servico": "1401",
    "cod_servico_municipio": "015", "cod_icms": "00", "qtd": 1.0, "p_unit": 80.0,
}
CONTROLE_ROW_NFSE = {"cgc": "12345678000199", "uf": "RJ", "cidade": "RIO DE JANEIRO", "simples_servico": 13.8}
CONTROLE_AUX_NFSE = {
    "numero_DPS": 5, "serie_DPS": "1", "opcao_simples": False, "RegimeEspecialTributacao": 0,
    "codigo_nbs": "120018900",
}


def _mock_nfse_emissao_ok(monkeypatch, **overrides):
    resultado = {
        "success": True, "numero": 6, "serie": "1", "chave_acesso": "5" * 50,
        "id_dps": "DPS" + "1" * 42, "xml_nfse": "<NFSe/>", "xml_dps": "<DPS/>",
    }
    resultado.update(overrides)
    monkeypatch.setattr(svc.nfse_emissao_service, "emitir_nfse_sync", lambda cur, **kw: resultado)
    return resultado


class TestEmitirNfseAgrupadaSync:
    """`_emitir_nfse_agrupada_sync` — generaliza `comanda_service.
    _emitir_nfse_comanda_sync` (1 comanda) pro mesmo agrupamento de várias
    comandas já usado por NF-e. Achado 2026-08-21 (Leandro): tela tem 2
    ações fiscais independentes, não uma exclusão silenciosa de serviço."""

    def test_emite_nfse_agrupada_com_sucesso(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"sefin_nacional": 1},
                CONTROLE_ROW_NFSE,
                CONTROLE_AUX_NFSE,
                {"cgc_cpf": "12345678000199", "nome": "CLIENTE TESTE"},
                {"codigo": 999},
            ],
            many=[
                [{"comanda": 10, "cliente": 1, "situacao": "PG", "valor_venda": 80}],
                [],
                [dict(ITEM_SERVICO_MOV)],
            ],
        )
        conn = _patch(monkeypatch, cur)
        _mock_ibs_cbs_sem(monkeypatch)
        _mock_nfse_emissao_ok(monkeypatch)

        r = svc._emitir_nfse_agrupada_sync("srv", "bd", comandas=[10], master=True)
        assert r["success"] is True
        assert r["nota_fisc"] == 999
        assert r["comandas"] == [10]
        assert conn.committed is True
        assert any("INSERT INTO dps (" in q[0] for q in cur.queries)
        assert any("INSERT INTO n_fiscal (" in q[0] for q in cur.queries)
        comanda_nf_q = next(q for q in cur.queries if "INSERT INTO comanda_nf" in q[0])
        assert ", 2, 'A'" in comanda_nf_q[0]  # tipo=2 (NFSe), distinto de NFe agrupada=3

    def test_sem_item_de_servico_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"sefin_nacional": 1}],
            many=[
                [{"comanda": 10, "cliente": 1, "situacao": "PG", "valor_venda": 80}],
                [],
                [],  # nenhum item de serviço
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_agrupada_sync("srv", "bd", comandas=[10], master=True)
        assert r["success"] is False
        assert "serviço" in r["message"].lower()

    def test_modulo_sefin_desativado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"sefin_nacional": 0}])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_agrupada_sync("srv", "bd", comandas=[10], master=True)
        assert r["success"] is False
        assert "sefin" in r["message"].lower()

    def test_comanda_ja_com_nfse_bloqueia_reagrupamento(self, monkeypatch):
        cur = FakeCursor(
            one=[{"sefin_nacional": 1}],
            many=[
                [{"comanda": 10, "cliente": 1, "situacao": "PG", "valor_venda": 80}],
                [{"comanda": 10}],  # já tem NFS-e (tipo=2)
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_agrupada_sync("srv", "bd", comandas=[10], master=True)
        assert r["success"] is False
        assert "nfs-e" in r["message"].lower()

    def test_itens_consolidados_por_codigo_e_preco(self, monkeypatch):
        # 2 comandas com o MESMO serviço pelo mesmo preço → soma qtd numa
        # única linha da DPS, mesma regra já usada pra produtos.
        cur = FakeCursor(
            one=[
                {"sefin_nacional": 1},
                CONTROLE_ROW_NFSE,
                CONTROLE_AUX_NFSE,
                {"cgc_cpf": "12345678000199", "nome": "CLIENTE TESTE"},
                {"codigo": 999},
            ],
            many=[
                [
                    {"comanda": 10, "cliente": 1, "situacao": "PG", "valor_venda": 80},
                    {"comanda": 11, "cliente": 1, "situacao": "PG", "valor_venda": 80},
                ],
                [],
                [dict(ITEM_SERVICO_MOV), dict(ITEM_SERVICO_MOV)],
            ],
        )
        _patch(monkeypatch, cur)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 6, "serie": "1", "chave_acesso": "5" * 50,
                "id_dps": "DPS1", "xml_nfse": "<NFSe/>", "xml_dps": "<DPS/>",
            }

        monkeypatch.setattr(svc.nfse_emissao_service, "emitir_nfse_sync", _fake_emitir)
        r = svc._emitir_nfse_agrupada_sync("srv", "bd", comandas=[10, 11], master=True)
        assert r["success"] is True
        assert len(capturado["itens"]) == 1
        assert capturado["itens"][0]["valor"] == 160.0  # 2 x (1.0 * 80.0)

    def test_cod_servico_municipio_e_codigo_nbs_e_simples_servico_repassados(self, monkeypatch):
        # Mesmo achado 2026-08-24 já coberto em `test_comanda_service.py`
        # (`cTribMun`/`servicos.cod_servico_municipio`, `cNBS`/`controle_
        # aux.codigo_nbs`, `pTotTribSN`/`controle.simples_servico`) —
        # replicado aqui pro lado agrupado, mesma resolução de dados.
        cur = FakeCursor(
            one=[
                {"sefin_nacional": 1},
                CONTROLE_ROW_NFSE,
                CONTROLE_AUX_NFSE,
                {"cgc_cpf": "12345678000199", "nome": "CLIENTE TESTE"},
                {"codigo": 999},
            ],
            many=[
                [{"comanda": 10, "cliente": 1, "situacao": "PG", "valor_venda": 80}],
                [],
                [dict(ITEM_SERVICO_MOV)],
            ],
        )
        _patch(monkeypatch, cur)
        _mock_ibs_cbs_sem(monkeypatch)
        capturado = {}

        def _fake_emitir(cur, **kw):
            capturado.update(kw)
            return {
                "success": True, "numero": 6, "serie": "1", "chave_acesso": "5" * 50,
                "id_dps": "DPS1", "xml_nfse": "<NFSe/>", "xml_dps": "<DPS/>",
            }

        monkeypatch.setattr(svc.nfse_emissao_service, "emitir_nfse_sync", _fake_emitir)
        r = svc._emitir_nfse_agrupada_sync("srv", "bd", comandas=[10], master=True)
        assert r["success"] is True
        assert capturado["codigo_nbs"] == "120018900"
        assert capturado["simples_servico_pct"] == 13.8
        assert capturado["itens"][0]["cod_servico_municipio"] == "015"


class TestEmitirAgrupadoSync:
    """Orquestrador `_emitir_agrupado_sync` — as 2 ações independentes
    (nenhuma/só produto/só serviço/ambas), pedido direto de Leandro."""

    def test_nenhuma_acao_marcada_bloqueia(self):
        r = svc._emitir_agrupado_sync("srv", "bd", comandas=[1], emitir_nfe=False, emitir_nfse=False, master=True)
        assert r["success"] is False
        assert "ao menos uma ação" in r["message"].lower()

    def test_so_produto_nao_chama_nfse(self, monkeypatch):
        chamou_nfse = {"v": False}
        monkeypatch.setattr(svc, "_emitir_nfe_agrupada_sync", lambda *a, **k: {"success": True, "nota_fisc": 1})
        monkeypatch.setattr(svc, "_emitir_nfse_agrupada_sync", lambda *a, **k: chamou_nfse.__setitem__("v", True))
        r = svc._emitir_agrupado_sync("srv", "bd", comandas=[1], emitir_nfe=True, emitir_nfse=False, master=True)
        assert r["success"] is True
        assert r["resultado_nfe"]["nota_fisc"] == 1
        assert r["resultado_nfse"] is None
        assert chamou_nfse["v"] is False

    def test_so_servico_nao_chama_nfe(self, monkeypatch):
        chamou_nfe = {"v": False}
        monkeypatch.setattr(svc, "_emitir_nfe_agrupada_sync", lambda *a, **k: chamou_nfe.__setitem__("v", True))
        monkeypatch.setattr(svc, "_emitir_nfse_agrupada_sync", lambda *a, **k: {"success": True, "nota_fisc": 2})
        r = svc._emitir_agrupado_sync("srv", "bd", comandas=[1], emitir_nfe=False, emitir_nfse=True, master=True)
        assert r["success"] is True
        assert r["resultado_nfse"]["nota_fisc"] == 2
        assert r["resultado_nfe"] is None
        assert chamou_nfe["v"] is False

    def test_ambas_marcadas_chama_as_duas_e_agrega_sucesso(self, monkeypatch):
        monkeypatch.setattr(svc, "_emitir_nfe_agrupada_sync", lambda *a, **k: {"success": True, "nota_fisc": 1})
        monkeypatch.setattr(svc, "_emitir_nfse_agrupada_sync", lambda *a, **k: {"success": True, "nota_fisc": 2})
        r = svc._emitir_agrupado_sync("srv", "bd", comandas=[1], emitir_nfe=True, emitir_nfse=True, master=True)
        assert r["success"] is True
        assert r["resultado_nfe"]["nota_fisc"] == 1
        assert r["resultado_nfse"]["nota_fisc"] == 2

    def test_ambas_marcadas_uma_falha_nao_impede_a_outra(self, monkeypatch):
        # Achado de design: cada emissão roda em transação própria — uma
        # falhar (ex.: sem item de serviço) não desfaz a outra que já
        # tenha sido transmitida com sucesso ao SEFAZ.
        monkeypatch.setattr(svc, "_emitir_nfe_agrupada_sync", lambda *a, **k: {"success": True, "nota_fisc": 1})
        monkeypatch.setattr(svc, "_emitir_nfse_agrupada_sync", lambda *a, **k: {"success": False, "message": "Nenhuma das comandas selecionadas tem item de serviço — nada a emitir."})
        r = svc._emitir_agrupado_sync("srv", "bd", comandas=[1], emitir_nfe=True, emitir_nfse=True, master=True)
        assert r["success"] is False  # geral é False (nem tudo que foi pedido deu certo)
        assert r["resultado_nfe"]["success"] is True  # mas a NF-e não se perdeu
        assert r["resultado_nfe"]["nota_fisc"] == 1
        assert r["resultado_nfse"]["success"] is False
