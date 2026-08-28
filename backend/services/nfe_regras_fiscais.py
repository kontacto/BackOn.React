"""Motor de Regras Fiscais — grupo `ICMSUFDest` (DIFAL) + validações de
consistência fiscal que crescem com o tempo, sem precisar remexer o motor
de emissão a cada achado novo (ver PENDENCIAS.md > "Taxas — DIFAL/
ICMSUFDest no motor de emissão" pro achado que motivou este módulo:
rejeição 695 real no SEFAZ, e a descoberta de que o grupo ICMSUFDest não
era construído em lugar nenhum do backend Python).

**Fontes oficiais citadas neste módulo** (nunca inventar campo/fórmula —
ver CLAUDE.md > "Papel Kelvin"):
- NT 2015.003 (ENCAT/SEFAZ, Ago/2015) — texto completo lido do PDF oficial
  (nfe.fazenda.gov.br/portal, mirror cieam.com.br) — cria o grupo
  `ICMSUFDest`, define as 3 condições de obrigatoriedade (regras NA01-20/
  NA01-30) e as fórmulas de `vICMSUFDest`/`vICMSUFRemet` (regras NA11-10/
  NA13-10). Também define a incompatibilidade de CSOSN com Consumidor
  Final (regra N12a-70).
- Ordem exata dos campos (XSD `leiauteNFe_v4.00.xsd`, mirror
  nfephp-org/sped-nfe, baixado e conferido campo a campo 2026-08-28):
  grupo por item = `vBCUFDest, vBCFCPUFDest?, pFCPUFDest?, pICMSUFDest,
  pICMSInter, pICMSInterPart, vFCPUFDest?, vICMSUFDest, vICMSUFRemet`
  (campos com `?` são opcionais, minOccurs=0); totais em `<ICMSTot>` =
  `vFCPUFDest?, vICMSUFDest?, vICMSUFRemet?` logo depois de `vICMSDeson`
  (não perto de `vNF` — confirmado direto no XSD, não por resumo de
  terceiro).
- FCP: fórmula `vFCPUFDest = vBCFCPUFDest * pFCPUFDest / 100` — assume
  `vBCFCPUFDest = vBCUFDest` (convenção comum quando não há base reduzida
  específica pro FCP; se algum estado exigir base diferente, ajustar
  aqui, não nos chamadores).

**Como adicionar uma regra fiscal nova** (é assim que este módulo
"aprende" sem precisar reescrever o motor de emissão):
1. Confirme a regra em fonte oficial (NT da NF-e, Ajuste SINIEF, Convênio
   ICMS, MOC) — nunca a partir de suposição.
2. Escreva uma função `_verificar_<nome>(contexto: dict) -> Optional[str]`
   — devolve a mensagem de erro (português, sem jargão técnico) se a
   regra for violada, `None` se estiver tudo certo. `contexto` tem o
   formato de `montar_contexto_validacao` abaixo.
3. Adicione um `RegraFiscal(...)` à lista `REGRAS_CONSISTENCIA`, citando
   a fonte oficial no campo `fonte`.
4. Cubra com teste em `test_nfe_regras_fiscais.py`.
`nfe_emissao_service.py` nunca precisa ser tocado pra uma regra nova —
só chama `validar_regras_fiscais(contexto)` uma vez, já cobre a lista
inteira.
"""
from dataclasses import dataclass
from typing import Callable, Optional


# =============================================================================
# Grupo ICMSUFDest (DIFAL) — construção por item.
# =============================================================================

def grupo_icms_uf_dest_aplicavel(id_dest: str, ind_final: str, ind_ie_dest: str) -> bool:
    """As 3 condições da NT 2015.003 (regras NA01-20/NA01-30) — só as 3
    JUNTAS decidem se o grupo é obrigatório (True) ou proibido (False).
    Deriva sempre de dados reais (UF do destinatário vs. emitente,
    `cliente.consumidor_final`, `cliente.não_contribuinte` via
    `indIEDest`) — nunca de um campo/checkbox digitado à mão na Taxa, que
    foi exatamente a causa da rejeição 695 real (Taxa com o grupo
    preenchido fora dessa combinação)."""
    return id_dest == "2" and ind_final == "1" and ind_ie_dest == "9"


def montar_grupo_icms_uf_dest_item(id_dest: str, ind_final: str, ind_ie_dest: str, item: dict) -> dict:
    """Monta o grupo `<ICMSUFDest>` de 1 item (vai dentro de
    `<det><imposto>`, logo depois de `</ICMS>`) — devolve também os 3
    valores já calculados, pra quem chama somar em `<ICMSTot>`.

    `item` precisa ter `valor_total` (usado como base de cálculo —
    "normalmente a BC é a mesma pro remetente e pro destinatário",
    NT 2015.003) e as 4 colunas de `taxas` já resolvidas:
    `aliquota_interestadual`, `aliquota_interna_destino`,
    `percentual_origem`, `fundo_pobreza`.

    Quando as 3 condições não batem, devolve tudo zerado e `xml=""` — é
    isso que evita a rejeição 695 (grupo presente indevidamente)."""
    vazio = {"xml": "", "v_icms_uf_dest": 0.0, "v_icms_uf_remet": 0.0, "v_fcp_uf_dest": 0.0}
    if not grupo_icms_uf_dest_aplicavel(id_dest, ind_final, ind_ie_dest):
        return vazio

    v_bc = float(item.get("valor_total") or 0)
    p_icms_uf_dest = float(item.get("aliquota_interna_destino") or 0)
    p_icms_inter = float(item.get("aliquota_interestadual") or 0)
    # `percentual_origem` é a fatia que fica com a UF de ORIGEM (rótulo já
    # confirmado/corrigido em apuracao_fiscal_service.py) — pICMSInterPart
    # é o percentual do DESTINO, o complemento. Desde 2019 tende a 0
    # (destino fica com 100%), mas a fórmula respeita o que a Taxa tiver.
    p_icms_inter_part = 100 - float(item.get("percentual_origem") or 0)
    p_fcp_uf_dest = float(item.get("fundo_pobreza") or 0)

    # Fórmula literal da NT 2015.003 (regras NA11-10/NA13-10).
    diferenca = p_icms_uf_dest - p_icms_inter
    if diferenca > 0:
        v_icms_uf_dest = round(v_bc * diferenca / 100 * p_icms_inter_part / 100, 2)
        v_icms_uf_remet = (
            0.0 if p_icms_inter_part >= 100
            else round(v_bc * diferenca / 100 * (100 - p_icms_inter_part) / 100, 2)
        )
    else:
        v_icms_uf_dest = 0.0
        v_icms_uf_remet = 0.0
    v_fcp_uf_dest = round(v_bc * p_fcp_uf_dest / 100, 2) if p_fcp_uf_dest else 0.0

    fcp_campos = (
        f"<vBCFCPUFDest>{v_bc:.2f}</vBCFCPUFDest><pFCPUFDest>{p_fcp_uf_dest:.2f}</pFCPUFDest>"
        if p_fcp_uf_dest else ""
    )
    xml = (
        "<ICMSUFDest>"
        f"<vBCUFDest>{v_bc:.2f}</vBCUFDest>"
        f"{fcp_campos}"
        f"<pICMSUFDest>{p_icms_uf_dest:.2f}</pICMSUFDest>"
        f"<pICMSInter>{p_icms_inter:.2f}</pICMSInter>"
        f"<pICMSInterPart>{p_icms_inter_part:.2f}</pICMSInterPart>"
        f"{f'<vFCPUFDest>{v_fcp_uf_dest:.2f}</vFCPUFDest>' if p_fcp_uf_dest else ''}"
        f"<vICMSUFDest>{v_icms_uf_dest:.2f}</vICMSUFDest>"
        f"<vICMSUFRemet>{v_icms_uf_remet:.2f}</vICMSUFRemet>"
        "</ICMSUFDest>"
    )
    return {"xml": xml, "v_icms_uf_dest": v_icms_uf_dest, "v_icms_uf_remet": v_icms_uf_remet, "v_fcp_uf_dest": v_fcp_uf_dest}


def montar_totais_icms_uf_dest_xml(v_icms_uf_dest_total: float, v_icms_uf_remet_total: float, v_fcp_uf_dest_total: float) -> str:
    """Fragmento pra inserir dentro de `<ICMSTot>`, logo depois de
    `</vICMSDeson>` (posição confirmada no XSD oficial, não perto de
    `vNF`). Campos opcionais (`minOccurs=0`) — omitidos quando não há
    DIFAL na nota (nenhum item ativou o grupo)."""
    partes = []
    if v_fcp_uf_dest_total:
        partes.append(f"<vFCPUFDest>{v_fcp_uf_dest_total:.2f}</vFCPUFDest>")
    if v_icms_uf_dest_total or v_icms_uf_remet_total:
        partes.append(f"<vICMSUFDest>{v_icms_uf_dest_total:.2f}</vICMSUFDest>")
        partes.append(f"<vICMSUFRemet>{v_icms_uf_remet_total:.2f}</vICMSUFRemet>")
    return "".join(partes)


# =============================================================================
# Regras de consistência — bloqueiam a emissão ANTES de gastar a chamada ao
# SEFAZ, com mensagem amigável (mesmo padrão de retorno de todo o pacote
# fiscal: `{"success": False, "message": ...}`).
# =============================================================================

def _verificar_taxa_difal_configurada(contexto: dict) -> Optional[str]:
    """Regra NA01-20 (NT 2015.003) — se as 3 condições batem mas a Taxa
    resolvida pro item não tem as alíquotas de DIFAL preenchidas, o grupo
    seria montado com valores zerados (XML válido, mas DIFAL real não
    seria recolhido — gap silencioso). Bloqueia e aponta o item, em vez
    de deixar a nota sair com imposto devido a zero."""
    id_dest, ind_final, ind_ie_dest = contexto["id_dest"], contexto["ind_final"], contexto["ind_ie_dest"]
    if not grupo_icms_uf_dest_aplicavel(id_dest, ind_final, ind_ie_dest):
        return None
    for i, item in enumerate(contexto.get("itens") or [], start=1):
        aliq_dest = float(item.get("aliquota_interna_destino") or 0)
        aliq_inter = float(item.get("aliquota_interestadual") or 0)
        if aliq_dest <= 0 or aliq_inter <= 0:
            return (
                f"Item {i} ({item.get('codigo_int') or '?'}): esta é uma venda interestadual para "
                "consumidor final não contribuinte (ativa o Diferencial de Alíquota — DIFAL), mas a Taxa "
                "cadastrada para este produto/UF não tem a Alíquota Interestadual/Interna de Destino "
                "preenchida. Cadastre a Taxa correta antes de emitir (Gestor Fiscal > Taxas)."
            )
    return None


_CSOSN_INCOMPATIVEIS_CONSUMIDOR_FINAL = {"101", "201", "202", "203", "900"}


def _verificar_csosn_consumidor_final(contexto: dict) -> Optional[str]:
    """Regra N12a-70 (NT 2015.003) — nas mesmas 3 condições, esses 5
    CSOSN nunca são compatíveis com venda a consumidor final não
    contribuinte. Regra irmã N12-70 (CST incompatível) não se aplica a
    este app — a emissão hoje só monta `<ICMSSN102>` (Simples Nacional),
    nunca CST de regime normal."""
    id_dest, ind_final, ind_ie_dest = contexto["id_dest"], contexto["ind_final"], contexto["ind_ie_dest"]
    if not grupo_icms_uf_dest_aplicavel(id_dest, ind_final, ind_ie_dest):
        return None
    for i, item in enumerate(contexto.get("itens") or [], start=1):
        csosn = str(item.get("csosn") or "").strip()
        if csosn in _CSOSN_INCOMPATIVEIS_CONSUMIDOR_FINAL:
            return (
                f"Item {i} ({item.get('codigo_int') or '?'}): CSOSN {csosn} não pode ser usado numa venda "
                "interestadual para consumidor final não contribuinte — o SEFAZ rejeita essa combinação. "
                "Ajuste o CSOSN cadastrado para este item."
            )
    return None


@dataclass(frozen=True)
class RegraFiscal:
    codigo_rejeicao: str
    nome: str
    fonte: str
    verificar: Callable[[dict], Optional[str]]


REGRAS_CONSISTENCIA: list[RegraFiscal] = [
    RegraFiscal(
        codigo_rejeicao="695",
        nome="Taxa sem alíquota de DIFAL configurada",
        fonte="NT 2015.003 (ENCAT/SEFAZ, ago/2015), regra NA01-20",
        verificar=_verificar_taxa_difal_configurada,
    ),
    RegraFiscal(
        codigo_rejeicao="N12a-70",
        nome="CSOSN incompatível com Consumidor Final",
        fonte="NT 2015.003 (ENCAT/SEFAZ, ago/2015), regra N12a-70",
        verificar=_verificar_csosn_consumidor_final,
    ),
    # Próximas regras candidatas, MESMA fonte já lida na íntegra — NÃO
    # implementadas ainda (não pedidas explicitamente, ver PENDENCIAS.md):
    # - NA07-20/NA07-30: alíquota interestadual (4/7/12%) incompatível
    #   com a origem do produto/UF envolvidas.
    # - NA09-10: percentual de partilha (pICMSInterPart) incompatível com
    #   o ano da emissão (hoje sempre 100, "a partir de 2019").
]


def validar_regras_fiscais(contexto: dict) -> Optional[dict]:
    """Roda todas as regras registradas, devolve a primeira falha (mesmo
    formato `{"success": False, "message": ...}` do resto do pacote
    fiscal) ou `None` se tudo passar. Chamada 1x por `emitir_nfe_sync`,
    antes de montar/assinar o XML."""
    for regra in REGRAS_CONSISTENCIA:
        mensagem = regra.verificar(contexto)
        if mensagem:
            return {"success": False, "message": mensagem}
    return None


def montar_contexto_validacao(id_dest: str, ind_final: str, ind_ie_dest: str, itens: list[dict]) -> dict:
    """Monta o dict padrão que toda regra registrada recebe — ponto único
    de montagem pra não cada chamador inventar o formato na mão."""
    return {"id_dest": id_dest, "ind_final": ind_final, "ind_ie_dest": ind_ie_dest, "itens": itens}
