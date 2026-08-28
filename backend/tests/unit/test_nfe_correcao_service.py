"""Testes UNITÁRIOS da Carta de Correção Eletrônica (CC-e, evento SEFAZ
110110) — `nfe_correcao_service.py`. Mesmo princípio de segurança de
`test_nfe_cancelamento_service.py`: nenhum teste aqui usa certificado real
nem faz chamada de rede de verdade — `nfe_fiscal_common.transmitir` é
sempre mockada via `monkeypatch`. Certificado gerado na hora,
autoassinado, só para exercitar a lógica de assinatura XML."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLVerifier

import services.nfe_correcao_service as svc
from services import nfe_fiscal_common


def _gerar_certificado_teste():
    """Certificado autoassinado só para teste — nunca usado fora deste
    arquivo, nunca transmitido a lugar nenhum."""
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
    return key, cert


def _certs_pem():
    key, cert = _gerar_certificado_teste()
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


class TestResolverUrl:
    def test_uf_svrs_resolve_modelo_55(self):
        # RJ = 33, está no grupo SVRS.
        assert svc._resolver_url("33", "1") == "https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"
        assert svc._resolver_url("33", "2") == "https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"

    def test_uf_fora_do_grupo_svrs_retorna_none(self):
        # MG = 31, tem SEFAZ própria — não mapeada ainda neste módulo.
        assert svc._resolver_url("31", "1") is None

    def test_mesmo_endpoint_do_cancelamento(self):
        # Confirma que o mapa foi realmente compartilhado (extraído pra
        # nfe_fiscal_common.py), não duplicado com valor divergente.
        import services.nfe_cancelamento_service as canc
        assert svc._resolver_url("33", "1") == canc._resolver_url("33", "55", "1")


class TestMontarXmlEventoCorrecao:
    def test_monta_evento_correcao_com_campos_esperados(self):
        xml_bytes, id_evento = svc._montar_xml_evento_correcao(
            "33", "12345678000199", "3" * 44, "Motivo de teste com mais de 15 caracteres", 1, "2",
        )
        xml = xml_bytes.decode("utf-8")
        assert id_evento == f"ID110110{'3' * 44}01"
        assert "<tpEvento>110110</tpEvento>" in xml
        assert "<nSeqEvento>1</nSeqEvento>" in xml
        assert "<cOrgao>33</cOrgao>" in xml
        assert "<tpAmb>2</tpAmb>" in xml
        assert "<CNPJ>12345678000199</CNPJ>" in xml
        assert f'<chNFe>{"3" * 44}</chNFe>' in xml
        assert "<descEvento>Carta de Correcao</descEvento>" in xml
        assert "Motivo de teste" in xml
        assert svc.X_COND_USO in xml
        assert f'Id="{id_evento}"' in xml
        # Ordem exigida pela NT 2011.003: descEvento, xCorrecao, xCondUso.
        assert xml.index("<descEvento>") < xml.index("<xCorrecao>") < xml.index("<xCondUso>")

    def test_id_evento_usa_sequencial_de_2_digitos(self):
        _, id_evento = svc._montar_xml_evento_correcao("33", "1", "2" * 44, "Motivo com bastante texto aqui", 7, "1")
        assert id_evento.endswith("07")

    def test_escapa_caracteres_especiais_no_motivo(self):
        xml_bytes, _ = svc._montar_xml_evento_correcao("33", "1", "2" * 44, "Motivo com & e < e > mais texto", 1, "1")
        xml = xml_bytes.decode("utf-8")
        assert "&amp;" in xml
        assert "Motivo com & e" not in xml


class TestAssinarEvento:
    def test_assinatura_e_valida_e_verificavel(self):
        key_pem, cert_pem = _certs_pem()
        xml_bytes, id_evento = svc._montar_xml_evento_correcao("33", "1", "4" * 44, "Motivo de teste com mais de 15 caracteres", 1, "2")
        assinado = nfe_fiscal_common.assinar_xml(xml_bytes, id_evento, key_pem, cert_pem)
        root = etree.fromstring(assinado)
        assert root.find("{*}Signature") is not None or any(c.tag.endswith("Signature") for c in root)
        XMLVerifier().verify(assinado, x509_cert=cert_pem)


class TestMontarEnvelopeSoap:
    def test_envelope_embrulha_evento_em_soap12(self):
        xml_evento = b'<?xml version="1.0" encoding="UTF-8"?><evento xmlns="http://www.portalfiscal.inf.br/nfe"><infEvento/></evento>'
        envelope = svc._montar_envelope_soap(xml_evento).decode("utf-8")
        assert "soap12:Envelope" in envelope
        assert "nfeDadosMsg" in envelope
        assert "NFeRecepcaoEvento4" in envelope
        assert "<envEvento" in envelope
        assert "<idLote>1</idLote>" in envelope
        assert envelope.count("<?xml") == 1


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


class TestEmitirCartaCorrecaoSync:
    def test_bloqueia_motivo_curto(self):
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="curto", n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "15 caracteres" in r["message"]

    def test_bloqueia_motivo_longo_demais(self):
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="x" * 1001, n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "1000 caracteres" in r["message"]

    def test_bloqueia_chave_acesso_invalida(self):
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="123", motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "chave de acesso" in r["message"].lower()

    def test_bloqueia_sequencial_fora_da_faixa(self):
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=21, tp_amb="2",
        )
        assert r["success"] is False
        assert "20" in r["message"]

    def test_bloqueia_uf_nao_mapeada(self, monkeypatch):
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="MG", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "MG" in r["message"]

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_com_sefaz_mockado(self, monkeypatch):
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEvento><infEvento><cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo>"
            "<nProt>135260000012345</nProt><dhRegEvento>2026-08-22T10:00:00-03:00</dhRegEvento></infEvento></retEvento>"
        )
        monkeypatch.setattr(nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="12345678000199", uf_sigla="RJ", chave_acesso="1" * 44,
            motivo="Motivo válido com bastante texto", n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is True
        assert r["protocolo"] == "135260000012345"
        assert r["cstat"] == "135"
        assert "<xCondUso>" in r["xml_evento"]

    def test_le_cstat_do_evento_nao_do_lote(self, monkeypatch):
        # Achado ao vivo 2026-08-23: `retEnvEvento` tem 2 `cStat`
        # aninhados — o do LOTE (nível externo, ex. 128 "Lote de Evento
        # Processado", neutro/sempre presente) e o do EVENTO de verdade,
        # dentro de `infEvento`. Uma extração ingênua (primeira ocorrência
        # de `cStat` na string) pegaria o do lote — mascarando uma
        # rejeição real (493) como se a resposta não tivesse `cStat`
        # nenhum reconhecido.
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEnvEvento><cStat>128</cStat><xMotivo>Lote de Evento Processado</xMotivo>"
            "<retEvento><infEvento><cStat>493</cStat>"
            "<xMotivo>Rejeicao: Evento nao atende o Schema XML especifico</xMotivo>"
            "</infEvento></retEvento></retEnvEvento>"
        )
        monkeypatch.setattr(nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "493" in r["message"]
        assert "Schema XML" in r["message"]

    def test_sefaz_recusa_a_correcao(self, monkeypatch):
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEvento><infEvento><cStat>573</cStat><xMotivo>Duplicidade de Evento</xMotivo></infEvento></retEvento>"
        monkeypatch.setattr(nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "573" in r["message"]

    def test_sefaz_recusa_dispara_apoio_fiscal_quando_servidor_banco_informados(self, monkeypatch):
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEvento><infEvento><cStat>573</cStat><xMotivo>Duplicidade de Evento</xMotivo></infEvento></retEvento>"
        monkeypatch.setattr(nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        chamada = {}

        def _fake_notificar(servidor, banco, *, tipo_documento, codigo_rejeicao, mensagem_original, referencia=None):
            chamada.update(servidor=servidor, banco=banco, tipo_documento=tipo_documento, codigo_rejeicao=codigo_rejeicao)
            return {"titulo": "x", "explicacao_curta": "y", "explicacao_detalhada": "z", "acao_usuario": None,
                    "notificado_suporte": {"email": True, "whatsapp": False}}

        monkeypatch.setattr(svc.apoio_fiscal_service, "notificar_rejeicao_sync", _fake_notificar)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2", servidor="srv", banco="bd",
        )
        assert r["success"] is False
        assert r["apoio_fiscal"]["notificado_suporte"]["email"] is True
        assert chamada == {"servidor": "srv", "banco": "bd", "tipo_documento": "Carta de Correção", "codigo_rejeicao": "573"}

    def test_sefaz_recusa_sem_servidor_banco_nao_chama_apoio_fiscal(self, monkeypatch):
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEvento><infEvento><cStat>573</cStat><xMotivo>Duplicidade de Evento</xMotivo></infEvento></retEvento>"
        monkeypatch.setattr(nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "apoio_fiscal" not in r

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _certs_pem()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(nfe_fiscal_common, "transmitir", _falha)
        r = svc.emitir_carta_correcao_sync(
            None, cnpj="1", uf_sigla="RJ", chave_acesso="1" * 44, motivo="Motivo válido com bastante texto",
            n_seq_evento=1, tp_amb="2",
        )
        assert r["success"] is False
        assert "sefaz" in r["message"].lower()
