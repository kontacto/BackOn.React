"""Emissão real de NFS-e via padrão nacional (DPS/Sefin Nacional) — Fase 3 do
pacote de emissão fiscal ("Impressão de Nota Fiscal", migração de
`FrmTraImpNFE.frm`). Ver `nfe_emissao_service.py` (Fase 1, NFC-e) pro
racional geral e `C:\\Users\\carlo\\.claude\\plans\\velvet-roaming-sparrow.md`
pro plano completo.

Fonte de referência VB6 (rastreada 2026-07-21): `Geral\\NFSe.bas::EmiteNFSe`
(linha 795) — a orquestração real, que NÃO está na DLL `Backon_Controllers`.
Essa rotina branca em 4 caminhos conforme `Dados_Controle_Configuracao.
Sefin_Nacional` e o código do município: (1) padrão nacional DPS/ADN —
implementado aqui; (2) São Gonçalo (webservice próprio); (3) Nova Iguaçu
(GINFES); (4) ABRASF genérico por município. **Decisão explícita do usuário
2026-07-21** (`AskUserQuestion`, escopo desta fase): implementar SÓ o
caminho (1), o padrão nacional — é o que a lei está unificando, e evita
replicar integrações municipais específicas que podem estar sendo
descontinuadas. Os caminhos (2)-(4) ficam documentados como pendência em
`PENDENCIAS.md`, não implementados.

O padrão nacional em si (DPS — Declaração de Prestação de Serviços — e o
Ambiente de Dados Nacional/ADN) não está na DLL nem no VB6: é uma
especificação pública nova (substituindo o RPS/ABRASF município-a-município),
documentada em www.gov.br/nfse. Fontes usadas para reconstruir o formato
(nenhuma delas exige o certificado real pra ler, ao contrário do Swagger
oficial em si — `https://adn.nfse.gov.br/**` devolve HTTP 496 "certificado
exigido" mesmo só pra ver a documentação, confirmado ao vivo 2026-07-21):
  - XML de exemplo real (`infDPS`/`prest`/`toma`/`serv`/`valores`) do PoC
    oficial: https://github.com/nfe/poc-nfse-nacional (arquivo
    `Poc.NFSe/assets/dps-teste.xml`).
  - Endpoint de submissão, formato JSON (`dpsXmlGZipB64`/`chaveAcesso`/
    `nfseXmlGZipB64`) e mTLS: relatos técnicos públicos de integradores
    (tabnews.com.br/Crazynds, tabnews.com.br/CesarMasserati) e o manual
    técnico oficial (`gov.br/nfse` — PDF não pôde ser lido integralmente por
    ferramenta automática nesta sessão, só os resumos acima).
  - Assinatura RSA-SHA256 + C14N + enveloped: mesmo padrão já confirmado
    (independentemente) pra NFe/NFCe — reaproveita `nfe_fiscal_common.
    assinar_xml` tal qual.
  - Composição do Id de `infDPS` (45 posições) e da chave de acesso da NFSe
    (50 posições): documentada de forma convergente em múltiplas fontes
    independentes (nfse-php, Unimake, TOTVS, espiaonfe.com.br).

**NUNCA testado contra o ADN real** (nem homologação/"produção restrita") —
exigiria certificado ICP-Brasil genuíno + cadastro prévio no ambiente, que
não tenho como obter nesta sessão. Só certificado autoassinado + rede
mockada nos testes, mesmo compromisso do resto do pacote fiscal. **A ordem
exata das tags e a validação contra o XSD oficial não foram conferidas** —
o XML aqui replica o exemplo público encontrado, não o schema formal.
Revalidar antes de qualquer transmissão real, mesmo em homologação — ver
CLAUDE.md §12.

Melhorias deliberadas em relação ao legado (documentadas, não mudança de
regra fiscal):
  - RSA-SHA256 na assinatura (mesmo precedente do resto do pacote).
  - Impressão do RPS legado (`ImprimeRPS`/`ImprimeNY`, GDI direto) fica pra
    Fase 4 (DANFSe em HTML) — não portada aqui.
  - Erros como dict estruturado, não string com código de status embutido.
"""
import base64
import gzip
import re
from datetime import date, datetime
from typing import Optional

from services import nfe_fiscal_common

# Endpoints do Ambiente de Dados Nacional (Sefin Nacional) — só o caminho de
# submissão síncrona de DPS. `tp_amb` segue a mesma convenção já usada em
# `nfe_emissao_service.py` (1=produção, 2=homologação/produção restrita).
_ENDPOINTS_DPS = {
    "1": "https://sefin.nfse.gov.br/SefinNacional/nfse",
    "2": "https://sefin.producaorestrita.nfse.gov.br/SefinNacional/nfse",
}

_DPS_NS = "http://www.sped.fazenda.gov.br/nfse"


def _resolver_url_dps(tp_amb: str) -> Optional[str]:
    return _ENDPOINTS_DPS.get(tp_amb)


# ---------------------------------------------------------------------------
# Id da DPS (45 posições) e chave de acesso da NFSe (50 posições) —
# composição pública, confirmada de forma convergente em múltiplas fontes
# independentes de integradores (ver docstring do módulo). Diferente da
# chave de 44 dígitos da NFe/NFCe (mesmo dígito verificador módulo-11 NÃO
# se aplica aqui — o ADN é quem calcula/devolve a chave real da NFSe; o Id
# da DPS não tem dígito verificador próprio, é só concatenação posicional).
# ---------------------------------------------------------------------------

def montar_id_dps(*, cod_municipio: str, tipo_inscricao: str, inscricao_federal: str, serie: str, numero_dps: int) -> str:
    """Id do elemento `infDPS` — "DPS" + cLocEmi(7) + tpInsc(1, "2"=CNPJ/
    "1"=CPF) + inscrição federal(14) + série(5) + nDPS(15), todos com zeros
    à esquerda. Usado como referência da assinatura (`Id="..."`), não como
    a chave de acesso final da NFSe (essa é devolvida pelo ADN na resposta)."""
    cmun = re.sub(r"\D", "", cod_municipio).zfill(7)
    inscricao = re.sub(r"\D", "", inscricao_federal).zfill(14)
    serie_num = re.sub(r"\D", "", str(serie)).zfill(5)
    ndps = str(int(numero_dps)).zfill(15)
    return f"DPS{cmun}{tipo_inscricao}{inscricao}{serie_num}{ndps}"


# ---------------------------------------------------------------------------
# XML da DPS — layout público do padrão nacional (validar contra o XSD
# oficial antes de transmitir de verdade — ver docstring do módulo).
# ---------------------------------------------------------------------------

def _montar_xml_dps(
    *, id_dps: str, tp_amb: str, cod_municipio: str, serie: str, numero_dps: int, data_competencia: date,
    cnpj_prest: str, opcao_simples_nacional: bool, regime_especial_tributacao: int,
    tomador: Optional[dict], itens: list[dict], ibs_cbs_cst: str = "", ibs_cbs_classtrib: str = "",
    codigo_nbs: str = "", simples_servico_pct: float = 0.0,
) -> tuple[bytes, str]:
    """Monta `<DPS><infDPS Id="...">` conforme o exemplo público oficial
    (ver docstring do módulo). `itens` já deve trazer o serviço com
    `cod_lista_servico`/`descricao`/`valor` resolvidos — este módulo não
    agrega/soma serviços diferentes numa mesma DPS (uma DPS = um serviço
    principal, mesma simplificação já aceita implicitamente pelo legado,
    que emite uma NFSe por comanda).

    `ibs_cbs_cst`/`ibs_cbs_classtrib` — CST/cClassTrib do IBS/CBS do
    serviço principal (`ibs_cbs_service.calcular_item_ibs_cbs`, chamado
    por quem orquestra). **Só CST/cClassTrib, nunca valor monetário** —
    decisão de leiaute confirmada pelo usuário pra fase de transição da
    Reforma Tributária (ver `[[project_ibs_cbs_vb6_pendente]]`: "durante a
    fase de transição, o leiaute do XML de envio da DPS deliberadamente só
    informa CST/cClassTrib, sem mandar o valor monetário calculado" — o
    sistema local já calcula o valor, só não é enviado no XML ainda).
    **Posicionamento do grupo dentro de `<serv>` não foi confirmado contra
    o XSD oficial da DPS Nacional** — mesma ressalva já registrada na
    docstring do módulo pro restante do layout."""
    dh_emi = datetime.now().astimezone().isoformat(timespec="seconds")
    d_compet = data_competencia.isoformat()

    valor_total = round(sum(float(i.get("valor") or 0) for i in itens), 2)
    primeiro = itens[0] if itens else {}
    cod_lista = re.sub(r"\D", "", primeiro.get("cod_lista_servico") or "") or "000000"
    # Código de Tributação Nacional (cTribNac, 6 dígitos) = `cod_lista_servico`
    # tal qual — confirmado 2026-08-24 contra a tabela real `Tributacao_MUnicipio`
    # (1071 linhas já carregadas no banco desta instalação, herdada do legado):
    # sua coluna `cTribNac` guarda exatamente esse valor de 6 dígitos pra cada
    # item LC116 (ex.: "140101" pro item 14.01.01 completo) — não é mais uma
    # aproximação não confirmada, é o mesmo dado que o legado sempre usou.
    c_trib_nac = cod_lista.zfill(6)[:6]
    x_desc_serv = nfe_fiscal_common.escapar_xml(primeiro.get("descricao") or "")
    # `cTribMun`/`cNBS` — rastreados até a raiz na fonte VB6 real
    # (`Backon.Data/DAO_NFE.vb`) em 2026-08-24, depois que a 1ª tentativa
    # (mapa hardcoded de 1 único cod_lista_servico, pesquisado em fonte
    # oficial mas nunca ligado ao cadastro real do cliente) funcionou pro
    # teste ao vivo mas divergia do dado que a própria instalação já tinha
    # cadastrado. Achado real, não suposição:
    #   - `cTribMun` é **por serviço**, já existe pronto: `servicos.
    #     cod_servico_municipio` (DAO_NFE.vb:1140/1216, `Me.ccTribMun =
    #     tb("cod_servico_municipio").Value` — sobrescreve incondicionalmente
    #     um valor-sugestão vindo da tabela `tributacao_municipio`/
    #     `ctribmun`, também real e já carregada nesta instalação com 1071
    #     linhas, mas não consultada aqui ainda — sugestão automática por
    #     `cod_lista_servico` fica como melhoria futura, ver PENDENCIAS.md).
    #     Já é um campo de cadastro real, editável em Cadastro de Serviços
    #     (aba Fiscal) — nenhum campo/tela novo foi necessário, só ligar
    #     este service ao dado que já existe. Recebido aqui via `itens[0]
    #     ["cod_servico_municipio"]` (quem chama resolve por JOIN com
    #     `servicos`, mesma query que já resolve `cod_lista_servico`).
    #   - `cNBS` **NÃO é por serviço** — achado que corrige a 1ª tentativa:
    #     no legado é um único campo por EMPRESA, `controle_aux.codigo_nbs`
    #     (DAO_NFE.vb:625, lido de `controle_aux` junto com `iss_retido`,
    #     nada a ver com a tabela `servicos`). Já existe, já é editável em
    #     Controle do Sistema (aba Fiscal) — recebido aqui via o parâmetro
    #     `codigo_nbs` (quem chama lê `controle_aux.codigo_nbs` uma vez só).
    #   - Confirmado com o usuário (2026-08-24, `AskUserQuestion` — "Bloquear
    #     com mensagem clara") que emissão deve BLOQUEAR com mensagem
    #     amigável quando qualquer um dos dois estiver vazio, nunca inventar
    #     um valor de preenchimento — mesmo princípio de Kelvin usado o
    #     resto desta migração.
    c_trib_mun = re.sub(r"\D", "", primeiro.get("cod_servico_municipio") or "")
    if not c_trib_mun:
        descricao_serv = primeiro.get("descricao") or primeiro.get("codigo_int") or "selecionado"
        raise ValueError(
            f"O serviço \"{descricao_serv}\" não tem o Código de Tributação Municipal cadastrado "
            "(Cadastro de Serviços > aba Fiscal, campo \"Código Complementar Municipal\") — "
            "obrigatório pra emitir NFS-e, nunca preenchido automaticamente."
        )
    c_nbs = re.sub(r"\D", "", codigo_nbs or "")
    if not c_nbs:
        raise ValueError(
            "O Código NBS da empresa não está cadastrado (Controle do Sistema > aba Fiscal, "
            "campo \"Código NBS\") — obrigatório pra emitir NFS-e, nunca preenchido automaticamente."
        )
    c_trib_mun = c_trib_mun.zfill(3)
    c_nbs = c_nbs.zfill(9)

    toma_xml = ""
    if tomador and tomador.get("cgc_cpf"):
        doc = re.sub(r"\D", "", tomador["cgc_cpf"])
        doc_tag = "CNPJ" if len(doc) > 11 else "CPF"
        nome_toma = nfe_fiscal_common.escapar_xml(tomador.get("nome") or "")
        toma_xml = f'<toma><{doc_tag}>{doc}</{doc_tag}><xNome>{nome_toma}</xNome></toma>'

    serie_fmt = re.sub(r"\D", "", str(serie)).zfill(5)
    cod_municipio_num = re.sub(r"\D", "", cod_municipio)
    cnpj_num = re.sub(r"\D", "", cnpj_prest)

    xml = (
        f'<DPS versao="1.00" xmlns="{_DPS_NS}">'
        f'<infDPS Id="{id_dps}">'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<dhEmi>{dh_emi}</dhEmi>'
        f'<verAplic>APPIAREACT_1.0</verAplic>'
        f'<serie>{serie_fmt}</serie>'
        f'<nDPS>{numero_dps}</nDPS>'
        f'<dCompet>{d_compet}</dCompet>'
        f'<tpEmit>1</tpEmit>'
        f'<cLocEmi>{cod_municipio_num}</cLocEmi>'
        f'<prest>'
        f'<CNPJ>{cnpj_num}</CNPJ>'
        f'<regTrib>'
        # Achado ao vivo 2026-08-23 (E0160, "situação perante o Simples
        # Nacional... não está de acordo com o cadastro"): o enum real de
        # `opSimpNac` (confirmado no XSD oficial gov.br,
        # `tiposComplexos_v1.01.xsd`) é 1=Não Optante, 2=Optante MEI,
        # 3=Optante ME/EPP — DIFERENTE do CRT da NF-e (1=Simples,
        # 3=Normal), NUNCA "1=optante". O código anterior mandava
        # LITERALMENTE o oposto (1 quando optante). `opcao_simples_
        # nacional` (flag booleana local, `controle_aux.opcao_simples`)
        # não distingue MEI de ME/EPP — mapeado pra 3 (ME/EPP, o caso
        # comum/default pra uma flag booleana simples; empresa de teste
        # real, "ARGEN AR CONDICIONADO LTDA - EPP", confirma ME/EPP pelo
        # próprio nome) quando `True`, 1 quando `False`. MEI (2) fica de
        # fora do que essa flag booleana consegue representar — gap
        # registrado em PENDENCIAS.md, não um chute.
        f'<opSimpNac>{3 if opcao_simples_nacional else 1}</opSimpNac>'
        # `regApTribSN` — achado ao vivo 2026-08-23 (E0166, "obrigatorio
        # o preenchimento do campo de regime de apuração dos tributos do
        # SN pra o optante ME/EPP"): obrigatório quando `opSimpNac=3`
        # (confirmado no XSD oficial — `TSRegimeApuracaoSimpNac`,
        # documentação do elemento). Valor `1` ("Regime de apuração dos
        # tributos federais e municipal pelo SN") — o regime PADRÃO pra
        # uma ME/EPP normal, sem ter excedido sublimite algum; este
        # projeto não tem cadastro de sublimite excedido, então não há
        # base pra escolher `2`/`3` sem inventar — revisar se a empresa
        # de teste algum dia tiver esse cenário real.
        f'{"<regApTribSN>1</regApTribSN>" if opcao_simples_nacional else ""}'
        f'<regEspTrib>{int(regime_especial_tributacao or 0)}</regEspTrib>'
        f'</regTrib>'
        f'</prest>'
        f'{toma_xml}'
        f'<serv>'
        f'<locPrest><cLocPrestacao>{cod_municipio_num}</cLocPrestacao></locPrest>'
        # Ordem real do XSD (`TCCServ`): cTribNac, cTribMun, xDescServ, cNBS,
        # cIntContrib? — confirmado ao vivo 2026-08-23 contra
        # `schema_v101.xsd`. `<gIBSCBS>` dentro de `<serv>` (versão anterior
        # deste código) NÃO EXISTE no schema real — o grupo `IBSCBS` de
        # verdade (`TCRTCInfoIBSCBS`) é filho de `infDPS`, IRMÃO de `valores`
        # (não de `cServ`), e exige uma estrutura bem maior (`finNFSe`,
        # `cIndOp`, `indDest`, `valores` IBS/CBS próprios) que este módulo
        # ainda não monta — `ibs_cbs_cst`/`ibs_cbs_classtrib` ficam
        # recebidos mas NÃO USADOS por enquanto (não removidos da
        # assinatura pra não quebrar os 2 call sites que já calculam esses
        # valores); ver PENDENCIAS.md > "NFS-e (DPS Nacional)".
        f'<cServ><cTribNac>{c_trib_nac}</cTribNac><cTribMun>{c_trib_mun}</cTribMun>'
        f'<xDescServ>{x_desc_serv}</xDescServ><cNBS>{c_nbs}</cNBS></cServ>'
        f'</serv>'
        f'<valores>'
        f'<vServPrest><vServ>{valor_total:.2f}</vServ></vServPrest>'
        f'<trib>'
        # `tpRetISSQN` (1=Não Retido) é obrigatório dentro de `tribMun`
        # (`TCTribMunicipal`) — achado ao vivo 2026-08-23 (E1235, "Falha
        # no esquema XML"), confirmado contra o XSD oficial.
        f'<tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN></tribMun>'
        # `totTrib` (grupo IRMÃO de `tribMun`, também obrigatório) — a
        # escolha certa depende de `opSimpNac`, achado ao vivo 2026-08-23
        # (E0712, "Para ME/EPP o indicador de informação de valor total
        # de tributos não pode ser informado"): `indTotTrib=0` ("não
        # informar valor estimado", a opção mais simples do `<choice>` de
        # 4 do schema) só é aceita pra empresa NÃO optante — pra ME/EPP
        # (`opSimpNac=3`), o schema exige `pTotTribSN` (percentual
        # aproximado do total de tributos da alíquota efetiva do Simples
        # Nacional, campo informativo da Lei 12.741/2012 "Lei da
        # Transparência" — NUNCA afeta o ISS realmente devido/calculado,
        # só o texto de transparência mostrado ao consumidor). **Corrigido
        # 2026-08-24**: a 1ª versão usava uma estimativa fixa de 6.00%
        # (decisão do usuário 2026-08-23, só pra validar o mecanismo) —
        # rastreando a fonte VB6 até a raiz (`DAO_NFE.vb:585-587`,
        # `Me.cDPS_Alqt_Simples_Nacional = Format(tb("simples_servico").
        # Value, ...)`), o legado sempre teve o percentual REAL já
        # cadastrado em `controle.simples_servico` (confirmado ao vivo:
        # 13,80% pra ARGEN TESTE) — campo de cadastro de negócio já
        # existente e editável em Controle do Sistema, só não estava ligado
        # aqui. Confirmado com o usuário (`AskUserQuestion`, "Sim, usar o
        # percentual real") substituir a estimativa fixa por este valor.
        f'<totTrib>{"<pTotTribSN>" + f"{float(simples_servico_pct or 0):.2f}" + "</pTotTribSN>" if opcao_simples_nacional else "<indTotTrib>0</indTotTrib>"}</totTrib>'
        f'</trib>'
        f'</valores>'
        f'</infDPS>'
        f'</DPS>'
    ).encode("utf-8")
    return xml, id_dps


def _empacotar_dps(xml_assinado: bytes) -> str:
    """gzip + base64 do XML assinado — formato exigido pelo ADN
    (`dpsXmlGZipB64`, confirmado em múltiplos relatos de integradores)."""
    return base64.b64encode(gzip.compress(xml_assinado)).decode("ascii")


def _desempacotar_nfse(nfse_gzip_b64: str) -> str:
    return gzip.decompress(base64.b64decode(nfse_gzip_b64)).decode("utf-8")


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def emitir_nfse_sync(
    cur, *, comanda: int, cnpj_prest: str, cod_municipio: str, opcao_simples_nacional: bool,
    regime_especial_tributacao: int, proximo_numero: int, serie: str, tomador: Optional[dict],
    itens: list[dict], tp_amb: str, ibs_cbs_cst: str = "", ibs_cbs_classtrib: str = "",
    codigo_nbs: str = "", simples_servico_pct: float = 0.0,
) -> dict:
    """Orquestra a emissão de uma NFS-e (DPS Nacional) a partir de uma
    comanda já faturada com itens de serviço — monta/assina a DPS, envia ao
    ADN (`sefin.nfse.gov.br`) e devolve o resultado. `cur` é o cursor já
    aberto (mesma transação de quem chama, pra ler o certificado).
    `ibs_cbs_cst`/`ibs_cbs_classtrib` — repassados tal qual pra
    `_montar_xml_dps` (ver a docstring de lá). `codigo_nbs` (`controle_aux.
    codigo_nbs`, cadastro real por empresa) e `simples_servico_pct`
    (`controle.simples_servico`, percentual real do Simples Nacional) —
    resolvidos por quem chama (join com `controle`/`controle_aux`), nunca
    inventados aqui; ver `_montar_xml_dps` pra onde/como são usados e
    validados."""
    if not itens:
        return {"success": False, "message": "Comanda sem itens de serviço — nada a emitir."}
    if not cod_municipio:
        return {"success": False, "message": "Código do município (IBGE) não configurado em Controle do Sistema."}

    url = _resolver_url_dps(tp_amb)
    if not url:
        return {"success": False, "message": f"Ambiente '{tp_amb}' não reconhecido para emissão de NFS-e."}

    cert = nfe_fiscal_common.carregar_certificado_sync(cur)
    if not cert:
        return {"success": False, "message": "Nenhum certificado digital válido cadastrado (Controle do Sistema > aba Fiscal)."}
    key_pem, cert_pem = cert

    try:
        cnpj_num = re.sub(r"\D", "", cnpj_prest)
        id_dps = montar_id_dps(
            cod_municipio=cod_municipio, tipo_inscricao="2", inscricao_federal=cnpj_num,
            serie=serie, numero_dps=proximo_numero,
        )
        xml_dps, _ = _montar_xml_dps(
            id_dps=id_dps, tp_amb=tp_amb, cod_municipio=cod_municipio, serie=serie,
            numero_dps=proximo_numero, data_competencia=date.today(), cnpj_prest=cnpj_prest,
            opcao_simples_nacional=opcao_simples_nacional, regime_especial_tributacao=regime_especial_tributacao,
            tomador=tomador, itens=itens, ibs_cbs_cst=ibs_cbs_cst, ibs_cbs_classtrib=ibs_cbs_classtrib,
            codigo_nbs=codigo_nbs, simples_servico_pct=simples_servico_pct,
        )
        xml_assinado = nfe_fiscal_common.assinar_xml(xml_dps, id_dps, key_pem, cert_pem, sem_prefixo=True)
        payload = {"dpsXmlGZipB64": _empacotar_dps(xml_assinado)}
        resposta = nfe_fiscal_common.transmitir_json_mtls(payload, url, key_pem, cert_pem)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": f"Falha ao comunicar com o ADN (Sefin Nacional): {e}"}

    if resposta.get("_erro_http") or not resposta.get("chaveAcesso"):
        mensagens = resposta.get("mensagens") or resposta.get("message") or resposta
        return {"success": False, "message": f"ADN recusou a emissão da NFS-e: {mensagens}"}

    chave_acesso = resposta["chaveAcesso"]
    nfse_xml = None
    if resposta.get("nfseXmlGZipB64"):
        try:
            nfse_xml = _desempacotar_nfse(resposta["nfseXmlGZipB64"])
        except Exception:
            nfse_xml = None

    return {
        "success": True,
        "message": f"NFS-e autorizada pelo Sefin Nacional — chave de acesso {chave_acesso}.",
        "chave_acesso": chave_acesso,
        "id_dps": id_dps,
        "xml_dps": xml_assinado.decode("utf-8"),
        "xml_nfse": nfse_xml,
        "numero": proximo_numero,
        "serie": serie,
    }
