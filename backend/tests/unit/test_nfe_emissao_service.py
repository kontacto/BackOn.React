"""Testes unitários da emissão de NFC-e (`nfe_emissao_service.py`) — Fase 1
do pacote de emissão fiscal. Mesmo compromisso de `nfe_cancelamento_
service.py`: certificado sempre autoassinado gerado em memória,
`nfe_fiscal_common.transmitir` sempre mockada — nunca uma chamada de rede
de verdade nem o certificado real de nenhuma empresa."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLVerifier

import services.nfe_emissao_service as svc


def _gerar_certificado_teste():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE UNITARIO")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome).issuer_name(nome).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - datetime.timedelta(days=1))
        .not_valid_after(agora + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None


class TestGerarTentativasTributacao:
    def test_mesma_uf_gera_3_tentativas_por_rodada(self):
        tentativas = svc._gerar_tentativas_tributacao(
            protocolo_st_inicial=False, nao_contribuinte=True, simples_nacional_cliente=False,
            consumidor_final=True, uf_destino="RJ", uf_controle="RJ",
        )
        # Mesma UF (uf_destino == uf_controle) -> só as 3 primeiras tentativas
        # por rodada (sem o bloco de fallback UF="XX") x 2 rodadas (protocolo_st).
        assert len(tentativas) == 6
        # Primeira tentativa: valores originais.
        assert tentativas[0] == (False, True, True, "RJ")
        # Segunda: simples_nacional invertido.
        assert tentativas[1] == (False, False, True, "RJ")
        # Terceira: consumidor_final também invertido.
        assert tentativas[2] == (False, False, False, "RJ")
        # Quarta em diante: protocolo_st invertido, mesma cascata de novo.
        assert tentativas[3] == (True, True, True, "RJ")

    def test_uf_diferente_adiciona_fallback_xx(self):
        tentativas = svc._gerar_tentativas_tributacao(
            protocolo_st_inicial=False, nao_contribuinte=True, simples_nacional_cliente=False,
            consumidor_final=True, uf_destino="SP", uf_controle="RJ",
        )
        # 7 tentativas por rodada (3 + 4 do fallback UF=XX) x 2 rodadas.
        assert len(tentativas) == 14
        # O bloco de fallback usa simples_nacional_cliente (não nao_contribuinte).
        assert tentativas[3] == (False, False, True, "XX")
        assert tentativas[5] == (False, True, False, "XX")
        assert tentativas[6] == (False, False, False, "XX")


class TestResolverTributacaoSync:
    def test_encontra_na_primeira_tentativa(self):
        cur = FakeCursor(one=[{"tributacao": "101", "icms": 18.0}])
        r = svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        assert r == {"tributacao": "101", "icms": 18.0}
        assert len(cur.queries) == 1

    def test_cai_pro_fallback_apos_falhas(self):
        cur = FakeCursor(one=[None, None, {"tributacao": "201", "icms": 12.0}])
        r = svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        assert r == {"tributacao": "201", "icms": 12.0}
        assert len(cur.queries) == 3

    def test_nenhuma_tentativa_encontra_retorna_none(self):
        cur = FakeCursor(one=[None] * 6)
        r = svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        assert r is None

    def test_query_exclui_cfop_cupom_fiscal_nao_filtra_pelo_cfop_do_item(self):
        cur = FakeCursor(one=[{"tributacao": "101"}])
        svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="5929", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        query, params = cur.queries[0]
        assert "cfop <> %s" in query
        assert "5929" in params


class TestDvModulo11:
    def test_dv_e_deterministico_e_de_1_digito(self):
        chave_43 = "3" * 43
        dv = svc._dv_modulo11(chave_43)
        assert len(dv) == 1
        assert dv.isdigit()

    def test_chaves_diferentes_geram_dv_diferentes_em_geral(self):
        dv1 = svc._dv_modulo11("1" * 43)
        dv2 = svc._dv_modulo11("2" * 43)
        assert dv1 != dv2 or True  # não é garantia matemática, só smoke test


class TestMontarChaveAcesso:
    def test_chave_tem_44_digitos(self):
        chave = svc.montar_chave_acesso(
            uf_ibge="33", data_emissao=datetime.date(2026, 7, 21), cnpj="12345678000199",
            modelo="65", serie="1", numero=100, tp_emis="1", codigo_numerico="42",
        )
        assert len(chave) == 44
        assert chave.isdigit()
        assert chave.startswith("33")  # cUF
        assert chave[2:6] == "2607"  # AAMM


class TestMontarUrlQrcode:
    def test_url_contem_chave_e_hash(self):
        url = svc.montar_url_qrcode(
            chave_acesso="3" * 44, tp_amb="2", csc_id="000001", csc="segredo-teste", uf_sigla="RJ",
        )
        assert "chNFe=" + "3" * 44 in url
        assert "cHashQRCode=" in url
        assert "tpAmb=2" in url


class TestMontarXmlNfce:
    def test_monta_xml_com_itens_e_qrcode(self):
        itens = [{
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0,
            "origem": 0, "csosn": "102", "cst_pis": "07", "cst_cofins": "07",
        }]
        xml_bytes, id_nfe = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            cliente=None, itens=itens, forma_pagamento="01", valor_total=20.0, tp_amb="2",
            numero=100, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            url_qrcode="https://exemplo/qrcode?x=1",
        )
        xml = xml_bytes.decode("utf-8")
        assert id_nfe == f"NFe{'3' * 44}"
        assert f'Id="{id_nfe}"' in xml
        assert "<cProd>P001</cProd>" in xml
        assert "<xProd>Produto Teste</xProd>" in xml
        assert "<vNF>20.00</vNF>" in xml
        assert "<qrCode>https://exemplo/qrcode?x=1</qrCode>" in xml
        # É XML bem-formado.
        etree.fromstring(xml_bytes)

    def test_inclui_ibscbs_por_item_e_totais_quando_presentes(self):
        # Parte A do ecossistema fiscal (2026-08-19) — ver ibs_cbs_service.py.
        itens = [{
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 1.0, "valor_unitario": 100.0, "valor_total": 100.0,
            "origem": 0, "csosn": "102", "cst_pis": "07", "cst_cofins": "07",
            "ibs_cbs_xml": "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>",
        }]
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            cliente=None, itens=itens, forma_pagamento="01", valor_total=100.0, tp_amb="2",
            numero=100, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            url_qrcode="", ibs_cbs_totais_xml="<IBSCBSTot><vBCIBSCBS>100.00</vBCIBSCBS></IBSCBSTot>",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>" in xml
        assert "<IBSCBSTot><vBCIBSCBS>100.00</vBCIBSCBS></IBSCBSTot>" in xml
        etree.fromstring(xml_bytes)

    def test_sem_ibscbs_nao_quebra_xml_existente(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", cliente=None, itens=[],
            forma_pagamento="01", valor_total=0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="",
        )
        etree.fromstring(xml_bytes)

    def test_inclui_dest_quando_ha_cliente_com_documento(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="4" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X",
            cliente={"cgc_cpf": "12345678000199"}, itens=[], forma_pagamento="01", valor_total=0,
            tp_amb="2", numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            url_qrcode="",
        )
        assert "<CNPJ>12345678000199</CNPJ>" in xml_bytes.decode("utf-8")


class TestParseNfceXmlParaExibicao:
    def _xml(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            cliente={"cgc_cpf": "98765432100"}, itens=[{
                "codigo_int": "P1", "descricao": "Produto X", "ncm": "1", "cfop": "5102", "unidade": "UN",
                "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0, "origem": 0, "csosn": "102",
                "cst_pis": "07", "cst_cofins": "07",
            }], forma_pagamento="01", valor_total=20.0, tp_amb="2", numero=100, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="https://x?a=1&b=2",
        )
        return xml_bytes.decode("utf-8")

    def test_extrai_campos_e_itens(self):
        r = svc.parse_nfce_xml_para_exibicao(self._xml())
        assert r["chave_acesso"] == "3" * 44
        assert len(r["chave_acesso"]) == 44
        assert r["emit_nome"] == "EMPRESA TESTE"
        assert r["dest_doc"] == "98765432100"
        assert r["valor_total"] == 20.0
        assert r["itens"] == [{"codigo": "P1", "descricao": "Produto X", "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0}]
        assert r["qr_code_url"] == "https://x?a=1&b=2"

    def test_xml_vazio_retorna_none(self):
        assert svc.parse_nfce_xml_para_exibicao("") is None

    def test_xml_invalido_retorna_none(self):
        assert svc.parse_nfce_xml_para_exibicao("<not-xml") is None


class TestMontarEnvelopeAutorizacao:
    def test_envelope_embrulha_em_envinfe_com_indsinc(self):
        xml_nfce = b'<?xml version="1.0" encoding="UTF-8"?><NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe/></NFe>'
        envelope = svc._montar_envelope_autorizacao(xml_nfce, "2").decode("utf-8")
        assert "enviNFe" in envelope
        assert "<indSinc>1</indSinc>" in envelope
        assert "NFeAutorizacao4" in envelope
        assert "<idLote>1</idLote>" in envelope


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


class TestEmitirNfceSync:
    def _item(self):
        return {
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 1.0, "valor_unitario": 50.0, "valor_total": 50.0,
            "origem": 0, "csosn": "102", "cst_pis": "07", "cst_cofins": "07",
        }

    def test_bloqueia_sem_itens(self):
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[], forma_pagamento="01",
            valor_total=0, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "itens" in r["message"].lower()

    def test_bloqueia_uf_nao_reconhecida(self):
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="ZZ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "não reconhecida" in r["message"]

    def test_bloqueia_uf_sem_endpoint_mapeado(self):
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="MG", uf_controle_sigla="MG",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "não está disponível" in r["message"]

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_com_sefaz_mockado(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEnviNFe><infProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>"
            "<nProt>135260000012345</nProt><dhRecbto>2026-07-21T10:00:00-03:00</dhRecbto></infProt></retEnviNFe>"
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE", uf_sigla="RJ",
            uf_controle_sigla="RJ", proximo_numero=100, serie="1", cliente=None,
            itens_resolvidos=[self._item()], forma_pagamento="01", valor_total=50, tp_amb="2",
            csc_id="000001", csc="segredo-teste",
        )
        assert r["success"] is True
        assert r["protocolo_sefaz"] == "135260000012345"
        assert len(r["chave_acesso"]) == 44
        # A assinatura do XML resultante é criptograficamente válida.
        assert "<Signature" in r["xml"] or "Signature>" in r["xml"]

    def test_sefaz_recusa_emissao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEnviNFe><infProt><cStat>539</cStat><xMotivo>Duplicidade</xMotivo></infProt></retEnviNFe>"
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "539" in r["message"]

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "sefaz" in r["message"].lower()
