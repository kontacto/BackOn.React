"""Testes unitários de comanda_service — Fase 1 (Gestor de Comandas, listagem/
relatório + reimpressão de doc fiscal) e Fase 2 (Alterar Comandas: Gravar
cabeçalho, vendedor por item, alterar forma de pagamento de Cartão/Débito).
Migração de `FrmConCupom.frm`/`FrmAltComNV.frm`. Fase 3 (Cancelar) tem seus
próprios testes quando implementada — ver PENDENCIAS.md > "Gestor de
Comandas"."""
import datetime

import pytest

import services.comanda_service as svc
from models.comanda import (
    ComandaAddNumSerieRequest, ComandaAlterarFormaPagamentoRequest, ComandaAlterarVendedorItemRequest,
    ComandaCancelarRequest, ComandaGravarRequest, EmitirNfceRequest, EmitirNfseRequest, ListarComandasRequest,
)


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


def _req(**over):
    base = dict(servidor="srv", banco="bd")
    base.update(over)
    return ListarComandasRequest(**base)


def _row(**over):
    base = dict(
        comanda=1, data=datetime.date(2026, 7, 20), valor_venda=100.0, situacao="PG",
        cliente=10, cliente_nome="CLIENTE TESTE", num_pdv=None, num_cupom=None,
        num_nfce=None, num_nf=None, ped_vinculado=None, os_vinculada=None,
        atendente_nome="JOAO",
    )
    base.update(over)
    return base


class TestListComandasSync:
    def test_lista_basica_sem_filtros(self, monkeypatch):
        cur = FakeCursor(many=[[_row()]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req())
        assert r["success"] is True
        assert r["total"] == 1
        item = r["items"][0]
        assert item["comanda"] == 1
        assert item["cliente_nome"] == "CLIENTE TESTE"
        assert item["situacao_label"] == "Faturado"
        assert r["resumo"]["total_geral"] == 100.0
        assert r["resumo"]["total_sem_documento"] == 100.0

    def test_cliente_diversos_quando_sem_cliente(self, monkeypatch):
        cur = FakeCursor(many=[[_row(cliente=None, cliente_nome="CLIENTES DIVERSOS")]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req())
        assert r["items"][0]["cliente"] is None
        assert r["items"][0]["cliente_nome"] == "CLIENTES DIVERSOS"

    def test_resumo_soma_por_tipo_de_documento(self, monkeypatch):
        rows = [
            _row(comanda=1, valor_venda=50.0, num_cupom=100),
            _row(comanda=2, valor_venda=30.0, num_nfce=200),
            _row(comanda=3, valor_venda=20.0, num_nf=300),
            _row(comanda=4, valor_venda=10.0),
        ]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req())
        resumo = r["resumo"]
        assert resumo["total_geral"] == 110.0
        assert resumo["total_ecf"] == 50.0
        assert resumo["total_nfce"] == 30.0
        assert resumo["total_nf"] == 20.0
        assert resumo["total_sem_documento"] == 10.0

    def test_filtro_cliente_por_codigo_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 5}], many=[[_row(cliente=5)]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(cliente="5"))
        assert r["success"] is True
        assert r["items"][0]["cliente"] == 5
        # 1ª query resolve o código, 2ª é a listagem principal.
        assert len(cur.queries) == 2
        assert "c.cliente = %s" in cur.queries[1][0]
        assert cur.queries[1][1] == (5,)

    def test_filtro_cliente_nao_encontrado_retorna_vazio(self, monkeypatch):
        # codigo não bate, cgc_cpf também não bate.
        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(cliente="999999"))
        assert r["success"] is True
        assert r["items"] == []
        assert r["total"] == 0

    def test_filtro_cliente_por_nome(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 7}], many=[[_row(cliente=7)]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(cliente="FULANO"))
        assert r["success"] is True
        assert cur.queries[0][1] == ("FULANO", "FULANO")

    def test_filtro_produto_nao_encontrado_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None, None, None])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(produto="XPTO"))
        assert r["success"] is True
        assert r["items"] == []

    def test_filtro_produto_encontrado_aplica_filtro_movimentacao(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo_int": "P1"}], many=[[_row()]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(produto="P1"))
        assert r["success"] is True
        assert "m.codigo_int = %s" in cur.queries[1][0]

    def test_filtro_forma_pagamento_tipo_desconhecido_retorna_vazio(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": "ZZ"}])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(forma_pagamento="99"))
        assert r["success"] is True
        assert r["items"] == []

    def test_filtro_forma_pagamento_cartao_resolve_tabela(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": "cc"}], many=[[_row()]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(forma_pagamento="10"))
        assert r["success"] is True
        assert "comanda_cartao" in cur.queries[1][0]

    def test_filtro_comanda_especifica(self, monkeypatch):
        cur = FakeCursor(many=[[_row(comanda=42)]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(comanda=42))
        assert "c.comanda = %s" in cur.queries[0][0]
        assert cur.queries[0][1] == (42,)

    def test_filtro_com_nota_sem_nota_ambos_desmarcados_nao_filtra(self, monkeypatch):
        cur = FakeCursor(many=[[_row()]])
        _patch(monkeypatch, cur)
        r = svc._list_comandas_sync(_req(com_nota=False, sem_nota=False))
        assert r["success"] is True
        assert "EXISTS (SELECT 1 FROM comanda_nf" not in cur.queries[0][0]
        assert "NOT EXISTS (SELECT 1 FROM comanda_nf" not in cur.queries[0][0]

    def test_filtro_apenas_com_nota(self, monkeypatch):
        cur = FakeCursor(many=[[_row()]])
        _patch(monkeypatch, cur)
        svc._list_comandas_sync(_req(com_nota=True, sem_nota=False))
        assert "EXISTS (SELECT 1 FROM comanda_nf" in cur.queries[0][0]

    def test_filtro_apenas_sem_nota(self, monkeypatch):
        cur = FakeCursor(many=[[_row()]])
        _patch(monkeypatch, cur)
        svc._list_comandas_sync(_req(sem_nota=True, com_nota=False))
        assert "NOT EXISTS (SELECT 1 FROM comanda_nf" in cur.queries[0][0]

    def test_ordenar_por_cliente(self, monkeypatch):
        cur = FakeCursor(many=[[_row()]])
        _patch(monkeypatch, cur)
        svc._list_comandas_sync(_req(ordenar_por="cliente"))
        assert "ORDER BY cli.nome" in cur.queries[0][0]

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._list_comandas_sync(_req())
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


class TestGetDocFiscalSync:
    def test_encontra_nfce(self, monkeypatch):
        cur = FakeCursor(one=[{
            "num_nfce": 200, "situacao": "A", "protocolo_sefaz": "123", "chave_acesso": "4" * 44,
            "dhemi": datetime.datetime(2026, 7, 20, 10, 0, 0), "vnf": 50.0, "xml": "<xml/>",
        }])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["tipo"] == "NFCE"
        assert r["numero"] == 200
        assert r["xml"] == "<xml/>"

    def test_nfce_com_qr_code_url_ganha_imagem_png_base64(self, monkeypatch):
        # Extrato NFC-e ganhou QR Code real (2026-08-20) — o backend desenha
        # a imagem a partir da mesma URL já embutida no XML transmitido.
        monkeypatch.setattr(
            svc.nfe_emissao_service, "parse_nfce_xml_para_exibicao",
            lambda xml: {"chave_acesso": "4" * 44, "qr_code_url": "https://sefaz/qrcode?chNFe=123"},
        )
        cur = FakeCursor(one=[{
            "num_nfce": 200, "situacao": "A", "protocolo_sefaz": "123", "chave_acesso": "4" * 44,
            "dhemi": datetime.datetime(2026, 7, 20, 10, 0, 0), "vnf": 50.0, "xml": "<xml/>",
        }])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["detalhe"]["qr_code_png_base64"]
        import base64
        assert base64.b64decode(r["detalhe"]["qr_code_png_base64"])[:8] == b"\x89PNG\r\n\x1a\n"

    def test_nfce_sem_qr_code_url_nao_gera_imagem(self, monkeypatch):
        monkeypatch.setattr(
            svc.nfe_emissao_service, "parse_nfce_xml_para_exibicao",
            lambda xml: {"chave_acesso": "4" * 44, "qr_code_url": ""},
        )
        cur = FakeCursor(one=[{
            "num_nfce": 200, "situacao": "A", "protocolo_sefaz": "123", "chave_acesso": "4" * 44,
            "dhemi": datetime.datetime(2026, 7, 20, 10, 0, 0), "vnf": 50.0, "xml": "<xml/>",
        }])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert "qr_code_png_base64" not in r["detalhe"]

    def test_dhemi_como_string_nao_quebra(self, monkeypatch):
        # Achado ao vivo contra BD_PAJE 2026-07-21: `comanda_nfce.dhemi`
        # pode voltar do pymssql como `str`, não `datetime` — não pode
        # assumir `.isoformat()` incondicional.
        cur = FakeCursor(one=[{
            "num_nfce": 711, "situacao": "F", "protocolo_sefaz": "233261502899617", "chave_acesso": "3" * 44,
            "dhemi": "2026-06-25T15:24:24-03:00", "vnf": 319.0, "xml": "",
        }])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["data_emissao"] == "2026-06-25T15:24:24-03:00"

    def test_encontra_nfse_quando_sem_nfce(self, monkeypatch):
        cur = FakeCursor(one=[None, {
            "situacao": "A", "chave_acesso": "6" * 50, "data_dps": datetime.date(2026, 7, 21), "valor_total": 100.0,
            "num_dps": 11, "serie_dps": "1",
        }])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["tipo"] == "NFSE"
        assert r["chave_acesso"] == "6" * 50
        assert r["numero_dps"] == 11

    def test_encontra_nf_quando_sem_nfce_e_sem_nfse(self, monkeypatch):
        cur = FakeCursor(one=[None, None, {
            "num_nf": 300, "serie_nf": "1", "situacao": "A", "protocolo_sefaz": "456", "chave_acesso": "5" * 44,
            "xml": None, "dhRecbto": None,
        }, {"modelo_danfe": 0}])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["tipo"] == "NF"
        assert r["numero"] == 300
        assert r["detalhe"] is None
        assert r["modelo_danfe"] == 0

    def test_nf_com_xml_inclui_detalhe_do_danfe(self, monkeypatch):
        # Extensão 2026-08-20 — ver "DANFE NF-e (modelo 55)": a gestão de
        # comandas passa a incluir o fac-símile pronto (`detalhe`), mesmo
        # princípio já usado no branch NFCE.
        monkeypatch.setattr(
            svc.nfe_emissao_service, "parse_nfe_xml_para_exibicao",
            lambda xml: {"chave_acesso": "0" * 44, "protocolo_sefaz": None, "valor_total": 20.0},
        )
        cur = FakeCursor(one=[None, None, {
            "num_nf": 300, "serie_nf": "1", "situacao": "A", "protocolo_sefaz": "456", "chave_acesso": "5" * 44,
            "xml": "<NFe/>", "dhRecbto": "2026-08-20T10:00:00",
        }, {"modelo_danfe": 1}])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["detalhe"]["chave_acesso"] == "5" * 44  # coluna sobrepõe o que o parser devolveu
        assert r["detalhe"]["protocolo_sefaz"] == "456"
        assert r["modelo_danfe"] == 1

    def test_encontra_cupom_quando_sem_nenhum_documento_anterior(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None, {"num_pdv": 1, "num_cupom": 100, "coo": "5", "situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["tipo"] == "CUPOM"
        assert r["numero"] == 100

    def test_sem_documento_vinculado(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None, None])
        _patch(monkeypatch, cur)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Nenhum documento fiscal" in r["message"]

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._get_doc_fiscal_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


def _cab_row(**over):
    base = dict(
        comanda=1, data=datetime.date(2026, 7, 20), valor_venda=100.0, valor_liquido=100.0,
        situacao="PG", cliente=10, cliente_nome="CLIENTE TESTE", area_atuacao=2,
        area_atuacao_descricao="OFICINA", paga_comissao=True,
        atendente=5, atendente_nome="JOAO", atendente_dav=5, atendente_dav_nome="MARIA", faturar_para=None,
    )
    base.update(over)
    return base


class TestGetComandaSync:
    def test_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_comanda_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_sucesso_monta_itens_formas_pag_e_vinculos(self, monkeypatch):
        item_row = {"id_mov": 1, "codigo_int": "P1", "descricao": "Produto 1", "qtd": 2.0, "p_unit": 25.0, "vendedor": 5, "vendedor_nome": "JOAO"}
        cartao_row = {"sequencia": 900, "forma_pag": "10", "valor": 100.0, "transf_receber": False, "descricao": "Cartão Crédito"}
        # 1 fetchall pros itens + 8 fetchall (um por tabela de forma_pag, só comanda_cartao tem linha).
        many = [[item_row], [], [], [cartao_row], [], [], [], [], []]
        cur = FakeCursor(one=[_cab_row(), {"ped_vinculado": None, "os_vinculada": 77}], many=many)
        _patch(monkeypatch, cur)
        r = svc._get_comanda_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["comanda"]["comanda"] == 1
        assert r["comanda"]["situacao_label"] == "Faturado"
        assert r["comanda"]["os_vinculada"] == 77
        assert r["comanda"]["area_atuacao_descricao"] == "OFICINA"
        assert r["comanda"]["atendente_nome"] == "JOAO"
        assert r["comanda"]["atendente_dav_nome"] == "MARIA"
        assert len(r["itens"]) == 1
        assert r["itens"][0]["vendedor_nome"] == "JOAO"
        assert len(r["formas_pagamento"]) == 1
        assert r["formas_pagamento"][0]["tipo"] == "CC"
        assert r["formas_pagamento"][0]["alteravel"] is True

    def test_forma_pag_conciliada_nao_e_alteravel(self, monkeypatch):
        cartao_row = {"sequencia": 900, "forma_pag": "10", "valor": 100.0, "transf_receber": True, "descricao": "Cartão Crédito"}
        many = [[], [], [], [cartao_row], [], [], [], [], []]
        cur = FakeCursor(one=[_cab_row(), {"ped_vinculado": None, "os_vinculada": None}], many=many)
        _patch(monkeypatch, cur)
        r = svc._get_comanda_sync("srv", "bd", 1)
        assert r["formas_pagamento"][0]["conciliado"] is True
        assert r["formas_pagamento"][0]["alteravel"] is False

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._get_comanda_sync("srv", "bd", 1)
        assert r["success"] is False


def _gravar_req(**over):
    base = dict(servidor="srv", banco="bd", area_atuacao=2, paga_comissao=True, atendente=5, atendente_dav=5,
                cliente=10, faturar_para=None, usuario_alteracao=1, classe=1, plataforma="web", master=False)
    base.update(over)
    return ComandaGravarRequest(**base)


class TestSaveComandaSync:
    def test_grava_com_sucesso_master(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_comanda_sync(_gravar_req(master=True), 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_comanda_sync(_gravar_req(master=True), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])  # tem_permissao -> fetchone None -> False
        _patch(monkeypatch, cur)
        r = svc._save_comanda_sync(_gravar_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_com_permissao_concedida(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"comanda": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_comanda_sync(_gravar_req(master=False, classe=2), 1)
        assert r["success"] is True
        assert conn.committed is True


def _vendedor_item_req(**over):
    base = dict(servidor="srv", banco="bd", id_mov=1, vendedor=8, aplicar_aos_demais_itens_do_vendedor_anterior=False,
                usuario_alteracao=1, classe=1, plataforma="web", master=True)
    base.update(over)
    return ComandaAlterarVendedorItemRequest(**base)


class TestAlterarVendedorItemSync:
    def test_altera_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"vendedor": 5}])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_vendedor_item_sync(_vendedor_item_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("SET vendedor" in (q[0] or "") for q in cur.queries)

    def test_item_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._alterar_vendedor_item_sync(_vendedor_item_req(), 1)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_aplica_aos_demais_itens_do_vendedor_anterior(self, monkeypatch):
        cur = FakeCursor(one=[{"vendedor": 5}])
        _patch(monkeypatch, cur)
        r = svc._alterar_vendedor_item_sync(_vendedor_item_req(aplicar_aos_demais_itens_do_vendedor_anterior=True), 1)
        assert r["success"] is True
        # 2 UPDATEs: o item específico + os demais itens do vendedor anterior.
        updates = [q for q in cur.queries if q[0].strip().upper().startswith("UPDATE")]
        assert len(updates) == 2


def _forma_pag_req(**over):
    base = dict(servidor="srv", banco="bd", sequencia=900, tipo="CC", forma_pag_nova="11",
                usuario_alteracao=1, classe=1, plataforma="web", master=True)
    base.update(over)
    return ComandaAlterarFormaPagamentoRequest(**base)


class TestAlterarFormaPagamentoSync:
    def test_altera_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"sequencia": 900, "forma_pag": "10", "transf_receber": False}, {"tipo": "CC"}])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_forma_pagamento_sync(_forma_pag_req(), 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_bloqueia_tipo_nao_alteravel(self, monkeypatch):
        r = svc._alterar_forma_pagamento_sync(_forma_pag_req(tipo="DI"), 1)
        assert r["success"] is False
        assert "Cartão ou Débito" in r["message"]

    def test_lancamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._alterar_forma_pagamento_sync(_forma_pag_req(), 1)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_bloqueia_ja_conciliado(self, monkeypatch):
        cur = FakeCursor(one=[{"sequencia": 900, "forma_pag": "10", "transf_receber": True}])
        _patch(monkeypatch, cur)
        r = svc._alterar_forma_pagamento_sync(_forma_pag_req(), 1)
        assert r["success"] is False
        assert "conciliado" in r["message"].lower()

    def test_bloqueia_modalidade_diferente(self, monkeypatch):
        cur = FakeCursor(one=[{"sequencia": 900, "forma_pag": "10", "transf_receber": False}, {"tipo": "DI"}])
        _patch(monkeypatch, cur)
        r = svc._alterar_forma_pagamento_sync(_forma_pag_req(), 1)
        assert r["success"] is False
        assert "mesma modalidade" in r["message"]

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])  # tem_permissao -> False
        _patch(monkeypatch, cur)
        r = svc._alterar_forma_pagamento_sync(_forma_pag_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()


class TestListNumSerieComandaSync:
    def test_lista_vinculados(self, monkeypatch):
        rows = [{"sequencia": 1, "data": datetime.date(2026, 7, 20), "codigo": 50, "num_serie": "ABC123", "codigo_int": "P1", "descricao": "Produto 1"}]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._list_num_serie_comanda_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["items"][0]["num_serie"] == "ABC123"

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._list_num_serie_comanda_sync("srv", "bd", 1)
        assert r["success"] is False


def _num_serie_req(**over):
    base = dict(servidor="srv", banco="bd", codigo=50, usuario_alteracao=1, classe=1, plataforma="web", master=True)
    base.update(over)
    return ComandaAddNumSerieRequest(**base)


class TestAddNumSerieComandaSync:
    def test_vincula_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1}, {"codigo": 50, "disponivel": True}])
        conn = _patch(monkeypatch, cur)
        r = svc._add_num_serie_comanda_sync(_num_serie_req(), 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_num_serie_comanda_sync(_num_serie_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_num_serie_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._add_num_serie_comanda_sync(_num_serie_req(), 1)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_num_serie_indisponivel_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1}, {"codigo": 50, "disponivel": False}])
        _patch(monkeypatch, cur)
        r = svc._add_num_serie_comanda_sync(_num_serie_req(), 1)
        assert r["success"] is False
        assert "disponível" in r["message"].lower()

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_num_serie_comanda_sync(_num_serie_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()


class TestRemoveNumSerieComandaSync:
    def test_remove_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"num_serie": 50}])
        conn = _patch(monkeypatch, cur)
        r = svc._remove_num_serie_comanda_sync("srv", "bd", 1, 10, True, None)
        assert r["success"] is True
        assert conn.committed is True

    def test_vinculo_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._remove_num_serie_comanda_sync("srv", "bd", 1, 999, True, None)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._remove_num_serie_comanda_sync("srv", "bd", 1, 10, False, 2)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()


def _cancelar_req(**over):
    base = dict(servidor="srv", banco="bd", motivo="Motivo de teste com mais de 15 caracteres", usuario_alteracao=1, classe=1, plataforma="web", master=True)
    base.update(over)
    return ComandaCancelarRequest(**base)


def _ones_cancelar(header, financeiro=None, nfce=None, nf_incluido=True, nf=None, ped=None, os_row=None, cupom=None, controle=None):
    """Monta a fila de `fetchone()` na MESMA ordem que `_cancelar_comanda_sync`
    executa suas queries — ver o corpo da função pra conferir a ordem exata
    antes de alterar este helper."""
    financeiro = financeiro if financeiro is not None else [None] * 8
    ones = [header] + financeiro + [nfce]
    if nf_incluido:
        ones.append(nf)
    if controle is not None:
        ones.append(controle)
    ones += [ped, os_row, cupom]
    return ones


class TestCancelarComandaSync:
    def test_motivo_curto_bloqueia(self, monkeypatch):
        r = svc._cancelar_comanda_sync(_cancelar_req(motivo="curto"), 1)
        assert r["success"] is False
        assert "15 caracteres" in r["message"]

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])  # tem_permissao -> False
        _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_ja_cancelada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1, "situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is False
        assert "já está cancelada" in r["message"]

    def test_bloqueio_financeiro_ja_conciliado(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        financeiro = [None, None, {"ok": 1}] + [None] * 5  # comanda_cartao (3ª tabela) conciliado
        cur = FakeCursor(one=[header] + financeiro)
        _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is False
        assert "conciliado" in r["message"].lower()
        # Não deve ter chegado a apagar nenhum pagamento nem alterar a comanda.
        assert not any(q[0].strip().upper().startswith("DELETE") for q in cur.queries)
        assert not any("UPDATE comanda SET" in q[0] for q in cur.queries)

    def test_sucesso_sem_doc_fiscal_sem_pedido_sem_os(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        ones = _ones_cancelar(header, nfce=None, nf=None, ped=None, os_row=None, cupom={"num_cupom": 55})
        item_row = {"codigo_int": "P1", "qtd": 2.0}
        cur = FakeCursor(one=ones, many=[[item_row], []])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE pecas SET qtd" in q[0] for q in cur.queries)
        assert any("Estornado = 1" in q[0] for q in cur.queries)
        assert any("INSERT INTO cancelamento" in q[0] for q in cur.queries)

    def test_sucesso_com_pedido_vinculado_volta_pra_fechado(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        ones = _ones_cancelar(header, ped={"ped": 500}, os_row=None, cupom=None)
        cur = FakeCursor(one=ones, many=[[], []])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE pedido_venda SET situacao = 'F'" in q[0] for q in cur.queries)
        assert any("DELETE FROM comanda_ped" in q[0] for q in cur.queries)

    def test_sucesso_com_os_vinculada_volta_pra_fechado(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        ones = _ones_cancelar(header, ped=None, os_row={"os": 700}, cupom=None)
        cur = FakeCursor(one=ones, many=[[], []])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE os SET situacao = 'F'" in q[0] for q in cur.queries)
        assert any("DELETE FROM comanda_os" in q[0] for q in cur.queries)

    def test_libera_numeros_de_serie_vinculados(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        ones = _ones_cancelar(header)
        cur = FakeCursor(one=ones, many=[[], [{"num_serie": 50}]])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE pecas_num_serie SET disponivel = 1" in q[0] for q in cur.queries)

    def test_nfce_sem_protocolo_marca_local_sem_chamar_sefaz(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        nfce = {"num_nfce": 200, "situacao": "A", "protocolo_sefaz": "", "chave_acesso": "1" * 44}
        ones = _ones_cancelar(header, nfce=nfce, nf_incluido=False, controle=None)
        cur = FakeCursor(one=ones, many=[[], []])
        conn = _patch(monkeypatch, cur)
        chamou = {"v": False}

        def _fake_cancelar(*a, **k):
            chamou["v"] = True
            return {"success": True}

        monkeypatch.setattr(svc.nfe_cancelamento_service, "cancelar_nfe_sync", _fake_cancelar)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert chamou["v"] is False
        assert any("UPDATE comanda_nfce SET situacao = 'C'" in q[0] for q in cur.queries)

    def test_nfce_com_protocolo_chama_sefaz_com_sucesso(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        nfce = {"num_nfce": 200, "situacao": "A", "protocolo_sefaz": "123456", "chave_acesso": "1" * 44}
        controle = {"cgc": "12345678000199", "uf": "RJ"}
        ones = _ones_cancelar(header, nfce=nfce, nf_incluido=False, controle=controle)
        cur = FakeCursor(one=ones, many=[[], []])
        conn = _patch(monkeypatch, cur)
        chamado = {}

        def _fake_cancelar(cur_, *, cnpj, uf_sigla, modelo, chave_acesso, protocolo, motivo, tp_amb, servidor="", banco=""):
            chamado.update(cnpj=cnpj, uf_sigla=uf_sigla, modelo=modelo, protocolo=protocolo)
            return {"success": True, "protocolo_cancelamento": "999"}

        monkeypatch.setattr(svc.nfe_cancelamento_service, "cancelar_nfe_sync", _fake_cancelar)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert chamado["cnpj"] == "12345678000199"
        assert chamado["uf_sigla"] == "RJ"
        assert chamado["modelo"] == "65"
        assert chamado["protocolo"] == "123456"
        assert any("UPDATE comanda_nfce SET situacao = 'C'" in q[0] for q in cur.queries)

    def test_cancelamento_fiscal_persiste_protocolo_e_xml(self, monkeypatch):
        # Achado ao vivo 2026-08-23 (1º cancelamento real de NF-e/NFC-e
        # desta migração): antes só `situacao='C'` era gravado — o
        # protocolo/motivo/XML assinado do cancelamento real eram
        # descartados. Trava que os valores retornados por
        # `cancelar_nfe_sync` realmente chegam nos parâmetros do UPDATE.
        header = {"comanda": 1, "situacao": "PG"}
        nfce = {"num_nfce": 200, "situacao": "A", "protocolo_sefaz": "123456", "chave_acesso": "1" * 44}
        controle = {"cgc": "12345678000199", "uf": "RJ"}
        ones = _ones_cancelar(header, nfce=nfce, nf_incluido=False, controle=controle)
        cur = FakeCursor(one=ones, many=[[], []])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc.nfe_cancelamento_service, "cancelar_nfe_sync",
            lambda *a, **k: {
                "success": True, "protocolo_cancelamento": "135260000099999",
                "xml_evento": "<evento>cancelado</evento>",
            },
        )
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        update_q = next(q for q in cur.queries if q[0].strip().startswith("UPDATE comanda_nfce") and "protocolo_cancelamento" in q[0])
        assert "135260000099999" in update_q[1]
        assert "<evento>cancelado</evento>" in update_q[1]
        # A migração idempotente de colunas foi chamada (só quando há
        # cancelamento fiscal real, não em toda comanda cancelada).
        assert any("ALTER TABLE comanda_nfce ADD protocolo_cancelamento" in q[0] for q in cur.queries)

    def test_sefaz_recusa_bloqueia_cancelamento_inteiro(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        nfce = {"num_nfce": 200, "situacao": "A", "protocolo_sefaz": "123456", "chave_acesso": "1" * 44}
        controle = {"cgc": "1", "uf": "RJ"}
        ones = _ones_cancelar(header, nfce=nfce, nf_incluido=False, controle=controle)
        cur = FakeCursor(one=ones)
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc.nfe_cancelamento_service, "cancelar_nfe_sync",
            lambda *a, **k: {"success": False, "message": "Duplicidade de Evento (573)"},
        )
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is False
        assert "SEFAZ" in r["message"]
        assert conn.committed is False
        # Nada de reversão local deve ter acontecido.
        assert not any("UPDATE comanda SET" in q[0] for q in cur.queries)

    def test_nf_usada_quando_nfce_ausente(self, monkeypatch):
        header = {"comanda": 1, "situacao": "PG"}
        nf = {"codigo": 900, "situacao": "A", "protocolo_sefaz": "", "chave_acesso": "2" * 44}
        ones = _ones_cancelar(header, nfce=None, nf_incluido=True, nf=nf, controle=None)
        cur = FakeCursor(one=ones, many=[[], []])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE n_fiscal SET situacao = 'C'" in q[0] for q in cur.queries)

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._cancelar_comanda_sync(_cancelar_req(), 1)
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


def _emitir_nfce_req(**over):
    base = dict(servidor="srv", banco="bd", usuario_alteracao=1, classe=1, plataforma="web", master=True)
    base.update(over)
    return EmitirNfceRequest(**base)


class TestEmitirNfceComandaSync:
    @pytest.fixture(autouse=True)
    def _modulo_nfce_ativo(self, monkeypatch):
        # Módulo "NFCe" (controle_aux.emite_nfce, 2026-08-20) — checado em
        # runtime dentro de _emitir_nfce_comanda_sync; mockado True por
        # padrão pra não exigir mais uma linha no FakeCursor de cada teste
        # já existente (nenhum deles testa o módulo desligado).
        monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfce_ativo_sync", lambda cur: True)

    @pytest.fixture(autouse=True)
    def _tp_amb_producao(self, monkeypatch):
        # Ambiente NFe/NFCe (controle_aux.ambiente_nfe, 2026-08-20) — antes
        # hardcodado "1" (produção) em todo lugar; agora resolvido em
        # runtime. Mockado "1" por padrão pra não exigir mais uma linha no
        # FakeCursor de cada teste já existente.
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")

    def _item_mov(self):
        return {"codigo_int": "P001", "descricao": "Produto Teste", "qtd": 1.0, "p_unit": 50.0,
                "cod_icms": "00", "origem": 0, "ncm": "12345678", "unidade": "UN"}

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_bloqueia_comanda_nao_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1, "situacao": "A", "cliente": None, "valor_venda": 50.0}])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is False
        assert "faturada" in r["message"].lower()

    def test_bloqueia_ja_tem_nfce(self, monkeypatch):
        cur = FakeCursor(one=[
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0},
            {"ok": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is False
        assert "já tem uma nfc-e" in r["message"].lower()

    def test_bloqueia_sem_itens(self, monkeypatch):
        cur = FakeCursor(one=[{"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is False
        assert "itens" in r["message"].lower()

    def test_bloqueia_produto_sem_tributacao(self, monkeypatch):
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None,
            {"cgc": "1", "uf": "RJ", "rz_social": "X"}, {"numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h"},
            None,  # PECAS_PROTOCOLO_ST
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: None)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is False
        assert "sem tributação" in r["message"].lower()

    def test_sucesso_grava_n_fiscal_comanda_nfce_comanda_nf(self, monkeypatch):
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None,
            {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE"},
            {"numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h"},
            None,  # PECAS_PROTOCOLO_ST
            {},  # taxas_nfce (resolver_taxa_nfce_para_ibs_cbs_sync) — sem flags de IBS/CBS
            None,  # contingencia_aberta_sync — sem contingência aberta
            {"codigo": 999},  # OUTPUT INSERTED.codigo do INSERT n_fiscal
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: {"cfop_livro": "5102"})
        monkeypatch.setattr(
            svc.nfe_emissao_service, "emitir_nfce_sync",
            lambda cur_, **kw: {
                "success": True, "message": "ok", "chave_acesso": "3" * 44, "protocolo_sefaz": "135000000001",
                "dh_recbto": "2026-07-21T10:00:00-03:00", "xml": "<NFe/>", "numero": 11, "serie": "1",
                "url_qrcode": "https://x",
            },
        )
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q[0].strip().upper().startswith("INSERT INTO N_FISCAL") for q in cur.queries)
        assert any("INSERT INTO comanda_nfce" in q[0] for q in cur.queries)
        assert any("INSERT INTO comanda_nf" in q[0] for q in cur.queries)
        # Achado 2026-08-24 (mesmo bug já corrigido no MDF-e 2026-08-23):
        # `dh_recbto` cru do SEFAZ (com offset "-03:00") quebra numa coluna
        # DATETIME — precisa chegar como `datetime` NAIVE já convertido,
        # nunca a string crua, no parâmetro do INSERT.
        insert_nf = next(q for q in cur.queries if q[0].strip().upper().startswith("INSERT INTO N_FISCAL"))
        import datetime as _dt
        dh_param = next(p for p in insert_nf[1] if isinstance(p, _dt.datetime))
        assert dh_param == _dt.datetime(2026, 7, 21, 10, 0, 0)
        assert any("UPDATE controle_aux SET numero_nfce" in q[0] for q in cur.queries)

    def test_sem_servico_frete_configurado_nao_resolve_frete(self, monkeypatch):
        # Achado real 2026-08-22: `controle_aux.SERVICO_FRETE_NFCE` já era
        # exposto em Controle do Sistema mas nunca lido na emissão — sem
        # essa config, o comportamento tem que continuar exatamente igual
        # a antes (frete_valor=0, sem transportador, sem query extra).
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None,
            {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE"},
            {"numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h"},  # sem SERVICO_FRETE_NFCE
            None,  # PECAS_PROTOCOLO_ST
            {},  # taxas_nfce
            None,  # contingencia_aberta_sync
            {"codigo": 999},
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: {"cfop_livro": "5102"})
        capturado = {}

        def _fake_emitir(cur_, **kw):
            capturado.update(kw)
            return {
                "success": True, "chave_acesso": "3" * 44, "protocolo_sefaz": "1", "dh_recbto": None,
                "xml": "<NFe/>", "numero": 11, "serie": "1", "url_qrcode": "https://x",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfce_sync", _fake_emitir)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is True
        assert capturado["frete_valor"] == 0
        assert capturado["transportador"] is None
        assert not any("Fornecedor_End" in q[0] for q in cur.queries if isinstance(q[0], str))

    def test_com_servico_frete_resolve_valor_e_transportador(self, monkeypatch):
        # Achado real 2026-08-22 (DAO_NFE.vb:2736-2745/5436-5476): o frete
        # da NFC-e é um item de SERVIÇO na própria comanda, cujo código é
        # configurável (`SERVICO_FRETE_NFCE`) — a soma dele vira <vFrete>
        # e decide modFrete=1 (com transportadora) ou 9.
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 150.0}, None,
            {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE"},
            {
                "numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h",
                "SERVICO_FRETE_NFCE": "S-FRETE", "TRANSPORTADOR_FRETE_NFCE": 55,
            },
            {"total": 20.0},  # SUM(qtd*p_unit) do item de frete
            {"codigo": "12345678000100", "nome": "TRANSPORTADORA X", "inscr_est": "ISENTO"},
            {"endereco": "RUA DO FRETE", "numero": 10, "complemento": "", "bairro": "CENTRO", "cidade": "RIO DE JANEIRO", "uf": "RJ"},
            None,  # PECAS_PROTOCOLO_ST
            {},  # taxas_nfce
            None,  # contingencia_aberta_sync
            {"codigo": 999},
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: {"cfop_livro": "5102"})
        capturado = {}

        def _fake_emitir(cur_, **kw):
            capturado.update(kw)
            return {
                "success": True, "chave_acesso": "3" * 44, "protocolo_sefaz": "1", "dh_recbto": None,
                "xml": "<NFe/>", "numero": 11, "serie": "1", "url_qrcode": "https://x",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfce_sync", _fake_emitir)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is True
        assert capturado["frete_valor"] == 20.0
        assert capturado["transportador"]["cgc_cpf"] == "12345678000100"
        assert capturado["transportador"]["nome"] == "TRANSPORTADORA X"
        assert capturado["transportador"]["cidade"] == "RIO DE JANEIRO"

    def test_servico_frete_sem_valor_na_comanda_nao_busca_transportador(self, monkeypatch):
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None,
            {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE"},
            {
                "numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h",
                "SERVICO_FRETE_NFCE": "S-FRETE", "TRANSPORTADOR_FRETE_NFCE": 55,
            },
            {"total": 0},  # nenhum item de frete nesta comanda
            None,  # PECAS_PROTOCOLO_ST
            {},  # taxas_nfce
            None,  # contingencia_aberta_sync
            {"codigo": 999},
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: {"cfop_livro": "5102"})
        capturado = {}

        def _fake_emitir(cur_, **kw):
            capturado.update(kw)
            return {
                "success": True, "chave_acesso": "3" * 44, "protocolo_sefaz": "1", "dh_recbto": None,
                "xml": "<NFe/>", "numero": 11, "serie": "1", "url_qrcode": "https://x",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfce_sync", _fake_emitir)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is True
        assert capturado["frete_valor"] == 0
        assert capturado["transportador"] is None
        assert not any("FROM fornecedor WHERE" in q[0] for q in cur.queries if isinstance(q[0], str))

    def test_ibs_cbs_resolve_de_taxas_nfce_nao_de_taxas(self, monkeypatch):
        # Achado 2026-08-19: IBS/CBS usa `taxas_nfce` (por cod_icms), NÃO a
        # linha de `taxas` já resolvida por `_resolver_tributacao_sync`
        # (essa é só pro sistema tributário antigo — ICMS/CSOSN/PIS/
        # COFINS). Este teste prova a separação: a linha de `taxas` não
        # tem NENHUM campo de IBS/CBS, só a de `taxas_nfce` tem — se o
        # código (por engano) reaproveitasse a linha errada, o item
        # sairia sem `<IBSCBS>` no XML.
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None,
            {"cgc": "12345678000199", "uf": "RJ", "rz_social": "EMPRESA TESTE"},
            {"numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h"},
            None,  # PECAS_PROTOCOLO_ST
            {  # taxas_nfce (resolver_taxa_nfce_para_ibs_cbs_sync) — COM IBS/CBS real
                "INFORMA_CBS_IBS": 1, "CST_IBS": "000", "CCLASSTRIB_IBS": "000001",
                "ALQT_IBS_ESTADO": 8.0, "ALQT_IBS_MUNICIPIO": 2.0, "ALQT_CBS_ESTADO": 0.9,
            },
            None,  # contingencia_aberta_sync — sem contingência aberta
            {"codigo": 999},
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)
        # `taxas` (sistema antigo) NÃO tem nenhum campo de IBS/CBS —
        # prova que o item não reaproveita essa linha por engano.
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: {"cfop_livro": "5102"})

        itens_capturados = {}

        def _emitir_fake(cur_, **kw):
            itens_capturados["itens"] = kw["itens_resolvidos"]
            return {
                "success": True, "message": "ok", "chave_acesso": "3" * 44, "protocolo_sefaz": "135000000001",
                "dh_recbto": "2026-07-21T10:00:00-03:00", "xml": "<NFe/>", "numero": 11, "serie": "1",
                "url_qrcode": "https://x",
            }

        monkeypatch.setattr(svc.nfe_emissao_service, "emitir_nfce_sync", _emitir_fake)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is True
        xml_item = itens_capturados["itens"][0]["ibs_cbs_xml"]
        assert "<IBSCBS>" in xml_item
        assert "<CST>000</CST>" in xml_item
        assert "<vIBSUF>4.00</vIBSUF>" in xml_item  # 50.0 (qtd*p_unit) * 8% / 100

    def test_bloqueia_quando_sefaz_recusa(self, monkeypatch):
        ones = [
            {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 50.0}, None,
            {"cgc": "1", "uf": "RJ", "rz_social": "X"}, {"numero_nfce": 10, "serie_nfce": "1", "csc": "1", "csc_hash": "h"},
            None,
            {},  # taxas_nfce (resolver_taxa_nfce_para_ibs_cbs_sync)
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_emissao_service, "_resolver_tributacao_sync", lambda *a, **k: {"cfop_livro": "5102"})
        monkeypatch.setattr(
            svc.nfe_emissao_service, "emitir_nfce_sync",
            lambda cur_, **kw: {"success": False, "message": "SEFAZ recusou a emissão (status 539): Duplicidade."},
        )
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is False
        assert "539" in r["message"]
        assert conn.committed is False

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._emitir_nfce_comanda_sync(_emitir_nfce_req(), 1)
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


def _emitir_nfse_req(**over):
    base = dict(servidor="srv", banco="bd", usuario_alteracao=1, classe=1, plataforma="web", master=True)
    base.update(over)
    return EmitirNfseRequest(**base)


class TestEmitirNfseComandaSync:
    """Fase 3 do pacote de emissão fiscal (NFS-e via DPS Nacional) — ver
    `nfse_emissao_service.py`. Espelha `TestEmitirNfceComandaSync`, mas com
    o passo extra de checagem do módulo `sefin_nacional` (Regra de Módulo
    Ativo) e a resolução do item de SERVIÇO (join com `servicos`, não
    `pecas`)."""

    @pytest.fixture(autouse=True)
    def _tp_amb_producao(self, monkeypatch):
        # Ambiente NFe/NFSe (controle_aux.ambiente_nfe, 2026-08-20) — antes
        # hardcodado "1" (produção); agora resolvido em runtime. Mockado
        # "1" por padrão pra não exigir mais uma linha no FakeCursor de
        # cada teste já existente.
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")

    def _item_mov(self):
        return {
            "codigo_int": "SALD", "descricao": "Alinhamento Dianteiro", "cod_lista_servico": "140101",
            "cod_servico_municipio": "015", "qtd": 1.0, "p_unit": 100.0,
        }

    def _controle_row(self):
        return {"cgc": "12345678000199", "cidade": "RIO DE JANEIRO", "uf": "RJ", "simples_servico": 13.8}

    def _controle_aux_row(self):
        return {
            "numero_DPS": 10, "serie_DPS": "1", "opcao_simples": 1, "RegimeEspecialTributacao": 0,
            "codigo_nbs": "120018900",
        }

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(master=False, classe=2), 1)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_modulo_sefin_nacional_desligado(self, monkeypatch):
        cur = FakeCursor(one=[{"sefin_nacional": 0}])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert "sefin nacional" in r["message"].lower()

    def test_comanda_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[{"sefin_nacional": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_bloqueia_comanda_nao_faturada(self, monkeypatch):
        cur = FakeCursor(one=[{"sefin_nacional": 1}, {"comanda": 1, "situacao": "A", "cliente": None, "valor_venda": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert "faturada" in r["message"].lower()

    def test_bloqueia_ja_tem_nfse(self, monkeypatch):
        cur = FakeCursor(one=[
            {"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, {"ok": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert "já tem uma nfs-e" in r["message"].lower()

    def test_bloqueia_sem_itens_de_servico(self, monkeypatch):
        cur = FakeCursor(
            one=[{"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, None],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert "serviço" in r["message"].lower()

    def test_bloqueia_municipio_desconhecido(self, monkeypatch):
        ones = [
            {"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, None,
            {"cgc": "1", "cidade": "CIDADE INVENTADA", "uf": "ZZ"}, self._controle_aux_row(),
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert "município" in r["message"].lower()

    def test_sucesso_grava_n_fiscal_comanda_nf_tipo_2(self, monkeypatch):
        ones = [
            {"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, None,
            self._controle_row(), self._controle_aux_row(),
            {"codigo": 999},  # OUTPUT INSERTED.codigo do INSERT n_fiscal
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc.nfse_emissao_service, "emitir_nfse_sync",
            lambda cur_, **kw: {
                "success": True, "message": "ok", "chave_acesso": "3" * 50, "id_dps": "DPS" + "0" * 42,
                "xml_dps": "<DPS/>", "xml_nfse": "<NFse/>", "numero": 11, "serie": "1",
            },
        )
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q[0].strip().upper().startswith("INSERT INTO DPS") for q in cur.queries)
        assert any(q[0].strip().upper().startswith("INSERT INTO N_FISCAL") for q in cur.queries)
        assert any("INSERT INTO comanda_nf" in q[0] and "%s, %s, 2, 'A'" in q[0] for q in cur.queries)
        assert any("UPDATE controle_aux SET numero_DPS" in q[0] for q in cur.queries)

    def test_ibs_cbs_do_servico_resolve_de_taxas_nfce_por_cod_icms(self, monkeypatch):
        # Achado 2026-08-19: a fonte resolve IBS/CBS de serviço com o MESMO
        # padrão simples de produto (`taxas_nfce` por `cod_icms`, sem
        # tipo_mov/destino/etc.) — corrige uma integração anterior que
        # reaproveitava por engano a cascata de `_resolver_tributacao_sync`
        # (pro sistema tributário antigo, tabela `taxas`).
        item_com_icms = {**self._item_mov(), "cod_icms": "05"}
        ones = [
            {"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, None,
            self._controle_row(), self._controle_aux_row(),
            {  # taxas_nfce (resolver_taxa_nfce_para_ibs_cbs_sync)
                "INFORMA_CBS_IBS": 1, "CST_IBS": "200", "CCLASSTRIB_IBS": "000123",
                "ALQT_IBS_ESTADO": 5.0, "ALQT_IBS_MUNICIPIO": 1.0, "ALQT_CBS_ESTADO": 0.5,
            },
            {"codigo": 999},
        ]
        cur = FakeCursor(one=ones, many=[[item_com_icms]])
        _patch(monkeypatch, cur)

        kwargs_capturados = {}

        def _emitir_fake(cur_, **kw):
            kwargs_capturados.update(kw)
            return {
                "success": True, "message": "ok", "chave_acesso": "3" * 50, "id_dps": "DPS" + "0" * 42,
                "xml_dps": "<DPS/>", "xml_nfse": "<NFse/>", "numero": 11, "serie": "1",
            }

        monkeypatch.setattr(svc.nfse_emissao_service, "emitir_nfse_sync", _emitir_fake)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is True
        assert kwargs_capturados["ibs_cbs_cst"] == "200"
        assert kwargs_capturados["ibs_cbs_classtrib"] == "000123"
        # `execute` da resolução de taxas_nfce foi feita com cod_icms do
        # item + UF da própria empresa (_controle_row()'s uf="RJ") + tipo_mov="S01".
        assert any("taxas_nfce" in q and p == ("05", "RJ", "S01") for q, p in cur.queries)

    def test_bloqueia_quando_adn_recusa(self, monkeypatch):
        ones = [
            {"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, None,
            self._controle_row(), self._controle_aux_row(),
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc.nfse_emissao_service, "emitir_nfse_sync",
            lambda cur_, **kw: {"success": False, "message": "ADN recusou a emissão da NFS-e: erro."},
        )
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert conn.committed is False

    def test_cod_servico_municipio_e_codigo_nbs_e_simples_servico_repassados(self, monkeypatch):
        # Achado 2026-08-24 (rastreio até a raiz de `DAO_NFE.vb`): `cTribMun`
        # é `servicos.cod_servico_municipio` (por serviço), `cNBS` é
        # `controle_aux.codigo_nbs` (por empresa), e o percentual real do
        # `pTotTribSN` vem de `controle.simples_servico` — os 3 precisam
        # chegar intactos em `nfse_emissao_service.emitir_nfse_sync`.
        ones = [
            {"sefin_nacional": 1}, {"comanda": 1, "situacao": "PG", "cliente": None, "valor_venda": 100.0}, None,
            self._controle_row(), self._controle_aux_row(),
            {"codigo": 999},  # OUTPUT INSERTED.codigo do INSERT n_fiscal
        ]
        cur = FakeCursor(one=ones, many=[[self._item_mov()]])
        _patch(monkeypatch, cur)

        kwargs_capturados = {}

        def _emitir_fake(cur_, **kw):
            kwargs_capturados.update(kw)
            return {
                "success": True, "message": "ok", "chave_acesso": "3" * 50, "id_dps": "DPS" + "0" * 42,
                "xml_dps": "<DPS/>", "xml_nfse": "<NFse/>", "numero": 11, "serie": "1",
            }

        monkeypatch.setattr(svc.nfse_emissao_service, "emitir_nfse_sync", _emitir_fake)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is True
        assert kwargs_capturados["codigo_nbs"] == "120018900"
        assert kwargs_capturados["simples_servico_pct"] == 13.8
        assert kwargs_capturados["itens"][0]["cod_servico_municipio"] == "015"

    def test_falha_conexao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._emitir_nfse_comanda_sync(_emitir_nfse_req(), 1)
        assert r["success"] is False
        assert "Falha conexão" in r["message"]
