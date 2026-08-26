"""Descomplicar Taxas — "Sugerir com IA" (Apoio Fiscal, apelido "João") —
2026-08-22, pedido explícito do usuário: o cliente final tem muita
dificuldade de preencher a Manutenção de Taxas (`taxas.tsx`/
`tabelas_aux_service.py`, ~90 colunas fiscais por linha) por causa da
complexidade real dos conceitos fiscais brasileiros. Este módulo sugere
valores pra alguns desses campos, com base no regime tributário da
própria empresa, reaproveitando o mesmo recurso de IA (Claude/Anthropic)
já usado por "Importar Formulário" (`layout_service.py::
_importar_formulario_sync`) — mesmo SDK, mesmo padrão de saída
estruturada (`output_config.format.json_schema`), mesma chave de API
(`controle.ANTHROPIC_API_KEY`, tela "IA Key" — é isso que o usuário
chamou de "apoio IA por contrato": só instalações com essa chave
configurada têm o recurso disponível).

**Regra de segurança inegociável (CLAUDE.md > "Papel Kelvin" — nunca
inventar CST/CFOP/ClassTrib/alíquota)**: a IA aqui NUNCA escolhe um valor
livre — toda saída estruturada é restrita (`enum` do JSON Schema) a
valores que já existem numa fonte real e citada:
  - `tributacao` (CST/CSOSN de ICMS): restrito às tabelas nacionais
    `fiscal_referencia_nacional.CST_ICMS`/`CSOSN`, filtradas pelo CRT
    (Código de Regime Tributário) real da empresa (`controle_aux.
    Regime_Trib`) — nunca os dois conjuntos ao mesmo tempo.
  - `cst_pis`/`cst_cofins`: restrito a `fiscal_referencia_nacional.
    CST_PIS_COFINS_SAIDA`/`_ENTRADA`, conforme `tipo_mov` (E=entrada,
    S=saída — mesma convenção já usada em `tabelas_aux_service.py:3230`).
  - `cst_ibs`/`cclasstrib_ibs`: restrito à tabela `classtrib` (já existe
    no banco, LC 214/2025, mesma fonte que `_list_classtrib_opcoes_sync`/
    `_classtrib_lookup_sync` já usam pra essa mesma tela).
Alíquotas/percentuais/reduções LIVRES (ICMS, FCP, DIFAL, alíquota
estadual/municipal de IBS-CBS) ficam **fora do escopo desta IA** — não
existe fonte fechada/oficial integrada a este sistema pra validar esses
números por estado/produto/operação; sugerir um valor aqui seria
inventar. Só os percentuais de REDUÇÃO ligados ao ClassTrib escolhido
(`pRedIBS`/`pRedCBS`) entram — e nem esses vêm da IA: são lidos direto
da tabela `classtrib` depois que a IA escolhe o par CST/ClassTrib (ver
`_anexar_derivados_classtrib`).

**Nunca grava nada.** Só devolve uma lista de sugestões (com o motivo de
cada uma, em linguagem simples — vira o texto didático do Apoio Fisco/
João na tela) pra revisão humana. A gravação real continua sendo os
endpoints manuais já existentes (`POST /api/tabelas/tributacao` pra
cadastrar o código escolhido antes, `POST /api/tabelas/taxas` pra gravar
a linha) — sem endpoint novo de gravação em lote, de propósito.

**Fontes das tabelas nacionais** (`fiscal_referencia_nacional.py`) —
pesquisadas e cross-checadas nesta sessão contra fontes secundárias
especializadas, sem carregar o PDF primário do Ajuste SINIEF/SPED direto
(erro de redirecionamento) — validar contra o texto primário antes de
confiar em produção real, ver docstring daquele módulo.

**NUNCA testado contra a API Anthropic real nesta sessão** — mesma
cautela de sempre pra qualquer chamada externa real neste projeto.
"""
import asyncio
import json
import logging
from typing import Optional

from db.connection import _open_conn
from services import fiscal_referencia_nacional as ref
from services import tabelas_aux_service
from services.layout_service import _estimar_custo_ia, _friendly_query_error, _IA_IMPORT_MODEL

_log = logging.getLogger(__name__)


def _resolver_regime_sync(cur) -> dict:
    """CRT (Código de Regime Tributário) real da empresa —
    `controle_aux.Regime_Trib` (1=Simples Nacional, 2=Simples excesso
    sublimite, 3=Regime Normal — rótulo legado "Regime Tributação
    Municipal" está errado, é o CRT nacional, ver `controle_sistema_
    service.py:162-164`). Nunca confia num regime mandado pelo frontend
    pra uma decisão que orienta sugestão fiscal — sempre lido de novo
    aqui, no backend."""
    cur.execute("SELECT TOP 1 Regime_Trib, opcao_simples FROM controle_aux")
    row = cur.fetchone() or {}
    crt = row.get("Regime_Trib")
    return {
        "crt": int(crt) if crt else None,
        "opcao_simples": bool(row.get("opcao_simples")),
        "eh_simples": crt in (1, 2),
    }


def _montar_schema(regime: dict, tipo_mov: str, tem_classtrib: bool) -> dict:
    """Monta o JSON Schema de saída estruturada — cada campo do `enum` vem
    de uma fonte real (ver docstring do módulo), nunca aberto."""
    tributacao_opcoes = ref.CSOSN if regime["eh_simples"] else ref.CST_ICMS
    eh_entrada = (tipo_mov or "").strip().upper().startswith("E")
    pis_cofins_opcoes = ref.CST_PIS_COFINS_ENTRADA if eh_entrada else ref.CST_PIS_COFINS_SAIDA

    properties: dict = {
        "tributacao": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "enum": list(tributacao_opcoes.keys())},
                "motivo": {"type": "string", "description": "Explicação curta, em português simples, do porquê deste código se aplica — sem jargão contábil."},
            },
            "required": ["codigo", "motivo"],
            "additionalProperties": False,
        },
        "cst_pis": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "enum": list(pis_cofins_opcoes.keys())},
                "motivo": {"type": "string"},
            },
            "required": ["codigo", "motivo"],
            "additionalProperties": False,
        },
        "cst_cofins": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "enum": list(pis_cofins_opcoes.keys())},
                "motivo": {"type": "string"},
            },
            "required": ["codigo", "motivo"],
            "additionalProperties": False,
        },
    }
    required = ["tributacao", "cst_pis", "cst_cofins"]

    if tem_classtrib:
        properties["ibs_cbs"] = {
            "type": "object",
            "properties": {
                "cst": {"type": "string", "description": "CST do IBS/CBS — escolha um dos valores já cadastrados na tabela nacional ClassTrib."},
                "cclasstrib": {"type": "string", "description": "Código ClassTrib correspondente ao CST escolhido, já cadastrado na tabela nacional."},
                "motivo": {"type": "string"},
            },
            "required": ["cst", "cclasstrib", "motivo"],
            "additionalProperties": False,
        }
        # `cclasstrib` não é enum fixo aqui (é 1-CST-pra-N, dependente da
        # escolha de `cst`, uma cascata) — a validação real de que o par
        # escolhido pela IA existe de fato em `classtrib` acontece DEPOIS,
        # em `_anexar_derivados_classtrib` (rejeita se não achar), não só
        # confiando no enum solto do `cst`.
        required.append("ibs_cbs")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _anexar_descricoes_oficiais(regime: dict, sugestao: dict) -> None:
    """Anexa a descrição oficial (do dict fechado, nunca gerada pela IA) de
    cada código sugerido — usada pra (1) exibir o texto oficial na tela de
    revisão e (2) alimentar `Tributacao.descricao` no upsert que acontece
    ao aceitar a sugestão (ver docstring do módulo, "Opção B")."""
    tributacao_tabela = ref.CSOSN if regime["eh_simples"] else ref.CST_ICMS
    if sugestao.get("tributacao"):
        cod = sugestao["tributacao"].get("codigo")
        sugestao["tributacao"]["descricao_oficial"] = tributacao_tabela.get(cod, "")
    for campo in ("cst_pis", "cst_cofins"):
        if sugestao.get(campo):
            cod = sugestao[campo].get("codigo")
            sugestao[campo]["descricao_oficial"] = ref.CST_PIS_COFINS.get(cod, "")


def _anexar_derivados_classtrib(servidor: str, banco: str, sugestao: dict) -> None:
    """Depois que a IA escolhe CST/ClassTrib do IBS/CBS, busca os valores
    REAIS de redução/monofasia direto da tabela `classtrib` — a IA nunca
    gera esses números, só escolhe o par de código (`_classtrib_lookup_
    sync`, mesma função que já alimenta o botão manual "Consultar
    ClassTrib" desta mesma tela)."""
    ibs_cbs = sugestao.get("ibs_cbs")
    if not ibs_cbs:
        return
    res = tabelas_aux_service._classtrib_lookup_sync(servidor, banco, ibs_cbs.get("cst"), ibs_cbs.get("cclasstrib"))
    if res.get("success"):
        ibs_cbs["pred_ibs"] = res["pred_ibs"]
        ibs_cbs["pred_cbs"] = res["pred_cbs"]
        ibs_cbs["g_trib_regular"] = res["g_trib_regular"]
        ibs_cbs["g_mono_padrao"] = res["g_mono_padrao"]
        ibs_cbs["g_mono_reten"] = res["g_mono_reten"]
        ibs_cbs["g_mono_ret"] = res["g_mono_ret"]
        ibs_cbs["g_mono_dif"] = res["g_mono_dif"]
    else:
        # A IA "alucinou" um par CST/ClassTrib que não existe na tabela
        # nacional — descarta a sugestão inteira desse bloco em vez de
        # devolver um par inválido pra tela (nunca confiar cegamente).
        sugestao.pop("ibs_cbs", None)


def _sugerir_tributacao_sync(
    servidor: str, banco: str, *,
    destino: Optional[str], cfop: Optional[str], cod_icms: Optional[str], tipo_mov: Optional[str],
    simples_nacional: bool, consumidor_final: bool, descricao_operacao: Optional[str],
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 ANTHROPIC_API_KEY FROM controle")
        row = cur.fetchone()
        api_key = ((row.get("ANTHROPIC_API_KEY") if row else None) or "").strip()
        if not api_key:
            cur.close()
            return {
                "success": False,
                "message": "A sugestão por IA não está configurada — cadastre a chave em "
                           "Configurações > Administração > IA Key.",
            }

        regime = _resolver_regime_sync(cur)
        if not regime["crt"]:
            cur.close()
            return {
                "success": False,
                "message": "O Regime Tributário (CRT) da empresa ainda não está configurado — "
                           "cadastre em Controle do Sistema antes de usar a sugestão por IA.",
            }

        cur.execute("SELECT TOP 1 1 AS ok FROM classtrib")
        tem_classtrib = cur.fetchone() is not None
        cur.close()
    except Exception as e:
        return {"success": False, "message": _friendly_query_error("carregar as configurações fiscais", e)}
    finally:
        conn.close()

    schema = _montar_schema(regime, tipo_mov or "", tem_classtrib)
    crt_label = {1: "Simples Nacional", 2: "Simples Nacional (excesso de sublimite)", 3: "Regime Normal"}.get(regime["crt"], "não identificado")
    prompt = (
        f"Sugira a tributação de uma linha de Taxas (regra fiscal de venda/compra) pra uma empresa "
        f"no regime '{crt_label}' (CRT {regime['crt']}).\n\n"
        f"Contexto da operação já escolhido na tela:\n"
        f"- Destino: {destino or 'não informado'}\n"
        f"- CFOP: {cfop or 'não informado'}\n"
        f"- Situação ICMS (cod_icms): {cod_icms or 'não informado'}\n"
        f"- Tipo de movimentação: {tipo_mov or 'não informado'}\n"
        f"- Simples Nacional (regra específica pra esse caso): {'sim' if simples_nacional else 'não'}\n"
        f"- Consumidor final: {'sim' if consumidor_final else 'não'}\n"
        + (f"- Descrição da operação (informada pelo usuário): {descricao_operacao}\n" if descricao_operacao else "")
        + "\nPra cada campo pedido no schema, escolha SOMENTE um código dentre os já oferecidos no "
          "enum (nunca invente um código fora da lista) e explique o motivo em português simples, "
          "sem jargão contábil, pensando num lojista sem formação em contabilidade."
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=_IA_IMPORT_MODEL,
            max_tokens=4000,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = stream.get_final_message()
        custo = _estimar_custo_ia(response.usage)
        if response.stop_reason == "refusal":
            return {
                "success": False,
                "message": "Não foi possível gerar uma sugestão agora (recusado pelos filtros de "
                           "segurança). Tente novamente com uma descrição diferente.",
                "custo": custo,
            }
        texto = next((b.text for b in response.content if b.type == "text"), "")
        sugestao = json.loads(texto) if texto else {}
    except Exception as e:
        return {"success": False, "message": _friendly_query_error("gerar a sugestão de tributação", e)}

    _anexar_descricoes_oficiais(regime, sugestao)
    _anexar_derivados_classtrib(servidor, banco, sugestao)
    return {"success": True, "sugestao": sugestao, "custo": custo}


async def sugerir_tributacao(
    servidor: str, banco: str, *,
    destino: Optional[str], cfop: Optional[str], cod_icms: Optional[str], tipo_mov: Optional[str],
    simples_nacional: bool, consumidor_final: bool, descricao_operacao: Optional[str],
) -> dict:
    return await asyncio.to_thread(
        _sugerir_tributacao_sync, servidor, banco,
        destino=destino, cfop=cfop, cod_icms=cod_icms, tipo_mov=tipo_mov,
        simples_nacional=simples_nacional, consumidor_final=consumidor_final,
        descricao_operacao=descricao_operacao,
    )
