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
"""
import re
from datetime import date, datetime, timezone
from typing import Optional

from services import nfe_fiscal_common

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


def montar_chave_acesso(
    *, uf_ibge: str, data_emissao: date, cnpj: str, modelo: str, serie: str, numero: int,
    tp_emis: str, codigo_numerico: str,
) -> str:
    """Monta a chave de acesso de 44 dígitos (cUF+AAMM+CNPJ+mod+serie+
    nNF+tpEmis+cNF+cDV) — algoritmo público, mesmo pra NFe quanto NFCe."""
    aamm = data_emissao.strftime("%y%m")
    cnpj_num = re.sub(r"\D", "", cnpj).zfill(14)
    serie_num = str(int(serie or 0)).zfill(3)
    numero_num = str(int(numero)).zfill(9)
    cnf = str(int(codigo_numerico) % 100000000).zfill(8)
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
) -> str:
    import hashlib

    base = homologacao_url or "https://www.sefazvirtual.fazenda.gov.br/NFCE/qrcode"
    params = f"chNFe={chave_acesso}&nVersao=200&tpAmb={tp_amb}&cDest=&dhEmi=&vNF=&vICMS=&digVal=&cIdToken={csc_id}"
    hash_qr = hashlib.sha1((params + csc).encode("utf-8")).hexdigest()
    return f"{base}?{params}&cHashQRCode={hash_qr}"


# ---------------------------------------------------------------------------
# XML da NFCe — layout NFe 4.00 (validar contra o XSD oficial antes de
# transmitir de verdade — ver docstring do módulo).
# ---------------------------------------------------------------------------

def _montar_xml_nfce(
    *, chave_acesso: str, cod_ibge: str, cnpj_emit: str, nome_emit: str, cliente: Optional[dict],
    itens: list[dict], forma_pagamento: str, valor_total: float, tp_amb: str, numero: int, serie: str,
    data_emissao: datetime, url_qrcode: str,
) -> tuple[bytes, str]:
    """Monta `<NFe><infNFe Id="NFe...">` conforme layout NFCe 4.00. `itens`
    é uma lista de dicts já com tributação resolvida
    (`_resolver_tributacao_sync`) e valores calculados por item."""
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
        f'<natOp>Venda</natOp>'
        f'<mod>65</mod>'
        f'<serie>{serie}</serie>'
        f'<nNF>{numero}</nNF>'
        f'<dhEmi>{dh_emi}</dhEmi>'
        f'<tpNF>1</tpNF>'
        f'<idDest>1</idDest>'
        f'<cMunFG>{cod_ibge}00000</cMunFG>'
        f'<tpImp>4</tpImp>'
        f'<tpEmis>1</tpEmis>'
        f'<cDV>{chave_acesso[-1]}</cDV>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<finNFe>1</finNFe>'
        f'<indFinal>1</indFinal>'
        f'<indPres>1</indPres>'
        f'<procEmi>0</procEmi>'
        f'<verProc>1.0</verProc>'
        f'</ide>'
        f'<emit>'
        f'<CNPJ>{re.sub(r"[^0-9]", "", cnpj_emit)}</CNPJ>'
        f'<xNome>{nfe_fiscal_common.escapar_xml(nome_emit)}</xNome>'
        f'<CRT>1</CRT>'
        f'</emit>'
        f'{dest_xml}'
        f'{det_xml}'
        f'<total><ICMSTot><vNF>{valor_total:.2f}</vNF></ICMSTot></total>'
        f'<transp><modFrete>9</modFrete></transp>'
        f'<pag><detPag><tPag>{forma_pagamento}</tPag><vPag>{valor_total:.2f}</vPag></detPag></pag>'
        f'<infNFeSupl><qrCode>{nfe_fiscal_common.escapar_xml(url_qrcode)}</qrCode></infNFeSupl>'
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
    qrcode = _t(inf, "n:infNFeSupl/n:qrCode")

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


def _montar_envelope_autorizacao(xml_nfce_assinado: bytes, tp_amb: str) -> bytes:
    corpo = xml_nfce_assinado.decode("utf-8")
    corpo = re.sub(r"^<\?xml[^>]*\?>", "", corpo)
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
) -> dict:
    """Orquestra a emissão de uma NFC-e a partir de uma comanda já faturada
    — assina, transmite ao SEFAZ (grupo SVRS) e devolve o resultado. `cur`
    é o cursor já aberto (mesma transação de quem chama, pra ler o
    certificado). `itens_resolvidos` já deve trazer a tributação resolvida
    (`_resolver_tributacao_sync`) — este orquestrador não resolve tributos
    sozinho, só monta/assina/transmite."""
    if not itens_resolvidos:
        return {"success": False, "message": "Comanda sem itens de produto — nada a emitir."}

    cod_ibge = nfe_fiscal_common.IBGE_POR_UF.get((uf_sigla or "").strip().upper())
    if not cod_ibge:
        return {"success": False, "message": f"UF '{uf_sigla}' não reconhecida."}
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
        chave_acesso = montar_chave_acesso(
            uf_ibge=cod_ibge, data_emissao=date.today(), cnpj=cnpj_emit, modelo="65",
            serie=serie, numero=proximo_numero, tp_emis="1", codigo_numerico=str(comanda),
        )
        url_qrcode = montar_url_qrcode(
            chave_acesso=chave_acesso, tp_amb=tp_amb, csc_id=csc_id, csc=csc, uf_sigla=uf_sigla,
        )
        xml_nfce, id_nfe = _montar_xml_nfce(
            chave_acesso=chave_acesso, cod_ibge=cod_ibge, cnpj_emit=cnpj_emit, nome_emit=nome_emit,
            cliente=cliente, itens=itens_resolvidos, forma_pagamento=forma_pagamento,
            valor_total=valor_total, tp_amb=tp_amb, numero=proximo_numero, serie=serie,
            data_emissao=datetime.now(timezone.utc), url_qrcode=url_qrcode,
        )
        xml_assinado = nfe_fiscal_common.assinar_xml(xml_nfce, id_nfe, key_pem, cert_pem)
        envelope = _montar_envelope_autorizacao(xml_assinado, tp_amb)
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(resposta, "xMotivo")
    n_prot = nfe_fiscal_common.extrair_tag(resposta, "nProt")
    dh_recbto = nfe_fiscal_common.extrair_tag(resposta, "dhRecbto")
    # 100 = "Autorizado o uso da NF-e" (sucesso).
    if c_stat != "100":
        return {
            "success": False,
            "message": f"SEFAZ recusou a emissão (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
        }
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
    }
