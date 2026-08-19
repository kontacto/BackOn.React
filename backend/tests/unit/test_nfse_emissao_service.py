"""Testes unitários da emissão de NFS-e via DPS Nacional
(`nfse_emissao_service.py`) — Fase 3 do pacote de emissão fiscal. Mesmo
compromisso do resto do pacote: certificado sempre autoassinado gerado em
memória, `nfe_fiscal_common.transmitir_json_mtls` sempre mockada — nunca
uma chamada de rede de verdade nem o certificado real de nenhuma empresa."""
import base64
import datetime
import gzip

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree

import services.nfse_emissao_service as svc


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


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


class TestMontarIdDps:
    def test_id_tem_45_caracteres_e_prefixo_dps(self):
        id_dps = svc.montar_id_dps(
            cod_municipio="3304557", tipo_inscricao="2", inscricao_federal="12345678000199",
            serie="1", numero_dps=100,
        )
        assert len(id_dps) == 45
        assert id_dps.startswith("DPS")
        assert id_dps[3:10] == "3304557"
        assert id_dps[10] == "2"
        assert id_dps[11:25] == "12345678000199"
        assert id_dps[25:30] == "00001"
        assert id_dps[30:45] == "0" * 12 + "100"

    def test_serie_e_numero_com_zeros_a_esquerda(self):
        id_dps = svc.montar_id_dps(
            cod_municipio="1400159", tipo_inscricao="2", inscricao_federal="1",
            serie="900", numero_dps=1028360962,
        )
        assert id_dps == "DPS" + "1400159" + "2" + "0" * 13 + "1" + "00900" + "000001028360962"


class TestMontarXmlDps:
    def test_monta_xml_com_servico_e_valores(self):
        itens = [{"codigo_int": "SALD", "descricao": "Alinhamento Dianteiro", "cod_lista_servico": "140101", "valor": 100.0}]
        xml_bytes, id_dps = svc._montar_xml_dps(
            id_dps="DPS" + "3304557" + "2" + "12345678000199" + "00001" + "0" * 14 + "1",
            tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="12345678000199",
            opcao_simples_nacional=True, regime_especial_tributacao=0,
            tomador={"cgc_cpf": "12345678901", "nome": "CLIENTE TESTE"}, itens=itens,
        )
        xml = xml_bytes.decode("utf-8")
        assert f'Id="{id_dps}"' in xml
        assert "<cTribNac>140101</cTribNac>" in xml
        assert "<xDescServ>Alinhamento Dianteiro</xDescServ>" in xml
        assert "<vServ>100.00</vServ>" in xml
        assert "<opSimpNac>1</opSimpNac>" in xml
        assert "<CPF>12345678901</CPF>" in xml
        assert "<xNome>CLIENTE TESTE</xNome>" in xml
        # É XML bem-formado.
        etree.fromstring(xml_bytes)

    def test_soma_valores_de_multiplos_itens(self):
        itens = [
            {"codigo_int": "A", "descricao": "Serviço A", "cod_lista_servico": "0101", "valor": 30.0},
            {"codigo_int": "B", "descricao": "Serviço B", "cod_lista_servico": "0101", "valor": 20.5},
        ]
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None, itens=itens,
        )
        assert "<vServ>50.50</vServ>" in xml_bytes.decode("utf-8")

    def test_ibs_cbs_cst_classtrib_incluidos_quando_presentes(self):
        # Parte A do ecossistema fiscal (2026-08-19) — só CST/cClassTrib,
        # nunca valor monetário (leiaute de transição, ver docstring).
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[{"codigo_int": "A", "descricao": "X", "cod_lista_servico": "0101", "valor": 10.0}],
            ibs_cbs_cst="000", ibs_cbs_classtrib="000001",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<gIBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></gIBSCBS>" in xml
        etree.fromstring(xml_bytes)

    def test_sem_ibs_cbs_cst_nao_inclui_bloco(self):
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[{"codigo_int": "A", "descricao": "X", "cod_lista_servico": "0101", "valor": 10.0}],
        )
        assert "<gIBSCBS>" not in xml_bytes.decode("utf-8")

    def test_sem_tomador_nao_inclui_tag_toma(self):
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[{"codigo_int": "A", "descricao": "X", "cod_lista_servico": "0101", "valor": 10.0}],
        )
        assert "<toma>" not in xml_bytes.decode("utf-8")


class TestEmpacotarDps:
    def test_ida_e_volta_preserva_conteudo(self):
        xml_original = b"<DPS>conteudo de teste</DPS>"
        empacotado = svc._empacotar_dps(xml_original)
        # formato esperado pelo ADN: base64 de um gzip.
        assert gzip.decompress(base64.b64decode(empacotado)) == xml_original


class TestEmitirNfseSync:
    def _item(self):
        return {"codigo_int": "SALD", "descricao": "Alinhamento Dianteiro", "cod_lista_servico": "140101", "valor": 100.0}

    def test_bloqueia_sem_itens(self):
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None, itens=[], tp_amb="1",
        )
        assert r["success"] is False
        assert "serviço" in r["message"].lower()

    def test_bloqueia_sem_codigo_municipio(self):
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[self._item()], tp_amb="1",
        )
        assert r["success"] is False
        assert "município" in r["message"].lower()

    def test_bloqueia_ambiente_nao_reconhecido(self):
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[self._item()], tp_amb="9",
        )
        assert r["success"] is False
        assert "ambiente" in r["message"].lower()

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[self._item()], tp_amb="1",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_com_adn_mockado(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        nfse_xml_fake = b"<NFse><infNFse>autorizada</infNFse></NFse>"
        resposta_fake = {
            "chaveAcesso": "3" * 50,
            "nfseXmlGZipB64": base64.b64encode(gzip.compress(nfse_xml_fake)).decode("ascii"),
        }
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", lambda payload, url, k, c: resposta_fake)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="12345678000199", cod_municipio="3304557",
            opcao_simples_nacional=True, regime_especial_tributacao=0, proximo_numero=100, serie="1",
            tomador=None, itens=[self._item()], tp_amb="1",
        )
        assert r["success"] is True
        assert r["chave_acesso"] == "3" * 50
        assert r["xml_nfse"] == nfse_xml_fake.decode("utf-8")
        assert "<Signature" in r["xml_dps"] or "Signature>" in r["xml_dps"]

    def test_adn_recusa_emissao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = {"_erro_http": 400, "mensagens": [{"codigo": "E0714", "descricao": "Arquivo enviado com erro na assinatura"}]}
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", lambda payload, url, k, c: resposta_fake)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[self._item()], tp_amb="1",
        )
        assert r["success"] is False
        assert "E0714" in r["message"]

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", _falha)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[self._item()], tp_amb="1",
        )
        assert r["success"] is False
        assert "adn" in r["message"].lower()
