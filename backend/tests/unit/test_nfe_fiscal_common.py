"""Testes de `nfe_fiscal_common.py` — resolvedores de destinatário
(cliente já coberto indiretamente via `test_nfe_agrupada_service.py`;
aqui o foco é o resolvedor de FORNECEDOR, novo em 2026-08-20 pra NF-e
Avulsa — ver PENDENCIAS.md > "NF-e Avulsa"), mais `montar_xml_
inutilizacao`/`resolver_usuario_texto_sync`, generalizados no mesmo dia
ao implementar Inutilização de Faixa NFe (antes só existiam, versão
NFC-e-only, dentro de `gestor_nfce_service.py`)."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLVerifier

import services.nfe_fiscal_common as common


def _gerar_certificado_teste():
    """Certificado autoassinado só para teste — nunca usado fora deste
    arquivo, nunca transmitido a lugar nenhum (mesmo padrão já usado em
    `test_nfe_cancelamento_service.py`)."""
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
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption(),
    )
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


class TestMontarXmlInutilizacao:
    def test_modelo_55_monta_id_e_mod_corretos(self):
        xml, id_inut = common.montar_xml_inutilizacao(
            modelo="55", cod_ibge="33", cnpj="12345678000199", serie="1", numero_inicial=10, numero_final=20,
            motivo="Erro de digitação no valor total", tp_amb="1",
        )
        # "ID" + cUF(2) + ano(2) + CNPJ(14) + mod(2) + serie(3) + nNFIni(9) + nNFFin(9) = 43 chars.
        assert len(id_inut) == 43
        assert id_inut.startswith("ID33")
        assert "12345678000199" in id_inut
        assert id_inut.endswith("55" + "001" + "000000010" + "000000020")
        assert "<mod>55</mod>" in xml.decode("utf-8")
        assert 'Id="' + id_inut + '"' in xml.decode("utf-8")
        etree.fromstring(xml)

    def test_modelo_65_preserva_comportamento_anterior(self):
        xml, id_inut = common.montar_xml_inutilizacao(
            modelo="65", cod_ibge="33", cnpj="12345678000199", serie="1", numero_inicial=10, numero_final=10,
            motivo="Erro de digitação no valor total", tp_amb="1",
        )
        assert id_inut.startswith("ID33")
        assert "<mod>65</mod>" in xml.decode("utf-8")


class TestResolverUsuarioTextoSync:
    def test_sem_usuario_nao_consulta_banco(self):
        cur = FakeCursor()
        r = common.resolver_usuario_texto_sync(cur, None)
        assert r is None
        assert cur.queries == []


class TestResolverTpAmbSync:
    # `controle_aux.ambiente_nfe` (2026-08-20, achado em FrmGerKon.frm:
    # 858-862) — fail-safe fiel ao legado: só o valor exato 1 é Produção,
    # qualquer outra coisa (ausente/0/2) cai pra Homologação.
    def test_valor_1_e_producao(self):
        cur = FakeCursor(one=[{"ambiente_nfe": 1}])
        assert common.resolver_tp_amb_sync(cur) == "1"

    def test_valor_2_e_homologacao(self):
        cur = FakeCursor(one=[{"ambiente_nfe": 2}])
        assert common.resolver_tp_amb_sync(cur) == "2"

    def test_valor_0_e_homologacao(self):
        cur = FakeCursor(one=[{"ambiente_nfe": 0}])
        assert common.resolver_tp_amb_sync(cur) == "2"

    def test_valor_ausente_null_e_homologacao(self):
        cur = FakeCursor(one=[{"ambiente_nfe": None}])
        assert common.resolver_tp_amb_sync(cur) == "2"

    def test_linha_nao_encontrada_e_homologacao(self):
        cur = FakeCursor(one=[None])
        assert common.resolver_tp_amb_sync(cur) == "2"

    def test_resolve_nome_guerra(self):
        cur = FakeCursor(one=[{"nome": "JOAOZINHO"}])
        r = common.resolver_usuario_texto_sync(cur, 42)
        assert r == "JOAOZINHO"

    def test_funcionario_nao_encontrado_cai_pro_codigo(self):
        cur = FakeCursor(one=[None])
        r = common.resolver_usuario_texto_sync(cur, 42)
        assert r == "42"


class TestGerarQrcodePngBase64:
    def test_gera_png_valido(self):
        import base64

        b64 = common.gerar_qrcode_png_base64("https://exemplo.com/consulta?chave=123")
        assert isinstance(b64, str) and len(b64) > 0
        raw = base64.b64decode(b64)
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"

    def test_conteudos_diferentes_geram_imagens_diferentes(self):
        b64_a = common.gerar_qrcode_png_base64("https://exemplo.com/a")
        b64_b = common.gerar_qrcode_png_base64("https://exemplo.com/b")
        assert b64_a != b64_b


class TestAssinarXmlSemPrefixo:
    """`assinar_xml(..., sem_prefixo=True)` — exigência real do ADN/Sefin
    Nacional pra NFS-e (achado ao vivo 2026-08-23): rejeita qualquer
    elemento com prefixo de namespace (`ds:Signature`), diferente de
    NF-e/NFC-e/MDF-e/CC-e onde `ds:` é aceito normalmente. A rota
    `signxml.XMLSigner(namespaces={None: ds_uri})` (a forma "óbvia") foi
    testada e descartada — produz assinatura que nem o próprio
    `XMLVerifier` do signxml aceita, por um bug de C14N do lxml com
    namespace padrão herdado (`xmlns=""` espúrio — ver
    `_c14n_sem_xmlns_vazio` em `nfe_fiscal_common.py`). Por isso os testes
    aqui usam criptografia REAL (certificado autoassinado) e verificação
    REAL via `XMLVerifier`, não só checam a presença de tags — mockar a
    assinatura esconderia exatamente esse tipo de bug."""

    def test_nenhum_prefixo_de_namespace_no_xml_assinado(self):
        key_pem, cert_pem = _gerar_certificado_teste()
        xml = b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">' \
              b'<infDPS Id="DPS1"><prest><CNPJ>12345678000199</CNPJ></prest></infDPS></DPS>'
        assinado = common.assinar_xml(xml, "DPS1", key_pem, cert_pem, sem_prefixo=True)
        assert b"ds:" not in assinado
        assert b"xmlns:" not in assinado
        assert b'xmlns="http://www.w3.org/2000/09/xmldsig#"' in assinado

    def test_assinatura_verifica_com_xmlverifier_real(self):
        key_pem, cert_pem = _gerar_certificado_teste()
        xml = (
            b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
            b'<infDPS Id="DPS1">'
            b'<prest><CNPJ>12345678000199</CNPJ><regTrib><opSimpNac>2</opSimpNac></regTrib></prest>'
            b'<toma><CPF>12345678909</CPF><xNome>CLIENTE TESTE</xNome></toma>'
            b"</infDPS></DPS>"
        )
        assinado = common.assinar_xml(xml, "DPS1", key_pem, cert_pem, sem_prefixo=True)
        resultado = XMLVerifier().verify(etree.fromstring(assinado), x509_cert=cert_pem)
        assert resultado.signed_xml.tag == "{http://www.sped.fazenda.gov.br/nfse}infDPS"

    def test_assinatura_e_sibling_de_inf_dps_nao_filha(self):
        # `infNFeSupl` (NFC-e) e a assinatura de MDF-e já seguem esse
        # mesmo padrão (irmã, não filha, do elemento referenciado) — aqui
        # confirma que a montagem manual splica a `<Signature>` como
        # irmã de `<infDPS>`, ambas filhas de `<DPS>`.
        key_pem, cert_pem = _gerar_certificado_teste()
        xml = b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">' \
              b'<infDPS Id="DPS1"><foo>bar</foo></infDPS></DPS>'
        assinado = common.assinar_xml(xml, "DPS1", key_pem, cert_pem, sem_prefixo=True)
        root = etree.fromstring(assinado)
        assert [c.tag.split("}")[-1] for c in root] == ["infDPS", "Signature"]

    def test_altera_conteudo_apos_assinar_invalida_verificacao(self):
        key_pem, cert_pem = _gerar_certificado_teste()
        xml = b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">' \
              b'<infDPS Id="DPS1"><prest><CNPJ>12345678000199</CNPJ></prest></infDPS></DPS>'
        assinado = common.assinar_xml(xml, "DPS1", key_pem, cert_pem, sem_prefixo=True)
        adulterado = assinado.replace(b"12345678000199", b"99999999000199")
        try:
            XMLVerifier().verify(etree.fromstring(adulterado), x509_cert=cert_pem)
            assert False, "deveria ter recusado o XML adulterado"
        except Exception:
            pass

    def test_elemento_referenciado_nao_encontrado_gera_erro_claro(self):
        key_pem, cert_pem = _gerar_certificado_teste()
        xml = b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse"><infDPS Id="OUTRO"/></DPS>'
        try:
            common.assinar_xml(xml, "NAO_EXISTE", key_pem, cert_pem, sem_prefixo=True)
            assert False, "deveria ter levantado ValueError"
        except ValueError as e:
            assert "NAO_EXISTE" in str(e)
