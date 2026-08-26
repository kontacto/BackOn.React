"""Cancelamento de NFe/NFCe junto ao SEFAZ (evento 110111) — construído
dentro do pacote "Gestor de Comandas"/"Alterar Comandas" (Cancelar Comanda),
pedido explícito do usuário 2026-07-21, depois de ele apontar onde a
implementação real vive no legado.

Portado de `Backon.Controllers/NFe.vb` (pasta canônica
"C:/Desenv/VB6/vb.net/APICamadas/BackOn", rastreado e verificado
2026-07-21):
  - `CancelaNFe` (linha 2753) monta o XML do evento de cancelamento.
  - `Assinar` (linha 3335) assina esse XML com o certificado digital
    (`SignedXml` do .NET — enveloped transform + C14N, `KeyInfoX509Data`).
  - `Transmitir_NFe` (linha 3576, `Case 4` — "Evento/cancelamento") monta o
    envelope SOAP e chama o webservice `nfeRecepcaoEvento` do SEFAZ.
  - `URL_UF_Autorizadora.SetaURL` (`NFE_Webservices.vb`, linha 13592)
    resolve a URL do webservice por UF/modelo/versão/ambiente.

**NUNCA testado contra o SEFAZ real** — não existe certificado de teste
nem acesso a um ambiente de homologação neste projeto. Mesmo princípio já
aceito pra integração Tray (`tray_service.py`): construído com fidelidade
ao rastreio da fonte, mas sem validação ao vivo — revisar com cuidado
antes de usar em produção (ver CLAUDE.md §12 "Telas Fiscais").

Diferenças deliberadas em relação à fonte VB6 (modernização técnica, não
mudança de regra fiscal):
  - Assinatura RSA-SHA256 (não SHA1). A fonte VB6 assina em SHA1 porque foi
    escrita quando esse era o padrão vigente do SEFAZ; SHA1 está obsoleto/
    inseguro hoje, e os webservices do SEFAZ aceitam SHA256 há anos —
    `signxml` (a lib usada aqui) inclusive recusa assinar com SHA1 por
    padrão, por não ser mais seguro.
  - Só o grupo de UFs atendidas pela SEFAZ Virtual do Rio Grande do Sul
    (SVRS) está mapeado (`_UFS_SVRS` abaixo) — escopo reduzido de
    propósito pra UF da empresa testada nesta sessão (RJ), pedido
    explícito do usuário ("construir só pra UF da empresa atual"). Estados
    com SEFAZ própria (ex.: Minas Gerais, código 31) precisam de outra
    entrada em `_ENDPOINTS_RECEPCAO_EVENTO`, copiando o mesmo padrão de
    `NFE_Webservices.vb::URL_UF_Autorizadora.SetaURL` — não adicionados
    ainda por não terem sido necessários até agora.

**2026-07-21 — refatorado**: as peças genéricas (assinatura, envelope SOAP,
transmissão, certificado, extração de resposta, tabela de UF/IBGE) foram
extraídas pra `nfe_fiscal_common.py`, reaproveitadas também por
`nfe_emissao_service.py` (emissão real de NFC-e/NF-e, mesmo pacote). Este
módulo mantém os mesmos nomes de função de sempre (`_assinar_evento`,
`_montar_envelope_soap`, `_transmitir`, etc.) como wrappers finos, pra não
quebrar os testes já existentes nem quem já importa este módulo.
"""
import re
from datetime import datetime, timezone
from typing import Optional

from services import nfe_fiscal_common

# Código IBGE de UF — tabela pública, não é regra de negócio, só referência
# de dados (mesma tabela usada em qualquer integração fiscal brasileira).
_IBGE_POR_UF = nfe_fiscal_common.IBGE_POR_UF

# UFs atendidas pela SEFAZ Virtual do Rio Grande do Sul (SVRS) — mesmo
# grupo/comentário de `NFE_Webservices.vb` linha 13630-13632.
_UFS_SVRS = nfe_fiscal_common.UFS_SVRS

# Endpoints "recepção de evento" (versão 4.00, grupo SVRS) — **extraído
# pra `nfe_fiscal_common.ENDPOINTS_RECEPCAO_EVENTO` 2026-08-22**, reaproveitado
# também pela Carta de Correção (`nfe_correcao_service.py`, evento 110110) —
# é o MESMO webservice pros dois eventos, só o corpo do `<evento>` muda.
_ENDPOINTS_RECEPCAO_EVENTO = nfe_fiscal_common.ENDPOINTS_RECEPCAO_EVENTO

_NFE_NS = nfe_fiscal_common.NFE_NS
_SOAP_NS = nfe_fiscal_common.SOAP_NS


class NfeCancelamentoIndisponivel(Exception):
    """UF sem endpoint mapeado ainda — ver docstring do módulo."""


def _resolver_url(cod_ibge: str, modelo: str, tp_amb: str) -> Optional[str]:
    """URL do webservice "recepção de evento" (cancelamento) — só resolve
    UFs do grupo SVRS por enquanto (ver docstring do módulo). `modelo` é
    "55" (NFe) ou "65" (NFCe), `tp_amb` é "1" (produção) ou "2"
    (homologação)."""
    return nfe_fiscal_common.resolver_endpoint(cod_ibge, modelo, tp_amb, _ENDPOINTS_RECEPCAO_EVENTO)


def _montar_xml_evento(
    cod_uf_ibge: str, cnpj: str, chave_acesso: str, protocolo: str, motivo: str, tp_amb: str,
) -> tuple[bytes, str]:
    """Monta o `<evento>` de cancelamento (tpEvento 110111) — réplica de
    `CancelaNFe` (`Backon.Controllers/NFe.vb`, linhas 2774-2792). Retorna
    (xml_bytes, id_evento) — `id_evento` é usado depois como
    `reference_uri` da assinatura."""
    # `isoformat(timespec="seconds")` num datetime timezone-aware já produz
    # exatamente o formato "AAAA-MM-DDTHH:MM:SS-03:00" que o `dhEvento`
    # exige (equivalente ao `FormataDataNFSE(...) & "T" & ... & "-03:00"`
    # manual da fonte VB6).
    dh_evento = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    id_evento = f"ID110111{chave_acesso}01"
    xml = (
        f'<evento xmlns="{_NFE_NS}" versao="1.00">'
        f'<infEvento Id="{id_evento}">'
        f'<cOrgao>{cod_uf_ibge}</cOrgao>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<CNPJ>{cnpj}</CNPJ>'
        f'<chNFe>{chave_acesso}</chNFe>'
        f'<dhEvento>{dh_evento}</dhEvento>'
        f'<tpEvento>110111</tpEvento>'
        f'<nSeqEvento>1</nSeqEvento>'
        f'<verEvento>1.00</verEvento>'
        f'<detEvento versao="1.00">'
        f'<descEvento>Cancelamento</descEvento>'
        f'<nProt>{protocolo}</nProt>'
        f'<xJust>{_escapar_xml(motivo)}</xJust>'
        f'</detEvento>'
        f'</infEvento>'
        f'</evento>'
    ).encode("utf-8")
    return xml, id_evento


def _escapar_xml(texto: str) -> str:
    return nfe_fiscal_common.escapar_xml(texto)


def _carregar_certificado_sync(cur) -> Optional[tuple[bytes, bytes]]:
    """Certificado A1 ativo mais recente — ver `nfe_fiscal_common.
    carregar_certificado_sync` (extraído daqui, mesmo comportamento)."""
    return nfe_fiscal_common.carregar_certificado_sync(cur)


def _assinar_evento(xml_bytes: bytes, id_evento: str, key_pem: bytes, cert_pem: bytes) -> bytes:
    """Assinatura XMLDSig enveloped + C14N — ver `nfe_fiscal_common.
    assinar_xml` (extraído daqui, mesmo comportamento)."""
    # sha1=True — mesmo achado do MDF-e/NFC-e (2026-08-23): o XSD
    # compartilhado (`xmldsig-core-schema_v1.01.xsd`) ainda fixa SHA-1,
    # não SHA-256 como a docstring do módulo presumia sem ter testado ao
    # vivo até hoje.
    return nfe_fiscal_common.assinar_xml(xml_bytes, id_evento, key_pem, cert_pem, sha1=True)


def _montar_envelope_soap(xml_evento_assinado: bytes) -> bytes:
    """Envelope SOAP 1.2 pro webservice `NFeRecepcaoEvento4` — mesmo
    padrão WSDL usado pelo proxy .NET (`Transmitir_NFe`, `Case 4`), o
    corpo (`envEvento`) embrulha o `<evento>` já assinado."""
    corpo = xml_evento_assinado.decode("utf-8")
    # `\s*` — achado ao vivo 2026-08-23, ver docstring de
    # `nfe_fiscal_common.montar_envelope_soap` pro racional completo
    # (lxml deixa `\n` residual depois da declaração XML).
    corpo = re.sub(r"^<\?xml[^>]*\?>\s*", "", corpo)
    env_evento = f'<envEvento xmlns="{_NFE_NS}" versao="1.00"><idLote>1</idLote>{corpo}</envEvento>'
    return nfe_fiscal_common.montar_envelope_soap(env_evento.encode("utf-8"), "NFeRecepcaoEvento4")


def _transmitir(envelope: bytes, endpoint: str, key_pem: bytes, cert_pem: bytes, timeout: int = 30) -> str:
    """POST do envelope SOAP pro SEFAZ (TLS mútuo) — ver `nfe_fiscal_common.
    transmitir` (extraído daqui, mesmo comportamento)."""
    return nfe_fiscal_common.transmitir(envelope, endpoint, key_pem, cert_pem, timeout)


def _extrair_tag(xml_texto: str, tag: str) -> Optional[str]:
    return nfe_fiscal_common.extrair_tag(xml_texto, tag)


def cancelar_nfe_sync(
    cur, *, cnpj: str, uf_sigla: str, modelo: str, chave_acesso: str, protocolo: str,
    motivo: str, tp_amb: str,
) -> dict:
    """Orquestra o cancelamento (evento 110111) — chamado por
    `comanda_service._cancelar_comanda_sync` quando a comanda tem NF/NFCe
    com protocolo SEFAZ real vinculada. `cur` é o cursor já aberto (mesma
    transação/conexão de quem chama, pra ler o certificado)."""
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        return {"success": False, "message": "O motivo do cancelamento precisa ter pelo menos 15 caracteres."}
    if not chave_acesso or len(chave_acesso.strip()) != 44:
        return {"success": False, "message": "Chave de acesso da NF/NFCe inválida ou ausente."}
    if not protocolo:
        return {"success": False, "message": "Nota sem protocolo de autorização do SEFAZ — nada a cancelar."}

    cod_ibge = _IBGE_POR_UF.get((uf_sigla or "").strip().upper())
    if not cod_ibge:
        return {"success": False, "message": f"UF '{uf_sigla}' não reconhecida."}
    url = _resolver_url(cod_ibge, modelo, tp_amb)
    if not url:
        return {
            "success": False,
            "message": (
                f"Cancelamento automático ainda não está disponível pra UF '{uf_sigla}' — "
                "faça o cancelamento oficial no sistema legado (VB6) por enquanto."
            ),
        }

    cert = _carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert

    try:
        xml_evento, id_evento = _montar_xml_evento(cod_ibge, cnpj, chave_acesso.strip(), protocolo, motivo, tp_amb)
        xml_assinado = _assinar_evento(xml_evento, id_evento, key_pem, cert_pem)
        envelope = _montar_envelope_soap(xml_assinado)
        resposta = _transmitir(envelope, url, key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    # `retEnvEvento` tem 2 `cStat` aninhados — o do LOTE (nível externo,
    # neutro/sempre presente) e o do EVENTO de verdade, dentro de
    # `infEvento` (nível interno) — mesmo achado ao vivo 2026-08-23 já
    # corrigido em `nfe_correcao_service.py`/`nfe_emissao_service.py`
    # (CC-e/NFC-e/NF-e) no mesmo dia; aplicado aqui também por
    # consistência, mesmo sem cancelamento real de NF-e/NFC-e ter sido
    # testado ao vivo ainda nesta sessão (só MDF-e, código separado).
    inf_evento = nfe_fiscal_common.extrair_bloco(resposta, "infEvento") or resposta
    c_stat = _extrair_tag(inf_evento, "cStat")
    x_motivo = _extrair_tag(inf_evento, "xMotivo")
    n_prot = _extrair_tag(inf_evento, "nProt")
    dh_reg = _extrair_tag(inf_evento, "dhRegEvento")
    # 135 = "Evento registrado e vinculado a NF-e" (cancelamento homologado).
    # 136 = "Evento registrado, mas não vinculado a NF-e" (também sucesso).
    if c_stat not in ("135", "136"):
        return {
            "success": False,
            "message": f"SEFAZ recusou o cancelamento (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
        }
    return {
        "success": True,
        "message": f"Cancelamento autorizado pelo SEFAZ — protocolo {n_prot or '?'}.",
        "protocolo_cancelamento": n_prot,
        "data_hora_registro": dh_reg,
        # Achado ao vivo 2026-08-23 (1ª cancelamento real de NF-e/NFC-e
        # nesta migração): `xml_assinado` era calculado mas NUNCA
        # devolvido pra quem chama — o cancelamento acontecia de verdade
        # no SEFAZ, mas o XML assinado do evento (prova documental do
        # cancelamento) ficava só na memória, descartado assim que a
        # função retornava. Devolvido aqui pra `comanda_service.
        # _cancelar_comanda_sync` poder persistir (ver achado irmão:
        # nem `protocolo_cancelamento` estava sendo gravado em lugar
        # nenhum, só `situacao='C'`).
        "xml_evento": xml_assinado.decode("utf-8"),
    }
