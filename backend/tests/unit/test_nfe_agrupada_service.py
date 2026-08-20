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
            "tem_nfce": True, "ja_agrupada": False, "tem_item_produto": True,
        }
        cur = FakeCursor(many=[[linha]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_agrupaveis_sync("srv", "bd", cliente=1, master=True)
        assert r["success"] is True
        assert r["itens"] == [{
            "comanda": 10, "data": "2026-08-19", "valor_venda": 100.0,
            "tem_nfce": True, "ja_agrupada": False, "tem_item_produto": True,
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
