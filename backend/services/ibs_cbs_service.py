"""Motor de cálculo IBS/CBS (Reforma Tributária) — porte fiel de
`CalculaIBSCBS` (`Geral\\mdl_proc.bas:36433-36985`, ~550 linhas VB6),
lido por completo em 2026-08-19 (não um resumo/fragmento) pra esta
implementação. Ver `[[project_ibs_cbs_vb6_pendente]]` (memória do
projeto) e PENDENCIAS.md > "Gap real confirmado 2026-08-19" pro
histórico completo do porquê este motor nunca tinha sido portado antes.

Este módulo é um CALCULADOR PURO — recebe o item já resolvido (qtd,
p_unit, codigo_int) e a linha de `taxas`/`taxas_nfce` já buscada (mesma
chave de negócio já usada por
`nfe_emissao_service._resolver_tributacao_sync`), devolve os campos
calculados + fragmentos de XML prontos. Não abre conexão, não faz
`SELECT`/`UPDATE` — a orquestração de banco fica com quem chama
(`comanda_service.py`), assim como a legada `tb`/`tb2`/`comanda_rtc`
(recordsets de staging linha-a-linha do VB6, workaround da linguagem,
não regra de negócio — ver "Não replicar truques VB6" em CLAUDE.md) foi
deliberadamente NÃO replicada aqui.

## Correções aplicadas em relação à fonte VB6 (documentadas, não silenciosas)

1. **Typo de nome de coluna** (`mdl_proc.bas:36575`/`36844`): a fonte lê
   `tb2("ALQT_ADREM_DIFERIMENTO_UBS")` ("U" em vez de "I") no grupo
   monofásico `gMonoDif`. Usamos o nome correto,
   `ALQT_ADREM_DIFERIMENTO_IBS` (já é assim em
   `tabelas_aux_service.CAMPOS_TAXAS`). Achado a reportar à equipe VB6
   separadamente (fora deste código).
2. **Segunda passagem com bug real, não replicada** (`mdl_proc.bas:
   36843-36847`): dentro do bloco de montagem do XML `<gMonoDif>` (que a
   própria fonte deixa vazio — linhas 36839-36842), o VB6 RECALCULA
   `VALOR_DIFERIMENTO_IBS`/`VALOR_DIFERIMENTO_CBS` usando
   `BASE_ADREM_MONO` (base do grupo "padrão", `qtd`) em vez de
   `BASE_ADREM_DIFERIMENTO` (base correta deste grupo, `qtd * p_unit`,
   calculada 2 linhas acima na mesma sub-rotina) — sobrescrevendo o
   valor correto já calculado no primeiro cálculo (linhas 36573-36579,
   esse sim replicado aqui). Como (a) o resultado dessa segunda conta
   nunca é lido por mais nada dentro da própria função (o acúmulo de
   `vTotIBSMonoItem`/`vTotCBSMonoItem` já aconteceu ANTES, usando o
   valor correto) e (b) a tag XML `<gMonoDif>` já sai vazia mesmo assim,
   esta segunda passagem é código morto com um bug — não replicado.
   Achado a reportar à equipe VB6 separadamente.
3. **Tag XML malformada** (`mdl_proc.bas:36651`): o `gRed` de `gIBSMun`
   fecha `pAliqEfet` com `"/<pAliqEfet>"` (barra e `<` trocados) em vez
   de `"</pAliqEfet>"` — geraria XML inválido. Corrigido pra fechamento
   válido.

## O que NÃO foi portado (decisão já registrada, não esquecimento)

- **IS (Imposto Seletivo)**: os campos existem em `CAMPOS_TAXAS`
  (`CST_IS`/`CCLASSTRIB_IS`/`ALQT_IS`) mas o próprio VB6 tem esse bloco
  de cálculo COMENTADO (`mdl_proc.bas:36499-36502`) — aguarda
  legislação/alíquota (ver `[[project_ibs_cbs_vb6_pendente]]`). Não
  implementado aqui também.
- **`GTRIBREGULAR` tem DOIS blocos na fonte** — achado só nesta leitura
  completa (uma leitura anterior, parcial, tinha concluído erroneamente
  que a feature inteira era no-op): o primeiro (`mdl_proc.bas:
  36549-36550`) está genuinamente vazio (`If ... = 1 Then End If`, sem
  corpo — replicado como no-op, não há nada a fazer). O SEGUNDO
  (`mdl_proc.bas:36689-36738`), bem mais adiante na mesma função, tem
  lógica real de montagem de XML `<gTribRegular>` — ESSE bloco é
  replicado fielmente aqui (`_montar_gtribregular_xml`).
"""
from typing import Optional


def _taxa_get(taxa: dict, chave: str, default=None):
    """Lookup case-insensitive na linha de `taxas`/`taxas_nfce` — o cursor
    devolve as colunas com o casing exato definido no banco (ex.:
    `gMonoDif`, mixed-case), que pode divergir do casing usado aqui;
    não vale a pena arriscar acoplar a um casing específico."""
    if chave in taxa:
        return taxa[chave]
    chave_low = chave.lower()
    for k, v in taxa.items():
        if k.lower() == chave_low:
            return v
    return default


def resolver_taxa_nfce_para_ibs_cbs_sync(cur, *, cod_icms: str, destino: str, tipo_mov: str = "S01") -> Optional[dict]:
    """Resolve a linha de `taxas_nfce` usada pra IBS/CBS — baseado no JOIN
    que `CalculaIBSCBS` faz pra popular `comanda_rtc`
    (`mdl_proc.bas:36446-36447`), com 2 filtros extra confirmados
    DIRETAMENTE pelo usuário 2026-08-19 (não inferidos do SQL literal do
    VB6, que só filtra por `cod_icms` — ver histórico abaixo).

    **Achado original (2026-08-19, releitura mais precisa da fonte)**:
    pra uma comanda (NFC-e OU NFS-e — as duas linhas do VB6 seguem
    exatamente o mesmo padrão, uma pra `pecas` outra pra `servicos`), a
    taxação usada pelo cálculo de IBS/CBS NÃO é a cascata completa de
    `SitTribut()`/`_resolver_tributacao_sync` (que resolve `taxas` por
    protocolo_st+consumidor_final+simples_nacional+destino+tipo_mov+
    cod_icms, usada pro sistema tributário ANTIGO — ICMS/CSOSN/PIS/
    COFINS). É uma tabela DIFERENTE (`taxas_nfce`), corrigindo uma
    integração anterior que reaproveitava por engano a linha de `taxas`
    já resolvida por `_resolver_tributacao_sync`.

    **Ambiguidade real da fonte, resolvida com a informação do
    usuário**: `taxas_nfce` tem uma chave de negócio de 4 campos
    (destino+cfop+cod_icms+tipo_mov), então mais de uma linha PODE
    compartilhar o mesmo `cod_icms` — o `JOIN` literal do VB6 nessa
    rotina específica não desempata (só filtra por `cod_icms`), o que
    seria arriscado numa instalação com mais de uma linha por
    `cod_icms`. O usuário confirmou que, na prática, os outros 2 campos
    da chave são sempre CONSTANTES neste contexto — não precisam de
    resolução dinâmica: **`tipo_mov` é sempre `"S01"`** (NFC-e só existe
    pro tipo de movimentação VENDA, não há outro tipo_mov possível) e
    **`destino` é sempre a UF da própria empresa emitente** (não a UF do
    cliente/destinatário — NFC-e é venda presencial, sempre dentro do
    estado do emitente). Adicionar esses 2 filtros explícitos resolve a
    ambiguidade sem inventar critério de desempate.

    **Sugestão do usuário, não implementada aqui** (fora de escopo desta
    correção, registrar se for pedida): o cadastro de `taxas_nfce`
    (`taxas.tsx`, variante "nfce") poderia até BLOQUEAR/pré-preencher
    `destino`/`tipo_mov` com esses valores padrão na tela, já que eles
    nunca variam nesse contexto — evitaria cadastro divergente na
    origem, não só filtrar na hora de emitir.
    """
    cur.execute(
        "SELECT TOP 1 * FROM taxas_nfce WHERE cod_icms = %s AND destino = %s AND tipo_mov = %s",
        (cod_icms, destino, tipo_mov),
    )
    return cur.fetchone()


def _num(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _txt(v) -> str:
    return (str(v) if v is not None else "").strip()


def _fmt(v: float, casas: int) -> str:
    return f"{v:.{casas}f}"


def _reducao(base: float, alqt_cheia: float, perc_dif: float, perc_reducao: float, alqt_efetiva: float) -> tuple[float, float]:
    """Réplica do padrão repetido 3x na fonte (IBS-UF, IBS-Município, CBS):
    valor final usa a alíquota efetiva de redução quando > 0, senão a
    alíquota cheia (`mdl_proc.bas:36517-36521`/`36531-36535`/`36543-36547`)."""
    valor_dif = round((base * perc_dif) / 100, 2)
    if alqt_efetiva > 0:
        valor = round((base * alqt_efetiva) / 100, 2)
    else:
        valor = round((base * alqt_cheia) / 100, 2)
    return valor_dif, valor


def calcular_item_ibs_cbs(*, qtd: float, p_unit: float, codigo_int: str, taxa: dict) -> Optional[dict]:
    """Calcula IBS/CBS de UM item — porte de `CalculaIBSCBS`'s corpo do
    loop principal (`mdl_proc.bas:36491-36866`).

    `taxa` é a linha de `taxas`/`taxas_nfce` já resolvida (mesma que
    `nfe_emissao_service._resolver_tributacao_sync` devolve).

    Devolve `None` quando o item não gera IBS/CBS algum (réplica do
    `GoTo semibs`, `mdl_proc.bas:36491-36497`): acontece quando
    `INFORMA_CBS_IBS` está desligado E o CST do IBS não é "400"/"410".
    """
    informa_cbs_ibs = bool(_taxa_get(taxa, "INFORMA_CBS_IBS"))
    cst_ibs = _txt(_taxa_get(taxa, "CST_IBS"))
    eh_400_410 = cst_ibs in ("400", "410")
    if not informa_cbs_ibs and not eh_400_410:
        return None

    classtrib_ibs = _txt(_taxa_get(taxa, "CCLASSTRIB_IBS"))
    base = round(qtd * p_unit, 2)

    alqt_ibs_uf = _num(_taxa_get(taxa, "ALQT_IBS_ESTADO"))
    perc_dif_ibs_uf = _num(_taxa_get(taxa, "PERC_DIFERIMENTO_IBS_ESTADO"))
    perc_red_ibs_uf = _num(_taxa_get(taxa, "PERC_REDUCAO_IBS_ESTADO"))
    alqt_efetiva_ibs_uf = _num(_taxa_get(taxa, "ALQT_EFETIVA_REDUCAO_IBS_ESTADO"))
    valor_dif_ibs_uf, valor_ibs_uf = _reducao(base, alqt_ibs_uf, perc_dif_ibs_uf, perc_red_ibs_uf, alqt_efetiva_ibs_uf)

    alqt_ibs_mun = _num(_taxa_get(taxa, "ALQT_IBS_MUNICIPIO"))
    perc_dif_ibs_mun = _num(_taxa_get(taxa, "PERC_DIFERIMENTO_IBS_MUNICIPIO"))
    perc_red_ibs_mun = _num(_taxa_get(taxa, "PERC_REDUCAO_IBS_MUNICIPIO"))
    alqt_efetiva_ibs_mun = _num(_taxa_get(taxa, "ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO"))
    valor_dif_ibs_mun, valor_ibs_mun = _reducao(base, alqt_ibs_mun, perc_dif_ibs_mun, perc_red_ibs_mun, alqt_efetiva_ibs_mun)

    alqt_cbs = _num(_taxa_get(taxa, "ALQT_CBS_ESTADO"))
    perc_dif_cbs = _num(_taxa_get(taxa, "PERC_DIFERIMENTO_CBS_ESTADO"))
    perc_red_cbs = _num(_taxa_get(taxa, "PERC_REDUCAO_CBS_ESTADO"))
    alqt_efetiva_cbs = _num(_taxa_get(taxa, "ALQT_EFETIVA_REDUCAO_CBS_ESTADO"))
    valor_dif_cbs, valor_cbs = _reducao(base, alqt_cbs, perc_dif_cbs, perc_red_cbs, alqt_efetiva_cbs)

    # Grupos monofásico ad rem (mdl_proc.bas:36551-36579) — cada um só existe
    # se o flag correspondente estiver ligado na linha de taxas.
    mono: dict = {}
    if _taxa_get(taxa, "gMonoPadrao"):
        base_mono = round(qtd, 4)
        a_ibs = _num(_taxa_get(taxa, "ALQT_ADREM_PADRAO_IBS"))
        a_cbs = _num(_taxa_get(taxa, "ALQT_ADREM_PADRAO_CBS"))
        mono["padrao"] = {
            "base": base_mono, "alqt_ibs": a_ibs, "alqt_cbs": a_cbs,
            "valor_ibs": round(base_mono * a_ibs, 2), "valor_cbs": round(base_mono * a_cbs, 2),
        }
    if _taxa_get(taxa, "gMonoReten"):
        base_reten = round(qtd, 4)
        a_ibs = _num(_taxa_get(taxa, "ALQT_ADREM_RETENCAO_IBS"))
        a_cbs = _num(_taxa_get(taxa, "ALQT_ADREM_RETENCAO_CBS"))
        mono["retencao"] = {
            "base": base_reten, "alqt_ibs": a_ibs, "alqt_cbs": a_cbs,
            "valor_ibs": round(base_reten * a_ibs, 2), "valor_cbs": round(base_reten * a_cbs, 2),
        }
    if _taxa_get(taxa, "gMonoRet"):
        base_ret = round(qtd, 4)
        a_ibs = _num(_taxa_get(taxa, "ALQT_ADREM_RETIDO_IBS"))
        a_cbs = _num(_taxa_get(taxa, "ALQT_ADREM_RETIDO_CBS"))
        mono["retido"] = {
            "base": base_ret, "alqt_ibs": a_ibs, "alqt_cbs": a_cbs,
            "valor_ibs": round(base_ret * a_ibs, 2), "valor_cbs": round(base_ret * a_cbs, 2),
        }
    if _taxa_get(taxa, "gMonoDif"):
        base_dif = base  # BASE_ADREM_DIFERIMENTO = qtd * p_unit (mdl_proc.bas:36574)
        a_ibs = _num(_taxa_get(taxa, "ALQT_ADREM_DIFERIMENTO_IBS"))  # corrige typo "_UBS" da fonte
        a_cbs = _num(_taxa_get(taxa, "ALQT_ADREM_DIFERIMENTO_CBS"))
        mono["diferimento"] = {
            "base": base_dif, "alqt_ibs": a_ibs, "alqt_cbs": a_cbs,
            "valor_ibs": round((base_dif * a_ibs) / 100, 2), "valor_cbs": round((base_dif * a_cbs) / 100, 2),
        }

    valor_mono_ibs = mono.get("padrao", {}).get("valor_ibs", 0.0)
    valor_mono_cbs = mono.get("padrao", {}).get("valor_cbs", 0.0)
    valor_retencao_ibs = mono.get("retencao", {}).get("valor_ibs", 0.0)
    valor_retencao_cbs = mono.get("retencao", {}).get("valor_cbs", 0.0)
    valor_retido_ibs = mono.get("retido", {}).get("valor_ibs", 0.0)
    valor_retido_cbs = mono.get("retido", {}).get("valor_cbs", 0.0)
    valor_diferimento_ibs = mono.get("diferimento", {}).get("valor_ibs", 0.0)
    valor_diferimento_cbs = mono.get("diferimento", {}).get("valor_cbs", 0.0)

    # mdl_proc.bas:36582-36583 — só computado (e só usado) pra item de PRODUTO,
    # mas a fórmula em si não depende disso, calculamos sempre.
    v_tot_ibs_mono_item = round(valor_mono_ibs + valor_retencao_ibs - valor_diferimento_ibs, 2)
    v_tot_cbs_mono_item = round(valor_mono_cbs + valor_retencao_cbs - valor_diferimento_cbs, 2)

    eh_400_410_ou_mono = eh_400_410 or bool(mono)
    eh_servico = codigo_int.strip().upper().startswith("S")

    resultado = {
        "skip": False,
        "cst_ibs_uf": cst_ibs, "classtrib_ibs_uf": classtrib_ibs,
        "cst_ibs_municipio": cst_ibs, "classtrib_ibs_municipio": classtrib_ibs,
        "cst_cbs": cst_ibs, "classtrib_cbs": classtrib_ibs,
        "base_ibs_uf": base, "alqt_ibs_uf": alqt_ibs_uf, "perc_dif_ibs_uf": perc_dif_ibs_uf,
        "valor_dif_ibs_uf": valor_dif_ibs_uf, "perc_reducao_ibs_uf": perc_red_ibs_uf,
        "alqt_efetiva_ibs_uf": alqt_efetiva_ibs_uf, "valor_ibs_uf": valor_ibs_uf,
        "base_ibs_municipio": base, "alqt_ibs_municipio": alqt_ibs_mun, "perc_dif_ibs_municipio": perc_dif_ibs_mun,
        "valor_dif_ibs_municipio": valor_dif_ibs_mun, "perc_reducao_ibs_municipio": perc_red_ibs_mun,
        "alqt_efetiva_ibs_municipio": alqt_efetiva_ibs_mun, "valor_ibs_municipio": valor_ibs_mun,
        "base_cbs": base, "alqt_cbs": alqt_cbs, "perc_dif_cbs": perc_dif_cbs,
        "valor_dif_cbs": valor_dif_cbs, "perc_reducao_cbs": perc_red_cbs,
        "alqt_efetiva_cbs": alqt_efetiva_cbs, "valor_cbs": valor_cbs,
        "gtribregular": bool(_taxa_get(taxa, "GTRIBREGULAR")),
        "mono": mono,
        "valor_diferimento_ibs": valor_diferimento_ibs, "valor_diferimento_cbs": valor_diferimento_cbs,
        "v_tot_ibs_mono_item": v_tot_ibs_mono_item, "v_tot_cbs_mono_item": v_tot_cbs_mono_item,
        "eh_400_410_ou_mono": eh_400_410_ou_mono,
        # mdl_proc.bas:36581 — só item de PRODUTO (codigo_int não começa com
        # "S") entra nos totais agregados e no XML <IBSCBS> por item; item de
        # serviço tem os campos acima calculados/disponíveis (pro DPS da
        # NFS-e ler CST/cClassTrib), mas não contribui pro XML/totais da NFCe.
        "contribui_totais": not eh_servico,
    }
    resultado["xml_item"] = _montar_xml_item(resultado) if not eh_servico else ""
    return resultado


def _montar_gtribregular_xml(r: dict) -> str:
    """`mdl_proc.bas:36689-36738` — bloco REAL (não no-op, ver docstring do
    módulo). Achado não-óbvio confirmado na fonte: a condição
    `ALQT_EFETIVA_REDUCAO_IBS_ESTADO > 0` decide a alíquota efetiva tanto
    do IBS-UF quanto do IBS-Município (não usa a alíquota efetiva de
    município pra decidir o município) — replicado tal qual."""
    usa_efetiva_uf = r["alqt_efetiva_ibs_uf"] > 0
    p_uf = r["alqt_efetiva_ibs_uf"] if usa_efetiva_uf else r["alqt_ibs_uf"]
    p_mun = r["alqt_efetiva_ibs_municipio"] if usa_efetiva_uf else r["alqt_ibs_municipio"]
    usa_efetiva_cbs = r["alqt_efetiva_cbs"] > 0
    p_cbs = r["alqt_efetiva_cbs"] if usa_efetiva_cbs else r["alqt_cbs"]
    return (
        "<gTribRegular>"
        f"<CSTReg>{r['cst_ibs_uf']}</CSTReg>"
        f"<cClassTribReg>{r['classtrib_ibs_uf']}</cClassTribReg>"
        f"<pAliqEfetRegIBSUF>{_fmt(p_uf, 4)}</pAliqEfetRegIBSUF>"
        f"<vTribRegIBSUF>{_fmt(r['valor_ibs_uf'], 2)}</vTribRegIBSUF>"
        f"<pAliqEfetRegIBSMun>{_fmt(p_mun, 4)}</pAliqEfetRegIBSMun>"
        f"<vTribRegIBSMun>{_fmt(r['valor_ibs_municipio'], 2)}</vTribRegIBSMun>"
        f"<pAliqEfetRegCBS>{_fmt(p_cbs, 4)}</pAliqEfetRegCBS>"
        f"<vTribRegCBS>{_fmt(r['valor_cbs'], 2)}</vTribRegCBS>"
        "</gTribRegular>"
    )


def _montar_gibscbsmono_xml(r: dict) -> str:
    """`mdl_proc.bas:36740-36858`."""
    mono = r["mono"]
    xml = "<gIBSCBSMono>"
    if "padrao" in mono:
        m = mono["padrao"]
        xml += (
            "<gMonoPadrao>"
            f"<qBCMono>{_fmt(m['base'], 4)}</qBCMono>"
            f"<adRemIBS>{_fmt(m['alqt_ibs'], 4)}</adRemIBS>"
            f"<adRemCBS>{_fmt(m['alqt_cbs'], 4)}</adRemCBS>"
            f"<vIBSMono>{_fmt(m['valor_ibs'], 2)}</vIBSMono>"
            f"<vCBSMono>{_fmt(m['valor_cbs'], 2)}</vCBSMono>"
            "</gMonoPadrao>"
        )
    if "retencao" in mono:
        m = mono["retencao"]
        xml += (
            "<gMonoReten>"
            f"<qBCMonoReten>{_fmt(m['base'], 4)}</qBCMonoReten>"
            f"<adRemIBSReten>{_fmt(m['alqt_ibs'], 4)}</adRemIBSReten>"
            f"<vIBSMonoReten>{_fmt(m['valor_ibs'], 2)}</vIBSMonoReten>"
            f"<adRemCBSReten>{_fmt(m['alqt_cbs'], 4)}</adRemCBSReten>"
            f"<vCBSMonoReten>{_fmt(m['valor_cbs'], 2)}</vCBSMonoReten>"
            "</gMonoReten>"
        )
    if "retido" in mono:
        m = mono["retido"]
        xml += (
            "<gMonoRet>"
            f"<qBCMonoRet>{_fmt(m['base'], 4)}</qBCMonoRet>"
            f"<adRemIBSRet>{_fmt(m['alqt_ibs'], 4)}</adRemIBSRet>"
            f"<vIBSMonoRet>{_fmt(m['valor_ibs'], 2)}</vIBSMonoRet>"
            f"<adRemCBSRet>{_fmt(m['alqt_cbs'], 4)}</adRemCBSRet>"
            f"<vCBSMonoRet>{_fmt(m['valor_cbs'], 2)}</vCBSMonoRet>"
            "</gMonoRet>"
        )
    if "diferimento" in mono:
        # mdl_proc.bas:36838-36842 — a própria fonte deixa este bloco vazio.
        xml += "<gMonoDif></gMonoDif>"
    xml += (
        f"<vTotIBSMonoItem>{_fmt(r['v_tot_ibs_mono_item'], 2)}</vTotIBSMonoItem>"
        f"<vTotCBSMonoItem>{_fmt(r['v_tot_cbs_mono_item'], 2)}</vTotCBSMonoItem>"
    )
    xml += "</gIBSCBSMono>"
    return xml


def _montar_xml_item(r: dict) -> str:
    """`mdl_proc.bas:36596-36866` — fragmento `<IBSCBS>` de UM item."""
    especial = r["eh_400_410_ou_mono"]  # cst 400/410 ou algum grupo monofásico ligado
    xml = "<IBSCBS>"
    xml += f"<CST>{r['cst_ibs_uf']}</CST>"
    xml += f"<cClassTrib>{r['classtrib_ibs_uf']}</cClassTrib>"
    if not especial:
        xml += (
            "<gIBSCBS>"
            f"<vBC>{_fmt(r['base_ibs_uf'], 2)}</vBC>"
            "<gIBSUF>"
            f"<pIBSUF>{_fmt(r['alqt_ibs_uf'], 4)}</pIBSUF>"
        )
        if r["perc_reducao_ibs_uf"] > 0:
            xml += (
                "<gRed>"
                f"<pRedAliq>{_fmt(r['perc_reducao_ibs_uf'], 4)}</pRedAliq>"
                f"<pAliqEfet>{_fmt(r['alqt_efetiva_ibs_uf'], 4)}</pAliqEfet>"
                "</gRed>"
            )
        xml += f"<vIBSUF>{_fmt(r['valor_ibs_uf'], 2)}</vIBSUF>" "</gIBSUF>"
        xml += "<gIBSMun>" f"<pIBSMun>{_fmt(r['alqt_ibs_municipio'], 4)}</pIBSMun>"
        if r["perc_reducao_ibs_municipio"] > 0:
            xml += (
                "<gRed>"
                f"<pRedAliq>{_fmt(r['perc_reducao_ibs_municipio'], 4)}</pRedAliq>"
                # mdl_proc.bas:36651 fecha com "/<pAliqEfet>" (tag malformada) — corrigido aqui.
                f"<pAliqEfet>{_fmt(r['alqt_efetiva_ibs_municipio'], 4)}</pAliqEfet>"
                "</gRed>"
            )
        xml += f"<vIBSMun>{_fmt(r['valor_ibs_municipio'], 2)}</vIBSMun>" "</gIBSMun>"
        xml += f"<vIBS>{_fmt(r['valor_ibs_uf'] + r['valor_ibs_municipio'], 2)}</vIBS>"
        xml += "<gCBS>" f"<pCBS>{_fmt(r['alqt_cbs'], 4)}</pCBS>"
        if r["perc_reducao_cbs"] > 0:
            xml += (
                "<gRed>"
                f"<pRedAliq>{_fmt(r['perc_reducao_cbs'], 4)}</pRedAliq>"
                f"<pAliqEfet>{_fmt(r['alqt_efetiva_cbs'], 4)}</pAliqEfet>"
                "</gRed>"
            )
        xml += f"<vCBS>{_fmt(r['valor_cbs'], 2)}</vCBS>" "</gCBS>"
        xml += "</gIBSCBS>"

    if r["gtribregular"]:
        xml += _montar_gtribregular_xml(r)

    if r["mono"]:
        xml += _montar_gibscbsmono_xml(r)

    xml += "</IBSCBS>"
    return xml


def calcular_totais_ibs_cbs(itens_calculados: list[Optional[dict]]) -> dict:
    """Agrega os itens (só os que `contribui_totais`, ou seja, itens de
    PRODUTO não pulados pelo `semibs`) — porte de `mdl_proc.bas:
    36584-36591` (acúmulo) + `36879-36953` (montagem do XML agregado
    `<IBSCBSTot>`). Devolve os totais numéricos + o fragmento XML pronto
    (string vazia se nenhum item processado, mesma condição da fonte:
    `TotBaseIBSCBS > 0 OR algum total mono > 0 OR TEVECBS = "1"`)."""
    tot_ibs_uf = 0.0
    tot_ibs_mun = 0.0
    tot_cbs = 0.0
    tot_base = 0.0
    v_ibs_mono = 0.0
    v_cbs_mono = 0.0
    v_ibs_mono_reten = 0.0
    v_cbs_mono_reten = 0.0
    v_ibs_mono_ret = 0.0
    v_cbs_mono_ret = 0.0
    teve_algo = False

    for item in itens_calculados:
        if not item or item.get("skip"):
            continue
        teve_algo = True  # mdl_proc.bas:36498 — TEVECBS="1" pra qualquer item processado, produto ou serviço
        if not item.get("contribui_totais"):
            continue
        tot_ibs_uf += item["valor_ibs_uf"]
        tot_ibs_mun += item["valor_ibs_municipio"]
        tot_cbs += item["valor_cbs"]
        if not item["eh_400_410_ou_mono"]:
            tot_base += item["base_cbs"]
        mono = item.get("mono") or {}
        if "padrao" in mono:
            v_ibs_mono += mono["padrao"]["valor_ibs"]
            v_cbs_mono += mono["padrao"]["valor_cbs"]
        if "retencao" in mono:
            v_ibs_mono_reten += mono["retencao"]["valor_ibs"]
            v_cbs_mono_reten += mono["retencao"]["valor_cbs"]
        if "retido" in mono:
            v_ibs_mono_ret += mono["retido"]["valor_ibs"]
            v_cbs_mono_ret += mono["retido"]["valor_cbs"]

    tot_ibs_uf = round(tot_ibs_uf, 2)
    tot_ibs_mun = round(tot_ibs_mun, 2)
    tot_cbs = round(tot_cbs, 2)
    tot_base = round(tot_base, 2)
    v_ibs_mono = round(v_ibs_mono, 2)
    v_cbs_mono = round(v_cbs_mono, 2)
    v_ibs_mono_reten = round(v_ibs_mono_reten, 2)
    v_cbs_mono_reten = round(v_cbs_mono_reten, 2)
    v_ibs_mono_ret = round(v_ibs_mono_ret, 2)
    v_cbs_mono_ret = round(v_cbs_mono_ret, 2)

    tem_mono = any([v_ibs_mono, v_cbs_mono, v_ibs_mono_reten, v_cbs_mono_reten, v_ibs_mono_ret, v_cbs_mono_ret])
    xml = ""
    if tot_base > 0 or tem_mono or teve_algo:
        xml = (
            "<IBSCBSTot>"
            f"<vBCIBSCBS>{_fmt(tot_base, 2)}</vBCIBSCBS>"
            "<gIBS>"
            f"<gIBSUF><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib><vIBSUF>{_fmt(tot_ibs_uf, 2)}</vIBSUF></gIBSUF>"
            f"<gIBSMun><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib><vIBSMun>{_fmt(tot_ibs_mun, 2)}</vIBSMun></gIBSMun>"
            f"<vIBS>{_fmt(tot_ibs_uf + tot_ibs_mun, 2)}</vIBS>"
            "<vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus>"
            "</gIBS>"
            "<gCBS>"
            "<vDif>0.00</vDif><vDevTrib>0.00</vDevTrib>"
            f"<vCBS>{_fmt(tot_cbs, 2)}</vCBS>"
            "<vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus>"
            "</gCBS>"
        )
        if tem_mono:
            xml += (
                "<gMono>"
                f"<vIBSMono>{_fmt(v_ibs_mono, 2)}</vIBSMono>"
                f"<vCBSMono>{_fmt(v_cbs_mono, 2)}</vCBSMono>"
                f"<vIBSMonoReten>{_fmt(v_ibs_mono_reten, 2)}</vIBSMonoReten>"
                f"<vCBSMonoReten>{_fmt(v_cbs_mono_reten, 2)}</vCBSMonoReten>"
                f"<vIBSMonoRet>{_fmt(v_ibs_mono_ret, 2)}</vIBSMonoRet>"
                f"<vCBSMonoRet>{_fmt(v_cbs_mono_ret, 2)}</vCBSMonoRet>"
                "</gMono>"
            )
        xml += "</IBSCBSTot>"

    return {
        "tot_ibs_uf": tot_ibs_uf, "tot_ibs_mun": tot_ibs_mun, "tot_cbs": tot_cbs, "tot_base_ibs_cbs": tot_base,
        "v_ibs_mono": v_ibs_mono, "v_cbs_mono": v_cbs_mono,
        "v_ibs_mono_reten": v_ibs_mono_reten, "v_cbs_mono_reten": v_cbs_mono_reten,
        "v_ibs_mono_ret": v_ibs_mono_ret, "v_cbs_mono_ret": v_cbs_mono_ret,
        "xml_totais": xml,
    }
