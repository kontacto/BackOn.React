"""Testes UNITÁRIOS do cancelamento de NFe/NFCe junto ao SEFAZ
(`nfe_cancelamento_service.py`) — construído dentro do pacote "Cancelar
Comanda", pedido explícito do usuário 2026-07-21.

**Importantíssimo**: nenhum teste aqui usa certificado real nem faz
chamada de rede de verdade — `_transmitir` (a única função que realmente
fala com o SEFAZ) é sempre mockada via `monkeypatch`. O certificado usado
nos testes é gerado na hora, autoassinado, só para exercitar a lógica de
assinatura XML — nunca o certificado real de nenhuma empresa."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLVerifier

import services.nfe_cancelamento_service as svc


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


def _pfx_bytes_teste(key, cert, senha: str) -> bytes:
    return pkcs12.serialize_key_and_certificates(
        name=b"teste", key=key, cert=cert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")),
    )


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None


class TestResolverUrl:
    def test_uf_svrs_resolve_nfe_e_nfce(self):
        # RJ = 33, está no grupo SVRS.
        assert svc._resolver_url("33", "55", "1") == "https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"
        assert svc._resolver_url("33", "55", "2") == "https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"
        assert svc._resolver_url("33", "65", "1") == "https://nfce.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx"

    def test_uf_fora_do_grupo_svrs_retorna_none(self):
        # MG = 31, tem SEFAZ própria — não mapeada ainda neste módulo.
        assert svc._resolver_url("31", "55", "1") is None


class TestMontarXmlEvento:
    def test_monta_evento_cancelamento_com_campos_esperados(self):
        xml_bytes, id_evento = svc._montar_xml_evento(
            "33", "12345678000199", "3" * 44, "135200000012345", "Motivo de teste com mais de 15 caracteres", "2",
        )
        xml = xml_bytes.decode("utf-8")
        assert id_evento == f"ID110111{'3' * 44}01"
        assert "<tpEvento>110111</tpEvento>" in xml
        assert "<cOrgao>33</cOrgao>" in xml
        assert "<tpAmb>2</tpAmb>" in xml
        assert "<CNPJ>12345678000199</CNPJ>" in xml
        assert f'<chNFe>{"3" * 44}</chNFe>' in xml
        assert "<nProt>135200000012345</nProt>" in xml
        assert "Motivo de teste" in xml
        assert f'Id="{id_evento}"' in xml

    def test_escapa_caracteres_especiais_no_motivo(self):
        xml_bytes, _ = svc._montar_xml_evento("33", "1", "2" * 44, "1", "Motivo com & e < e >", "1")
        assert "&amp;" in xml_bytes.decode("utf-8")
        assert "Motivo com & e" not in xml_bytes.decode("utf-8")


class TestAssinarEvento:
    def test_assinatura_e_valida_e_verificavel(self):
        key, cert = _gerar_certificado_teste()
        key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        xml_bytes, id_evento = svc._montar_xml_evento("33", "1", "4" * 44, "1", "Motivo de teste com mais de 15 caracteres", "2")
        assinado = svc._assinar_evento(xml_bytes, id_evento, key_pem, cert_pem)
        root = etree.fromstring(assinado)
        assert root.find("{*}Signature") is not None or any(c.tag.endswith("Signature") for c in root)
        # A verificação confirma que a assinatura é criptograficamente válida
        # pro conteúdo do próprio XML — não que o SEFAZ aceitaria (isso só um
        # certificado ICP-Brasil real + o ambiente de homologação confirmam).
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
        assert envelope.count("<?xml") == 1  # não duplica a declaração XML


class TestExtrairTag:
    def test_extrai_valor_da_tag(self):
        xml = "<retEvento><infEvento><cStat>135</cStat><xMotivo>Evento registrado</xMotivo></infEvento></retEvento>"
        assert svc._extrair_tag(xml, "cStat") == "135"
        assert svc._extrair_tag(xml, "xMotivo") == "Evento registrado"
        assert svc._extrair_tag(xml, "nProt") is None


class TestCarregarCertificado:
    def test_carrega_certificado_pfx_valido(self):
        key, cert = _gerar_certificado_teste()
        pfx = _pfx_bytes_teste(key, cert, "senha123")
        cur = FakeCursor(one=[{"certificado_digital": pfx, "senha_certificado": "senha123"}])
        resultado = svc._carregar_certificado_sync(cur)
        assert resultado is not None
        key_pem, cert_pem = resultado
        assert b"PRIVATE KEY" in key_pem
        assert b"CERTIFICATE" in cert_pem

    def test_sem_certificado_cadastrado_retorna_none(self):
        cur = FakeCursor(one=[None])
        assert svc._carregar_certificado_sync(cur) is None


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc, "_carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


class TestCancelarNfeSync:
    def _certs(self):
        key, cert = _gerar_certificado_teste()
        key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        return key_pem, cert_pem

    def test_bloqueia_motivo_curto(self):
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="RJ", modelo="65", chave_acesso="1" * 44,
            protocolo="123", motivo="curto", tp_amb="2",
        )
        assert r["success"] is False
        assert "15 caracteres" in r["message"]

    def test_bloqueia_chave_acesso_invalida(self):
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="RJ", modelo="65", chave_acesso="123",
            protocolo="123", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is False
        assert "chave de acesso" in r["message"].lower()

    def test_bloqueia_sem_protocolo(self):
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="RJ", modelo="65", chave_acesso="1" * 44,
            protocolo="", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is False
        assert "protocolo" in r["message"].lower()

    def test_bloqueia_uf_nao_mapeada(self, monkeypatch):
        key_pem, cert_pem = self._certs()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="MG", modelo="55", chave_acesso="1" * 44,
            protocolo="123", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is False
        assert "MG" in r["message"]

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc, "_carregar_certificado_sync", lambda cur: None)
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="RJ", modelo="65", chave_acesso="1" * 44,
            protocolo="123", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_com_sefaz_mockado(self, monkeypatch):
        key_pem, cert_pem = self._certs()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEvento><infEvento><cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo>"
            "<nProt>135260000012345</nProt><dhRegEvento>2026-07-21T10:00:00-03:00</dhRegEvento></infEvento></retEvento>"
        )
        monkeypatch.setattr(svc, "_transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.cancelar_nfe_sync(
            None, cnpj="12345678000199", uf_sigla="RJ", modelo="65", chave_acesso="1" * 44,
            protocolo="123", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is True
        assert r["protocolo_cancelamento"] == "135260000012345"

    def test_sefaz_recusa_o_cancelamento(self, monkeypatch):
        key_pem, cert_pem = self._certs()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEvento><infEvento><cStat>573</cStat>"
            "<xMotivo>Duplicidade de Evento</xMotivo></infEvento></retEvento>"
        )
        monkeypatch.setattr(svc, "_transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="RJ", modelo="65", chave_acesso="1" * 44,
            protocolo="123", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is False
        assert "573" in r["message"]

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = self._certs()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc, "_transmitir", _falha)
        r = svc.cancelar_nfe_sync(
            None, cnpj="1", uf_sigla="RJ", modelo="65", chave_acesso="1" * 44,
            protocolo="123", motivo="Motivo válido com bastante texto", tp_amb="2",
        )
        assert r["success"] is False
        assert "sefaz" in r["message"].lower()
