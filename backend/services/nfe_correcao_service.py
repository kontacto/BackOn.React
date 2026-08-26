"""Carta de Correção Eletrônica (CC-e) — evento SEFAZ 110110 — construído
2026-08-22, depois de a equipe VB6 (Leandro Kontacto) corrigir um
levantamento de gaps: eu tinha listado CC-e como "fora de escopo", mas é
usada diariamente por todos os clientes, dentro da tela já migrada
"Notas Fiscais — Manutenção" (ver `notas_fiscais_service.py`).

Portado de `Geral\\FrmManRec.frm` (`Command32_Click`/`Command33_Click`,
linhas 7541-7708) — o legado chama `Backon_Controllers.Nfe.
CartadeCorrecao(...)`, mesma DLL/família de eventos que `CancelaNFe`
(ver `nfe_cancelamento_service.py`). Regra oficial confirmada via Nota
Técnica 2011.003 do SEFAZ (busca + fetch num guia técnico especializado
que cita a NT — o PDF oficial não carregou direto por redirecionamento;
recomendado validar contra o PDF oficial antes de produção):
  - `tpEvento` = 110110 (Cancelamento é 110111, mesmo webservice
    `NFeRecepcaoEvento4`).
  - `nSeqEvento`: 1 a 20 — uma NF-e pode ter até 20 cartas de correção,
    a última substitui as anteriores pra quem lê o histórico. **O
    legado mostra só as 5 primeiras na listagem (`PrepEventos`,
    `FrmManRec.frm:9533`, `For k = 1 To 5`) — confirmado limitação
    arbitrária de UI, não a regra real do SEFAZ** (ver "Não replicar
    truques VB6" no CLAUDE.md) — aqui o cap real de 20 é enforçado no
    backend (`notas_fiscais_service.py::_carta_correcao_sync`), não 5.
  - `xCorrecao`: texto livre, 15 a 1000 caracteres.
  - `xCondUso`: texto FIXO obrigatório (ver `X_COND_USO` abaixo),
    nunca editável pelo usuário — sempre o mesmo em toda CC-e.
  - `cStat` de sucesso: 135 ("Evento registrado e vinculado a NF-e") —
    mesmo código de sucesso do cancelamento (mesma família de eventos).

**Divergência deliberada da fonte VB6**: o legado concatena o XML de
retorno cru dentro de `n_fiscal.obs_livro` (coluna de texto livre, tags
customizadas feitas na mão tipo `<xml da carta correcao01>`) e salva o
XML assinado num arquivo local por instalação (`cce_NN_chave.xml`) — é
gambiarra de era VB6 (sem acesso fácil a criar tabela nova por
instalação, backend local single-process com pasta própria), não regra
fiscal. Este backend é multi-tenant/stateless: cada CC-e emitida vira uma
linha própria em `n_fiscal_carta_correcao` (`notas_fiscais_service.py`),
com o XML assinado guardado na própria linha — nunca no sistema de
arquivos local.

**Só modelo 55 (NF-e), nunca NFC-e** — mesmo escopo do legado
(`CartadeCorrecao(..., 55, ...)` hardcoded).

**NUNCA testado contra o SEFAZ real** — mesma ressalva de sempre (ver
`nfe_cancelamento_service.py` e CLAUDE.md §12 "Telas Fiscais"). Reaproveita
toda a infraestrutura genérica já construída pro Cancelamento
(`nfe_fiscal_common.py`: assinatura, envelope SOAP, transporte TLS
mútuo, certificado, endpoints por UF) — só o `tpEvento`/`detEvento`/
validação de motivo mudam.
"""
import re
from datetime import datetime, timezone
from typing import Optional

from services import nfe_fiscal_common

_IBGE_POR_UF = nfe_fiscal_common.IBGE_POR_UF
_NFE_NS = nfe_fiscal_common.NFE_NS

# Texto legal fixo do `xCondUso` — Nota Técnica 2011.003 (SEFAZ), verbatim,
# nunca editável pelo usuário.
#
# Achado ao vivo 2026-08-23 (1ª CC-e real testada nesta migração): SEFAZ
# recusou ("Rejeição: Evento não atende o Schema XML específico [.../
# detEvento/xCondUso]") a versão anterior deste texto, que usava
# acentuação portuguesa correta (Correção/É/Convênio/etc). O texto oficial
# publicado pelo SEFAZ (NT 2011.003) usa ortografia SEM acentos —
# confirmado batendo caractere-a-caractere contra `nfephp-org/sped-nfe`'s
# `Tools::sefazCCe()`, implementação de referência amplamente usada em
# produção. **Nunca reintroduzir acentos aqui**, mesmo que pareça erro de
# digitação — é o texto oficial, tal qual o SEFAZ espera.
X_COND_USO = (
    "A Carta de Correcao e disciplinada pelo paragrafo "
    "1o-A do art. 7o do Convenio S/N, de 15 de dezembro de 1970 "
    "e pode ser utilizada para regularizacao de erro ocorrido "
    "na emissao de documento fiscal, desde que o erro nao esteja "
    "relacionado com: I - as variaveis que determinam o valor "
    "do imposto tais como: base de calculo, aliquota, "
    "diferenca de preco, quantidade, valor da operacao ou da "
    "prestacao; II - a correcao de dados cadastrais que implique "
    "mudanca do remetente ou do destinatario; III - a data de "
    "emissao ou de saida."
)


def _resolver_url(cod_ibge: str, tp_amb: str) -> Optional[str]:
    """URL do webservice "recepção de evento" — só resolve UFs do grupo
    SVRS por enquanto (mesmo recorte do Cancelamento). CC-e é só modelo
    "55" nesta migração, mesmo escopo do legado."""
    return nfe_fiscal_common.resolver_endpoint(cod_ibge, "55", tp_amb, nfe_fiscal_common.ENDPOINTS_RECEPCAO_EVENTO)


def _montar_xml_evento_correcao(
    cod_uf_ibge: str, cnpj: str, chave_acesso: str, motivo: str, n_seq_evento: int, tp_amb: str,
) -> tuple[bytes, str]:
    """Monta o `<evento>` de Carta de Correção (tpEvento 110110) — réplica
    de `_montar_xml_evento` do cancelamento (`nfe_cancelamento_service.py`),
    com `detEvento` na ordem `descEvento`/`xCorrecao`/`xCondUso` (NT
    2011.003). Retorna (xml_bytes, id_evento)."""
    dh_evento = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    id_evento = f"ID110110{chave_acesso}{n_seq_evento:02d}"
    xml = (
        f'<evento xmlns="{_NFE_NS}" versao="1.00">'
        f'<infEvento Id="{id_evento}">'
        f'<cOrgao>{cod_uf_ibge}</cOrgao>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<CNPJ>{cnpj}</CNPJ>'
        f'<chNFe>{chave_acesso}</chNFe>'
        f'<dhEvento>{dh_evento}</dhEvento>'
        f'<tpEvento>110110</tpEvento>'
        f'<nSeqEvento>{n_seq_evento}</nSeqEvento>'
        f'<verEvento>1.00</verEvento>'
        f'<detEvento versao="1.00">'
        # Sem acento — mesmo achado ao vivo 2026-08-23 do `X_COND_USO`
        # (valor fixo esperado pelo schema do SEFAZ, confirmado contra
        # `nfephp-org/sped-nfe`'s `Tools::tpEv()`, que usa exatamente
        # "Carta de Correcao" pro tpEvento 110110).
        f'<descEvento>Carta de Correcao</descEvento>'
        f'<xCorrecao>{nfe_fiscal_common.escapar_xml(motivo)}</xCorrecao>'
        f'<xCondUso>{nfe_fiscal_common.escapar_xml(X_COND_USO)}</xCondUso>'
        f'</detEvento>'
        f'</infEvento>'
        f'</evento>'
    ).encode("utf-8")
    return xml, id_evento


def _montar_envelope_soap(xml_evento_assinado: bytes) -> bytes:
    """Envelope SOAP 1.2 pro webservice `NFeRecepcaoEvento4` — mesmo padrão
    do cancelamento, o corpo (`envEvento`) embrulha o `<evento>` assinado."""
    corpo = xml_evento_assinado.decode("utf-8")
    # `\s*` — achado ao vivo 2026-08-23, ver docstring de
    # `nfe_fiscal_common.montar_envelope_soap` pro racional completo
    # (lxml deixa `\n` residual depois da declaração XML).
    corpo = re.sub(r"^<\?xml[^>]*\?>\s*", "", corpo)
    env_evento = f'<envEvento xmlns="{_NFE_NS}" versao="1.00"><idLote>1</idLote>{corpo}</envEvento>'
    return nfe_fiscal_common.montar_envelope_soap(env_evento.encode("utf-8"), "NFeRecepcaoEvento4")


def emitir_carta_correcao_sync(
    cur, *, cnpj: str, uf_sigla: str, chave_acesso: str, motivo: str, n_seq_evento: int, tp_amb: str,
) -> dict:
    """Orquestra a emissão da Carta de Correção (evento 110110) — chamado
    por `notas_fiscais_service._carta_correcao_sync`. `cur` é o cursor já
    aberto (mesma transação/conexão de quem chama, pra ler o certificado)."""
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        return {"success": False, "message": "A descrição da correção deve ter pelo menos 15 caracteres."}
    if len(motivo) > 1000:
        return {"success": False, "message": "A descrição da correção não pode passar de 1000 caracteres."}
    if not chave_acesso or len(chave_acesso.strip()) != 44:
        return {"success": False, "message": "Chave de acesso da NF-e inválida ou ausente."}
    if not (1 <= n_seq_evento <= 20):
        return {"success": False, "message": "Esta Nota Fiscal já atingiu o limite de 20 cartas de correção do SEFAZ."}

    cod_ibge = _IBGE_POR_UF.get((uf_sigla or "").strip().upper())
    if not cod_ibge:
        return {"success": False, "message": f"UF '{uf_sigla}' não reconhecida."}
    url = _resolver_url(cod_ibge, tp_amb)
    if not url:
        return {
            "success": False,
            "message": (
                f"Carta de Correção automática ainda não está disponível pra UF '{uf_sigla}' — "
                "faça a correção oficial no sistema legado (VB6) por enquanto."
            ),
        }

    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert

    try:
        xml_evento, id_evento = _montar_xml_evento_correcao(cod_ibge, cnpj, chave_acesso.strip(), motivo, n_seq_evento, tp_amb)
        # sha1=True — mesmo achado do MDF-e/NFC-e (2026-08-23), ver
        # `nfe_cancelamento_service._assinar_evento`.
        xml_assinado = nfe_fiscal_common.assinar_xml(xml_evento, id_evento, key_pem, cert_pem, sha1=True)
        envelope = _montar_envelope_soap(xml_assinado)
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    # `retEnvEvento` tem 2 `cStat` aninhados — o do LOTE (nível externo,
    # ex. 128 "Lote de Evento Processado", neutro/sempre presente) e o do
    # EVENTO de verdade, dentro de `infEvento` (nível interno) — achado ao
    # vivo 2026-08-23 (1ª CC-e real testada): `extrair_tag` ingênuo sempre
    # pega o primeiro (o do lote), mascarando rejeições reais como se
    # fossem sucesso silencioso/status errado. Mesmo padrão já corrigido
    # em `nfe_emissao_service.py` (NFC-e/NF-e) no mesmo dia.
    inf_evento = nfe_fiscal_common.extrair_bloco(resposta, "infEvento") or resposta
    c_stat = nfe_fiscal_common.extrair_tag(inf_evento, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(inf_evento, "xMotivo")
    n_prot = nfe_fiscal_common.extrair_tag(inf_evento, "nProt")
    dh_reg = nfe_fiscal_common.extrair_tag(inf_evento, "dhRegEvento")
    # 135 = "Evento registrado e vinculado a NF-e" (CC-e homologada).
    if c_stat != "135":
        return {
            "success": False,
            "message": f"SEFAZ recusou a Carta de Correção (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
        }
    return {
        "success": True,
        "message": f"Carta de Correção autorizada pelo SEFAZ — protocolo {n_prot or '?'}.",
        "protocolo": n_prot,
        "cstat": c_stat,
        "xmotivo": x_motivo,
        "data_hora_registro": dh_reg,
        "xml_evento": xml_assinado.decode("utf-8"),
    }
