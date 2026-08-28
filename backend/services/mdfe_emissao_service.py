"""MDF-e — Fase B: emissão real ao SEFAZ (`GeraMDFe`), Encerramento
(evento 110112), Cancelamento (evento 110111), Consulta de Situação
(`MDFeConsulta`, por chave de acesso) e Gerar XML (`MontaXMLMDFe`, só
reexportação, sem transmitir de novo). Complementa `mdfe_service.py`
(Fase A — cadastro/anexar notas, sem SEFAZ).

Fonte: `Backon.Controllers/NFe.vb:4952-6216` (lida linha a linha nesta
rodada, não resumida por agente) + `Kontacto\\FrmTraMDF.frm` (trechos que
faltavam da Fase A: `Command7_Click` — botão "Gerar MDFe" — e os
handlers de Encerrar/Cancelar, linhas ~1500-1690/2205-2299). Ver
PENDENCIAS.md > "MDF-e (Fase B)" pro rastreio completo.

**Nunca testado contra o SEFAZ real** — não existe certificado de
homologação neste projeto (mesmo aviso já registrado em
`nfe_cancelamento_service.py`/`nfe_emissao_service.py`). **Nunca chamar
`emitir_mdfe_sync` (ou qualquer função deste módulo que transmita)
contra uma conexão real sem confirmação explícita do usuário antes** —
documento fiscal com efeito legal genuíno, mesma regra já aplicada a
`emitir_nfe_sync`/`emitir_nfce_sync`/`cancelar_nfe_sync`.

Diferenças deliberadas em relação à fonte VB6 (modernização técnica ou
correção de bug, nunca mudança de regra fiscal — ver CLAUDE.md §12):
  - **`<tpTransp>` sempre emitida quando preenchida.** No legado,
    `Command7_Click` sempre chama `GeraMDFe` com `TpTransp="2"`
    hardcoded, e `MontaXMLMDFe`/`GeraMDFe` só escrevem a tag quando o
    valor é DIFERENTE de `"2"` — ou seja, a tag nunca sai no XML de
    produção hoje, com ou sem o combo da tela. Isso é um bug de
    comparação de string do chamador, não uma regra fiscal — aqui a tag
    é emitida sempre que `mdfe.tptransp` está preenchido.
  - **Limite "só 1 UF além da UF da empresa" (`Command7_Click`,
    hardcoded `"RJ"`) NÃO foi portado** — é um workaround específico
    desta instalação (RJ), de uma versão antiga do MDF-e que tinha essa
    limitação real; o layout 3.00 (o mesmo declarado por este código) já
    não tem esse limite no MOC oficial. Decisão consciente, registrada
    aqui (não omissão silenciosa).
  - Assinatura RSA-SHA256 (não SHA1) — mesma justificativa já registrada
    em `nfe_cancelamento_service.py`.
  - Autorização e resgate-por-`nRec` (`ConsultaSituacaoMDFe`, caminho de
    "204 - lote em processamento") não foram portados — o "Consultar
    Situação" por chave de acesso (`MDFeConsulta`) já cobre o caso de
    uso prático de recuperação de uma transmissão que ficou pendente.
"""
import asyncio
from datetime import date, datetime
from typing import Optional

from db.connection import _open_conn
from services import apoio_fiscal_service, mdfe_service, nfe_emissao_service, nfe_fiscal_common


class MdfeSituacaoInvalida(Exception):
    """Ação chamada com o manifesto numa situação que não permite."""


def _carregar_certificado_sync(cur) -> Optional[tuple[bytes, bytes]]:
    return nfe_fiscal_common.carregar_certificado_sync(cur)


def _escapar(texto: str) -> str:
    return nfe_fiscal_common.escapar_xml(texto)


# ---------------------------------------------------------------------------
# Builder único do XML do MDF-e — réplica de `MontaXMLMDFe`/corpo de
# `GeraMDFe` (que no legado são quase idênticos, um duplicado do outro) —
# usado tanto na emissão real (`emitir_mdfe_sync`) quanto em "Gerar XML"
# (`gerar_xml_mdfe_sync`, que só reconstrói pra reexportação).
# ---------------------------------------------------------------------------
def _montar_xml_mdfe_sync(cur, cod_mdfe: int) -> bytes:
    cur.execute(
        """
        SELECT m.*, v.placa, v.doc_proprietario, v.rntrc_proprietario, v.nome_proprietario,
               v.ie_proprietario, v.uf_proprietario, v.tpRod, v.tpCar, v.UF AS uf_veiculo
        FROM MDFe m JOIN veiculos_transp v ON v.codigo = m.veiculo
        WHERE m.codigo = %s
        """,
        (cod_mdfe,),
    )
    m = cur.fetchone()
    if not m:
        raise MdfeSituacaoInvalida("MDF-e não encontrado.")

    reboque = None
    if m.get("reboque"):
        cur.execute(
            "SELECT placa, doc_proprietario, rntrc_proprietario, nome_proprietario, "
            "ie_proprietario, uf_proprietario, tpCar, UF AS uf_veiculo, peso_max "
            "FROM veiculos_transp WHERE codigo=%s",
            (m["reboque"],),
        )
        reboque = cur.fetchone()

    cur.execute("SELECT nome, cpf_PROF AS cpf FROM funcionarios WHERE codigo_int=%s", (m["motorista"],))
    motorista = cur.fetchone() or {}
    ajudante = None
    if m.get("ajudante"):
        cur.execute("SELECT nome, cpf_PROF AS cpf FROM funcionarios WHERE codigo_int=%s", (m["ajudante"],))
        ajudante = cur.fetchone()

    cur.execute(
        "SELECT cgc, rz_social, fantasia, inscr_est, endereco, numero, complemento, "
        "bairro, cep, uf, telefone FROM controle"
    )
    controle = cur.fetchone() or {}
    origem = mdfe_service._resolver_origem_empresa_sync(cur)

    cur.execute(
        """
        SELECT DISTINCT mn.origem, mu.descricao
        FROM mdfe_notas mn JOIN municipio mu ON mu.codigo = mn.origem
        WHERE mn.cod_mdfe = %s
        """,
        (cod_mdfe,),
    )
    municipios_carga = cur.fetchall()

    cur.execute(
        """
        SELECT nf.chave_acesso, nf.valor_total, nf.peso_bruto, mn.destino, mu.descricao
        FROM mdfe_notas mn
        JOIN n_fiscal nf ON nf.codigo = mn.nota
        JOIN municipio mu ON mu.codigo = mn.destino
        WHERE mn.cod_mdfe = %s
        ORDER BY mu.descricao
        """,
        (cod_mdfe,),
    )
    notas = cur.fetchall()

    xml = ['<MDFe xmlns="', nfe_fiscal_common.MDFE_NS, '">']
    xml.append(f'<infMDFe versao="3.00" Id="MDFe{m["chave_acesso"]}">')

    xml.append("<ide>")
    xml.append(f'<cUF>{origem.get("cod_municipio") and str(origem["cod_municipio"])[:2] or ""}</cUF>')
    xml.append(f'<tpAmb>{m["tp_amb"]}</tpAmb>')
    xml.append("<tpEmit>2</tpEmit>")
    if m.get("tptransp"):
        xml.append(f'<tpTransp>{m["tptransp"]}</tpTransp>')
    xml.append("<mod>58</mod>")
    xml.append(f'<serie>{m["serie_mdfe"]}</serie>')
    xml.append(f'<nMDF>{m["num_mdfe"]}</nMDF>')
    xml.append(f'<cMDF>{m["chave_acesso"][35:43]}</cMDF>')
    xml.append(f'<cDV>{m["chave_acesso"][43]}</cDV>')
    xml.append("<modal>1</modal>")
    dhemi_val = m["dhemi"]
    dhemi_txt = dhemi_val.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(dhemi_val, "strftime") else str(dhemi_val)
    xml.append(f'<dhEmi>{dhemi_txt}-03:00</dhEmi>')
    xml.append("<tpEmis>1</tpEmis>")
    xml.append("<procEmi>0</procEmi>")
    xml.append("<verProc>1.0</verProc>")
    xml.append(f'<UFIni>{m.get("ufini") or ""}</UFIni>')
    xml.append(f'<UFFim>{m.get("uffim") or ""}</UFFim>')
    for mc in municipios_carga:
        xml.append("<infMunCarrega>")
        xml.append(f'<cMunCarrega>{int(mc["origem"])}</cMunCarrega>')
        xml.append(f'<xMunCarrega>{_escapar(mc["descricao"])}</xMunCarrega>')
        xml.append("</infMunCarrega>")
    percurso = (m.get("percurso") or "").strip()
    for i in range(0, len(percurso), 2):
        uf_per = percurso[i:i + 2].strip()
        if uf_per:
            xml.append(f"<infPercurso><UFPer>{uf_per}</UFPer></infPercurso>")
    xml.append("</ide>")

    xml.append("<emit>")
    xml.append(f'<CNPJ>{(controle.get("cgc") or "").strip()}</CNPJ>')
    xml.append(f'<IE>{(controle.get("inscr_est") or "").strip()}</IE>')
    xml.append(f'<xNome>{_escapar((controle.get("rz_social") or "").strip())}</xNome>')
    if (controle.get("fantasia") or "").strip():
        xml.append(f'<xFant>{_escapar(controle["fantasia"].strip())}</xFant>')
    xml.append("<enderEmit>")
    xml.append(f'<xLgr>{_escapar((controle.get("endereco") or "").strip())}</xLgr>')
    xml.append(f'<nro>{_escapar(str(controle.get("numero") or "").strip())}</nro>')
    if (controle.get("complemento") or "").strip():
        xml.append(f'<xCpl>{_escapar(controle["complemento"].strip())}</xCpl>')
    xml.append(f'<xBairro>{_escapar((controle.get("bairro") or "").strip())}</xBairro>')
    xml.append(f'<cMun>{origem.get("cod_municipio") or ""}</cMun>')
    xml.append(f'<xMun>{_escapar(origem.get("cidade") or "")}</xMun>')
    if (controle.get("cep") or "").strip():
        xml.append(f'<CEP>{controle["cep"].strip()}</CEP>')
    xml.append(f'<UF>{(controle.get("uf") or "").strip()}</UF>')
    if (controle.get("telefone") or "").strip():
        xml.append(f'<fone>{controle["telefone"].strip()}</fone>')
    xml.append("</enderEmit>")
    xml.append("</emit>")

    xml.append('<infModal versaoModal="3.00">')
    xml.append("<rodo>")
    xml.append("<infANTT></infANTT>")
    xml.append("<veicTracao>")
    xml.append(f'<placa>{m["placa"]}</placa>')
    xml.append("<tara>0</tara>")
    doc_prop = (m.get("doc_proprietario") or "").strip()
    if doc_prop:
        xml.append("<prop>")
        if len(doc_prop) == 11:
            xml.append(f"<CPF>{doc_prop}</CPF>")
            tp_prop = "1"
        else:
            xml.append(f"<CNPJ>{doc_prop}</CNPJ>")
            tp_prop = "2"
        xml.append(f'<RNTRC>{(m.get("rntrc_proprietario") or "").strip() or "ISENTO"}</RNTRC>')
        xml.append(f'<xNome>{_escapar((m.get("nome_proprietario") or "").strip())}</xNome>')
        xml.append(f'<IE>{(m.get("ie_proprietario") or "").strip()}</IE>')
        xml.append(f'<UF>{(m.get("uf_proprietario") or "").strip()}</UF>')
        xml.append(f"<tpProp>{tp_prop}</tpProp>")
        xml.append("</prop>")
    if motorista:
        xml.append("<condutor>")
        xml.append(f'<xNome>{_escapar((motorista.get("nome") or "").strip())}</xNome>')
        xml.append(f'<CPF>{(motorista.get("cpf") or "").strip()}</CPF>')
        xml.append("</condutor>")
    if ajudante:
        xml.append("<condutor>")
        xml.append(f'<xNome>{_escapar((ajudante.get("nome") or "").strip())}</xNome>')
        xml.append(f'<CPF>{(ajudante.get("cpf") or "").strip()}</CPF>')
        xml.append("</condutor>")
    xml.append(f'<tpRod>{(m.get("tpRod") or "").strip()}</tpRod>')
    xml.append(f'<tpCar>{(m.get("tpCar") or "").strip()}</tpCar>')
    xml.append(f'<UF>{(m.get("uf_veiculo") or "").strip().upper()}</UF>')
    xml.append("</veicTracao>")
    if reboque:
        xml.append("<veicReboque>")
        xml.append(f'<placa>{reboque["placa"]}</placa>')
        xml.append("<tara>0</tara>")
        xml.append(f'<capKG>{reboque.get("peso_max") or 0}</capKG>')
        doc_prop_reb = (reboque.get("doc_proprietario") or "").strip()
        if doc_prop_reb:
            xml.append("<prop>")
            if len(doc_prop_reb) == 11:
                xml.append(f"<CPF>{doc_prop_reb}</CPF>")
                tp_prop_reb = "1"
            else:
                xml.append(f"<CNPJ>{doc_prop_reb}</CNPJ>")
                tp_prop_reb = "2"
            xml.append(f'<RNTRC>{(reboque.get("rntrc_proprietario") or "").strip() or "ISENTO"}</RNTRC>')
            xml.append(f'<xNome>{_escapar((reboque.get("nome_proprietario") or "").strip())}</xNome>')
            xml.append(f'<IE>{(reboque.get("ie_proprietario") or "").strip()}</IE>')
            xml.append(f'<UF>{(reboque.get("uf_proprietario") or "").strip()}</UF>')
            xml.append(f"<tpProp>{tp_prop_reb}</tpProp>")
            xml.append("</prop>")
        xml.append(f'<tpCar>{(reboque.get("tpCar") or "").strip()}</tpCar>')
        xml.append(f'<UF>{(reboque.get("uf_veiculo") or "").strip().upper()}</UF>')
        xml.append("</veicReboque>")
    xml.append("</rodo>")
    xml.append("</infModal>")

    qtd_notas = 0
    tot_valor = 0.0
    tot_peso = 0.0
    municipio_atual = None
    if notas:
        xml.append("<infDoc>")
        for n in notas:
            if municipio_atual != n["descricao"]:
                if municipio_atual is not None:
                    xml.append("</infMunDescarga>")
                xml.append("<infMunDescarga>")
                xml.append(f'<cMunDescarga>{int(n["destino"])}</cMunDescarga>')
                xml.append(f'<xMunDescarga>{_escapar(n["descricao"])}</xMunDescarga>')
                municipio_atual = n["descricao"]
            xml.append(f'<infNFe><chNFe>{n["chave_acesso"]}</chNFe></infNFe>')
            qtd_notas += 1
            tot_valor += float(n.get("valor_total") or 0)
            tot_peso += float(n.get("peso_bruto") or 0)
        xml.append("</infMunDescarga>")
        xml.append("</infDoc>")

    xml.append("<tot>")
    xml.append(f"<qNFe>{qtd_notas}</qNFe>")
    xml.append(f'<vCarga>{tot_valor:.2f}</vCarga>')
    xml.append("<cUnid>01</cUnid>")
    xml.append(f'<qCarga>{tot_peso:.4f}</qCarga>')
    xml.append("</tot>")

    if (m.get("obs") or "").strip():
        xml.append(f'<infAdic><infCpl>{_escapar(m["obs"].strip())}</infCpl></infAdic>')

    xml.append("</infMDFe>")
    xml.append("</MDFe>")
    return "".join(xml).encode("utf-8")


# ---------------------------------------------------------------------------
# Emissão real (GeraMDFe)
# ---------------------------------------------------------------------------
def emitir_mdfe_sync(cur, cod_mdfe: int, usuario: Optional[str], *, servidor: str = "", banco: str = "") -> dict:
    cur.execute("SELECT * FROM MDFe WHERE codigo=%s", (cod_mdfe,))
    m = cur.fetchone()
    if not m:
        return {"success": False, "message": "MDF-e não encontrado."}
    if m.get("situacao") not in ("A", "N"):
        return {"success": False, "message": "Só é possível emitir manifestos em edição ou não transmitidos."}
    cur.execute("SELECT COUNT(*) AS qtd FROM mdfe_notas WHERE cod_mdfe=%s", (cod_mdfe,))
    if (cur.fetchone() or {}).get("qtd", 0) == 0:
        return {"success": False, "message": "Anexe pelo menos uma Nota Fiscal antes de emitir o MDF-e."}
    if not m.get("veiculo") or not m.get("motorista"):
        return {"success": False, "message": "Veículo e Motorista são obrigatórios pra emitir."}

    cert = _carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert

    tp_amb = nfe_fiscal_common.resolver_tp_amb_sync(cur)
    url = nfe_fiscal_common.resolver_endpoint_mdfe("autorizacao", tp_amb)
    if not url:
        return {"success": False, "message": "Webservice de autorização do MDF-e não configurado pra este ambiente."}

    cur.execute("SELECT cgc, uf FROM controle")
    controle = cur.fetchone() or {}
    cnpj = (controle.get("cgc") or "").strip()
    origem = mdfe_service._resolver_origem_empresa_sync(cur)
    cod_ibge = str(origem.get("cod_municipio") or "")[:2]
    if not cod_ibge:
        return {"success": False, "message": "Não foi possível resolver o município/UF da própria empresa — confira o cadastro em Controle do Sistema."}

    cur.execute("SELECT numero_MDFE, serie_MDFE FROM controle_aux")
    aux = cur.fetchone() or {}
    proximo_numero = int(aux.get("numero_MDFE") or 0) + 1
    serie = str(aux.get("serie_MDFE") or "1").strip() or "1"

    # `dhemi` é gravado como `datetime` puro (coluna DATETIME, sem
    # timezone) — o offset (-03:00) só entra na hora de montar a tag
    # <dhEmi> do XML (`_montar_xml_mdfe_sync`), nunca no valor gravado.
    dh_emi = datetime.now()
    chave_acesso = nfe_emissao_service.montar_chave_acesso(
        uf_ibge=cod_ibge, data_emissao=date.today(), cnpj=cnpj, modelo="58",
        serie=serie, numero=proximo_numero, tp_emis="1", codigo_numerico=str(proximo_numero),
    )

    # Grava número/série/chave/dhEmi/ambiente ANTES de montar o XML — o
    # builder único (`_montar_xml_mdfe_sync`) lê tudo isso da própria
    # linha da `MDFe`, mesma fonte usada depois por "Gerar XML".
    cur.execute(
        "UPDATE MDFe SET num_mdfe=%s, serie_mdfe=%s, chave_acesso=%s, dhemi=%s, tp_amb=%s WHERE codigo=%s",
        (proximo_numero, serie, chave_acesso, dh_emi, tp_amb, cod_mdfe),
    )

    url_qrcode = f"https://dfe-portal.svrs.rs.gov.br/mdfe/QRCode?chMDFe={chave_acesso}&tpAmb={tp_amb}"

    try:
        xml_mdfe = _montar_xml_mdfe_sync(cur, cod_mdfe)
        # sha1=True: XSD do MDF-e ainda fixa SignatureMethod/DigestMethod em
        # SHA-1 — achado ao vivo, ver docstring de `assinar_xml`.
        xml_assinado = nfe_fiscal_common.assinar_xml(xml_mdfe, f"MDFe{chave_acesso}", key_pem, cert_pem, sha1=True)
        # `<infMDFeSupl>` (QR Code) precisa ir DEPOIS de `</infMDFe>` e ANTES
        # de `<Signature>` — mesmo lugar que `GeraMDFe` insere na fonte VB6
        # (`VarXMLQrCode`, splice de string, não regra de assinatura: a
        # assinatura cobre só a subárvore `infMDFe` via `Reference URI`,
        # inserir um IRMÃO depois dela não invalida nada). Achado ao vivo
        # 2026-08-22 — SEFAZ recusou (480, "QR Code deve ser informado")
        # sem esse bloco.
        inf_supl = f"<infMDFeSupl><qrCodMDFe><![CDATA[{url_qrcode}]]></qrCodMDFe></infMDFeSupl>"
        xml_assinado = xml_assinado.replace(b"</infMDFe>", f"</infMDFe>{inf_supl}".encode("utf-8"), 1)
        envelope = nfe_fiscal_common.montar_envelope_soap_gzip_b64(
            xml_assinado, "MDFeRecepcaoSinc", nfe_fiscal_common.MDFE_NS,
        )
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem, timeout=60)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(resposta, "xMotivo")
    n_prot = nfe_fiscal_common.extrair_tag(resposta, "nProt")
    dh_recbto = nfe_fiscal_common.extrair_tag(resposta, "dhRecbto")
    if c_stat != "100":
        resultado_rejeicao = {
            "success": False,
            "message": f"SEFAZ recusou a emissão (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}.",
        }
        if servidor and banco:
            resultado_rejeicao["apoio_fiscal"] = apoio_fiscal_service.notificar_rejeicao_sync(
                servidor, banco, tipo_documento="MDF-e", codigo_rejeicao=c_stat or "?",
                mensagem_original=x_motivo or "", referencia=chave_acesso,
            )
        return resultado_rejeicao

    xml_prot = nfe_fiscal_common.extrair_bloco(resposta, "protMDFe") or ""
    cur.execute(
        "UPDATE MDFe SET situacao='T', protocolo_sefaz=%s, dhRecbto=%s, xml_protMDFe=%s, urlqrcode=%s, cstat=%s "
        "WHERE codigo=%s",
        (n_prot, nfe_fiscal_common.parse_dh_sefaz(dh_recbto), xml_prot, url_qrcode, c_stat, cod_mdfe),
    )
    cur.execute("UPDATE controle_aux SET numero_MDFE=%s, serie_MDFE=%s", (proximo_numero, serie))
    return {
        "success": True,
        "message": f"MDF-e autorizado pelo SEFAZ — protocolo {n_prot or '?'}.",
        "num_mdfe": proximo_numero, "chave_acesso": chave_acesso, "protocolo_sefaz": n_prot,
    }


# ---------------------------------------------------------------------------
# Eventos (Encerramento/Cancelamento) — mesmo padrão já usado em
# `nfe_cancelamento_service.py`, só troca webservice/namespace/corpo.
# ---------------------------------------------------------------------------
def _montar_xml_evento_mdfe(
    tp_evento: str, desc_evento: str, tag_evento: str, cod_ibge: str, cnpj: str, chave_acesso: str,
    protocolo: str, tp_amb: str, corpo_especifico: str,
) -> tuple[bytes, str]:
    """`tag_evento` = `"evEncMDFe"`/`"evCancMDFe"` — achado ao vivo
    2026-08-23 (1ª tentativa real de cancelamento, depois da 1ª emissão
    real de MDF-e ter sido autorizada de verdade): SEFAZ recusou com
    "detEvento has invalid child element nProt" — `descEvento`/`nProt`/
    corpo específico (`xJust`/`dtEnc`+`cUF`+`cMun`) precisam estar
    envelopados dentro de um elemento PRÓPRIO por tipo de evento
    (`<evCancMDFe>`/`<evEncMDFe>`), não soltos direto dentro de
    `<detEvento>` — exatamente a estrutura de `CancelaMDFe`/`EncerraMDFe`
    na fonte VB6 (`Backon.Controllers/NFe.vb:5511,5597`), que eu tinha
    lido mas não reproduzido corretamente na 1ª versão deste builder."""
    dh_evento = datetime.now().astimezone().isoformat(timespec="seconds")
    id_evento = f"ID{tp_evento}{chave_acesso}01"
    xml = (
        f'<eventoMDFe xmlns="{nfe_fiscal_common.MDFE_NS}" versao="3.00">'
        f'<infEvento Id="{id_evento}">'
        f'<cOrgao>{cod_ibge}</cOrgao>'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<CNPJ>{cnpj}</CNPJ>'
        f'<chMDFe>{chave_acesso}</chMDFe>'
        f'<dhEvento>{dh_evento}</dhEvento>'
        f'<tpEvento>{tp_evento}</tpEvento>'
        f'<nSeqEvento>1</nSeqEvento>'
        f'<detEvento versaoEvento="3.00">'
        f'<{tag_evento}>'
        f'<descEvento>{desc_evento}</descEvento>'
        f'<nProt>{protocolo}</nProt>'
        f'{corpo_especifico}'
        f'</{tag_evento}>'
        f'</detEvento>'
        f'</infEvento>'
        f'</eventoMDFe>'
    ).encode("utf-8")
    return xml, id_evento


def _transmitir_evento_mdfe(cur, xml_evento: bytes, id_evento: str, tp_amb: str) -> str:
    cert = _carregar_certificado_sync(cur)
    if not cert:
        raise RuntimeError("Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal).")
    key_pem, cert_pem = cert
    url = nfe_fiscal_common.resolver_endpoint_mdfe("evento", tp_amb)
    if not url:
        raise RuntimeError("Webservice de evento do MDF-e não configurado pra este ambiente.")
    # sha1=True: mesmo achado da emissão — o XSD de evento do MDF-e (mesma
    # família de schema) também fixa SHA-1, não testado ao vivo ainda pros
    # eventos especificamente, mas mesma hipótese até prova em contrário.
    xml_assinado = nfe_fiscal_common.assinar_xml(xml_evento, id_evento, key_pem, cert_pem, sha1=True)
    envelope = nfe_fiscal_common.montar_envelope_soap(
        xml_assinado, "MDFeRecepcaoEvento", ns=nfe_fiscal_common.MDFE_NS, tag="mdfeDadosMsg",
    )
    return nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)


def encerrar_mdfe_sync(
    cur, cod_mdfe: int, municipio_encerra: int, usuario: Optional[str],
    *, servidor: str = "", banco: str = "",
) -> dict:
    cur.execute("SELECT * FROM MDFe WHERE codigo=%s", (cod_mdfe,))
    m = cur.fetchone()
    if not m:
        return {"success": False, "message": "MDF-e não encontrado."}
    if m.get("situacao") != "T":
        return {"success": False, "message": "Só é possível encerrar um manifesto Transmitido."}
    if not municipio_encerra:
        return {"success": False, "message": "Informe o Município de Encerramento."}

    cur.execute("SELECT cgc FROM controle")
    cnpj = ((cur.fetchone() or {}).get("cgc") or "").strip()
    tp_amb = m.get("tp_amb") or nfe_fiscal_common.resolver_tp_amb_sync(cur)
    cod_ibge = m["chave_acesso"][:2]
    corpo = f"<dtEnc>{date.today().isoformat()}</dtEnc><cUF>{cod_ibge}</cUF><cMun>{municipio_encerra}</cMun>"
    xml_evento, id_evento = _montar_xml_evento_mdfe(
        "110112", "Encerramento", "evEncMDFe", cod_ibge, cnpj, m["chave_acesso"], m.get("protocolo_sefaz") or "", tp_amb, corpo,
    )
    try:
        resposta = _transmitir_evento_mdfe(cur, xml_evento, id_evento, tp_amb)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(resposta, "xMotivo")
    if c_stat not in ("135", "136"):
        resultado_rejeicao = {"success": False, "message": f"SEFAZ recusou o encerramento (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}."}
        if servidor and banco:
            resultado_rejeicao["apoio_fiscal"] = apoio_fiscal_service.notificar_rejeicao_sync(
                servidor, banco, tipo_documento="Encerramento MDF-e", codigo_rejeicao=c_stat or "?",
                mensagem_original=x_motivo or "", referencia=m.get("chave_acesso"),
            )
        return resultado_rejeicao

    historico_novo = f"{datetime.now().strftime('%d/%m/%Y %H:%M')} - Encerrado por {usuario or '?'}\n" + (m.get("historico") or "")
    cur.execute(
        "UPDATE MDFe SET situacao='E', municipio_encerra=%s, data_encerramento=%s, "
        "xml_retEventoMDFe_encerra=%s, historico=%s WHERE codigo=%s",
        (municipio_encerra, date.today(), resposta, historico_novo, cod_mdfe),
    )
    return {"success": True, "message": "MDF-e encerrado junto ao SEFAZ."}


def cancelar_mdfe_sync(
    cur, cod_mdfe: int, motivo: str, usuario: Optional[str],
    *, servidor: str = "", banco: str = "",
) -> dict:
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        return {"success": False, "message": "O motivo do cancelamento precisa ter pelo menos 15 caracteres."}
    cur.execute("SELECT * FROM MDFe WHERE codigo=%s", (cod_mdfe,))
    m = cur.fetchone()
    if not m:
        return {"success": False, "message": "MDF-e não encontrado."}
    if m.get("situacao") != "T":
        return {"success": False, "message": "Só é possível cancelar um manifesto Transmitido."}

    cur.execute("SELECT cgc FROM controle")
    cnpj = ((cur.fetchone() or {}).get("cgc") or "").strip()
    tp_amb = m.get("tp_amb") or nfe_fiscal_common.resolver_tp_amb_sync(cur)
    cod_ibge = m["chave_acesso"][:2]
    corpo = f"<xJust>{_escapar(motivo)}</xJust>"
    xml_evento, id_evento = _montar_xml_evento_mdfe(
        "110111", "Cancelamento", "evCancMDFe", cod_ibge, cnpj, m["chave_acesso"], m.get("protocolo_sefaz") or "", tp_amb, corpo,
    )
    try:
        resposta = _transmitir_evento_mdfe(cur, xml_evento, id_evento, tp_amb)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat")
    x_motivo = nfe_fiscal_common.extrair_tag(resposta, "xMotivo")
    if c_stat not in ("135", "136"):
        resultado_rejeicao = {"success": False, "message": f"SEFAZ recusou o cancelamento (status {c_stat or '?'}): {x_motivo or 'sem detalhe'}."}
        if servidor and banco:
            resultado_rejeicao["apoio_fiscal"] = apoio_fiscal_service.notificar_rejeicao_sync(
                servidor, banco, tipo_documento="Cancelamento MDF-e", codigo_rejeicao=c_stat or "?",
                mensagem_original=x_motivo or "", referencia=m.get("chave_acesso"),
            )
        return resultado_rejeicao

    historico_novo = f"{datetime.now().strftime('%d/%m/%Y %H:%M')} - Cancelado por {usuario or '?'}: {motivo}\n" + (m.get("historico") or "")
    cur.execute(
        "UPDATE MDFe SET situacao='C', motivo_cancelamento=%s, xml_retEventoMDFe_Cancela=%s, historico=%s WHERE codigo=%s",
        (motivo, resposta, historico_novo, cod_mdfe),
    )
    return {"success": True, "message": "MDF-e cancelado junto ao SEFAZ."}


# ---------------------------------------------------------------------------
# Consulta de situação (MDFeConsulta, por chave de acesso)
# ---------------------------------------------------------------------------
def consultar_situacao_mdfe_sync(cur, cod_mdfe: int) -> dict:
    cur.execute("SELECT * FROM MDFe WHERE codigo=%s", (cod_mdfe,))
    m = cur.fetchone()
    if not m:
        return {"success": False, "message": "MDF-e não encontrado."}
    if not m.get("chave_acesso"):
        return {"success": False, "message": "Manifesto ainda não foi emitido — nada a consultar no SEFAZ."}

    cert = _carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert
    tp_amb = m.get("tp_amb") or nfe_fiscal_common.resolver_tp_amb_sync(cur)
    url = nfe_fiscal_common.resolver_endpoint_mdfe("consulta", tp_amb)
    if not url:
        return {"success": False, "message": "Webservice de consulta do MDF-e não configurado pra este ambiente."}

    xml_consulta = (
        f'<consSitMDFe xmlns="{nfe_fiscal_common.MDFE_NS}" versao="3.00">'
        f'<tpAmb>{tp_amb}</tpAmb><xServ>CONSULTAR</xServ><chMDFe>{m["chave_acesso"]}</chMDFe>'
        f'</consSitMDFe>'
    ).encode("utf-8")
    envelope = nfe_fiscal_common.montar_envelope_soap(
        xml_consulta, "MDFeConsulta", ns=nfe_fiscal_common.MDFE_NS, tag="mdfeDadosMsg",
    )
    try:
        resposta = nfe_fiscal_common.transmitir(envelope, url, key_pem, cert_pem)
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o SEFAZ: {e}"}

    c_stat = nfe_fiscal_common.extrair_tag(resposta, "cStat") or ""
    n_prot = nfe_fiscal_common.extrair_tag(resposta, "nProt")
    dh_recbto = nfe_fiscal_common.extrair_tag(resposta, "dhRecbto")
    if n_prot:
        xml_prot = nfe_fiscal_common.extrair_bloco(resposta, "protMDFe") or ""
        cur.execute(
            "UPDATE MDFe SET situacao='T', protocolo_sefaz=%s, dhRecbto=%s, xml_protMDFe=%s, cstat=%s WHERE codigo=%s",
            (n_prot, nfe_fiscal_common.parse_dh_sefaz(dh_recbto), xml_prot, c_stat, cod_mdfe),
        )
    else:
        cur.execute("UPDATE MDFe SET cstat=%s WHERE codigo=%s", (c_stat, cod_mdfe))
    return {"success": True, "cstat": c_stat, "protocolo_sefaz": n_prot, "message": f"Situação no SEFAZ: {c_stat or '?'}."}


# ---------------------------------------------------------------------------
# Gerar XML (MontaXMLMDFe) — só reexportação, nunca transmite de novo.
# ---------------------------------------------------------------------------
def gerar_xml_mdfe_sync(cur, cod_mdfe: int) -> dict:
    cur.execute("SELECT situacao, xml_protMDFe, chave_acesso FROM MDFe WHERE codigo=%s", (cod_mdfe,))
    m = cur.fetchone()
    if not m:
        return {"success": False, "message": "MDF-e não encontrado."}
    if m.get("situacao") not in ("T", "E", "C"):
        return {"success": False, "message": "Só é possível gerar o XML de um manifesto já transmitido."}

    xml_mdfe = _montar_xml_mdfe_sync(cur, cod_mdfe)
    xml_final = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<mdfeProc xmlns="{nfe_fiscal_common.MDFE_NS}" versao="3.00">'
        f'{xml_mdfe.decode("utf-8")}'
        f'{m.get("xml_protMDFe") or ""}'
        '</mdfeProc>'
    )
    cur.execute("UPDATE MDFe SET xml=%s WHERE codigo=%s", (xml_final, cod_mdfe))
    return {"success": True, "xml": xml_final, "chave_acesso": m.get("chave_acesso")}


# ---------------------------------------------------------------------------
# Camada de conexão — cada `*_sync(cur, ...)` acima só orquestra dentro de
# um cursor já aberto (mesmo padrão de `nfe_cancelamento_service.
# cancelar_nfe_sync`); estas funções abrem a conexão, committam só em
# sucesso (nunca em erro/timeout — documento fiscal real não pode ficar
# meio-gravado), e expõem a versão async que as rotas chamam.
# ---------------------------------------------------------------------------
def _com_conexao(servidor: str, banco: str, fn, *args) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        mdfe_service._ensure_mdfe_tables(cur)
        resultado = fn(cur, *args)
        if resultado.get("success"):
            conn.commit()
        else:
            conn.rollback()
        cur.close()
        return resultado
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Erro inesperado: {e}"}
    finally:
        conn.close()


def _emitir_mdfe_com_conexao_sync(servidor, banco, cod_mdfe, usuario):
    return _com_conexao(
        servidor, banco,
        lambda cur: emitir_mdfe_sync(cur, cod_mdfe, usuario, servidor=servidor, banco=banco),
    )


def _encerrar_mdfe_com_conexao_sync(servidor, banco, cod_mdfe, municipio_encerra, usuario):
    return _com_conexao(
        servidor, banco,
        lambda cur: encerrar_mdfe_sync(cur, cod_mdfe, municipio_encerra, usuario, servidor=servidor, banco=banco),
    )


def _cancelar_mdfe_com_conexao_sync(servidor, banco, cod_mdfe, motivo, usuario):
    return _com_conexao(
        servidor, banco,
        lambda cur: cancelar_mdfe_sync(cur, cod_mdfe, motivo, usuario, servidor=servidor, banco=banco),
    )


def _consultar_mdfe_com_conexao_sync(servidor, banco, cod_mdfe):
    return _com_conexao(servidor, banco, consultar_situacao_mdfe_sync, cod_mdfe)


def _gerar_xml_mdfe_com_conexao_sync(servidor, banco, cod_mdfe):
    return _com_conexao(servidor, banco, gerar_xml_mdfe_sync, cod_mdfe)


async def emitir_mdfe(servidor, banco, cod_mdfe, usuario):
    return await asyncio.to_thread(_emitir_mdfe_com_conexao_sync, servidor, banco, cod_mdfe, usuario)


async def encerrar_mdfe(servidor, banco, cod_mdfe, municipio_encerra, usuario):
    return await asyncio.to_thread(_encerrar_mdfe_com_conexao_sync, servidor, banco, cod_mdfe, municipio_encerra, usuario)


async def cancelar_mdfe(servidor, banco, cod_mdfe, motivo, usuario):
    return await asyncio.to_thread(_cancelar_mdfe_com_conexao_sync, servidor, banco, cod_mdfe, motivo, usuario)


async def consultar_mdfe(servidor, banco, cod_mdfe):
    return await asyncio.to_thread(_consultar_mdfe_com_conexao_sync, servidor, banco, cod_mdfe)


async def gerar_xml_mdfe(servidor, banco, cod_mdfe):
    return await asyncio.to_thread(_gerar_xml_mdfe_com_conexao_sync, servidor, banco, cod_mdfe)
