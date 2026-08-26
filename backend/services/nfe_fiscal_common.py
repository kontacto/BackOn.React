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

**Achado ao vivo 2026-08-22 (1º teste real de verdade contra o SEFAZ,
MDF-e Fase B)**: toda chamada `requests` contra `nfe.svrs.rs.gov.br`/
`mdfe.svrs.rs.gov.br` falhava com `SSLCertVerificationError: unable to
get local issuer certificate` — **não é bug de código**, é que o
certificado desses hosts é emitido pela hierarquia ICP-Brasil (raiz
"Autoridade Certificadora Raiz Brasileira v10"), que não está no bundle
público padrão (`certifi`/Mozilla) — nenhum navegador/cliente Python
comum confia nela por padrão, só quem instala a cadeia ICP-Brasil
manualmente. Confirmado via `openssl s_client -showcerts` contra o host
real. Corrigido com `_ca_bundle_path()` abaixo (certifi + raiz ICP-Brasil
v10, `backend/certs/icp-brasil-raiz-v10.pem`, baixada de
`https://acraiz.icpbrasil.gov.br/credenciadas/RAIZ/ICP-Brasilv10.crt`,
fonte oficial ITI) — usado em toda chamada deste módulo daqui pra
frente. Se uma UF futura tiver autorizador PRÓPRIO (fora do grupo SVRS)
usando uma AC diferente da v10, pode precisar de outra raiz — checar o
mesmo jeito (`openssl s_client -showcerts`) antes de assumir que
funciona.
"""
import base64
import functools
import hashlib
import os
import re
import tempfile
from datetime import datetime
from typing import Optional

import requests
import signxml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from signxml import XMLSigner

_ICP_BRASIL_ROOT_PEM = os.path.join(os.path.dirname(__file__), "..", "certs", "icp-brasil-raiz-v10.pem")


@functools.lru_cache(maxsize=1)
def _ca_bundle_path() -> str:
    """Bundle de CA = certifi (padrão) + raiz ICP-Brasil v10 — ver achado
    no docstring do módulo. Gerado uma vez por processo (cacheado), num
    arquivo temporário — nunca reescreve o `cacert.pem` do certifi."""
    import certifi

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
        with open(certifi.where(), "rb") as base:
            f.write(base.read())
        f.write(b"\n")
        with open(_ICP_BRASIL_ROOT_PEM, "rb") as icp:
            f.write(icp.read())
        return f.name

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

# Tabela-semente de código de município (IBGE, 7 dígitos) por cidade+UF —
# **não é uma tabela completa de municípios brasileiros** (são ~5570), só os
# já confirmados nas empresas testadas nesta migração. Sem tabela de
# município dedicada no schema (`controle`/`cliente_end` só guardam
# `cidade` como texto livre + `uf` — confirmado ao vivo, sem coluna de
# código IBGE), qualquer empresa/cliente fora desta lista bloqueia com
# mensagem clara em vez de adivinhar um código errado. Movida de
# `comanda_service.py` (onde nasceu, pra emissão de NFS-e/DPS) pra cá
# 2026-08-19 ao virar necessária também pro destinatário de NF-e modelo 55
# (`nfe_agrupada_service.py`) — mesmo helper, dois consumidores. Ver
# PENDENCIAS.md > "Emissão Fiscal Real" — resolver de verdade exige uma
# tabela de municípios (IBGE) própria ou um novo campo dedicado, fora do
# escopo desta fase.
_MUNICIPIOS_IBGE_CONHECIDOS = {
    ("RIO DE JANEIRO", "RJ"): "3304557",
}


def resolver_cod_municipio_ibge(cidade: Optional[str], uf: Optional[str]) -> Optional[str]:
    chave = ((cidade or "").strip().upper(), (uf or "").strip().upper())
    return _MUNICIPIOS_IBGE_CONHECIDOS.get(chave)


# ---------------------------------------------------------------------------
# Destinatário (cliente OU fornecedor) — validação obrigatória (bloqueante)
# pra NF-e modelo 55, diferença real vs. NFC-e (`TestaEnderecoNFE`,
# rastreio 2026-08-19/20, `frmtranfe.frm`): CPF (pessoa física) exige algum
# endereço cadastrado (qualquer tipo); CNPJ exige especificamente endereço
# tipo comercial (`tipo=0`/`tipo_endereco=0`). Movido de
# `nfe_agrupada_service.py` (onde nasceu, só pra cliente) pra cá 2026-08-20
# ao virar necessário também pra fornecedor (NF-e Avulsa, `tipo_mov.
# origem_destino='F'`) — mesmo formato de retorno pros dois, dois
# consumidores. `nfe_agrupada_service._resolver_destinatario_sync` continua
# existindo como alias, não duplicado.
# ---------------------------------------------------------------------------

def resolver_destinatario_cliente_sync(cur, cliente_codigo: int) -> dict:
    """Resolve e valida o destinatário CLIENTE — devolve `{"success": True,
    "destinatario": {...}, "consumidor_final": bool, "simples_nacional_
    cliente": bool}` ou `{"success": False, "message": ...}`."""
    cur.execute(
        "SELECT cgc_cpf, nome, fantasia, ISNULL(inscr_est, '') AS inscr_est, consumidor_final, credita_icms "
        "FROM cliente WHERE codigo = %s",
        (cliente_codigo,),
    )
    cli = cur.fetchone()
    cgc_cpf = (cli.get("cgc_cpf") or "").strip() if cli else ""
    if not cli or len(cgc_cpf) < 11:
        return {"success": False, "message": "Cliente sem CPF/CNPJ cadastrado — obrigatório para emitir NF-e."}

    is_cnpj = len(cgc_cpf) > 11
    if is_cnpj:
        cur.execute(
            "SELECT TOP 1 endereco, numero, bairro, cidade, uf, cep FROM cliente_end "
            "WHERE codigo = %s AND tipo = 0",
            (cliente_codigo,),
        )
    else:
        cur.execute(
            "SELECT TOP 1 endereco, numero, bairro, cidade, uf, cep FROM cliente_end "
            "WHERE codigo = %s ORDER BY tipo",
            (cliente_codigo,),
        )
    end = cur.fetchone()
    if not end:
        tipo_msg = "endereço comercial" if is_cnpj else "endereço"
        return {"success": False, "message": f"Cliente sem {tipo_msg} cadastrado — obrigatório para emitir NF-e."}

    cod_municipio = resolver_cod_municipio_ibge(end.get("cidade"), end.get("uf"))
    if not cod_municipio:
        return {
            "success": False,
            "message": f"Município '{end.get('cidade')}/{end.get('uf')}' do cliente não está na lista de códigos IBGE conhecidos — cadastre-o antes de emitir.",
        }

    contribuinte = bool((cli.get("inscr_est") or "").strip()) and is_cnpj
    return {
        "success": True,
        "destinatario": {
            "cgc_cpf": cgc_cpf, "nome": (cli.get("fantasia") or cli.get("nome") or "").strip(),
            "endereco": (end.get("endereco") or "").strip(), "numero": (end.get("numero") or "S/N"),
            "bairro": (end.get("bairro") or "").strip(), "cidade": (end.get("cidade") or "").strip(),
            "uf": (end.get("uf") or "").strip().upper(), "cep": (end.get("cep") or "").strip(),
            "cod_municipio_ibge": cod_municipio,
            "ie": (cli.get("inscr_est") or "").strip() if contribuinte else None,
            "indIEDest": "1" if contribuinte else "9",
        },
        "consumidor_final": bool(cli.get("consumidor_final")),
        "simples_nacional_cliente": bool(cli.get("credita_icms")),
    }


def resolver_destinatario_fornecedor_sync(cur, fornecedor_codigo_int: int) -> dict:
    """Mesma regra de `resolver_destinatario_cliente_sync`, pro lado
    FORNECEDOR — usado quando `tipo_mov.origem_destino='F'` (NF-e Avulsa
    de compra/devolução/etc.). `fornecedor.codigo` é o documento (CPF/CNPJ,
    mesma convenção de `cliente.cgc_cpf` — não confundir com `codigo_int`,
    a PK interna). `fornecedor_end.tipo_endereco=0` = comercial, mesmo
    código do cliente. Fornecedor não tem `consumidor_final`/`credita_icms`
    — `consumidor_final` sempre `False` aqui (destinatário de compra/
    devolução, nunca venda a consumidor final)."""
    cur.execute(
        "SELECT codigo AS cgc_cpf, nome, fantasia, ISNULL(inscr_est, '') AS inscr_est "
        "FROM fornecedor WHERE codigo_int = %s",
        (fornecedor_codigo_int,),
    )
    forn = cur.fetchone()
    cgc_cpf = (forn.get("cgc_cpf") or "").strip() if forn else ""
    if not forn or len(cgc_cpf) < 11:
        return {"success": False, "message": "Fornecedor sem CPF/CNPJ cadastrado — obrigatório para emitir NF-e."}

    is_cnpj = len(cgc_cpf) > 11
    if is_cnpj:
        cur.execute(
            "SELECT TOP 1 endereco, numero, bairro, cidade, uf, cep FROM fornecedor_end "
            "WHERE codigo = %s AND tipo_endereco = 0",
            (fornecedor_codigo_int,),
        )
    else:
        cur.execute(
            "SELECT TOP 1 endereco, numero, bairro, cidade, uf, cep FROM fornecedor_end "
            "WHERE codigo = %s ORDER BY tipo_endereco",
            (fornecedor_codigo_int,),
        )
    end = cur.fetchone()
    if not end:
        tipo_msg = "endereço comercial" if is_cnpj else "endereço"
        return {"success": False, "message": f"Fornecedor sem {tipo_msg} cadastrado — obrigatório para emitir NF-e."}

    cod_municipio = resolver_cod_municipio_ibge(end.get("cidade"), end.get("uf"))
    if not cod_municipio:
        return {
            "success": False,
            "message": f"Município '{end.get('cidade')}/{end.get('uf')}' do fornecedor não está na lista de códigos IBGE conhecidos — cadastre-o antes de emitir.",
        }

    contribuinte = bool((forn.get("inscr_est") or "").strip()) and is_cnpj
    return {
        "success": True,
        "destinatario": {
            "cgc_cpf": cgc_cpf, "nome": (forn.get("fantasia") or forn.get("nome") or "").strip(),
            "endereco": (end.get("endereco") or "").strip(), "numero": (end.get("numero") or "S/N"),
            "bairro": (end.get("bairro") or "").strip(), "cidade": (end.get("cidade") or "").strip(),
            "uf": (end.get("uf") or "").strip().upper(), "cep": (end.get("cep") or "").strip(),
            "cod_municipio_ibge": cod_municipio,
            "ie": (forn.get("inscr_est") or "").strip() if contribuinte else None,
            "indIEDest": "1" if contribuinte else "9",
        },
        "consumidor_final": False,
        "simples_nacional_cliente": False,
    }


# ---------------------------------------------------------------------------
# Módulos do ecossistema fiscal (2026-08-20, user-directed) — "Regra de
# Módulo Ativo" (CLAUDE.md), mesmo padrão de `pedido_common._modulo_
# servicos_ativo`: cada módulo é verificado em runtime (defesa em
# profundidade — vale até pra master, que bypassa `can()` mas NÃO
# `moduleOn()`/checagem de módulo).
#
# **Correção 2026-08-20, mesmo dia**: a 1ª versão gerou colunas novas
# (`controle_configuracao.NFE`/`NFSE`) e reaproveitou `DMC` — errado. O
# usuário mostrou a tela real "Módulos do Cliente" (`Geral\FrmGerKon.frm`)
# e os campos fiscais JÁ EXISTIAM no legado, só numa tabela irmã
# (`controle_aux`, não `controle_configuracao`): `emite_nfce`/`nfe_ws`/
# `emite_nfse`. `DMC` nunca foi campo fiscal (é "Exportação do DMC
# Combustíveis", ligado a Posto) — revertido em `controle_config_
# service.py`. Ver CLAUDE.md > "Sempre checar regras reais de controle/
# controle_aux/controle_configuracao" pro racional completo. `emite_nfse`
# (legado, "Emite NFSe via PC-RJ" — municipal) **não** corresponde ao
# caminho de emissão implementado nesta migração (`_emitir_nfse_comanda_
# sync`, Sefin Nacional/DPS) — por isso não existe um `modulo_nfse_ativo_
# sync` aqui; o gate correto pra essa função continua sendo só
# `_modulo_sefin_nacional_ativo` (`comanda_service.py`), inalterado.
# ---------------------------------------------------------------------------

def modulo_nfce_ativo_sync(cur) -> bool:
    """True se o módulo "NFCe" está ligado (`controle_aux.emite_nfce`,
    campo real do legado — "Módulos do Cliente" > "NFCE"). Gateia Gestor
    NFCe + emissão de NFC-e via comanda."""
    cur.execute("SELECT TOP 1 emite_nfce FROM controle_aux")
    row = cur.fetchone()
    val = row.get("emite_nfce") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def modulo_nfe_ativo_sync(cur) -> bool:
    """True se o módulo "NFe" está ligado (`controle_aux.nfe_ws`, campo
    real do legado — "Módulos do Cliente" > "NFe via Webservice"). Gateia
    Gerar NFe Comanda (agrupada) + Gerar NFe (avulsa), modelo 55."""
    cur.execute("SELECT TOP 1 nfe_ws FROM controle_aux")
    row = cur.fetchone()
    val = row.get("nfe_ws") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def resolver_tp_amb_sync(cur) -> str:
    """Ambiente de emissão SEFAZ/ADN — `"1"` (Produção) ou `"2"`
    (Homologação) — lido de `controle_aux.ambiente_nfe`, campo real do
    legado (2026-08-20, `Geral\\FrmGerKon.frm:520-521,858-862` —
    "Módulos do Cliente" > aba Kontacto, único lugar do legado que grava
    esse campo; a mesma tela grava `Ambiente_NFSE` a partir do MESMO
    toggle, então este resolvedor também serve pra emissão de NFS-e via
    Sefin Nacional — não é um campo por-modelo separado). Antes desta
    rodada, todo o pacote fiscal desta migração hardcodava `tp_amb="1"`
    (produção) em todo lugar — nenhuma forma de testar em homologação
    sem editar código.

    **Fail-safe fiel ao legado**: valor ausente/`0`/`2` cai pra
    Homologação — só `1` exato é Produção (`FrmGerKon.frm:858`,
    `CByte("0" & TbAux("ambiente_nfe")) = 0 Or ... = 2 Then Option11
    (Homologação)`) — uma instalação que nunca configurou este campo
    (Kontacto-only, a maioria dos clientes nunca abre essa aba) nunca
    emite em produção sem decisão explícita."""
    cur.execute("SELECT TOP 1 ambiente_nfe FROM controle_aux")
    row = cur.fetchone()
    val = row.get("ambiente_nfe") if isinstance(row, dict) else (row[0] if row else None)
    return "1" if val == 1 else "2"


def resolver_endpoint(cod_ibge: str, modelo: str, tp_amb: str, endpoints: dict) -> Optional[str]:
    """Resolve a URL de um webservice SEFAZ dado o dict `{modelo: {tp_amb: url}}`
    do serviço específico (recepção de evento, autorização, etc.) — só
    resolve UFs do grupo SVRS por enquanto (ver docstring do módulo)."""
    if cod_ibge not in UFS_SVRS:
        return None
    return endpoints.get(modelo, {}).get(tp_amb)


# Endpoints "consulta protocolo" (`NfeConsultaProtocolo4`) e "inutilização"
# (`NfeInutilizacao4`), versão 4.00, grupo SVRS — mesmo recorte de UF já
# documentado acima (`UFS_SVRS`). Confirmados direto no Portal SVRS
# (`dfe-portal.svrs.rs.gov.br/Nfe|Nfce/Servicos`): o par "65" (NFC-e) em
# 2026-08-19 (ao implementar Gestor NFCe), o par "55" (NF-e) em 2026-08-20
# (ao implementar Inutilização de Faixa NFe) — nunca inventados por padrão
# de nome. Movidos de `gestor_nfce_service.py` (onde só "65" existia) pra
# cá, pra serem compartilhados entre o lado NFC-e (`gestor_nfce_service.py`)
# e o lado NFe (`inutilizacao_nfe_service.py`).
ENDPOINTS_CONSULTA_PROTOCOLO = {
    "55": {
        "1": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "2": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
    },
    "65": {
        "1": "https://nfce.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "2": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
    },
}
ENDPOINTS_INUTILIZACAO = {
    "55": {
        "1": "https://nfe.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
        "2": "https://nfe-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
    },
    "65": {
        "1": "https://nfce.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
        "2": "https://nfce-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
    },
}
# Endpoints "recepção de evento" (`NFeRecepcaoEvento4`), versão 4.00,
# grupo SVRS — webservice único compartilhado por TODO evento de NFe/NFCe
# (cancelamento tpEvento 110111, carta de correção tpEvento 110110, etc.),
# só o corpo do `<evento>` muda por tipo. Extraído de
# `nfe_cancelamento_service.py` (onde vivia como `_ENDPOINTS_RECEPCAO_
# EVENTO`, só pro cancelamento) 2026-08-22, ao construir a Carta de
# Correção — mesmo mapa, reaproveitado pelos dois eventos em vez de
# duplicado.
ENDPOINTS_RECEPCAO_EVENTO = {
    "55": {
        "1": "https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
        "2": "https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    },
    "65": {
        "1": "https://nfce.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
        "2": "https://nfce-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    },
}

# MDF-e (modelo "58") — namespace/webservices próprios, diferentes de NF-e/
# NFC-e. Diferente do resto deste módulo, o MDF-e NÃO varia por UF: um único
# autorizador nacional (grupo SVRS) atende todo o Brasil pra MDF-e (achado
# confirmado ao rastrear `Backon.Controllers/NFe.vb::Transmitir_MDFe` —
# nenhuma tabela de UF é consultada ali, só ambiente produção/homologação).
# Endpoints confirmados por busca (fonte: portal.fazenda.sp.gov.br "URL
# WebServices" MDF-e) — mesmo padrão de confiança já usado nos endpoints
# NF-e acima, nunca inventados. Ver `mdfe_emissao_service.py`.
MDFE_NS = "http://www.portalfiscal.inf.br/mdfe"
ENDPOINTS_MDFE = {
    "autorizacao": {
        "1": "https://mdfe.svrs.rs.gov.br/ws/MDFeRecepcaoSinc/MDFeRecepcaoSinc.asmx",
        "2": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeRecepcaoSinc/MDFeRecepcaoSinc.asmx",
    },
    "evento": {
        "1": "https://mdfe.svrs.rs.gov.br/ws/mdferecepcaoevento/MDFeRecepcaoEvento.asmx",
        "2": "https://mdfe-homologacao.svrs.rs.gov.br/ws/mdferecepcaoevento/MDFeRecepcaoEvento.asmx",
    },
    "consulta": {
        "1": "https://mdfe.svrs.rs.gov.br/ws/mdfeconsulta/MDFeConsulta.asmx",
        "2": "https://mdfe-homologacao.svrs.rs.gov.br/ws/mdfeconsulta/MDFeConsulta.asmx",
    },
}


def resolver_endpoint_mdfe(servico: str, tp_amb: str) -> Optional[str]:
    """Resolve a URL do webservice MDF-e (`servico` = "autorizacao"/
    "evento"/"consulta") pro ambiente (`tp_amb` "1"=produção/"2"=
    homologação) — sem gating por UF (ver `ENDPOINTS_MDFE` acima)."""
    return ENDPOINTS_MDFE.get(servico, {}).get(tp_amb)


def montar_xml_inutilizacao(
    *, modelo: str, cod_ibge: str, cnpj: str, serie: str, numero_inicial: int, numero_final: int,
    motivo: str, tp_amb: str,
) -> tuple[bytes, str]:
    """`<inutNFe>` — layout público NFe 4.00 (`inutNFe_v4.00.xsd`), comum a
    NF-e (`modelo="55"`) e NFC-e (`modelo="65"`) — mesmo XSD, só o `<mod>`
    e o `Id` de `infInut` mudam. `Id`: "ID"+cUF(2)+ano(2)+CNPJ(14)+mod(2)+
    serie(3)+nNFIni(9)+nNFFin(9) — algoritmo público (MOC), mesma categoria
    de `montar_chave_acesso` já existente neste pacote. Generalizada
    2026-08-20 (antes só NFC-e, vivia em `gestor_nfce_service.py`) ao
    implementar o lado NFe — ver alias `gestor_nfce_service._montar_xml_
    inutilizacao` (modelo="65" fixo, preserva os testes já existentes)."""
    ano = datetime.now().strftime("%y")
    cnpj_num = cnpj.strip()
    # `Id` (atributo) usa serie(3) de largura FIXA (algoritmo público de
    # composição do Id, MOC) — mas o elemento `<serie>` do XML em si
    # NUNCA pode ter zero à esquerda (exceto o valor "0" sozinho): achado
    # ao vivo 2026-08-24 (rejeição real "Falha no schema XML [inutNFe/
    # infInut/serie]"), confirmado contra o XSD oficial
    # (`tiposBasico_v4.00.xsd`, `TSerie`, pattern `0|[1-9]{1}[0-9]{0,2}`)
    # — "001" não bate com esse padrão (só "0" sozinho, ou um número que
    # COMEÇA com dígito 1-9). Precisa de 2 formatações diferentes, nunca
    # reaproveitar a mesma variável pros dois usos.
    serie_id = str(int(serie or 0)).zfill(3)
    serie_xml = str(int(serie or 0))
    # Mesmo achado — `nNFIni`/`nNFFin` (`TNF`, pattern `[1-9]{1}[0-9]{0,8}`,
    # SEM exceção pro "0") também não podem ter zero à esquerda no
    # elemento, só no `Id`.
    ini_id = str(int(numero_inicial)).zfill(9)
    fim_id = str(int(numero_final)).zfill(9)
    ini_xml = str(int(numero_inicial))
    fim_xml = str(int(numero_final))
    id_inut = f"ID{cod_ibge}{ano}{cnpj_num}{modelo}{serie_id}{ini_id}{fim_id}"
    xml = (
        f'<inutNFe xmlns="{NFE_NS}" versao="4.00">'
        f'<infInut Id="{id_inut}">'
        f'<tpAmb>{tp_amb}</tpAmb>'
        f'<xServ>INUTILIZAR</xServ>'
        f'<cUF>{cod_ibge}</cUF>'
        f'<ano>{ano}</ano>'
        f'<CNPJ>{cnpj_num}</CNPJ>'
        f'<mod>{modelo}</mod>'
        f'<serie>{serie_xml}</serie>'
        f'<nNFIni>{ini_xml}</nNFIni>'
        f'<nNFFin>{fim_xml}</nNFFin>'
        f'<xJust>{escapar_xml(motivo)}</xJust>'
        f'</infInut>'
        f'</inutNFe>'
    ).encode("utf-8")
    return xml, id_inut


def resolver_usuario_texto_sync(cur, usuario: Optional[int]) -> Optional[str]:
    """Nome de exibição do funcionário que fez uma ação (`nome_guerra`,
    mesma regra global "nome do vendedor" já aplicada em todo o resto do
    sistema — CLAUDE.md "Nome do Vendedor"), usado por tabelas legadas cuja
    coluna `usuario` é texto livre (não FK), como `inutilizacao_nfe`
    (armazenava `Trim(UCase(UsuarioAtual))` no VB6). `usuario` aqui é
    `funcionarios.codigo_int` (mesma convenção de `usuario_alteracao` em
    todo o resto do backend) — resolvido pra nome só na hora de gravar,
    sem round-trip quando `usuario` vem vazio."""
    if not usuario:
        return None
    cur.execute(
        "SELECT COALESCE(NULLIF(nome_guerra, ''), nome) AS nome FROM funcionarios WHERE codigo_int = %s",
        (usuario,),
    )
    row = cur.fetchone()
    nome = (row.get("nome") if row else None) or ""
    return nome.strip() or str(usuario)


def escapar_xml(texto: str) -> str:
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def gerar_qrcode_png_base64(texto: str) -> str:
    """Gera um QR Code PNG (base64) a partir de um texto/URL arbitrário —
    mesmo padrão já usado por `equipamentos_service._gerar_qrcode_sync`
    (`qrcode.make(...)` → PNG em `BytesIO` → base64), generalizado aqui
    pra qualquer conteúdo em vez de um prefixo fixo. Usado pra desenhar o
    QR Code real do Extrato NFC-e (`danfeFacsimile.ts::buildDanfceHtml`)
    a partir da URL já montada por `nfe_emissao_service.montar_url_
    qrcode` — o conteúdo do QR (a própria URL de consulta) já é
    especificação pública, esta função só desenha a imagem."""
    import base64
    import io

    import qrcode

    img = qrcode.make(texto)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


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


class _XMLSignerPermiteSha1(XMLSigner):
    """`signxml.XMLSigner` recusa SHA-1 por padrão (`check_deprecated_
    methods`, chamado no `__init__`) — hook de instância pensado pra ser
    sobrescrito, não uma trava obscura. Usado só quando o próprio SEFAZ
    EXIGE SHA-1 (MDF-e — ver achado abaixo), nunca por preferência."""

    def check_deprecated_methods(self):
        pass


def assinar_xml(
    xml_bytes: bytes, id_referencia: str, key_pem: bytes, cert_pem: bytes, *, sha1: bool = False,
    sem_prefixo: bool = False,
) -> bytes:
    """Assinatura XMLDSig enveloped + C14N — mesmo padrão de `Assinar`
    (`Backon.Controllers/NFe.vb:3335`), RSA-SHA256 por padrão em vez de
    SHA1 (ver docstring do módulo). `id_referencia` é o `Id` do elemento
    assinado (`infEvento` no cancelamento, `infNFe`/`infNFCe` na emissão,
    `infMDFe`/`infEvento` no MDF-e, `infDPS` na NFS-e).

    **`sha1=True`, achado ao vivo 2026-08-22 (1ª emissão real de MDF-e,
    ARGEN TESTE)**: SEFAZ recusou com "Falha no schema XML [The value of
    the 'Algorithm' attribute does not equal its fixed value]" — o XSD do
    MDF-e (layout 3.00) ainda fixa `SignatureMethod`/`DigestMethod` em
    SHA-1 (`http://www.w3.org/2000/09/xmldsig#rsa-sha1`), diferente do
    NF-e/NFC-e/CC-e (que aceitam SHA-256, já testado — schemas migrados
    em ritmos diferentes por documento). **Só usar `sha1=True` pro
    MDF-e** — não generalizar pros outros documentos sem confirmar o
    mesmo erro contra o schema deles primeiro.

    **`sem_prefixo=True`, achado ao vivo 2026-08-23 (1ª emissão real de
    NFS-e, ADN/Sefin Nacional)**: rejeitado com "E1228 - Xml declarado
    com prefixo de namespace" pro `<ds:Signature>` padrão do signxml —
    confirmado (busca web, manual técnico do Sistema Nacional NFS-e) que
    o ADN **não aceita nenhum elemento com prefixo de namespace em lugar
    nenhum do documento**, diferente de NF-e/NFC-e/MDF-e (onde
    `ds:Signature` sempre foi aceito normalmente). Delega pra
    `_assinar_xml_manual_sem_prefixo` — ver a docstring dela pro porquê
    de NÃO usar `signxml.XMLSigner` com `namespaces={None: ds}` (parece
    a solução óbvia, documentada até no próprio `_ds_tag` do signxml, mas
    achado ao vivo que produz assinatura **inválida**, não só "com
    prefixo diferente"). **Só usar pra NFS-e** — não generalizar pros
    outros documentos sem confirmar a mesma exigência."""
    if sem_prefixo:
        return _assinar_xml_manual_sem_prefixo(xml_bytes, id_referencia, key_pem, cert_pem)
    root = etree.fromstring(xml_bytes)
    cls = _XMLSignerPermiteSha1 if sha1 else XMLSigner
    signer = cls(
        method=signxml.methods.enveloped,
        signature_algorithm="rsa-sha1" if sha1 else "rsa-sha256",
        digest_algorithm="sha1" if sha1 else "sha256",
        c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )
    signed_root = signer.sign(root, key=key_pem, cert=cert_pem, reference_uri=f"#{id_referencia}")
    return etree.tostring(signed_root, xml_declaration=True, encoding="UTF-8")


_DS_URI = "http://www.w3.org/2000/09/xmldsig#"


def _c14n_sem_xmlns_vazio(el) -> bytes:
    """`etree.tostring(el, method="c14n")` do lxml tem um bug de longa
    data (reconhecido pelo próprio `signxml` — ver `XMLSigner._c14n`,
    parâmetro `excise_empty_xmlns_declarations`, comentário citando
    https://github.com/XML-Security/signxml/issues/193): ao canonicalizar
    um elemento que HERDA um namespace padrão (sem prefixo) de um
    ancestral fora do próprio elemento sendo serializado, o lxml insere
    `xmlns=""` espúrio em cada descendente que só herda (nunca declara o
    próprio) — mudando os bytes, e portanto o digest, de forma
    incompatível com qualquer implementação de C14N que siga a RFC à
    risca (`http://www.w3.org/TR/xml-c14n2/#sec-Namespace-Processing`).
    `signxml` deixa esse expurgo DESLIGADO por padrão
    (`excise_empty_xmlns_declarations=False`) — não afeta NF-e/NFC-e/
    MDF-e/CC-e porque lá a assinatura E a verificação sempre passam pela
    MESMA função internamente (auto-consistente mesmo com o bug). Aqui a
    assinatura é montada manualmente (concatenação de string, sem
    `signxml.XMLSigner`) — sem esse expurgo, o digest que EU calculo (via
    `etree.tostring`) diverge do que `XMLVerifier`/qualquer verificador
    de verdade recalcula, confirmado ao vivo 2026-08-23 (1ª tentativa de
    NFS-e: `InvalidDigest`, mesmo com a assinatura em si válida)."""
    return etree.tostring(el, method="c14n").replace(b' xmlns=""', b"")


def _assinar_xml_manual_sem_prefixo(xml_bytes: bytes, id_referencia: str, key_pem: bytes, cert_pem: bytes) -> bytes:
    """Assinatura XMLDSig enveloped + C14N (RSA-SHA256) construída
    manualmente por concatenação de string, sem nenhum prefixo de
    namespace em lugar nenhum (`xmlns="{_DS_URI}"` direto em CADA
    elemento da assinatura, nunca `ds:Tag`) — exigência real do ADN/
    Sefin Nacional pra NFS-e (achado ao vivo 2026-08-23, ver docstring de
    `assinar_xml`).

    **Por que não usar `signxml.XMLSigner(namespaces={{None: ds_uri}})`**
    (a forma "óbvia", documentada no próprio `_ds_tag` do signxml pra
    produzir assinatura sem prefixo): testado ao vivo e a assinatura
    resultante **falha na própria verificação do signxml**
    (`XMLVerifier().verify()` recusa até um XML trivial assinado assim,
    e o motivo raiz é exatamente o bug do lxml documentado em
    `_c14n_sem_xmlns_vazio` acima — `signxml.XMLSigner._c14n` não liga o
    próprio expurgo por padrão, então mesmo o caminho "oficial" do
    signxml tropeça nisso quando forçado a não usar prefixo). A montagem
    manual aqui usa `_c14n_sem_xmlns_vazio` em TODO ponto de
    canonicalização (digest do elemento referenciado E do `SignedInfo`
    antes de assinar) — com isso, testado ao vivo e verificado
    corretamente por `XMLVerifier().verify()` mesmo sem nenhum prefixo em
    lugar nenhum do documento. Declarar `xmlns="{_DS_URI}"`
    explicitamente em cada elemento (em vez de confiar só em herança) é
    reforço adicional, não a causa raiz da correção — mantido porque
    deixa o XML resultante mais robusto a qualquer outra implementação de
    C14N que use `excise_empty_xmlns_declarations`-like diferente."""
    root = etree.fromstring(xml_bytes)
    alvo = root.xpath(f"//*[@Id='{id_referencia}']")
    if not alvo:
        raise ValueError(f"Elemento com Id='{id_referencia}' não encontrado no XML a assinar.")
    digest_input = _c14n_sem_xmlns_vazio(alvo[0])
    digest_b64 = base64.b64encode(hashlib.sha256(digest_input).digest()).decode("ascii")

    signed_info_str = (
        f'<SignedInfo xmlns="{_DS_URI}">'
        f'<CanonicalizationMethod xmlns="{_DS_URI}" Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f'<SignatureMethod xmlns="{_DS_URI}" Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>'
        f'<Reference xmlns="{_DS_URI}" URI="#{id_referencia}">'
        f'<Transforms xmlns="{_DS_URI}">'
        f'<Transform xmlns="{_DS_URI}" Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>'
        f'<Transform xmlns="{_DS_URI}" Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f"</Transforms>"
        f'<DigestMethod xmlns="{_DS_URI}" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
        f'<DigestValue xmlns="{_DS_URI}">{digest_b64}</DigestValue>'
        f"</Reference>"
        f"</SignedInfo>"
    )
    signed_info_c14n = _c14n_sem_xmlns_vazio(etree.fromstring(signed_info_str.encode("utf-8")))

    chave_privada = serialization.load_pem_private_key(key_pem, password=None)
    assinatura = chave_privada.sign(signed_info_c14n, asym_padding.PKCS1v15(), hashes.SHA256())
    assinatura_b64 = base64.b64encode(assinatura).decode("ascii")

    certificado = x509.load_pem_x509_certificate(cert_pem)
    cert_der_b64 = base64.b64encode(certificado.public_bytes(serialization.Encoding.DER)).decode("ascii")

    bloco_assinatura = (
        signed_info_str
        + f'<SignatureValue xmlns="{_DS_URI}">{assinatura_b64}</SignatureValue>'
        + f'<KeyInfo xmlns="{_DS_URI}"><X509Data xmlns="{_DS_URI}">'
        + f'<X509Certificate xmlns="{_DS_URI}">{cert_der_b64}</X509Certificate>'
        + f"</X509Data></KeyInfo>"
    )
    bloco_assinatura = f'<Signature xmlns="{_DS_URI}">{bloco_assinatura}</Signature>'

    tag_local = alvo[0].tag.split("}")[-1] if alvo[0].tag.startswith("{") else alvo[0].tag
    marcador_fechamento = f"</{tag_local}>".encode("utf-8")
    if marcador_fechamento not in xml_bytes:
        raise ValueError(f"Marcador de fechamento '{marcador_fechamento!r}' não encontrado — não foi possível posicionar a assinatura.")
    xml_final = xml_bytes.replace(marcador_fechamento, marcador_fechamento + bloco_assinatura.encode("utf-8"), 1)
    # Declaração `<?xml ...?>` explícita — achado ao vivo 2026-08-23
    # (2ª tentativa real de NFS-e): sem ela, o ADN recusa com "E1229 -
    # Xml não está utilizando codificação UTF-8" (não consegue detectar a
    # codificação sem a declaração, mesmo o XML já sendo UTF-8 de fato).
    # Aspas duplas (não simples, ao contrário do padrão do próprio lxml
    # em `etree.tostring(..., xml_declaration=True)`) — forma mais comum/
    # esperada por validadores estritos.
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_final


def montar_envelope_soap(corpo_interno: bytes, wsdl_service: str, ns: str = NFE_NS, tag: str = "nfeDadosMsg") -> bytes:
    """Envelope SOAP 1.2 genérico — `corpo_interno` é o XML já pronto
    (`envEvento`/`enviNFe`/`consSitNFe`, já assinado quando aplicável) e
    `wsdl_service` é o nome do serviço WSDL alvo (ex.: "NFeRecepcaoEvento4"
    pro cancelamento, "NFeAutorizacao4" pra emissão). `ns`/`tag` têm default
    NF-e (preserva 100% o comportamento já usado por NF-e/NFC-e/CC-e) —
    MDF-e passa `ns=MDFE_NS, tag="mdfeDadosMsg"` (ver `mdfe_emissao_service.py`)."""
    corpo = corpo_interno.decode("utf-8") if isinstance(corpo_interno, bytes) else corpo_interno
    # `\s*` depois da declaração — achado ao vivo 2026-08-23 (1ª emissão
    # real de NFC-e): `lxml.etree.tostring(..., xml_declaration=True)`
    # sempre insere um `\n` logo após `<?xml ...?>`; sem consumir esse
    # `\n` junto, ele sobra como texto solto ENTRE tags do envelope SOAP
    # (`<indSinc>1</indSinc>\n<NFe...>`) — SEFAZ recusa com "Nao eh
    # permitida a presenca de caracteres de edicao... entre as tags da
    # mensagem" (rejeição 588). Mesmo padrão de bug repetido em
    # `nfe_emissao_service.py`/`nfe_correcao_service.py`/
    # `nfe_cancelamento_service.py` — corrigido nos 4 ao mesmo tempo.
    corpo = re.sub(r"^<\?xml[^>]*\?>\s*", "", corpo)
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="{SOAP_NS}">'
        '<soap12:Body>'
        f'<{tag} xmlns="{ns}/wsdl/{wsdl_service}">{corpo}</{tag}>'
        '</soap12:Body>'
        '</soap12:Envelope>'
    )
    return envelope.encode("utf-8")


def montar_envelope_soap_gzip_b64(xml_bytes: bytes, wsdl_service: str, ns: str, tag: str = "mdfeDadosMsg") -> bytes:
    """Variante exigida só pela autorização síncrona do MDF-e
    (`MDFeRecepcaoSinc`) — MOC MDF-e (Confaz/SPED) exige o XML assinado
    comprimido em GZIP e convertido pra Base64 antes de entrar no envelope
    SOAP (confirmado também na DLL legada, `Backon.Controllers/NFe.vb`
    `Transmitir_MDFe` `Case 1`: `compactaArquivo` + `ConvertFileToBase64`
    antes de `mdfeRecepcao(mdfebase64)`) — nenhum outro webservice fiscal
    já integrado neste projeto (NF-e/NFC-e/CC-e/eventos MDF-e) faz isso,
    por isso é uma função separada de `montar_envelope_soap`, não um `if`
    a mais nela."""
    import base64
    import gzip

    b64 = base64.b64encode(gzip.compress(xml_bytes)).decode("ascii")
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="{SOAP_NS}">'
        '<soap12:Body>'
        f'<{tag} xmlns="{ns}/wsdl/{wsdl_service}">{b64}</{tag}>'
        '</soap12:Body>'
        '</soap12:Envelope>'
    )
    return envelope.encode("utf-8")


def transmitir(
    envelope: bytes, endpoint: str, key_pem: bytes, cert_pem: bytes, timeout: int = 30,
    soap_action: Optional[str] = None,
) -> str:
    """POST do envelope SOAP pro SEFAZ, autenticado com o certificado
    cliente (TLS mútuo — mesmo `WSNfeRecepcaoEvento.ClientCertificates.Add`
    do proxy .NET). `requests` só aceita certificado via caminho de
    arquivo, por isso os PEMs são gravados num arquivo temporário (apagado
    logo depois, nunca persistido em disco por mais tempo que o necessário
    pra fazer a chamada).

    `soap_action` — achado ao vivo 2026-08-23/24 (1ª consulta real de
    situação, `NfeConsultaProtocolo4`): sem o parâmetro `action` no
    `Content-Type`, o SVRS recusa com "Unable to handle request without a
    valid action parameter. Please supply a valid soap action." — mas
    NENHUM dos webservices de autorização/evento já usados o dia inteiro
    (NFeAutorizacao4/NFeRecepcaoEvento4/MDFe/CC-e) precisou disso, todos
    funcionaram normalmente sem `action` nenhum. Por isso o parâmetro é
    OPCIONAL (default `None` = omite o header, preserva 100% o
    comportamento já testado dos outros serviços) — só os call sites de
    CONSULTA precisam passar o valor real (formato confirmado ao vivo:
    `"{ns}/wsdl/{wsdl_service}/{nomeDaOperacao}"`, ex.:
    `"http://www.portalfiscal.inf.br/nfe/wsdl/NfeConsultaProtocolo4/nfeConsultaNF"`
    — o nome da operação, ao contrário do serviço, não é derivável
    genericamente, então não dá pra montar isso automaticamente aqui
    dentro sem o chamador informar)."""
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_cert, \
         tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_key:
        f_cert.write(cert_pem)
        f_key.write(key_pem)
        cert_path, key_path = f_cert.name, f_key.name
    try:
        content_type = "application/soap+xml; charset=utf-8"
        if soap_action:
            content_type += f'; action="{soap_action}"'
        resp = requests.post(
            endpoint, data=envelope,
            headers={"Content-Type": content_type},
            cert=(cert_path, key_path), timeout=timeout, verify=_ca_bundle_path(),
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


def resolver_endereco_emitente_sync(cur) -> dict:
    """Endereço completo + IE da própria empresa (`controle`), com
    resolução de município real (mesmo padrão de `mdfe_service._resolver_
    origem_empresa_sync`, generalizado aqui pra qualquer documento fiscal
    que precise montar `<enderEmit>` — achado ao vivo 2026-08-23: a NFC-e
    nunca incluía `<enderEmit>`/`<IE>` no `<emit>`, SEFAZ recusa por
    schema incompleto)."""
    cur.execute(
        "SELECT inscr_est, endereco, numero, complemento, bairro, cep, cidade, uf, telefone FROM controle"
    )
    row = cur.fetchone() or {}
    cidade = (row.get("cidade") or "").strip()
    uf = (row.get("uf") or "").strip().upper()
    cod_municipio = None
    try:
        cur.execute(
            "SELECT TOP 1 municipio.codigo AS codmun FROM municipio, UF "
            "WHERE municipio.descricao = %s AND UF.codigo = %s "
            "AND LEFT(RTRIM(LTRIM(STR(municipio.codigo))), 2) = UF.Cod_Ibge",
            (cidade, uf),
        )
        r = cur.fetchone()
        if r:
            cod_municipio = r.get("codmun")
    except Exception:
        cod_municipio = None
    if not cod_municipio:
        cod_municipio = resolver_cod_municipio_ibge(cidade, uf)
    try:
        cod_municipio = int(float(cod_municipio)) if cod_municipio is not None else None
    except (TypeError, ValueError):
        cod_municipio = None
    return {**row, "cidade": cidade, "uf": uf, "cod_municipio": cod_municipio}


def parse_dh_sefaz(texto: Optional[str]) -> Optional[datetime]:
    """Converte um `dhRecbto`/`dhRegEvento`/`dhEvento` cru da resposta do
    SEFAZ (ISO 8601 COM offset, ex.: "2026-08-23T00:54:32-03:00") pro
    `datetime` NAIVE que uma coluna `DATETIME` do SQL Server aceita —
    achado ao vivo 2026-08-23 (1ª emissão real de MDF-e autorizada de
    verdade): gravar a string crua (com o sufixo `-03:00`) numa coluna
    `DATETIME` derruba com "Conversion failed when converting date
    and/or time from character string" — e como esse `UPDATE` só roda
    DEPOIS do SEFAZ confirmar sucesso (`cStat==100`), a falha acontecia
    tarde o bastante pra derrubar a transação inteira (rollback), perdendo
    o registro local de um documento fiscal JÁ REALMENTE AUTORIZADO em
    produção — mesmo padrão de risco já resolvido pra `dhemi` (gravado
    como `datetime.now()` puro, nunca string), aqui generalizado pra
    qualquer timestamp que volte do SEFAZ. Descarta o offset (mantém só o
    horário local, que é o que a string já representa)."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=None)
    except ValueError:
        return None


def extrair_bloco(xml_texto: str, tag: str) -> Optional[str]:
    """Como `extrair_tag`, mas devolve o elemento INTEIRO (com suas
    próprias tags de abertura/fechamento, atributos incluídos) em vez de
    só o conteúdo interno — usado quando o bloco extraído precisa ser
    reencaixado como está em outro XML (ex.: `<protMDFe>` da resposta do
    SEFAZ, reencaixado dentro do `mdfeProc` final do MDF-e)."""
    m = re.search(rf"<{tag}[ >].*?</{tag}>", xml_texto, re.DOTALL)
    if m:
        return m.group(0)
    m = re.search(rf"<{tag}/>", xml_texto)
    return m.group(0) if m else None


def consultar_json_mtls(endpoint: str, key_pem: bytes, cert_pem: bytes, timeout: int = 30) -> dict:
    """GET autenticado por TLS mútuo — mesmo padrão de `transmitir_json_
    mtls`, mas pra consulta (sem corpo). Usado pra "Recuperar Informações"
    do Gestor NFSe (2026-08-20) — `Backon_Controllers.NFSeDPS.
    RetornaXMLDANFEDPS` (`NFSeDPS.vb:705,738`) faz exatamente essa
    chamada, `GET https://sefin.nfse.gov.br/SefinNacional/nfse/{chave}`,
    sem payload."""
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_cert, \
         tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_key:
        f_cert.write(cert_pem)
        f_key.write(key_pem)
        cert_path, key_path = f_cert.name, f_key.name
    try:
        resp = requests.get(endpoint, cert=(cert_path, key_path), timeout=timeout, verify=_ca_bundle_path())
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


def consultar_binario_mtls(endpoint: str, key_pem: bytes, cert_pem: bytes, timeout: int = 30) -> bytes:
    """GET autenticado por TLS mútuo devolvendo o corpo BINÁRIO da resposta
    (não JSON) — usado pro download do DANFE em PDF do Gestor NFSe
    (`GET https://adn.nfse.gov.br/danfse/{chave}`, host `adn.`, diferente
    do `sefin.` usado pra consulta/transmissão — confirmado no rastreio
    de "Recuperar Informações", mesma exigência de certificado como client
    cert TLS que todo o resto do ADN). Mesmo padrão de arquivo temporário
    de `consultar_json_mtls`/`transmitir_json_mtls`, mas sem tentar
    decodificar JSON — levanta em qualquer erro HTTP."""
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_cert, \
         tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f_key:
        f_cert.write(cert_pem)
        f_key.write(key_pem)
        cert_path, key_path = f_cert.name, f_key.name
    try:
        resp = requests.get(endpoint, cert=(cert_path, key_path), timeout=timeout, verify=_ca_bundle_path())
        resp.raise_for_status()
        return resp.content
    finally:
        for p in (cert_path, key_path):
            try:
                os.remove(p)
            except OSError:
                pass


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
            cert=(cert_path, key_path), timeout=timeout, verify=_ca_bundle_path(),
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
