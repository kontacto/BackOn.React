"""Emissão real de NFC-e (modelo 65) junto ao SEFAZ — Fase 1 do pacote de
emissão fiscal ("Impressão de Nota Fiscal", migração de `FrmTraImpNFE.frm`),
pedido explícito do usuário 2026-07-21: "tudo que estiver na DLL, referente
à parte fiscal, deve ser reimplementado e melhorado em Python" (decisão
tomada depois de investigar `Backon_Controllers.Nfe` — ver o plano de
implementação, `C:\\Users\\carlo\\.claude\\plans\\velvet-roaming-sparrow.md`,
pro racional completo e o porquê de NÃO chamar a DLL via COM-interop).

Fonte de referência (rastreada 2026-07-21, ver docstring completa no plano):
  - `Backon.Controllers/NFe.vb::GeraNFe` — NÃO calcula alíquota, só monta/
    assina/transmite valores já resolvidos. A resolução de tributação real
    está inteira no VB6 (`FrmTraImpNFE.frm::SitTribut`), portada fielmente
    aqui em `_resolver_tributacao_sync`.
  - `Backon.Controllers/NFe.vb::ImprimeDanfe` depende de
    `System.Windows.Forms.PrintPreviewDialog` + um driver de impressora
    virtual COM de terceiros (`biopdf.PDFUtil`) — não portável pra um
    backend. A melhoria fica pra Fase 4 (DANFCe em HTML, reaproveitando
    `printHtml.ts`/`print-report-header.ts` do frontend).
  - `EmiteNFSe` não existe na DLL — fica de fora deste módulo (Fase 3,
    bloqueada até a fonte VB6 real da orquestração aparecer).

**NUNCA testado contra o SEFAZ real** — mesma ressalva de
`nfe_cancelamento_service.py`: só certificado autoassinado + rede mockada
nos testes. **A ordem exata das tags XML aqui não foi extraída da DLL**
(o corpo de `GeraNFe` monta o XML por concatenação de string ao longo de
~600 linhas, não documentado tag-a-tag na investigação) — segue o layout
público da NFe 4.00 (MOC/NT vigente), mas precisa ser validada contra o
XSD oficial da SEFAZ antes de qualquer transmissão real (mesmo em
homologação) — ver CLAUDE.md §12.

Melhorias deliberadas em relação ao legado (documentadas, não mudança de
regra fiscal):
  - RSA-SHA256 na assinatura (mesmo precedente do cancelamento).
  - Erros como dict estruturado, não string com código de status embutido.
  - Endpoint/UF resolvidos por dict explícito e testável.

**Correção real 2026-08-21 (usuário contestou diretamente uma pergunta de
esclarecimento e forçou o rastreio completo — ver CLAUDE.md > "Toda
ramificação condicional...")**: `_montar_xml_nfe` (modelo 55) tinha
`<modFrete>9</modFrete>` cravado sempre. Rastreio corrigido confirmou que
`n_fiscal.paga_frete` é um campo real, gravado de verdade
(`Grava_Frete`, `ModNF.bas`/`ModNFNfe.bas`, chamado por `FrmTraImpNFE.frm`
via o seletor `opFrete` Emitente/Destinatário) e lido de verdade pelo
motor compartilhado de emissão do legado (`DAO_NFE.vb:5478-5491`) pra
produzir qualquer um dos 6 códigos válidos de `<modFrete>` — não um
atalho de preenchimento morto. `_resolver_mod_frete` replica essa tabela
exatamente. `frmtranfe.frm` (fonte do NF-e Avulsa) não tem esse seletor —
quando `paga_frete` não é informado, o comportamento correto (réplica do
branch `Else` do DAO_NFE) é `modFrete=0` (Emitente/CIF), não 9. O
hardcode de `_montar_xml_nfce` (modelo 65/NFC-e, linha ~290) **não foi
tocado** — segue outra regra (`FreteNFCeValor > 0` → 1, senão 9,
`DAO_NFE.vb:5438-5476`), não investigada nesta rodada."""
import re
from datetime import date, datetime, time, timezone
from typing import Optional

from services import apoio_fiscal_service, nfe_fiscal_common, nfe_regras_fiscais

# Endpoints "autorização" (emissão), versão 4.00, só pro grupo SVRS — mesma
# limitação documentada em `nfe_cancelamento_service.py`.
_ENDPOINTS_AUTORIZACAO = {
    "55": {
        "1": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "2": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
    },
    "65": {
        "1": "https://nfce.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "2": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
    },
}

_NFE_NS = nfe_fiscal_common.NFE_NS


def _resolver_url_autorizacao(cod_ibge: str, modelo: str, tp_amb: str) -> Optional[str]:
    return nfe_fiscal_common.resolver_endpoint(cod_ibge, modelo, tp_amb, _ENDPOINTS_AUTORIZACAO)


# ---------------------------------------------------------------------------
# Resolução de tributação — porta fiel de `SitTribut()` (FrmTraImpNFE.frm).
# ---------------------------------------------------------------------------

def _gerar_tentativas_tributacao(
    protocolo_st_inicial: bool, nao_contribuinte: bool, simples_nacional_cliente: bool,
    consumidor_final: bool, uf_destino: str, uf_controle: str,
) -> list[tuple[bool, bool, bool, str]]:
    """Gera, EXPLICITAMENTE na mesma ordem do VB6, a cascata de combinações
    (protocolo_st, simples_nacional, consumidor_final, uf) que `SitTribut()`
    tenta até achar uma linha em `taxas`. Achado não-óbvio confirmado direto
    na fonte: o parâmetro chamado "CSN" no VB6 começa valendo
    `NaoContribuinte` (não `Cliente_Simples_Nacional`, apesar do nome da
    variável) — só quando a cascata cai pro fallback de UF="XX" é que ele
    é reiniciado com o valor real de `Cliente_Simples_Nacional`. Portado
    tal qual, não é engano do port.

    Cada "rodada" (2 no total, replicando `FEZ=0`/`FEZ=1` — a segunda com
    `protocolo_st` invertido) tenta, em ordem: (a) valores originais,
    (b) inverte simples_nacional, (c) também inverte consumidor_final,
    depois, só se `uf_destino != uf_controle`, reinicia com os valores
    "reais" de simples_nacional/consumidor_final e UF="XX" e repete a
    mesma cascata de 4 combinações."""
    tentativas: list[tuple[bool, bool, bool, str]] = []
    protocolo_atual = protocolo_st_inicial
    for _ in range(2):
        csn = nao_contribuinte
        cfinal = consumidor_final
        tentativas.append((protocolo_atual, csn, cfinal, uf_destino))
        csn = not csn
        tentativas.append((protocolo_atual, csn, cfinal, uf_destino))
        cfinal = not cfinal
        tentativas.append((protocolo_atual, csn, cfinal, uf_destino))
        if uf_destino != uf_controle:
            csn = simples_nacional_cliente
            cfinal = consumidor_final
            tentativas.append((protocolo_atual, csn, cfinal, "XX"))
            csn = not csn
            tentativas.append((protocolo_atual, csn, cfinal, "XX"))
            cfinal = not cfinal
            tentativas.append((protocolo_atual, csn, cfinal, "XX"))
            csn = not csn
            tentativas.append((protocolo_atual, csn, cfinal, "XX"))
        protocolo_atual = not protocolo_atual
    return tentativas


def _resolver_tributacao_sync(
    cur, *, cod_icms: str, cfop_cupom_fiscal: str, tipo_mov: str, uf_destino: str, uf_controle: str,
    nao_contribuinte: bool, simples_nacional_cliente: bool, consumidor_final: bool, protocolo_st: bool,
) -> Optional[dict]:
    """Resolve a linha de `taxas` aplicável — porta de `SitTribut()`.
    Achado não-óbvio confirmado direto na fonte: a query da tabela `taxas`
    (ramo `DIRETO:`, sempre executado — o ramo alternativo do legado, ligado
    a `Venda_Ref_Cupom`/`Venda_Ref_NFCE`, é código morto por causa de um
    `GoTo DIRETO` incondicional logo no início do `If`) **não filtra pelo
    CFOP do item** — só EXCLUI linhas cujo `cfop` seja igual a
    `CFOP_Cupom_Fiscal` (normalmente vazio). A seleção real é por
    `protocolo_st + consumidor_final + simples_nacional + destino +
    tipo_mov + cod_icms`, pegando a de menor `tributacao` quando há mais de
    uma. Replicado tal qual — não é engano do port, é assim que o legado
    funciona de verdade."""
    tentativas = _gerar_tentativas_tributacao(
        protocolo_st, nao_contribuinte, simples_nacional_cliente, consumidor_final, uf_destino, uf_controle,
    )
    for protocolo_atual, csn, cfinal, uf in tentativas:
        cur.execute(
            "SELECT TOP 1 * FROM taxas WHERE protocolo_st = %s AND consumidor_final = %s "
            "AND Simples_Nacional = %s AND destino = %s AND tipo_mov = %s AND cfop <> %s "
            "AND cod_icms = %s ORDER BY tributacao",
            (1 if protocolo_atual else 0, 1 if cfinal else 0, 1 if csn else 0, uf, tipo_mov,
             cfop_cupom_fiscal or "", cod_icms),
        )
        row = cur.fetchone()
        if row:
            return row
    return None


# ---------------------------------------------------------------------------
# Chave de acesso (algoritmo público da NFe/NFCe — não é lógica proprietária
# da DLL, é o mesmo dígito verificador módulo-11 documentado no Manual de
# Orientação do Contribuinte, usado por qualquer emissor fiscal brasileiro).
# ---------------------------------------------------------------------------

def _dv_modulo11(chave_43_digitos: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = 0
    for i, digito in enumerate(reversed(chave_43_digitos)):
        soma += int(digito) * pesos[i % len(pesos)]
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return str(dv)


def _gerar_cnf_valido(seed: str, numero: int) -> str:
    """`cNF` (8 dígitos, parte da chave de acesso) — achado ao vivo
    2026-08-23 (1ª emissão real de NF-e modelo 55): SEFAZ recusou com
    "Rejeição 897 - Código numérico em formato inválido". Confirmado por
    busca (múltiplas fontes de integradores, convergentes): `cNF` NUNCA
    pode ser igual ao `nNF` (número sequencial do documento) nem uma
    sequência "óbvia" de dígito repetido (00000000, 11111111, ...,
    99999999) — regra real de validação do SEFAZ, não documentada de
    forma óbvia no MOC, só descoberta ao vivo. `emitir_nfe_sync` (modelo
    55) passava `codigo_numerico=str(proximo_numero)` — LITERALMENTE o
    mesmo valor de `numero` — colidindo 100% das vezes, garantido.
    `emitir_nfce_sync` usa o número da comanda como seed e nunca colidiu
    até hoje só por coincidência (comanda e nNF correm em contadores
    independentes) — mesmo bug latente, só não disparado ainda.

    Corrigido no ÚNICO lugar onde `cNF` é gerado: **nunca mais confia só
    no valor passado pelo chamador** — usa `secrets` (aleatoriedade
    criptográfica, não passível de colisão previsível) e SEMPRE valida
    contra as duas regras reais antes de aceitar, com o `seed` só como
    ponto de partida (mantém alguma relação com o valor já passado pelos
    2 call sites existentes, não estritamente necessário). Assim nenhum
    call site pode reintroduzir esse bug por acidente — inclusive
    `mdfe_emissao_service.py`, que tem o MESMO padrão (`codigo_numerico=
    str(proximo_numero)`) mas nunca disparou o erro em produção (a
    validação de colisão parece ser específica de NF-e/NFC-e, não de
    MDF-e — confirmado pela emissão real de MDF-e já autorizada
    2026-08-23) — reforçado aqui mesmo assim, sem custo."""
    import secrets

    base = abs(int(seed or 0)) % 100000000
    for tentativa in range(20):
        candidato = (base + secrets.randbelow(100000000) + tentativa) % 100000000
        cnf = str(candidato).zfill(8)
        if len(set(cnf)) > 1 and int(cnf) != int(numero):
            return cnf
    return str((int(numero) + 1) % 100000000).zfill(8)  # praticamente inatingível


def montar_chave_acesso(
    *, uf_ibge: str, data_emissao: date, cnpj: str, modelo: str, serie: str, numero: int,
    tp_emis: str, codigo_numerico: str,
) -> str:
    """Monta a chave de acesso de 44 dígitos (cUF+AAMM+CNPJ+mod+serie+
    nNF+tpEmis+cNF+cDV) — algoritmo público, mesmo pra NFe quanto NFCe.
    `codigo_numerico` é só o seed de partida pro `cNF` — ver
    `_gerar_cnf_valido` pra por que ele nunca é usado cru."""
    aamm = data_emissao.strftime("%y%m")
    cnpj_num = re.sub(r"\D", "", cnpj).zfill(14)
    serie_num = str(int(serie or 0)).zfill(3)
    numero_num = str(int(numero)).zfill(9)
    cnf = _gerar_cnf_valido(codigo_numerico, numero)
    chave_43 = f"{uf_ibge}{aamm}{cnpj_num}{modelo}{serie_num}{numero_num}{tp_emis}{cnf}"
    return chave_43 + _dv_modulo11(chave_43)


# ---------------------------------------------------------------------------
# QR Code da NFCe — algoritmo público (MOC, versão 2.00): URL de consulta +
# hash SHA-1 da chave+CSC. Não depende de `MessagingToolkit.QRCode` (a DLL
# só usa essa lib pra desenhar a imagem do QR — a STRING/URL em si é
# especificação pública). O desenho visual do QR fica pra Fase 4 (DANFCe
# em HTML).
# ---------------------------------------------------------------------------

def montar_url_qrcode(
    *, chave_acesso: str, tp_amb: str, csc_id: str, csc: str, uf_sigla: str, homologacao_url: Optional[str] = None,
    tp_emis: str = "1", dh_emi: Optional[datetime] = None, valor_total: Optional[float] = None,
    digest_value_b64: Optional[str] = None,
) -> str:
    """QR Code versão 2 (`|2|`, layout NFC-e 4.00 vigente) — achado ao vivo
    2026-08-23 (1ª emissão real de NFC-e): a versão anterior desta função
    montava o formato V1/legado (`?chNFe=...&nVersao=200&...`), que o XSD
    real (`leiauteNFe_v4.00.xsd`, `infNFeSupl/qrCode`) só aceita com
    `nVersao=100` E vários campos criptografados/hash que essa versão
    nunca calculava (deixados em branco) — nunca batia o pattern. Fórmula
    V2 real confirmada contra código-fonte de referência (`nfephp-org/
    sped-nfe`, `QRCode::get200`, biblioteca amplamente usada em produção):
    `p={chNFe}|2|{tpAmb}|{cscId}|{SHA1(chNFe|2|tpAmb|cscId + csc).upper()}`
    — `cscId` sem zeros à esquerda (`int(csc_id)`), hash em MAIÚSCULAS.

    **`tp_emis="9"` (contingência), achado ao vivo 2026-08-26 (1º teste
    ponta a ponta de Contingência NFC-e)**: essa fórmula ONLINE não bate
    o pattern do XSD quando `tpEmis=9` — SEFAZ recusa com "Falha no
    Schema XML... infNFeSupl/qrCode" (o `xs:pattern` de `qrCode` tem
    alternativas separadas pra online/offline, e a alternativa offline
    exige EXATAMENTE `chave{34}9{9}` na posição do tpEmis — confirmado
    lendo o XSD real, `leiauteNFe_v4.00.xsd`). Fórmula OFFLINE, também
    confirmada contra `QRCode::get200`'s ramo `tpEmis==9`:
    `p={chave}|2|{tpAmb}|{dia(2)}|{valor(0.00)}|{digHex}|{cscId}|{hash}`
    — `dia` é o dia do mês (2 dígitos) de `dhEmi`; `valor` é o total da
    NFC-e formatado `0.00`; `digHex` é o `DigestValue` da PRÓPRIA
    assinatura (já base64), com cada CARACTERE do base64 hex-encoded
    byte a byte (`ord(c):02x}`, NÃO decodificado antes — dá exatamente
    56 hex chars pra um SHA-1 base64 de 28 chars, batendo o `maxLength`
    do XSD); `hash` = `SHA1(seq + csc).upper()`, igual ao caso online.
    Como o QR Code depende da assinatura, só pode ser montado DEPOIS de
    assinar — ver `emitir_nfce_sync`."""
    import hashlib

    # Achado ao vivo 2026-08-23: SEFAZ recusou (395, "Endereco do site da
    # UF da consulta via QR-Code diverge do previsto") com a URL genérica
    # nacional antiga — cada UF tem sua PRÓPRIA URL de consulta pública
    # de QR Code (mesmo o autorizador sendo o grupo SVRS compartilhado).
    # Só RJ confirmada até agora (única UF testada nesta migração — ver
    # docstring do módulo): `consultadfe.fazenda.rj.gov.br` (atualizada
    # dez/2023, substituiu `www4.fazenda.rj.gov.br`). Escopo reduzido de
    # propósito, mesmo recorte já usado no resto do pacote fiscal.
    base = homologacao_url or "https://consultadfe.fazenda.rj.gov.br/consultaNFCe/QRCode"
    csc_id_num = int(csc_id or 0)
    if tp_emis == "9":
        dh = dh_emi or datetime.now()
        dia = f"{dh.day:02d}"
        valor = f"{(valor_total or 0):.2f}"
        dig_hex = "".join(f"{ord(c):02x}" for c in (digest_value_b64 or ""))
        seq = f"{chave_acesso}|2|{tp_amb}|{dia}|{valor}|{dig_hex}|{csc_id_num}"
    else:
        seq = f"{chave_acesso}|2|{tp_amb}|{csc_id_num}"
    hash_qr = hashlib.sha1((seq + csc).encode("utf-8")).hexdigest().upper()
    sep = "" if base.endswith("?p=") else ("&p=" if "?" in base else "?p=")
    return f"{base}{sep}{seq}|{hash_qr}"


def montar_url_chave_consulta(homologacao_url: Optional[str] = None) -> str:
    """`<urlChave>` (`infNFeSupl`) — achado ao vivo 2026-08-23: o schema
    NFC-e exige `urlChave` JUNTO com `qrCode` dentro de `infNFeSupl`
    (confirmado via busca — SEFAZ recusa "conteúdo incompleto" sem os
    dois); `urlChave` é a URL BASE de consulta pública por chave, sem os
    parâmetros de query do QR (mesma base usada em `montar_url_qrcode`)."""
    # Mesma ressalva de `montar_url_qrcode` — só RJ confirmada.
    return homologacao_url or "https://www.fazenda.rj.gov.br/nfce/consulta"


# ---------------------------------------------------------------------------
# XML da NFCe — layout NFe 4.00 (validar contra o XSD oficial antes de
# transmitir de verdade — ver docstring do módulo).
# ---------------------------------------------------------------------------

def _montar_transp_nfce_xml(frete_valor: float, transportador: Optional[dict]) -> str:
    """Monta `<transp>` da NFC-e — réplica exata de `DAO_NFE.vb:5436-5476`
    (ramo `ModeloNota = "65"`). `modFrete=1` (Destinatário/FOB) só quando
    há valor de frete de verdade (`FreteNFCeValor > 0`, resolvido pelo
    chamador a partir do item de serviço configurado em `controle_aux.
    SERVICO_FRETE_NFCE`); sem valor, `modFrete=9` (Sem transporte) — nunca
    o mesmo mapeamento de `paga_frete` usado pela NF-e modelo 55
    (`_resolver_mod_frete`), que é uma regra DIFERENTE (seletor de tipo,
    não valor de item). `transportador` (opcional, resolvido pelo
    chamador via `controle_aux.TRANSPORTADOR_FRETE_NFCE` → `fornecedor`/
    `fornecedor_end`) já vem com `cgc_cpf`/`nome`/`ie`/`endereco`/`cidade`/
    `uf` prontos — esta função só monta o XML, não faz nenhuma consulta."""
    if frete_valor <= 0:
        return "<transp><modFrete>9</modFrete></transp>"
    partes = ["<transp>", "<modFrete>1</modFrete>"]
    if transportador and transportador.get("cgc_cpf"):
        doc = re.sub(r"[^0-9]", "", transportador["cgc_cpf"])
        doc_tag = "CNPJ" if len(doc) > 11 else "CPF"
        partes.append("<transporta>")
        partes.append(f"<{doc_tag}>{doc}</{doc_tag}>")
        partes.append(f"<xNome>{nfe_fiscal_common.escapar_xml(transportador.get('nome') or '')}</xNome>")
        if (transportador.get("ie") or "").strip():
            partes.append(f"<IE>{nfe_fiscal_common.escapar_xml(transportador['ie'])}</IE>")
        if (transportador.get("endereco") or "").strip():
            partes.append(f"<xEnder>{nfe_fiscal_common.escapar_xml(transportador['endereco'][:60])}</xEnder>")
        if (transportador.get("cidade") or "").strip():
            partes.append(f"<xMun>{nfe_fiscal_common.escapar_xml(transportador['cidade'])}</xMun>")
        if (transportador.get("uf") or "").strip():
            partes.append(f"<UF>{transportador['uf']}</UF>")
        partes.append("</transporta>")
    partes.append("</transp>")
    return "".join(partes)


def _montar_icms_tot_xml(
    itens: list[dict], valor_total: float, frete_valor: float = 0,
    v_icms_uf_dest_total: float = 0.0, v_icms_uf_remet_total: float = 0.0, v_fcp_uf_dest_total: float = 0.0,
) -> str:
    """`<total><ICMSTot>...</ICMSTot></total>` completo — achado ao vivo
    2026-08-23 (1ª emissão real de NFC-e): a versão anterior só tinha
    `vNF`/`vFrete`, faltando toda a sequência obrigatória do schema NFe
    4.00 antes deles (`vBC, vICMS, vICMSDeson, vFCP, vBCST, vST, vFCPST,
    vFCPSTRet, vProd, vFrete, vSeg, vDesc, vII, vIPI, vIPIDevol, vPIS,
    vCOFINS, vOutro, vNF`) — SEFAZ recusa por schema incompleto. `vProd`
    somado a partir dos itens; os campos de imposto detalhado ficam em
    0.00 (mesmo alcance simplificado já documentado na docstring do
    módulo — sem PIS/COFINS/ICMS efetivamente calculados aqui, só a
    sequência de totais que o schema exige presente).

    `v_icms_uf_dest_total`/`v_icms_uf_remet_total`/`v_fcp_uf_dest_total` —
    totais do grupo DIFAL (`nfe_regras_fiscais.montar_grupo_icms_uf_dest_
    item`, somado por quem chama) — posição confirmada no XSD oficial
    (`leiauteNFe_v4.00.xsd`, `TICMSTot`): logo depois de `vICMSDeson`, não
    perto de `vNF`. Campos opcionais (`minOccurs=0`), omitidos quando a
    nota não tem DIFAL nenhuma."""
    v_prod = sum(float(i.get("valor_total") or 0) for i in itens)
    z = "0.00"
    icms_uf_dest_xml = nfe_regras_fiscais.montar_totais_icms_uf_dest_xml(
        v_icms_uf_dest_total, v_icms_uf_remet_total, v_fcp_uf_dest_total,
    )
    return (
        "<ICMSTot>"
        f"<vBC>{z}</vBC><vICMS>{z}</vICMS><vICMSDeson>{z}</vICMSDeson>"
        f"{icms_uf_dest_xml}"
        f"<vFCP>{z}</vFCP><vBCST>{z}</vBCST><vST>{z}</vST><vFCPST>{z}</vFCPST><vFCPSTRet>{z}</vFCPSTRet>"
        f"<vProd>{v_prod:.2f}</vProd><vFrete>{frete_valor:.2f}</vFrete><vSeg>{z}</vSeg><vDesc>{z}</vDesc>"
        f"<vII>{z}</vII><vIPI>{z}</vIPI><vIPIDevol>{z}</vIPIDevol>"
        f"<vPIS>{z}</vPIS><vCOFINS>{z}</vCOFINS><vOutro>{z}</vOutro>"
        f"<vNF>{valor_total:.2f}</vNF>"
        "</ICMSTot>"
    )


def _montar_emit_xml(cnpj_emit: str, nome_emit: str, emitente_end: Optional[dict]) -> str:
    """`<emit>` completo (CNPJ, xNome, enderEmit, IE, CRT) — achado ao vivo
    2026-08-23 (1ª emissão real de NFC-e): a versão anterior só tinha
    CNPJ/xNome/CRT, sem `<enderEmit>`/`<IE>` — SEFAZ recusa por schema
    incompleto (`emit/CRT` fora de sequência, já que o validador esperava
    `enderEmit`/`IE` antes dele). `emitente_end` vem de `nfe_fiscal_
    common.resolver_endereco_emitente_sync` — `None` só nos testes
    unitários que não montam esse dict (produz `<emit>` sem endereço,
    mantendo compatibilidade com fixtures antigas, mas nunca usado em
    transmissão real)."""
    end = emitente_end or {}
    partes = [
        "<emit>",
        f'<CNPJ>{re.sub(r"[^0-9]", "", cnpj_emit)}</CNPJ>',
        f"<xNome>{nfe_fiscal_common.escapar_xml(nome_emit)}</xNome>",
    ]
    if end:
        partes.append("<enderEmit>")
        partes.append(f'<xLgr>{nfe_fiscal_common.escapar_xml((end.get("endereco") or "").strip())}</xLgr>')
        partes.append(f'<nro>{nfe_fiscal_common.escapar_xml(str(end.get("numero") or "").strip())}</nro>')
        if (end.get("complemento") or "").strip():
            partes.append(f'<xCpl>{nfe_fiscal_common.escapar_xml(end["complemento"].strip())}</xCpl>')
        partes.append(f'<xBairro>{nfe_fiscal_common.escapar_xml((end.get("bairro") or "").strip())}</xBairro>')
        partes.append(f'<cMun>{end.get("cod_municipio") or ""}</cMun>')
        partes.append(f'<xMun>{nfe_fiscal_common.escapar_xml(end.get("cidade") or "")}</xMun>')
        partes.append(f'<UF>{(end.get("uf") or "").strip()}</UF>')
        if (end.get("cep") or "").strip():
            partes.append(f'<CEP>{end["cep"].strip()}</CEP>')
        if (end.get("telefone") or "").strip():
            partes.append(f'<fone>{end["telefone"].strip()}</fone>')
        partes.append("</enderEmit>")
        partes.append(f'<IE>{(end.get("inscr_est") or "").strip()}</IE>')
    partes.append("<CRT>1</CRT>")
    partes.append("</emit>")
    return "".join(partes)


def _montar_xml_nfce(
    *, chave_acesso: str, cod_ibge: str, cnpj_emit: str, nome_emit: str, cliente: Optional[dict],
    itens: list[dict], forma_pagamento: str, valor_total: float, tp_amb: str, numero: int, serie: str,
    data_emissao: datetime, url_qrcode: str, ibs_cbs_totais_xml: str = "",
    tp_emis: str = "1", dh_cont: Optional[str] = None, x_just: Optional[str] = None,
    frete_valor: float = 0, transportador: Optional[dict] = None, emitente_end: Optional[dict] = None,
) -> tuple[bytes, str]:
    """Monta `<NFe><infNFe Id="NFe...">` conforme layout NFCe 4.00. `itens`
    é uma lista de dicts já com tributação resolvida
    (`_resolver_tributacao_sync`) e valores calculados por item.

    `item.get("ibs_cbs_xml")` — fragmento `<IBSCBS>...</IBSCBS>` já pronto
    (`ibs_cbs_service.calcular_item_ibs_cbs`'s `xml_item`), embutido dentro
    de `<imposto>` de cada item. `ibs_cbs_totais_xml` — fragmento agregado
    `<IBSCBSTot>...</IBSCBSTot>` (`ibs_cbs_service.calcular_totais_ibs_cbs`),
    embutido dentro de `<total>`. Posicionamento segue o layout público de
    transição da Reforma Tributária (NT vigente) — mesma ressalva já
    registrada na docstring do módulo: não foi extraído de uma DLL
    tag-a-tag, validar contra o XSD oficial antes de qualquer transmissão
    real."""
    id_nfe = f"NFe{chave_acesso}"
    dh_emi = data_emissao.astimezone().isoformat(timespec="seconds")

    det_xml = ""
    for i, item in enumerate(itens, start=1):
        det_xml += (
            f'<det nItem="{i}">'
            f'<prod>'
            f'<cProd>{nfe_fiscal_common.escapar_xml(item["codigo_int"])}</cProd>'
            f'<cEAN>SEM GTIN</cEAN>'
            f'<xProd>{nfe_fiscal_common.escapar_xml(item["descricao"])}</xProd>'
            f'<NCM>{item.get("ncm") or "00000000"}</NCM>'
            f'<CFOP>{item["cfop"]}</CFOP>'
            f'<uCom>{nfe_fiscal_common.escapar_xml(item.get("unidade") or "UN")}</uCom>'
            f'<qCom>{item["qtd"]:.4f}</qCom>'
            f'<vUnCom>{item["valor_unitario"]:.10f}</vUnCom>'
            f'<vProd>{item["valor_total"]:.2f}</vProd>'
            f'<cEANTrib>SEM GTIN</cEANTrib>'
            f'<uTrib>{nfe_fiscal_common.escapar_xml(item.get("unidade") or "UN")}</uTrib>'
            f'<qTrib>{item["qtd"]:.4f}</qTrib>'
            f'<vUnTrib>{item["valor_unitario"]:.10f}</vUnTrib>'
            f'<indTot>1</indTot>'
            f'</prod>'
            f'<imposto>'
            f'<ICMS><ICMSSN102><orig>{item.get("origem", 0)}</orig><CSOSN>{item.get("csosn", "102")}</CSOSN></ICMSSN102></ICMS>'
            f'<PIS><PISNT><CST>{item.get("cst_pis", "07")}</CST></PISNT></PIS>'
            f'<COFINS><COFINSNT><CST>{item.get("cst_cofins", "07")}</CST></COFINSNT></COFINS>'
            f'{item.get("ibs_cbs_xml") or ""}'
            f'</imposto>'
            f'</det>'
        )

    dest_xml = ""
    if cliente and cliente.get("cgc_cpf"):
        doc_tag = "CNPJ" if len(cliente["cgc_cpf"]) > 11 else "CPF"
        dest_xml = f'<dest><{doc_tag}>{cliente["cgc_cpf"]}</{doc_tag}><indIEDest>9</indIEDest></dest>'

    xml = (
        f'<NFe xmlns="{_NFE_NS}">'
        f'<infNFe Id="{id_nfe}" versao="4.00">'
        f'<ide>'
        f'<cUF>{cod_ibge}</cUF>'
        # `<cNF>` — achado ao vivo 2026-08-23 (1ª emissão real de NFC-e):
        # SEFAZ recusou com "Falha no Schema XML... ide/natOp" — o XSD do
        # NFe 4.00 exige `<cNF>` logo depois de `<cUF>` (antes de
        # `<natOp>`), elemento que faltava aqui; o validador reporta o
        # PRÓXIMO elemento encontrado fora de sequência, não o que falta.
        # Mesmo valor já embutido na chave de acesso (posições 35-43,
        # 8 dígitos — `montar_chave_acesso`/`GeraMDFe` usam o mesmo
        # `cNF`/`cMDF`).
        f'<cNF>{chave_acesso[35:43]}</cNF>'
        f'<natOp>Venda</natOp>'
        f'<mod>65</mod>'
        f'<serie>{serie}</serie>'
        f'<nNF>{numero}</nNF>'
        f'<dhEmi>{dh_emi}</dhEmi>'
        f'<tpNF>1</tpNF>'
        f'<idDest>1</idDest>'
        # Código IBGE REAL do município — achado ao vivo 2026-08-23: o
        # hack anterior (`{cod_ibge}00000`, só a UF com zeros) não é um
        # município real, SEFAZ recusa ("Codigo Municipio do Fato Gerador
        # de ICMS inexistente"). `emitente_end.cod_municipio` já vem
        # resolvido de verdade (`resolver_endereco_emitente_sync`).
        f'<cMunFG>{(emitente_end or {}).get("cod_municipio") or f"{cod_ibge}00000"}</cMunFG>'
        f'<tpImp>4</tpImp>'
        f'<tpEmis>{tp_emis}</tpEmis>'
        f'<cDV>{chave_acesso[-1]}</cDV>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<finNFe>1</finNFe>'
        f'<indFinal>1</indFinal>'
        f'<indPres>1</indPres>'
        f'<procEmi>0</procEmi>'
        f'<verProc>1.0</verProc>'
        # <dhCont>/<xJust> — só presentes em emissão por contingência
        # (tp_emis != "1"). Achado 2026-08-19 (Gestor NFCe): réplica de
        # GeraNFe (NFe.vb:2206-2208/2240-2242) — grava a data/hora de
        # início da contingência e a justificativa (motivo já validado
        # ≥15 chars por contingencia_nfce_service).
        f'{f"<dhCont>{dh_cont}</dhCont><xJust>{nfe_fiscal_common.escapar_xml(x_just or "")}</xJust>" if tp_emis != "1" else ""}'
        f'</ide>'
        f'{_montar_emit_xml(cnpj_emit, nome_emit, emitente_end)}'
        f'{dest_xml}'
        f'{det_xml}'
        f'<total>{_montar_icms_tot_xml(itens, valor_total, frete_valor)}{ibs_cbs_totais_xml}</total>'
        f'{_montar_transp_nfce_xml(frete_valor, transportador)}'
        f'<pag><detPag><tPag>{forma_pagamento}</tPag><vPag>{valor_total:.2f}</vPag></detPag></pag>'
        # `<infNFeSupl>` NÃO entra aqui — achado ao vivo 2026-08-23: é
        # IRMÃO de `<infNFe>` (filho de `<NFe>`), não filho de `<infNFe>`.
        # A assinatura enveloped só cobre `infNFe` (via `Reference URI`),
        # então `infNFeSupl` é inserido depois, por `assinar_xml` post-
        # -splice em `emitir_nfce_sync` — mesmo padrão já usado pro QR
        # Code do MDF-e (`<infMDFeSupl>`).
        f'</infNFe>'
        f'</NFe>'
    ).encode("utf-8")
    return xml, id_nfe


# ---------------------------------------------------------------------------
# XML da NF-e (modelo 55) — layout NFe 4.00, mesmo princípio de
# `_montar_xml_nfce` (não extraído de DLL, validar contra o XSD oficial
# antes de qualquer transmissão real — ver docstring do módulo). Diferenças
# reais confirmadas contra a fonte VB6 (`frmtranfe.frm`/`FrmTraImpNFE.frm`,
# rastreio 2026-08-19 — ver PENDENCIAS.md > "Agrupar Comandas em NF-e"):
# destinatário sempre estruturado e completo (endereço obrigatório — NF-e
# nunca tem consumidor não identificado como NFC-e às vezes tem), sem QR
# Code/CSC (exclusividade de NFC-e), `tpImp` retrato (1) em vez do "sem
# geração de DANFE automática" (4) que NFC-e usa.
# ---------------------------------------------------------------------------

def _resolver_mod_frete(paga_frete: Optional[int]) -> str:
    """Traduz `n_fiscal.paga_frete` pro código `<modFrete>` real da NFe —
    réplica exata da tabela usada pelo motor compartilhado de emissão do
    legado (`DAO_NFE.vb:5478-5491`, camada VB.NET chamada por toda tela de
    NFe modelo 55 — ver "Legacy VB6 Source Reference" no CLAUDE.md).

    Achado 2026-08-21 (reauditoria pós-correção do usuário): `paga_frete`
    é gravado de verdade via `Grava_Frete` (`ModNF.bas`/`ModNFNfe.bas`,
    chamado por `FrmTraImpNFE.frm` — fonte do NF-e Agrupada) a partir do
    seletor `opFrete` (Emitente=1/Destinatário=2), e É lido de verdade
    pelo motor de emissão pra produzir qualquer um dos 6 códigos válidos —
    não é um atalho de preenchimento morto, e o hardcode anterior
    (`<modFrete>9</modFrete>` sempre) estava errado. `frmtranfe.frm`
    (fonte do NF-e Avulsa) não tem esse seletor — quando `paga_frete` não
    é informado, o comportamento do legado (branch `Else` do DAO_NFE) é
    `modFrete=0` (Emitente/CIF), não 9."""
    valor = int(paga_frete or 0)
    if valor == 2:
        return "1"  # Destinatário (FOB)
    if valor == 6:
        return "9"  # Sem transporte
    if valor >= 3:
        return str(valor - 1)  # 3->2 Terceiros, 4->3 Próprio Remetente, 5->4 Próprio Destinatário
    return "0"  # 0/1/ausente -> Emitente (CIF)


def _montar_transp_completo_nfe_xml(
    *, paga_frete: Optional[int], transportador: Optional[dict], veiculo: Optional[dict], volumes: Optional[dict],
) -> str:
    """Monta `<transp>` completo do modelo 55 — `<modFrete>` (achado
    2026-08-21, `_resolver_mod_frete`) + `<transporta>`/`<veicTransp>`/
    `<vol>`, opcionais conforme o layout oficial NFe 4.00 (todos os
    campos de `transporta`/`veicTransp`/`vol` são opcionais no XSD, não
    exigem preenchimento completo pra serem válidos).

    Achado 2026-08-22 (varredura de simplificações pendentes): `nf_aux`
    já captura `cnpj_transportadora`/`placa`/`volumes`/`especie_volume`/
    `peso_bruto`/`peso_liquido` desde a Fase 1 de NF-e Avulsa (2026-08-20)
    — mas nenhum desses campos nunca chegava ao XML transmitido nem ao
    DANFE, ficavam só armazenados sem uso real. `motorista` não tem tag
    correspondente no layout `<transp>` da NFe (só existe em MDF-e, fora
    de escopo) — capturado mas não usado aqui, mesmo tratamento de antes."""
    partes = ["<transp>", f"<modFrete>{_resolver_mod_frete(paga_frete)}</modFrete>"]
    if transportador and (transportador.get("cgc_cpf") or transportador.get("nome")):
        partes.append("<transporta>")
        doc = re.sub(r"[^0-9]", "", transportador.get("cgc_cpf") or "")
        if doc:
            doc_tag = "CNPJ" if len(doc) > 11 else "CPF"
            partes.append(f"<{doc_tag}>{doc}</{doc_tag}>")
        if (transportador.get("nome") or "").strip():
            partes.append(f"<xNome>{nfe_fiscal_common.escapar_xml(transportador['nome'])}</xNome>")
        if (transportador.get("ie") or "").strip():
            partes.append(f"<IE>{nfe_fiscal_common.escapar_xml(transportador['ie'])}</IE>")
        if (transportador.get("uf") or "").strip():
            partes.append(f"<UF>{transportador['uf']}</UF>")
        partes.append("</transporta>")
    if veiculo and (veiculo.get("placa") or "").strip():
        partes.append("<veicTransp>")
        partes.append(f"<placa>{nfe_fiscal_common.escapar_xml(veiculo['placa'])}</placa>")
        if (veiculo.get("uf") or "").strip():
            partes.append(f"<UF>{veiculo['uf']}</UF>")
        partes.append("</veicTransp>")
    if volumes and any(volumes.get(k) for k in ("qtd", "especie", "marca", "numero", "peso_bruto", "peso_liquido")):
        partes.append("<vol>")
        if volumes.get("qtd"):
            partes.append(f"<qVol>{int(volumes['qtd'])}</qVol>")
        if (volumes.get("especie") or "").strip():
            partes.append(f"<esp>{nfe_fiscal_common.escapar_xml(volumes['especie'])}</esp>")
        if (volumes.get("marca") or "").strip():
            partes.append(f"<marca>{nfe_fiscal_common.escapar_xml(volumes['marca'])}</marca>")
        if volumes.get("numero"):
            partes.append(f"<nVol>{nfe_fiscal_common.escapar_xml(str(volumes['numero']))}</nVol>")
        if volumes.get("peso_liquido"):
            partes.append(f"<pesoL>{float(volumes['peso_liquido']):.3f}</pesoL>")
        if volumes.get("peso_bruto"):
            partes.append(f"<pesoB>{float(volumes['peso_bruto']):.3f}</pesoB>")
        partes.append("</vol>")
    partes.append("</transp>")
    return "".join(partes)


def _montar_xml_nfe(
    *, chave_acesso: str, cod_ibge: str, cnpj_emit: str, nome_emit: str, uf_emit_sigla: str,
    destinatario: dict, itens: list[dict], valor_total: float, tp_amb: str, numero: int, serie: str,
    data_emissao: datetime, natureza_operacao: str, indFinal: str = "1",
    ibs_cbs_totais_xml: str = "", tp_emis: str = "1", dh_cont: Optional[str] = None, x_just: Optional[str] = None,
    paga_frete: Optional[int] = None,
    transportador: Optional[dict] = None, veiculo: Optional[dict] = None, volumes: Optional[dict] = None,
    emitente_end: Optional[dict] = None,
) -> tuple[bytes, str]:
    """Monta `<NFe><infNFe Id="NFe...">` conforme layout NF-e 4.00 (modelo
    55). `destinatario` já vem resolvido pelo chamador (cgc_cpf, nome,
    endereco, numero, bairro, cidade, uf, cep, cod_municipio_ibge, ie,
    indIEDest) — esta função só serializa, não resolve endereço/IE sozinha
    (mesma separação de responsabilidade de `_montar_xml_nfce`)."""
    id_nfe = f"NFe{chave_acesso}"
    dh_emi = data_emissao.astimezone().isoformat(timespec="seconds")
    uf_dest = (destinatario.get("uf") or "").strip().upper()
    id_dest = "1" if uf_dest == (uf_emit_sigla or "").strip().upper() else "2"

    # Grupo ICMSUFDest (DIFAL) por item — ver nfe_regras_fiscais.py pro
    # rastreio completo (NT 2015.003 + XSD oficial). Deriva de idDest/
    # indFinal/indIEDest reais, nunca de campo digitado à mão na Taxa —
    # é isso que evita a rejeição 695 (grupo presente/ausente indevido).
    ind_ie_dest = destinatario.get("indIEDest") or "9"
    v_icms_uf_dest_total = 0.0
    v_icms_uf_remet_total = 0.0
    v_fcp_uf_dest_total = 0.0

    det_xml = ""
    for i, item in enumerate(itens, start=1):
        grupo_uf_dest = nfe_regras_fiscais.montar_grupo_icms_uf_dest_item(id_dest, indFinal, ind_ie_dest, item)
        v_icms_uf_dest_total += grupo_uf_dest["v_icms_uf_dest"]
        v_icms_uf_remet_total += grupo_uf_dest["v_icms_uf_remet"]
        v_fcp_uf_dest_total += grupo_uf_dest["v_fcp_uf_dest"]
        det_xml += (
            f'<det nItem="{i}">'
            f'<prod>'
            f'<cProd>{nfe_fiscal_common.escapar_xml(item["codigo_int"])}</cProd>'
            f'<cEAN>SEM GTIN</cEAN>'
            f'<xProd>{nfe_fiscal_common.escapar_xml(item["descricao"])}</xProd>'
            f'<NCM>{item.get("ncm") or "00000000"}</NCM>'
            f'<CFOP>{item["cfop"]}</CFOP>'
            f'<uCom>{nfe_fiscal_common.escapar_xml(item.get("unidade") or "UN")}</uCom>'
            f'<qCom>{item["qtd"]:.4f}</qCom>'
            f'<vUnCom>{item["valor_unitario"]:.10f}</vUnCom>'
            f'<vProd>{item["valor_total"]:.2f}</vProd>'
            f'<cEANTrib>SEM GTIN</cEANTrib>'
            f'<uTrib>{nfe_fiscal_common.escapar_xml(item.get("unidade") or "UN")}</uTrib>'
            f'<qTrib>{item["qtd"]:.4f}</qTrib>'
            f'<vUnTrib>{item["valor_unitario"]:.10f}</vUnTrib>'
            f'<indTot>1</indTot>'
            f'</prod>'
            f'<imposto>'
            f'<ICMS><ICMSSN102><orig>{item.get("origem", 0)}</orig><CSOSN>{item.get("csosn", "102")}</CSOSN></ICMSSN102></ICMS>'
            f'{grupo_uf_dest["xml"]}'
            f'<PIS><PISNT><CST>{item.get("cst_pis", "07")}</CST></PISNT></PIS>'
            f'<COFINS><COFINSNT><CST>{item.get("cst_cofins", "07")}</CST></COFINSNT></COFINS>'
            f'{item.get("ibs_cbs_xml") or ""}'
            f'</imposto>'
            f'</det>'
        )

    doc_tag = "CNPJ" if len(destinatario.get("cgc_cpf") or "") > 11 else "CPF"
    ie_xml = f'<IE>{nfe_fiscal_common.escapar_xml(destinatario.get("ie") or "")}</IE>' if destinatario.get("ie") else ""
    dest_xml = (
        f'<dest>'
        f'<{doc_tag}>{destinatario.get("cgc_cpf") or ""}</{doc_tag}>'
        f'<xNome>{nfe_fiscal_common.escapar_xml(destinatario.get("nome") or "")}</xNome>'
        f'<enderDest>'
        f'<xLgr>{nfe_fiscal_common.escapar_xml(destinatario.get("endereco") or "")}</xLgr>'
        f'<nro>{nfe_fiscal_common.escapar_xml(str(destinatario.get("numero") or "S/N"))}</nro>'
        f'<xBairro>{nfe_fiscal_common.escapar_xml(destinatario.get("bairro") or "")}</xBairro>'
        f'<cMun>{destinatario.get("cod_municipio_ibge") or (cod_ibge + "00000")}</cMun>'
        f'<xMun>{nfe_fiscal_common.escapar_xml(destinatario.get("cidade") or "")}</xMun>'
        f'<UF>{uf_dest}</UF>'
        f'<CEP>{(destinatario.get("cep") or "").replace("-", "").strip()}</CEP>'
        f'<cPais>1058</cPais><xPais>BRASIL</xPais>'
        f'</enderDest>'
        f'<indIEDest>{destinatario.get("indIEDest") or "9"}</indIEDest>'
        f'{ie_xml}'
        f'</dest>'
    )

    xml = (
        f'<NFe xmlns="{_NFE_NS}">'
        f'<infNFe Id="{id_nfe}" versao="4.00">'
        f'<ide>'
        f'<cUF>{cod_ibge}</cUF>'
        f'<cNF>{chave_acesso[35:43]}</cNF>'
        f'<natOp>{nfe_fiscal_common.escapar_xml(natureza_operacao)}</natOp>'
        f'<mod>55</mod>'
        f'<serie>{serie}</serie>'
        f'<nNF>{numero}</nNF>'
        f'<dhEmi>{dh_emi}</dhEmi>'
        f'<tpNF>1</tpNF>'
        f'<idDest>{id_dest}</idDest>'
        # Código IBGE REAL do município — achado ao vivo 2026-08-23: o
        # hack anterior (`{cod_ibge}00000`, só a UF com zeros) não é um
        # município real, SEFAZ recusa ("Codigo Municipio do Fato Gerador
        # de ICMS inexistente"). `emitente_end.cod_municipio` já vem
        # resolvido de verdade (`resolver_endereco_emitente_sync`).
        f'<cMunFG>{(emitente_end or {}).get("cod_municipio") or f"{cod_ibge}00000"}</cMunFG>'
        f'<tpImp>1</tpImp>'
        f'<tpEmis>{tp_emis}</tpEmis>'
        f'<cDV>{chave_acesso[-1]}</cDV>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<finNFe>1</finNFe>'
        f'<indFinal>{indFinal}</indFinal>'
        f'<indPres>1</indPres>'
        f'<procEmi>0</procEmi>'
        f'<verProc>1.0</verProc>'
        f'{f"<dhCont>{dh_cont}</dhCont><xJust>{nfe_fiscal_common.escapar_xml(x_just or "")}</xJust>" if tp_emis != "1" else ""}'
        f'</ide>'
        f'{_montar_emit_xml(cnpj_emit, nome_emit, emitente_end)}'
        f'{dest_xml}'
        f'{det_xml}'
        f'<total>{_montar_icms_tot_xml(itens, valor_total, v_icms_uf_dest_total=v_icms_uf_dest_total, v_icms_uf_remet_total=v_icms_uf_remet_total, v_fcp_uf_dest_total=v_fcp_uf_dest_total)}{ibs_cbs_totais_xml}</total>'
        f'{_montar_transp_completo_nfe_xml(paga_frete=paga_frete, transportador=transportador, veiculo=veiculo, volumes=volumes)}'
        f'<pag><detPag><tPag>90</tPag><vPag>0.00</vPag></detPag></pag>'
        f'</infNFe>'
        f'</NFe>'
    ).encode("utf-8")
    return xml, id_nfe


def parse_nfce_xml_para_exibicao(xml_texto: str) -> Optional[dict]:
    """Extrai do XML assinado da NFC-e (já gravado em `comanda_nfce.xml`
    no momento da emissão — ver `comanda_service._emitir_nfce_comanda_
    sync`) os dados estruturados pro fac-símile visual (DANFCe) da tela de
    reimpressão — pedido explícito do usuário 2026-07-21 ("tem que trazer
    o documento fiscal", junto de um exemplo real de DANFCe/DANFSe). É o
    XML que EU mesmo montei (`_montar_xml_nfce`), então a estrutura/
    namespace são conhecidos com certeza — não uma tentativa de adivinhar
    schema de terceiro."""
    from lxml import etree

    if not xml_texto:
        return None
    try:
        root = etree.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    except Exception:
        return None
    ns = {"n": _NFE_NS}

    def _t(el, path, default=""):
        found = el.find(path, ns) if el is not None else None
        return (found.text or default) if found is not None else default

    inf = root.find(".//n:infNFe", ns)
    if inf is None:
        return None
    ide = inf.find("n:ide", ns)
    emit = inf.find("n:emit", ns)
    dest = inf.find("n:dest", ns)
    total = inf.find("n:total/n:ICMSTot", ns)
    pag = inf.find("n:pag/n:detPag", ns)
    # `infNFeSupl` é IRMÃO de `infNFe` (filho de `NFe`), não filho dele —
    # achado ao vivo 2026-08-23, ver docstring de `_montar_xml_nfce`.
    qrcode = _t(root, "n:infNFeSupl/n:qrCode")

    itens = []
    for det in inf.findall("n:det", ns):
        prod = det.find("n:prod", ns)
        if prod is None:
            continue
        itens.append({
            "codigo": _t(prod, "n:cProd"), "descricao": _t(prod, "n:xProd"),
            "qtd": float(_t(prod, "n:qCom", "0") or 0), "valor_unitario": float(_t(prod, "n:vUnCom", "0") or 0),
            "valor_total": float(_t(prod, "n:vProd", "0") or 0),
        })

    return {
        "chave_acesso": (inf.get("Id") or "")[3:],  # Id="NFe"+chave (44 dígitos), sempre 3 letras de prefixo
        "tp_amb": _t(ide, "n:tpAmb"), "serie": _t(ide, "n:serie"), "numero": _t(ide, "n:nNF"),
        "dh_emi": _t(ide, "n:dhEmi"),
        "emit_cnpj": _t(emit, "n:CNPJ"), "emit_nome": _t(emit, "n:xNome"),
        "dest_doc": (_t(dest, "n:CNPJ") or _t(dest, "n:CPF")) if dest is not None else "",
        "itens": itens,
        "valor_total": float(_t(total, "n:vNF", "0") or 0),
        "forma_pagamento": _t(pag, "n:tPag"), "valor_pago": float(_t(pag, "n:vPag", "0") or 0),
        "qr_code_url": qrcode,
    }


def parse_nfe_xml_para_exibicao(xml_texto: str) -> Optional[dict]:
    """Irmã de `parse_nfce_xml_para_exibicao`, pro modelo 55 — extrai do
    XML assinado da NF-e (gravado em `n_fiscal.xml` na emissão, ver
    `nfe_agrupada_service.py`/`nfe_avulsa_service.py`) os dados
    estruturados pro fac-símile visual (DANFE). É o XML que este próprio
    backend montou (`_montar_xml_nfe`), estrutura/namespace conhecidos —
    não uma tentativa de adivinhar schema de terceiro.

    Diferenças do irmão NFCe: destinatário sempre estruturado com
    endereço completo (NF-e nunca tem consumidor não identificado),
    itens trazem NCM/CFOP/unidade (não só código/descrição/qtd/valor),
    sem QR Code (exclusividade de NFCe), e inclui `natureza_operacao`/
    `tp_nf`/dados de contingência (`tp_emis`/`dh_cont`/`x_just`) e o
    fragmento agregado IBS/CBS de `<total>` quando presente — este
    pacote já calcula IBS/CBS de verdade antes de emitir (ver
    PENDENCIAS.md > "Gap real confirmado... CalculaIBSCBS"), então o
    XML pode genuinamente trazer o bloco (`<IBSCBSTot>`), diferente do
    precedente do DANFSe (`buildIbsCbsHtml`, sempre "-")."""
    from lxml import etree

    if not xml_texto:
        return None
    try:
        root = etree.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    except Exception:
        return None
    ns = {"n": _NFE_NS}

    def _t(el, path, default=""):
        found = el.find(path, ns) if el is not None else None
        return (found.text or default) if found is not None else default

    inf = root.find(".//n:infNFe", ns)
    if inf is None:
        return None
    ide = inf.find("n:ide", ns)
    emit = inf.find("n:emit", ns)
    dest = inf.find("n:dest", ns)
    ender_dest = dest.find("n:enderDest", ns) if dest is not None else None
    total = inf.find("n:total/n:ICMSTot", ns)
    ibs_cbs_tot = inf.find("n:total/n:IBSCBSTot", ns)
    ibs_cbs_totais = None
    if ibs_cbs_tot is not None:
        # `<IBSCBSTot>` é aninhado (`<gIBS><vIBS>.../gIBS><gCBS><vCBS>.../gCBS>`,
        # ver `ibs_cbs_service.calcular_totais_ibs_cbs`'s `xml_totais`) — só
        # os 3 totais agregados interessam pro DANFE, não a árvore inteira.
        ibs_cbs_totais = {
            "base": _t(ibs_cbs_tot, "n:vBCIBSCBS"),
            "valor_ibs": _t(ibs_cbs_tot, "n:gIBS/n:vIBS"),
            "valor_cbs": _t(ibs_cbs_tot, "n:gCBS/n:vCBS"),
        }

    itens = []
    for det in inf.findall("n:det", ns):
        prod = det.find("n:prod", ns)
        if prod is None:
            continue
        itens.append({
            "codigo": _t(prod, "n:cProd"), "descricao": _t(prod, "n:xProd"),
            "ncm": _t(prod, "n:NCM"), "cfop": _t(prod, "n:CFOP"), "unidade": _t(prod, "n:uCom"),
            "qtd": float(_t(prod, "n:qCom", "0") or 0), "valor_unitario": float(_t(prod, "n:vUnCom", "0") or 0),
            "valor_total": float(_t(prod, "n:vProd", "0") or 0),
        })

    # Transportador/Veículo/Volumes — achado 2026-08-22 (varredura de
    # simplificações pendentes): `_montar_xml_nfe` só ganhou esses blocos
    # nesta rodada (ver `_montar_transp_completo_nfe_xml`) — antes o XML
    # nunca carregava essa informação, então o DANFE nunca tinha o que
    # mostrar. `transportador`/`veiculo`/`volumes` ficam `None` (não um
    # dict com campos vazios) quando o bloco correspondente não existe no
    # XML — o chamador (DANFE) decide como mostrar "sem informação".
    transp = inf.find("n:transp", ns)
    mod_frete = _t(transp, "n:modFrete", "9") if transp is not None else "9"
    transporta_el = transp.find("n:transporta", ns) if transp is not None else None
    transportador = None
    if transporta_el is not None:
        transportador = {
            "cgc_cpf": _t(transporta_el, "n:CNPJ") or _t(transporta_el, "n:CPF"),
            "nome": _t(transporta_el, "n:xNome"), "ie": _t(transporta_el, "n:IE"),
            "uf": _t(transporta_el, "n:UF"),
        }
    veic_el = transp.find("n:veicTransp", ns) if transp is not None else None
    veiculo = {"placa": _t(veic_el, "n:placa"), "uf": _t(veic_el, "n:UF")} if veic_el is not None else None
    vol_el = transp.find("n:vol", ns) if transp is not None else None
    volumes = None
    if vol_el is not None:
        volumes = {
            "qtd": _t(vol_el, "n:qVol"), "especie": _t(vol_el, "n:esp"), "marca": _t(vol_el, "n:marca"),
            "numero": _t(vol_el, "n:nVol"), "peso_liquido": _t(vol_el, "n:pesoL"), "peso_bruto": _t(vol_el, "n:pesoB"),
        }

    tp_emis = _t(ide, "n:tpEmis", "1")
    return {
        "chave_acesso": (inf.get("Id") or "")[3:],  # Id="NFe"+chave (44 dígitos)
        "tp_amb": _t(ide, "n:tpAmb"), "serie": _t(ide, "n:serie"), "numero": _t(ide, "n:nNF"),
        "dh_emi": _t(ide, "n:dhEmi"), "natureza_operacao": _t(ide, "n:natOp"),
        "tp_nf": _t(ide, "n:tpNF", "1"), "tp_emis": tp_emis,
        "dh_cont": _t(ide, "n:dhCont") or None, "x_just": _t(ide, "n:xJust") or None,
        "emit_cnpj": _t(emit, "n:CNPJ"), "emit_nome": _t(emit, "n:xNome"),
        "dest_doc": (_t(dest, "n:CNPJ") or _t(dest, "n:CPF")) if dest is not None else "",
        "dest_nome": _t(dest, "n:xNome") if dest is not None else "",
        "dest_ie": _t(dest, "n:IE") if dest is not None else "",
        "dest_endereco": _t(ender_dest, "n:xLgr") if ender_dest is not None else "",
        "dest_numero": _t(ender_dest, "n:nro") if ender_dest is not None else "",
        "dest_bairro": _t(ender_dest, "n:xBairro") if ender_dest is not None else "",
        "dest_cidade": _t(ender_dest, "n:xMun") if ender_dest is not None else "",
        "dest_uf": _t(ender_dest, "n:UF") if ender_dest is not None else "",
        "dest_cep": _t(ender_dest, "n:CEP") if ender_dest is not None else "",
        "itens": itens,
        "valor_total": float(_t(total, "n:vNF", "0") or 0),
        "ibs_cbs_totais": ibs_cbs_totais,
        "mod_frete": mod_frete, "transportador": transportador, "veiculo": veiculo, "volumes": volumes,
    }


def _montar_envelope_autorizacao(xml_nfce_assinado: bytes, tp_amb: str) -> bytes:
    corpo = xml_nfce_assinado.decode("utf-8")
    # `\s*` — achado ao vivo 2026-08-23, ver docstring de
    # `nfe_fiscal_common.montar_envelope_soap` pro racional completo
    # (lxml deixa `\n` residual depois da declaração XML).
    corpo = re.sub(r"^<\?xml[^>]*\?>\s*", "", corpo)
    envi_nfe = (
        f'<enviNFe xmlns="{_NFE_NS}" versao="4.00">'
        f'<idLote>1</idLote><indSinc>1</indSinc>{corpo}</enviNFe>'
    )
    return nfe_fiscal_common.montar_envelope_soap(envi_nfe.encode("utf-8"), "NFeAutorizacao4")


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def emitir_nfce_sync(
    cur, *, comanda: int, cnpj_emit: str, nome_emit: str, uf_sigla: str, uf_controle_sigla: str,
    proximo_numero: int, serie: str, cliente: Optional[dict], itens_resolvidos: list[dict],
    forma_pagamento: str, valor_total: float, tp_amb: str, csc_id: str, csc: str,
    ibs_cbs_totais_xml: str = "", contingencia: Optional[dict] = None,
    frete_valor: float = 0, transportador: Optional[dict] = None,
    servidor: str = "", banco: str = "",
) -> dict:
    """Orquestra a emissão de uma NFC-e a partir de uma comanda já faturada
    — assina, transmite ao SEFAZ (grupo SVRS) e devolve o resultado. `cur`
    é o cursor já aberto (mesma transação de quem chama, pra ler o
    certificado). `itens_resolvidos` já deve trazer a tributação resolvida
    (`_resolver_tributacao_sync`) — este orquestrador não resolve tributos
    sozinho, só monta/assina/transmite. `itens_resolvidos[i].get("ibs_cbs_xml")`
    e `ibs_cbs_totais_xml` — fragmentos já calculados por
    `ibs_cbs_service` (ver `_montar_xml_nfce`), repassados tal qual.

    `contingencia` — a linha devolvida por `contingencia_nfce_service.
    contingencia_aberta_sync` (ou `None` se não há contingência aberta).
    Quando presente, réplica de `GeraNFe` em contingência (achado
    2026-08-19, Gestor NFCe — `NFe.vb:2570`/`2586-2594`): grava `tpEmis`/
    `<dhCont>`/`<xJust>` mas **pula a transmissão ao SEFAZ por completo**
    — devolve a nota assinada com `situacao="G"` (aguardando), sem
    protocolo/cStat. O endpoint SVRS nem precisa existir/estar disponível
    nesse caso (nunca é chamado)."""
    if not itens_resolvidos:
        return {"success": False, "message": "Comanda sem itens de produto — nada a emitir."}

    cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get((uf_sigla or "").strip().upper())
    if not cod_ibge:
        return {"success": False, "message": f"UF '{uf_sigla}' não reconhecida."}

    em_contingencia = contingencia is not None
    url = None
    if not em_contingencia:
        url = _resolver_url_autorizacao(cod_ibge, "65", tp_amb)
        if not url:
            return {
                "success": False,
                "message": (
                    f"Emissão automática de NFC-e ainda não está disponível pra UF '{uf_sigla}' — "
                    "emita pelo sistema legado (VB6) por enquanto."
                ),
            }

    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert

    try:
        tp_emis = str(contingencia["tipo_contingencia"]) if em_contingencia else "1"
        dh_cont = None
        x_just = None
        if em_contingencia:
            hora_partes = [int(p) for p in str(contingencia["hora_inicio"]).split(":")]
            while len(hora_partes) < 3:
                hora_partes.append(0)
            inicio_dt = datetime.combine(contingencia["data_inicio"], time(*hora_partes[:3]))
            dh_cont = inicio_dt.astimezone().isoformat(timespec="seconds")
            x_just = contingencia["motivo"]

        chave_acesso = montar_chave_acesso(
            uf_ibge=cod_ibge, data_emissao=date.today(), cnpj=cnpj_emit, modelo="65",
            serie=serie, numero=proximo_numero, tp_emis=tp_emis, codigo_numerico=str(comanda),
        )
        dh_emi_dt = datetime.now(timezone.utc)
        emitente_end = nfe_fiscal_common.resolver_endereco_emitente_sync(cur)
        xml_nfce, id_nfe = _montar_xml_nfce(
            chave_acesso=chave_acesso, cod_ibge=cod_ibge, cnpj_emit=cnpj_emit, nome_emit=nome_emit,
            emitente_end=emitente_end,
            cliente=cliente, itens=itens_resolvidos, forma_pagamento=forma_pagamento,
            valor_total=valor_total, tp_amb=tp_amb, numero=proximo_numero, serie=serie,
            data_emissao=dh_emi_dt, url_qrcode="",  # nunca lido dentro de _montar_xml_nfce, ver achado abaixo
            ibs_cbs_totais_xml=ibs_cbs_totais_xml, tp_emis=tp_emis, dh_cont=dh_cont, x_just=x_just,
            frete_valor=frete_valor, transportador=transportador,
        )
        # sha1=True — achado ao vivo 2026-08-23 (1ª emissão real de NFC-e):
        # SEFAZ recusou com "Falha no Schema XML... Atributo: Algorithm" —
        # mesmo achado já confirmado no MDF-e, o XSD compartilhado
        # (`xmldsig-core-schema_v1.01.xsd`, usado por NFe/NFCe/MDFe) ainda
        # fixa SHA-1, apesar da suposição de "SHA-256 aceito" documentada
        # na docstring do módulo nunca ter sido validada ao vivo até hoje.
        xml_assinado = nfe_fiscal_common.assinar_xml(xml_nfce, id_nfe, key_pem, cert_pem, sha1=True)
        # QR Code montado SÓ DEPOIS de assinar (achado ao vivo 2026-08-26,
        # 1º teste ponta a ponta de Contingência NFC-e): em contingência
        # (`tp_emis="9"`) o QR Code OFFLINE exige o DigestValue da própria
        # assinatura (ver docstring de `montar_url_qrcode`) — não dá pra
        # calcular antes. `_montar_xml_nfce`'s parâmetro `url_qrcode` nunca
        # é lido dentro da função (conferido — só existe pra manter a
        # assinatura simétrica com `_montar_xml_nfe`), por isso passar ""
        # ali em cima não quebra nada.
        digest_value_b64 = nfe_fiscal_common.extrair_tag(xml_assinado.decode("utf-8"), "ds:DigestValue")
        url_qrcode = montar_url_qrcode(
            chave_acesso=chave_acesso, tp_amb=tp_amb, csc_id=csc_id, csc=csc, uf_sigla=uf_sigla,
            tp_emis=tp_emis, dh_emi=dh_emi_dt, valor_total=valor_total, digest_value_b64=digest_value_b64,
        )
        # `<infNFeSupl>` — irmão de `<infNFe>`, inserido DEPOIS de assinar
        # (a assinatura enveloped só cobre `infNFe`, inserir um irmão não
        # invalida nada) — mesmo padrão já usado pro `<infMDFeSupl>` do
        # MDF-e. Achado ao vivo 2026-08-23: colocar isso dentro do XML
        # ANTES de assinar (como a 1ª versão fazia) deixa `infNFeSupl`
        # como FILHO de `infNFe`, estrutura inválida pro schema.
        inf_nfe_supl = (
            f'<infNFeSupl><qrCode><![CDATA[{url_qrcode}]]></qrCode>'
            f'<urlChave>{nfe_fiscal_common.escapar_xml(montar_url_chave_consulta())}</urlChave></infNFeSupl>'
        )
        xml_assinado = xml_assinado.replace(b"</infNFe>", f"</infNFe>{inf_nfe_supl}".encode("utf-8"), 1)

        if em_contingencia:
            return {
                "success": True,
                "message": (
                    "NFC-e emitida em contingência — ficará aguardando até a contingência ser "
                    "encerrada e \"Validar Contingência\" ser usado no Gestor NFCe pra transmitir ao SEFAZ."
                ),
                "chave_acesso": chave_acesso, "protocolo_sefaz": None, "dh_recbto": None,
                "xml": xml_assinado.decode("utf-8"), "numero": proximo_numero, "serie": serie,
                "url_qrcode": url_qrcode, "situacao": "G", "cstat": None,
            }

        envelope = _montar_envelope_autorizacao(xml_assinado, tp_amb)
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    # Achado ao vivo 2026-08-23 (1ª emissão real de NFC-e): a resposta do
    # `NFeAutorizacao4` síncrono (`indSinc=1`) vem envelopada em
    # `retEnviNFe><cStat>104 Lote processado</cStat>...<protNFe><infProt>
    # <cStat>100 Autorizado</cStat>...` — dois `cStat` na mesma resposta,
    # em NÍVEIS diferentes. `extrair_tag` pega o PRIMEIRO da string
    # inteira (o do lote, 104) — nunca o do documento em si. Preciso
    # extrair de DENTRO de `infProt` especificamente.
    inf_prot = nfe_fiscal_common.extrair_bloco(resposta, "infProt") or resposta
    c_stat = nfe_fiscal_common.extrair_tag(inf_prot, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(inf_prot, "xMotivo")
    n_prot = nfe_fiscal_common.extrair_tag(inf_prot, "nProt")
    dh_recbto = nfe_fiscal_common.extrair_tag(inf_prot, "dhRecbto")
    # 100 = "Autorizado o uso da NF-e" (sucesso).
    if c_stat != "100":
        resultado_rejeicao = {
            "success": False,
            "message": f"SEFAZ recusou a emissão (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
            "cstat": c_stat,
        }
        # Apoio Fiscal BackOn (2026-08-28) — tradução pro lojista + aviso
        # automático de suporte (e-mail sempre, WhatsApp se configurado).
        # `servidor`/`banco` opcionais (default "") pra não quebrar
        # chamadas antigas em teste que não passam esse par — só notifica
        # quando os dois vêm preenchidos (produção sempre passa).
        if servidor and banco:
            resultado_rejeicao["apoio_fiscal"] = apoio_fiscal_service.notificar_rejeicao_sync(
                servidor, banco, tipo_documento="NFC-e", codigo_rejeicao=c_stat or "?",
                mensagem_original=x_motivo or "", referencia=chave_acesso,
            )
        return resultado_rejeicao
    return {
        "success": True,
        "message": f"NFC-e autorizada pelo SEFAZ — protocolo {n_prot or '?'}.",
        "chave_acesso": chave_acesso,
        "protocolo_sefaz": n_prot,
        "dh_recbto": dh_recbto,
        "xml": xml_assinado.decode("utf-8"),
        "numero": proximo_numero,
        "serie": serie,
        "url_qrcode": url_qrcode,
        "situacao": "A",
        "cstat": c_stat,
    }


def emitir_nfe_sync(
    cur, *, cnpj_emit: str, nome_emit: str, uf_sigla: str, proximo_numero: int, serie: str,
    destinatario: dict, itens_resolvidos: list[dict], valor_total: float, tp_amb: str,
    natureza_operacao: str, indFinal: str = "1", ibs_cbs_totais_xml: str = "", contingencia: Optional[dict] = None,
    paga_frete: Optional[int] = None,
    transportador: Optional[dict] = None, veiculo: Optional[dict] = None, volumes: Optional[dict] = None,
    servidor: str = "", banco: str = "",
) -> dict:
    """Orquestra a emissão de uma NF-e modelo 55 — mesmo padrão de
    `emitir_nfce_sync`, mas sem CSC/QR Code (exclusividade de NFC-e) e com
    destinatário sempre estruturado (`_montar_xml_nfe`). `cur` é o cursor já
    aberto (mesma transação de quem chama, pra ler o certificado).
    `itens_resolvidos`/`ibs_cbs_totais_xml` já vêm calculados por quem
    chama (tributação + IBS/CBS) — este orquestrador só monta/assina/
    transmite, mesma separação de responsabilidade do resto do pacote.

    `contingencia` — mesmo mecanismo de `emitir_nfce_sync` (ver docstring
    lá): quando presente, grava `tpEmis`/`<dhCont>`/`<xJust>` mas pula a
    transmissão ao SEFAZ, devolvendo a nota assinada com `situacao="G"`."""
    if not itens_resolvidos:
        return {"success": False, "message": "Nenhum item pra emitir — comanda(s) sem itens de produto."}

    cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get((uf_sigla or "").strip().upper())
    if not cod_ibge:
        return {"success": False, "message": f"UF '{uf_sigla}' não reconhecida."}

    # Regras fiscais de consistência (DIFAL/ICMSUFDest + CSOSN incompatível
    # etc.) — checadas ANTES de montar/assinar/transmitir, pra não gastar a
    # chamada ao SEFAZ com um erro já detectável aqui. Ver nfe_regras_
    # fiscais.py pro rastreio completo e como registrar uma regra nova.
    uf_dest_check = (destinatario.get("uf") or "").strip().upper()
    id_dest_check = "1" if uf_dest_check == (uf_sigla or "").strip().upper() else "2"
    contexto_regras = nfe_regras_fiscais.montar_contexto_validacao(
        id_dest_check, indFinal, destinatario.get("indIEDest") or "9", itens_resolvidos,
    )
    erro_regras = nfe_regras_fiscais.validar_regras_fiscais(contexto_regras)
    if erro_regras:
        return erro_regras

    em_contingencia = contingencia is not None
    url = None
    if not em_contingencia:
        url = _resolver_url_autorizacao(cod_ibge, "55", tp_amb)
        if not url:
            return {
                "success": False,
                "message": (
                    f"Emissão automática de NF-e ainda não está disponível pra UF '{uf_sigla}' — "
                    "emita pelo sistema legado (VB6) por enquanto."
                ),
            }

    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert

    try:
        tp_emis = str(contingencia["tipo_contingencia"]) if em_contingencia else "1"
        dh_cont = None
        x_just = None
        if em_contingencia:
            hora_partes = [int(p) for p in str(contingencia["hora_inicio"]).split(":")]
            while len(hora_partes) < 3:
                hora_partes.append(0)
            inicio_dt = datetime.combine(contingencia["data_inicio"], time(*hora_partes[:3]))
            dh_cont = inicio_dt.astimezone().isoformat(timespec="seconds")
            x_just = contingencia["motivo"]

        chave_acesso = montar_chave_acesso(
            uf_ibge=cod_ibge, data_emissao=date.today(), cnpj=cnpj_emit, modelo="55",
            serie=serie, numero=proximo_numero, tp_emis=tp_emis, codigo_numerico=str(proximo_numero),
        )
        xml_nfe, id_nfe = _montar_xml_nfe(
            chave_acesso=chave_acesso, cod_ibge=cod_ibge, cnpj_emit=cnpj_emit, nome_emit=nome_emit,
            uf_emit_sigla=uf_sigla, destinatario=destinatario, itens=itens_resolvidos,
            valor_total=valor_total, tp_amb=tp_amb, numero=proximo_numero, serie=serie,
            data_emissao=datetime.now(timezone.utc), natureza_operacao=natureza_operacao,
            indFinal=indFinal, ibs_cbs_totais_xml=ibs_cbs_totais_xml, tp_emis=tp_emis, dh_cont=dh_cont, x_just=x_just,
            paga_frete=paga_frete, transportador=transportador, veiculo=veiculo, volumes=volumes,
            emitente_end=nfe_fiscal_common.resolver_endereco_emitente_sync(cur),
        )
        xml_assinado = nfe_fiscal_common.assinar_xml(xml_nfe, id_nfe, key_pem, cert_pem, sha1=True)

        if em_contingencia:
            return {
                "success": True,
                "message": (
                    "NF-e emitida em contingência — ficará aguardando até a contingência ser "
                    "encerrada e ser retransmitida pra o SEFAZ."
                ),
                "chave_acesso": chave_acesso, "protocolo_sefaz": None, "dh_recbto": None,
                "xml": xml_assinado.decode("utf-8"), "numero": proximo_numero, "serie": serie,
                "situacao": "G", "cstat": None,
            }

        envelope = _montar_envelope_autorizacao(xml_assinado, tp_amb)
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    # Mesmo achado do NFC-e (2026-08-23) — extrair de dentro de `infProt`,
    # não o primeiro `cStat` da resposta inteira (que é o do lote).
    inf_prot = nfe_fiscal_common.extrair_bloco(resposta, "infProt") or resposta
    c_stat = nfe_fiscal_common.extrair_tag(inf_prot, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(inf_prot, "xMotivo")
    n_prot = nfe_fiscal_common.extrair_tag(inf_prot, "nProt")
    dh_recbto = nfe_fiscal_common.extrair_tag(inf_prot, "dhRecbto")
    if c_stat != "100":
        resultado_rejeicao = {
            "success": False,
            "message": f"SEFAZ recusou a emissão (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
            "cstat": c_stat,
        }
        if servidor and banco:
            resultado_rejeicao["apoio_fiscal"] = apoio_fiscal_service.notificar_rejeicao_sync(
                servidor, banco, tipo_documento="NF-e", codigo_rejeicao=c_stat or "?",
                mensagem_original=x_motivo or "", referencia=chave_acesso,
            )
        return resultado_rejeicao
    return {
        "success": True,
        "message": f"NF-e autorizada pelo SEFAZ — protocolo {n_prot or '?'}.",
        "chave_acesso": chave_acesso,
        "protocolo_sefaz": n_prot,
        "dh_recbto": dh_recbto,
        "xml": xml_assinado.decode("utf-8"),
        "numero": proximo_numero,
        "serie": serie,
        "situacao": "A",
        "cstat": c_stat,
    }
