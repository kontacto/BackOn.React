"""Peças genéricas de integração fiscal com o SEFAZ (NFe/NFCe), compartilhadas
entre `nfe_cancelamento_service.py` (cancelamento, evento 110111) e
`nfe_emissao_service.py` (emissão real de NFC-e/NF-e) — extraído de
`nfe_cancelamento_service.py` em 2026-07-21 ao iniciar o pacote de emissão,
pra não duplicar assinatura/transmissão/resolução de UF entre os dois.

Fonte de referência: `Backon.Controllers/NFe.vb` (pasta canônica
"C:/Desenv/VB6/vb.net/APICamadas/BackOn", rastreado 2026-07-21 — ver
docstring de `nfe_cancelamento_service.py` e o plano de emissão pra o
racional completo). Este módulo não fala com o SEFAZ sozinho — só monta as
peças reaproveitáveis; cada service (`cancelamento`/`emissao`) monta seu
próprio corpo de XML (`envEvento`/`enviNFe`/...) e orquestra a chamada.

Diferenças deliberadas em relação à fonte VB6 (modernização técnica, não
mudança de regra fiscal) — ver CLAUDE.md §12:
  - Assinatura RSA-SHA256 (não SHA1, obsoleto/inseguro — `signxml` recusa
    SHA1 por padrão).
  - Só o grupo de UFs atendidas pela SEFAZ Virtual do Rio Grande do Sul
    (SVRS) está mapeado — escopo reduzido de propósito pra UF da empresa
    testada nesta sessão (RJ). Outras UFs com SEFAZ própria precisam de
    endpoints adicionais, copiando o padrão de
    `NFE_Webservices.vb::URL_UF_Autorizadora.SetaURL`.
"""
import os
import re
import tempfile
from typing import Optional

import requests
import signxml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from signxml import XMLSigner

# Código IBGE de UF — tabela pública, não é regra de negócio, só referência
# de dados (mesma tabela usada em qualquer integração fiscal brasileira).
IBGE_POR_UF = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29", "CE": "23",
    "DF": "53", "ES": "32", "GO": "52", "MA": "21", "MT": "51", "MS": "50",
    "MG": "31", "PA": "15", "PB": "25", "PR": "41", "PE": "26", "PI": "22",
    "RJ": "33", "RN": "24", "RS": "43", "RO": "11", "RR": "14", "SC": "42",
    "SP": "35", "SE": "28", "TO": "17",
}

# UFs atendidas pela SEFAZ Virtual do Rio Grande do Sul (SVRS) — mesmo
# grupo/comentário de `NFE_Webservices.vb` linha 13630-13632.
UFS_SVRS = {"12", "27", "16", "53", "32", "15", "25", "22", "33", "24", "11", "14", "43", "42", "28", "17"}

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"


def resolver_endpoint(cod_ibge: str, modelo: str, tp_amb: str, endpoints: dict) -> Optional[str]:
    """Resolve a URL de um webservice SEFAZ dado o dict `{modelo: {tp_amb: url}}`
    do serviço específico (recepção de evento, autorização, etc.) — só
    resolve UFs do grupo SVRS por enquanto (ver docstring do módulo)."""
    if cod_ibge not in UFS_SVRS:
        return None
    return endpoints.get(modelo, {}).get(tp_amb)


def escapar_xml(texto: str) -> str:
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def carregar_certificado_sync(cur) -> Optional[tuple[bytes, bytes]]:
    """Certificado A1 ativo mais recente (`certificado_digital`, mesma
    tabela de `certificado_digital_service.py`) — retorna (key_pem,
    cert_pem) prontos pra assinatura/TLS, ou None se não houver nenhum
    certificado válido cadastrado hoje."""
    cur.execute(
        "SELECT TOP 1 certificado_digital, senha_certificado FROM certificado_digital "
        "WHERE data_fim >= CAST(GETDATE() AS DATE) ORDER BY sequencia DESC"
    )
    row = cur.fetchone()
    if not row or not row.get("certificado_digital"):
        return None
    senha = (row.get("senha_certificado") or "").encode("utf-8") or None
    chave, cert, _cadeia = pkcs12.load_key_and_certificates(bytes(row["certificado_digital"]), senha)
    if chave is None or cert is None:
        return None
    key_pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


def assinar_xml(xml_bytes: bytes, id_referencia: str, key_pem: bytes, cert_pem: bytes) -> bytes:
    """Assinatura XMLDSig enveloped + C14N — mesmo padrão de `Assinar`
    (`Backon.Controllers/NFe.vb:3335`), só RSA-SHA256 em vez de SHA1 (ver
    docstring do módulo). `id_referencia` é o `Id` do elemento assinado
    (`infEvento` no cancelamento, `infNFe`/`infNFCe` na emissão)."""
    root = etree.fromstring(xml_bytes)
    signer = XMLSigner(
        method=signxml.methods.enveloped,
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )
    signed_root = signer.sign(root, key=key_pem, cert=cert_pem, reference_uri=f"#{id_referencia}")
    return etree.tostring(signed_root, xml_declaration=True, encoding="UTF-8")


def montar_envelope_soap(corpo_interno: bytes, wsdl_service: str) -> bytes:
    """Envelope SOAP 1.2 genérico — `corpo_interno` é o XML já pronto
    (`envEvento`/`enviNFe`/`consSitNFe`, já assinado quando aplicável) e
    `wsdl_service` é o nome do serviço WSDL alvo (ex.: "NFeRecepcaoEvento4"
    pro cancelamento, "NFeAutorizacao4" pra emissão)."""
    corpo = corpo_interno.decode("utf-8") if isinstance(corpo_interno, bytes) else corpo_interno
    corpo = re.sub(r"^<\?xml[^>]*\?>", "", corpo)
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="{SOAP_NS}">'
        '<soap12:Body>'
        f'<nfeDadosMsg xmlns="{NFE_NS}/wsdl/{wsdl_service}">{corpo}</nfeDadosMsg>'
        '</soap12:Body>'
        '</soap12:Envelope>'
    )
    return envelope.encode("utf-8")


def transmitir(envelope: bytes, endpoint: str, key_pem: bytes, cert_pem: bytes, timeout: int = 30) -> str:
    """POST do envelope SOAP pro SEFAZ, autenticado com o certificado
    cliente (TLS mútuo — mesmo `WSNfeRecepcaoEvento.ClientCertificates.Add`
    do proxy .NET). `requests` só aceita certificado via caminho de
    arquivo, por isso os PEMs são gravados num arquivo temporário (apagado
    logo depois, nunca persistido em disco por mais tempo que o necessário
    pra fazer a chamada)."""
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_cert, \
         tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_key:
        f_cert.write(cert_pem)
        f_key.write(key_pem)
        cert_path, key_path = f_cert.name, f_key.name
    try:
        resp = requests.post(
            endpoint, data=envelope,
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            cert=(cert_path, key_path), timeout=timeout,
        )
        resp.raise_for_status()
        return resp.text
    finally:
        for p in (cert_path, key_path):
            try:
                os.remove(p)
            except OSError:
                pass


def extrair_tag(xml_texto: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml_texto, re.DOTALL)
    return m.group(1).strip() if m else None


def transmitir_json_mtls(payload: dict, endpoint: str, key_pem: bytes, cert_pem: bytes, timeout: int = 30) -> dict:
    """POST JSON autenticado por TLS mútuo — usado pela API do Ambiente de
    Dados Nacional (ADN/Sefin Nacional, NFS-e), que ao contrário do SEFAZ
    (SOAP/XML puro) troca mensagens em JSON, mas ainda exige o certificado
    do contribuinte como client cert da conexão TLS (confirmado via HTTP 496
    "certificado exigido" ao tentar acessar a documentação Swagger sem
    certificado — ver `nfse_emissao_service.py` pro racional completo).
    Mesmo padrão de arquivo temporário de `transmitir()` acima."""
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_cert, \
         tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_key:
        f_cert.write(cert_pem)
        f_key.write(key_pem)
        cert_path, key_path = f_cert.name, f_key.name
    try:
        resp = requests.post(
            endpoint, json=payload,
            headers={"Content-Type": "application/json"},
            cert=(cert_path, key_path), timeout=timeout,
        )
        try:
            corpo = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise RuntimeError(f"Resposta não-JSON do ADN: {resp.text[:500]}")
        if resp.status_code >= 400:
            return {"_erro_http": resp.status_code, **(corpo if isinstance(corpo, dict) else {"detalhe": corpo})}
        return corpo
    finally:
        for p in (cert_path, key_path):
            try:
                os.remove(p)
            except OSError:
                pass
