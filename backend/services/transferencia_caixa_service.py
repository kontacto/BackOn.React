"""Financeiro > Transferência p/Fluxo de Caixa (`Geral\\FrmTransfCaixa.frm`,
caption real "Transferência para o Fluxo de Caixa..."). Tela IRMÃ de
`FrmTransfContas.frm` (`transferencia_contas_service.py`) — mas com um
papel BEM diferente: aquela promove Nota Fiscal/Comanda pra Contas a
Pagar/Receber; esta pega o que JÁ está em Contas a Pagar/Receber
(Previsões — ainda aberto, `situacao='A'` — ou Movimentações — já baixado,
`situacao='PG'`) e lança de fato no FLUXO DE CAIXA (`movimentacoes` +
atualização de `contas.saldo_atual`) ou em `previsoes` (sem mexer no saldo
— é só um forecast, ver Fase Previsões abaixo).

**Confirma diretamente o e-mail do Leandro citado em PENDENCIAS.md >
"Baixa de Duplicatas"** (2026-08-28): "A baixa ou cancelamento de
duplicatas não tem que mexer no saldo do fluxo de caixa! Quem faz isso é
a rotina de transferência pra fluxo de caixa" — **esta tela É essa
rotina**. Baixar uma duplicata (`contas_receber_service`/
`contas_pagar_service`) só marca `situacao='PG'`; só quando o usuário
roda esta transferência é que `contas.saldo_atual` realmente muda.

Fonte rastreada linha a linha (`Command1_Click`/listar e
`Command2_Click`/transferir, ~800 linhas). Tags reais geradas pela
listagem ATUAL/viva (não o bloco de "Agrupada por dia" que está inteiro
comentado no `.frm`): `PNFR`/`PNFP` (Previsões Receber/Pagar — situação
ainda Aberta), `NFR `/`NFP ` (Movimentações Receber/Pagar já baixadas,
situação PG), `ECX `/`SCX ` (Entrada/Saída de Caixa já lançadas, ainda
não transferidas).

**Fase 1 implementada aqui** — as 6 tags acima, com split proporcional
por centro de custo (juros/desconto/tarifa bancária) fielmente replicado,
inclusive as classes/sub-classes usadas por cada lado (`controle.
Classe_Sai_*`/`Classe_Ent_*`) — confirmado campo a campo contra a fonte,
**incluindo a assimetria real do legado**: Receber usa sempre `Sai_*`
pros 3 ajustes (juros/desconto/tarifa); Pagar usa `Ent_*` pra
juros/desconto mas `Sai_*` pra tarifa — não é erro de digitação deste
arquivo, é o que o `.frm` literalmente grava (`VCAMPOS(1)/(2)` na tarifa
do NFP), replicado tal como é.

**Fase 2 implementada** (2026-08-29): "Agrupamento de Comandas"
(`Command5_Click`/`FrmAgrCom` — tela de configuração própria — e
`Command6_Click`/tag `NFRA`, consolidando várias comandas do mesmo dia +
forma de pagamento num único lançamento de `movimentacoes`) — feature
opt-in, só entra em jogo quando `agrupa_comandas` tem 1 linha configurada
E pelo menos 1 forma de pagamento marcada em `agrupa_comandas_fp`. Ver
seção própria mais abaixo no arquivo pro rastreio completo, inclusive o
achado de código morto no filtro por tipo de forma de pagamento
(`ag_dinheiro`/`ag_cheque`/etc, nunca portado).

**Confirmado como código morto, NÃO portado**: as tags `MOV ` e `COM `
existem no `Select Case` de `Command2_Click`, mas o bloco de
`Command1_Click` que as geraria está **inteiro comentado** no `.frm` —
são hoje inalcançáveis na prática (a query viva só gera PNFR/PNFP/NFR/
NFRA/NFP/ECX/SCX), não uma regra de negócio perdida.

**Não portado — checagem de licença/integridade `Pos_Sistema`** (bloqueia
Transferir com "Banco de Dados Corrompido..."/validade de chave de
sistema expirada) — mecanismo de licenciamento do VB6 (`Mdl_Proc.bas`),
não regra de negócio desta tela (mesmo princípio "Não replicar truques
VB6" do CLAUDE.md).

**Simplificação registrada**: quando uma duplicata não tem NENHUM rateio
de centro de custo (`receber_custo`/`pagar_custo` vazio — deveria ser raro,
todo lançamento de NF grava rateio), o legado chama uma rotina de
auto-reparo (`CentroCustoReceber`/`CentroCustoPagar`, não rastreada nesta
rodada) que cria um rateio faltante e tenta de novo. Aqui, esse caso ainda
lança o valor financeiro por completo (o dinheiro nunca deixa de mover
corretamente), só cai num centro de custo genérico (`1`) em vez do rateio
real — a granularidade do relatório de centro de custo fica imprecisa
SÓ nesse caso raro, o saldo da conta nunca fica errado.

**Memorando simplificado**: o texto gravado é próximo do legado ("REC.
REF. NF Nº X"/"PAG. REF. NF Nº X"/parcela) mas sem a busca extra de
"amais"/`DadosComandaNF` (link de verificação pública de NFS-e por
município embutido no memorando) — cosmético, não afeta o valor/conta/
classe do lançamento.
"""
import asyncio
import logging
from typing import Optional

from db.connection import _open_conn

logger = logging.getLogger(__name__)


# =============================================================================
# Config (`controle`) — conta padrão de transferência + classes/sub-classes
# usadas nos ajustes de juros/desconto/tarifa bancária
# =============================================================================

def _controle_flags_sync(cur) -> dict:
    cur.execute(
        "SELECT TOP 1 conta_transf_caixa AS conta_transf_caixa, data_fecha_cx AS data_fecha_cx, "
        "Classe_Sai_Tarifa AS sai_tarifa_cl, Sub_Classe_Sai_Tarifa AS sai_tarifa_sc, "
        "Classe_Sai_Juros AS sai_juros_cl, Sub_Classe_Sai_Juros AS sai_juros_sc, "
        "Classe_Sai_Descontos AS sai_desc_cl, Sub_Classe_Sai_Descontos AS sai_desc_sc, "
        "Classe_Ent_Tarifa AS ent_tarifa_cl, Sub_Classe_Ent_Tarifa AS ent_tarifa_sc, "
        "Classe_Ent_Juros AS ent_juros_cl, Sub_Classe_Ent_Juros AS ent_juros_sc, "
        "Classe_Ent_Descontos AS ent_desc_cl, Sub_Classe_Ent_Descontos AS ent_desc_sc "
        "FROM controle"
    )
    r = cur.fetchone() or {}

    def _i(key: str) -> int:
        return int(r.get(key) or 0)

    return {
        "conta_transf_caixa": _i("conta_transf_caixa"),
        "data_fecha_cx": r.get("data_fecha_cx"),
        "sai_tarifa": (_i("sai_tarifa_cl"), _i("sai_tarifa_sc")),
        "sai_juros": (_i("sai_juros_cl"), _i("sai_juros_sc")),
        "sai_desconto": (_i("sai_desc_cl"), _i("sai_desc_sc")),
        "ent_tarifa": (_i("ent_tarifa_cl"), _i("ent_tarifa_sc")),
        "ent_juros": (_i("ent_juros_cl"), _i("ent_juros_sc")),
        "ent_desconto": (_i("ent_desc_cl"), _i("ent_desc_sc")),
    }


def _round2(v) -> float:
    return round(float(v or 0), 2)


def _split_proporcional(rateio: list, valor_total: float) -> list:
    """[(custo, classe_rateio, sub_classe_rateio, valor_aplicado), ...] —
    divide `valor_total` proporcionalmente a `porcusto/realdup` de cada
    linha do rateio, corrigindo o arredondamento na ÚLTIMA linha pra bater
    exatamente com `valor_total` (mesmo padrão do legado — nunca deixa
    sobra/falta por arredondamento)."""
    n = len(rateio)
    if n == 0:
        return []
    if n == 1:
        row = rateio[0]
        return [(row["custo"], row.get("classe_rateio"), row.get("sub_classe_rateio"), _round2(valor_total))]
    resultado = []
    soma_parcial = 0.0
    for i, row in enumerate(rateio):
        realdup = float(row.get("realdup") or 0)
        percentual = _round2((float(row["porcusto"]) / realdup * 100)) if realdup else 0.0
        aplica = _round2(valor_total * percentual / 100)
        soma_parcial += aplica
        if i == n - 1:
            diff = _round2(valor_total - soma_parcial)
            aplica = _round2(aplica + diff)
        resultado.append((row["custo"], row.get("classe_rateio"), row.get("sub_classe_rateio"), aplica))
    return resultado


def _upsert_favorecido_sync(cur, nome: str, conta_transf_contabil: int) -> int:
    """Réplica do `pegadenovo:` do legado — favorecido (contraparte do
    lançamento no fluxo de caixa) é achado/criado por NOME, não por FK de
    cliente/fornecedor (tabela `favorecidos` é independente)."""
    nome = (nome or "SEM NOME").strip()
    cur.execute("SELECT codigo FROM favorecidos WHERE descricao = %s", (nome,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE favorecidos SET conta_transf_contabil = %s WHERE codigo = %s",
            (conta_transf_contabil, row["codigo"]),
        )
        return int(row["codigo"])
    cur.execute(
        "INSERT INTO favorecidos (descricao, conta_transf_contabil) OUTPUT INSERTED.codigo VALUES (%s,%s)",
        (nome, conta_transf_contabil),
    )
    return int(cur.fetchone()["codigo"])


# =============================================================================
# Fase 2 — Agrupamento de Comandas (`Command5_Click`/`FrmAgrCom.frm` +
# `Command6_Click`/tag `NFRA`). Consolida várias comandas do mesmo dia +
# forma de pagamento num único lançamento de `movimentacoes`, com rateio
# de centro de custo somado no fim (`agrupacentrocusto`). Opt-in por
# instalação — só entra em jogo quando `agrupa_comandas` tem 1 linha
# configurada E pelo menos 1 forma de pagamento marcada.
#
# **Achado real, confirmado contra a fonte E contra dado real desta
# migração**: o `Select Case tb("tipoforma")` (`Case "DI"/"CH"/"CC"/"CD"/
# "VA"/"TI"`) que filtraria por TIPO de forma de pagamento (Dinheiro/
# Cheque/Cartão Crédito/Débito/Vale/Ticket) depende das variáveis
# `ag_dinheiro`/`ag_cheque`/`ag_credito`/`ag_debito`/`ag_vale`/`ag_ticket`
# — declaradas no `.frm`, sempre inicializadas `False`, e **nunca
# atribuídas `True` em lugar nenhum do arquivo inteiro** (`FrmAgrCom.frm`
# não tem NENHUM checkbox de tipo — só os 4 de cliente + a lista de forma
# de pagamento). Conferido contra dado real (GERDELL/BARESTELA,
# `forma_pagamento.tipo` tem valores reais "DI"/"CC"/"CD"/"VA"/"TI" em uso
# — os mesmos 6 códigos do `Select Case`) — replicar isso literalmente
# faria QUALQUER forma de pagamento comum (dinheiro, cartão, pix-como-
# dinheiro) ser SEMPRE excluída do agrupamento, o oposto do propósito da
# feature. Confirmado ser código morto/incompleto do legado (variável
# nunca ligável por nenhuma tela), não uma regra de negócio — **não
# portado**: a única filtragem por forma de pagamento é a lista explícita
# de `agrupa_comandas_fp` (o que o usuário marcou na tela de config).
# =============================================================================

def _get_config_agrupamento_sync(cur) -> dict:
    cur.execute("SELECT TOP 1 clientes_diversos AS clientes_diversos, sem_documento AS sem_documento, "
                "cpf AS cpf, cnpj AS cnpj FROM agrupa_comandas")
    cfg = cur.fetchone()
    cur.execute("SELECT codigo FROM agrupa_comandas_fp")
    formas = [r["codigo"] for r in (cur.fetchall() or [])]
    if not cfg:
        return {"ativo": False, "clientes_diversos": False, "sem_documento": False,
                "cpf": False, "cnpj": False, "formas": formas}
    clientes_diversos = bool(cfg.get("clientes_diversos"))
    sem_documento = bool(cfg.get("sem_documento"))
    cpf = bool(cfg.get("cpf"))
    cnpj = bool(cfg.get("cnpj"))
    ativo = bool(formas) and (clientes_diversos or sem_documento or cpf or cnpj)
    return {
        "ativo": ativo, "clientes_diversos": clientes_diversos, "sem_documento": sem_documento,
        "cpf": cpf, "cnpj": cnpj, "formas": formas,
    }


def _obter_config_agrupamento_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        config = _get_config_agrupamento_sync(cur)
        cur.execute("SELECT codigo, descricao FROM forma_pagamento ORDER BY descricao")
        formas_disponiveis = [{"codigo": r["codigo"], "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, **config, "formas_disponiveis": formas_disponiveis}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def obter_config_agrupamento(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_obter_config_agrupamento_sync, servidor, banco)


def _salvar_config_agrupamento_sync(servidor: str, banco: str, dados: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM agrupa_comandas")
        cur.execute("DELETE FROM agrupa_comandas_fp")
        cur.execute(
            "INSERT INTO agrupa_comandas (clientes_diversos, sem_documento, cpf, cnpj) VALUES (%s,%s,%s,%s)",
            (bool(dados.get("clientes_diversos")), bool(dados.get("sem_documento")),
             bool(dados.get("cpf")), bool(dados.get("cnpj"))),
        )
        for codigo in (dados.get("formas") or []):
            cur.execute("INSERT INTO agrupa_comandas_fp (codigo) VALUES (%s)", (str(codigo),))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def salvar_config_agrupamento(servidor: str, banco: str, dados: dict) -> dict:
    return await asyncio.to_thread(_salvar_config_agrupamento_sync, servidor, banco, dados)


def _diversos_codes_sync(cur) -> set:
    """Códigos de cliente tratados como \"Clientes Diversos\" — réplica de
    `Diversos_1`/`Diversos_2` do legado (colapsados num set só, já que em
    Python não precisamos de 2 variáveis pra comparar contra 2 valores)."""
    codes = set()
    cur.execute("SELECT cod_cliente_orcamento FROM controle_aux")
    r = cur.fetchone()
    if r and r.get("cod_cliente_orcamento"):
        codes.add(int(r["cod_cliente_orcamento"]))
    cur.execute("SELECT codigo FROM cliente WHERE nome = 'CLIENTES DIVERSOS'")
    r = cur.fetchone()
    if r:
        codes.add(int(r["codigo"]))
    return codes


def _listar_agrupadas_candidatas_sync(cur, config: dict, periodo: bool, data_ini, data_fim) -> list:
    """Candidatas a `Agrupadas` (tag `NFRA`) — Movimentação a Receber de
    origem Comanda (`dr.desmembramento='CM'`) cuja forma de pagamento está
    marcada pra agrupar (`fp.transf_caixa<>''` E código em
    `agrupa_comandas_fp`), filtradas pelo tipo de cliente (Clientes
    Diversos/Sem documento/CPF/CNPJ) — réplica de `Command1_Click`'s bloco
    `If Trim(Left(seriecontrole,4))="NFRA"`. Item que NÃO passa nesses
    filtros não é descartado aqui — a função quem chama decide se ele volta
    pra listagem normal (mesmo comportamento do `GoTo normal` do legado)."""
    if not config["ativo"]:
        return []
    diversos = _diversos_codes_sync(cur)
    placeholders = ",".join(["%s"] * len(config["formas"]))
    filtro_data = "AND drv.data_pag BETWEEN %s AND %s" if periodo else ""
    params = list(config["formas"]) + ([data_ini, data_fim] if periodo else [])
    cur.execute(
        "SELECT drv.codigo AS seq, c.codigo AS cli_codigo, c.nome AS nome, c.cgc_cpf AS cgc_cpf, "
        "fp.codigo AS forma_codigo, fp.descricao AS forma_descricao, "
        "drv.data_pag AS data_doc, drv.valor_pag AS valor_total "
        "FROM duplicata_receber dr JOIN cliente c ON c.codigo = dr.cliente "
        "JOIN duplicata_rec_venc drv ON drv.duplicata = dr.codigo "
        "JOIN forma_pagamento fp ON fp.codigo = drv.forma_pag "
        f"WHERE dr.desmembramento = 'CM' AND ISNULL(fp.transf_caixa,'') <> '' "
        f"AND drv.situacao = 'PG' AND ISNULL(drv.transf_caixa,'') = '' AND fp.codigo IN ({placeholders}) "
        f"{filtro_data} ORDER BY drv.data_pag",
        params,
    )
    candidatas = []
    for r in cur.fetchall():
        cgc = (r.get("cgc_cpf") or "").strip()
        cli_codigo = r.get("cli_codigo")
        if cli_codigo in diversos:
            if not config["clientes_diversos"]:
                continue
        elif cgc == "":
            if not config["sem_documento"]:
                continue
        elif len(cgc) == 11:
            if not config["cpf"]:
                continue
        elif len(cgc) == 14:
            if not config["cnpj"]:
                continue
        # comprimento de documento fora de 0/11/14 — o legado também não
        # tem ramo de exclusão pra esse caso, passa direto (réplica fiel).
        candidatas.append({
            "codigo": int(r["seq"]),
            "flag": "MovimentacaoReceberAgrupada",
            "nome": (r.get("nome") or "").strip(),
            "forma_pagamento": (r.get("forma_descricao") or "").strip(),
            "num_controle": None,
            "data_doc": r["data_doc"].isoformat() if r.get("data_doc") else None,
            "valor_total": float(r.get("valor_total") or 0),
        })
    return candidatas


# =============================================================================
# Listagem (`Command1_Click`) — Previsões/Movimentações/Entrada-Saída de
# Caixa, ainda não transferidos
# =============================================================================

def _listar_pendentes_sync(servidor: str, banco: str, opcoes: dict) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        flags = _controle_flags_sync(cur)
        if not flags["conta_transf_caixa"]:
            return {"success": False, "message": "Defina em Controle do Sistema a Conta de Transferência para o Fluxo de Caixa.", "items": []}

        periodo = bool(opcoes.get("periodo"))
        data_ini = opcoes.get("data_ini")
        data_fim = opcoes.get("data_fim")
        if periodo and (not data_ini or not data_fim):
            return {"success": False, "message": "Defina o período corretamente.", "items": []}

        data_fecha_cx = flags.get("data_fecha_cx")

        config_agrupamento = _get_config_agrupamento_sync(cur)
        agrupadas = _listar_agrupadas_candidatas_sync(cur, config_agrupamento, periodo, data_ini, data_fim)
        codigos_agrupados = {a["codigo"] for a in agrupadas}

        partes = []
        # Previsões — "Todos em Aberto" não filtra data nenhuma (mesmo o
        # legado: `IIf(Option1.Value, "", "... entre datas ...")`).
        filtro_prev = f"AND drv.dt_vencimento BETWEEN '{data_ini}' AND '{data_fim}'" if periodo else ""
        if opcoes.get("prev_receber"):
            partes.append((
                "PrevisaoReceber",
                "SELECT drv.codigo AS seq, c.nome AS nome, dr.duplicata AS num_controle, "
                "drv.dt_vencimento AS data_doc, drv.valor AS valor_total "
                "FROM duplicata_receber dr JOIN cliente c ON c.codigo = dr.cliente "
                "JOIN duplicata_rec_venc drv ON drv.duplicata = dr.codigo "
                f"WHERE drv.situacao = 'A' AND ISNULL(drv.transf_previsao,'') = '' {filtro_prev}",
            ))
        if opcoes.get("prev_pagar"):
            partes.append((
                "PrevisaoPagar",
                "SELECT dpv.codigo AS seq, f.nome AS nome, dp.duplicata AS num_controle, "
                "dpv.dt_vencimento AS data_doc, dpv.valor AS valor_total "
                "FROM duplicata_pagar dp JOIN fornecedor f ON f.codigo_int = dp.fornecedor "
                "JOIN duplicata_pag_venc dpv ON dpv.duplicata = dp.codigo "
                f"WHERE dpv.situacao = 'A' AND ISNULL(dpv.transf_previsao,'') = '' {filtro_prev}",
            ))

        # Movimentações (já baixadas) — "Todos em Aberto" filtra por
        # `data_pag > data_fecha_cx` (só o que foi pago depois do último
        # fechamento de caixa), réplica exata do legado.
        if periodo:
            filtro_mov = f"AND drv.data_pag BETWEEN '{data_ini}' AND '{data_fim}'"
            filtro_mov_p = f"AND dpv.data_pag BETWEEN '{data_ini}' AND '{data_fim}'"
        elif data_fecha_cx:
            filtro_mov = "AND drv.data_pag > %(data_fecha_cx)s" % {"data_fecha_cx": f"'{data_fecha_cx}'"}
            filtro_mov_p = "AND dpv.data_pag > %(data_fecha_cx)s" % {"data_fecha_cx": f"'{data_fecha_cx}'"}
        else:
            filtro_mov = ""
            filtro_mov_p = ""
        if opcoes.get("mov_receber"):
            partes.append((
                "MovimentacaoReceber",
                "SELECT drv.codigo AS seq, c.nome AS nome, dr.duplicata AS num_controle, "
                "drv.data_pag AS data_doc, drv.valor_pag AS valor_total "
                "FROM duplicata_receber dr JOIN cliente c ON c.codigo = dr.cliente "
                "JOIN duplicata_rec_venc drv ON drv.duplicata = dr.codigo "
                f"WHERE drv.situacao = 'PG' AND ISNULL(drv.transf_caixa,'') = '' {filtro_mov}",
            ))
        if opcoes.get("mov_pagar"):
            partes.append((
                "MovimentacaoPagar",
                "SELECT dpv.codigo AS seq, f.nome AS nome, dp.duplicata AS num_controle, "
                "dpv.data_pag AS data_doc, dpv.valor_pag AS valor_total "
                "FROM duplicata_pagar dp JOIN fornecedor f ON f.codigo_int = dp.fornecedor "
                "JOIN duplicata_pag_venc dpv ON dpv.duplicata = dp.codigo "
                f"WHERE dpv.situacao = 'PG' AND ISNULL(dpv.transf_caixa,'') = '' {filtro_mov_p}",
            ))

        # Entrada/Saída de Caixa — "Todos em Aberto" não filtra data (mesmo
        # padrão de Previsões).
        filtro_caixa = f"AND data BETWEEN '{data_ini}' AND '{data_fim}'" if periodo else ""
        if opcoes.get("entrada_caixa"):
            partes.append((
                "EntradaCaixa",
                "SELECT entrada_caixa.codigo AS seq, favorecidos.descricao AS nome, "
                "entrada_caixa.codigo AS num_controle, data AS data_doc, valor AS valor_total "
                "FROM entrada_caixa JOIN favorecidos ON favorecidos.codigo = entrada_caixa.favorecido "
                f"WHERE ISNULL(entrada_caixa.transf_caixa,'') = '' {filtro_caixa}",
            ))
        if opcoes.get("saida_caixa"):
            partes.append((
                "SaidaCaixa",
                "SELECT saida_caixa.codigo AS seq, favorecidos.descricao AS nome, "
                "saida_caixa.codigo AS num_controle, data AS data_doc, valor AS valor_total "
                "FROM saida_caixa JOIN favorecidos ON favorecidos.codigo = saida_caixa.favorecido "
                f"WHERE ISNULL(saida_caixa.transf_caixa,'') = '' {filtro_caixa}",
            ))

        if not partes:
            return {"success": False, "message": "Defina o que vai ser transferido.", "items": []}

        items = []
        for flag, sql in partes:
            cur.execute(sql + " ORDER BY data_doc")
            for r in cur.fetchall():
                codigo = int(r["seq"])
                # Movimentação a Receber de origem Comanda que já vai
                # aparecer agrupada (Fase 2) some da lista normal — evita
                # o mesmo vencimento poder ser transferido 2x por 2
                # caminhos diferentes. O que NÃO passou nos filtros de
                # agrupamento continua aqui normalmente (mesmo
                # comportamento do `GoTo normal` do legado).
                if flag == "MovimentacaoReceber" and codigo in codigos_agrupados:
                    continue
                items.append({
                    "codigo": codigo,
                    "flag": flag,
                    "nome": (r.get("nome") or "").strip(),
                    "num_controle": r.get("num_controle"),
                    "data_doc": r["data_doc"].isoformat() if r.get("data_doc") else None,
                    "valor_total": float(r.get("valor_total") or 0),
                })
        cur.close()
        conn.close()
        return {
            "success": True, "items": items, "agrupadas": agrupadas,
            "agrupamento_ativo": config_agrupamento["ativo"],
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def listar_pendentes(servidor: str, banco: str, opcoes: dict) -> dict:
    return await asyncio.to_thread(_listar_pendentes_sync, servidor, banco, opcoes)


# =============================================================================
# Previsões (`Case "PNFR"`/`Case "PNFP"`) — NÃO mexe em contas.saldo_atual,
# só registra o forecast em `previsoes`/`previsoes_centro_custo`.
# =============================================================================

def _rateio_receber_sync(cur, drv_codigo: int) -> list:
    cur.execute(
        "SELECT dr.codigo AS dup_codigo, dr.cliente AS cliente, c.nome AS cliente_nome, "
        "c.conta_transf_caixa AS conta_cliente, c.classe_caixa AS classe_cliente, "
        "c.sub_classe_caixa AS subclasse_cliente, c.conta_transf_contabil AS conta_contabil_cliente, "
        "drv.conta AS conta_venc, dr.valor AS realdup, drv.valor_pag AS valor_pag, "
        "dr.num_parcelas AS num_parcelas, "
        "drv.desmembramento AS parcela, dr.dt_emissao AS dt_emissao, drv.dt_vencimento AS dt_vencimento, "
        "drv.data_pag AS data_pag, drv.obs_vencimento AS obs_vencimento, "
        "drv.desconto_pag + drv.outros_desc_pag AS descontos, "
        "drv.juros_pag + drv.outros_acres_pag AS juros, drv.tarifa_banco AS tarifa_banco "
        "FROM cliente c JOIN duplicata_receber dr ON dr.cliente = c.codigo "
        "JOIN duplicata_rec_venc drv ON drv.duplicata = dr.codigo WHERE drv.codigo = %s",
        (drv_codigo,),
    )
    cab = cur.fetchone()
    if not cab:
        return []
    cur.execute(
        "SELECT rc.custo AS custo, SUM(rc.valor) AS porcusto, rc.rc_classe AS classe_rateio, "
        "rc.rc_sub_classe AS sub_classe_rateio, cc.classe_saida AS classe_saida, "
        "cc.sub_classe_saida AS sub_classe_saida "
        "FROM receber r JOIN receber_custo rc ON rc.nota = r.codigo "
        "JOIN centro_custo cc ON cc.codigo = rc.custo "
        "JOIN duplicata_rec_nf drnf ON drnf.nf_fiscal = r.codigo "
        "WHERE drnf.duplicata = %s GROUP BY rc.custo, rc.rc_classe, rc.rc_sub_classe, "
        "cc.classe_saida, cc.sub_classe_saida ORDER BY rc.custo",
        (cab["dup_codigo"],),
    )
    linhas = cur.fetchall() or []
    for linha in linhas:
        linha["realdup"] = cab["realdup"]
        if not linha.get("classe_rateio"):
            linha["classe_rateio"] = linha.get("classe_saida")
            linha["sub_classe_rateio"] = linha.get("sub_classe_saida")
    return [cab, linhas]


def _rateio_pagar_sync(cur, dpv_codigo: int) -> list:
    cur.execute(
        "SELECT dp.codigo AS dup_codigo, dp.fornecedor AS fornecedor, f.nome AS fornecedor_nome, "
        "f.conta_transf_caixa AS conta_fornecedor, f.classe_caixa AS classe_fornecedor, "
        "f.sub_classe_caixa AS subclasse_fornecedor, f.conta_transf_contabil AS conta_contabil_fornecedor, "
        "dpv.conta AS conta_venc, dp.valor AS realdup, dpv.valor_pag AS valor_pag, "
        "dp.num_parcelas AS num_parcelas, "
        "dpv.desmembramento AS parcela, dp.dt_emissao AS dt_emissao, dpv.dt_vencimento AS dt_vencimento, "
        "dpv.data_pag AS data_pag, dpv.obs_vencimento AS obs_vencimento, "
        "dpv.desconto_pag + dpv.outros_desc_pag AS descontos, "
        "dpv.juros_pag + dpv.outros_acres_pag AS juros, dpv.tarifa_banco AS tarifa_banco "
        "FROM fornecedor f JOIN duplicata_pagar dp ON dp.fornecedor = f.codigo_int "
        "JOIN duplicata_pag_venc dpv ON dpv.duplicata = dp.codigo WHERE dpv.codigo = %s",
        (dpv_codigo,),
    )
    cab = cur.fetchone()
    if not cab:
        return []
    cur.execute(
        "SELECT pc.custo AS custo, SUM(pc.valor) AS porcusto, pc.pc_classe AS classe_rateio, "
        "pc.pc_sub_classe AS sub_classe_rateio, cc.classe_entrada AS classe_entrada, "
        "cc.sub_classe_entrada AS sub_classe_entrada "
        "FROM pagar p JOIN pagar_custo pc ON pc.nota = p.codigo "
        "JOIN centro_custo cc ON cc.codigo = pc.custo "
        "JOIN duplicata_pag_nf dpnf ON dpnf.nf_fiscal = p.codigo "
        "WHERE dpnf.duplicata = %s GROUP BY pc.custo, pc.pc_classe, pc.pc_sub_classe, "
        "cc.classe_entrada, cc.sub_classe_entrada ORDER BY pc.custo",
        (cab["dup_codigo"],),
    )
    linhas = cur.fetchall() or []
    for linha in linhas:
        linha["realdup"] = cab["realdup"]
        if not linha.get("classe_rateio"):
            linha["classe_rateio"] = linha.get("classe_entrada")
            linha["sub_classe_rateio"] = linha.get("sub_classe_entrada")
    return [cab, linhas]


def _memorando(prefixo: str, tipo: str, controle: int, cab: dict) -> str:
    parcela_txt = ""
    if int(cab.get("num_parcelas") or 1) > 1:
        parcela_txt = f" ({cab.get('parcela')}/{cab.get('num_parcelas')})"
    obs = (cab.get("obs_vencimento") or "").strip()
    return f"{prefixo} REF. {tipo} Nº {controle}{parcela_txt}{(' ' + obs) if obs else ''}"


def _transferir_previsao_receber_sync(cur, flags: dict, drv_codigo: int) -> dict:
    cur.execute("SELECT transf_previsao FROM duplicata_rec_venc WHERE codigo = %s", (drv_codigo,))
    row = cur.fetchone()
    if not row:
        return {"success": False, "message": f"Vencimento {drv_codigo} não encontrado."}
    if (row.get("transf_previsao") or "").strip() == "T":
        return {"success": False, "message": "Esta previsão já foi transferida."}

    rateio = _rateio_receber_sync(cur, drv_codigo)
    if not rateio:
        return {"success": False, "message": f"Vencimento {drv_codigo} não encontrado."}
    cab, linhas = rateio

    favorecido = _upsert_favorecido_sync(cur, cab.get("cliente_nome"), cab.get("conta_contabil_cliente") or 0)

    if cab.get("conta_venc"):
        usaconta = int(cab["conta_venc"])
    elif cab.get("conta_cliente"):
        usaconta = int(cab["conta_cliente"])
    else:
        usaconta = flags["conta_transf_caixa"]

    if not linhas:
        linhas = [{"custo": 1, "porcusto": cab["realdup"], "realdup": cab["realdup"],
                   "classe_rateio": None, "sub_classe_rateio": None}]

    memorando = _memorando("REC.", "NF", drv_codigo, cab)
    cur.execute(
        "INSERT INTO previsoes (conta,data_documento,documento,data_vencimento,favorecido,valor,tipo,"
        "memorando,frequencia,flag_transf_caixa,cod_transf_caixa) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,1,%s,10,'R',%s)",
        (usaconta, cab["dt_emissao"], drv_codigo, cab["dt_vencimento"], favorecido,
         cab["realdup"], memorando, drv_codigo),
    )
    codprev = cur.fetchone()["codigo"]

    for custo, classe, sub_classe, valor in _split_proporcional(linhas, float(cab["realdup"] or 0)):
        cur.execute(
            "INSERT INTO previsoes_centro_custo (codigo_prev,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'C')",
            (codprev, custo, classe or 0, sub_classe or 0, valor, memorando),
        )

    cur.execute("UPDATE duplicata_rec_venc SET transf_previsao = 'T' WHERE codigo = %s", (drv_codigo,))
    return {"success": True}


def _transferir_previsao_pagar_sync(cur, flags: dict, dpv_codigo: int) -> dict:
    cur.execute("SELECT transf_previsao FROM duplicata_pag_venc WHERE codigo = %s", (dpv_codigo,))
    row = cur.fetchone()
    if not row:
        return {"success": False, "message": f"Vencimento {dpv_codigo} não encontrado."}
    if (row.get("transf_previsao") or "").strip() == "T":
        return {"success": False, "message": "Esta previsão já foi transferida."}

    rateio = _rateio_pagar_sync(cur, dpv_codigo)
    if not rateio:
        return {"success": False, "message": f"Vencimento {dpv_codigo} não encontrado."}
    cab, linhas = rateio

    favorecido = _upsert_favorecido_sync(cur, cab.get("fornecedor_nome"), cab.get("conta_contabil_fornecedor") or 0)

    if cab.get("conta_venc"):
        usaconta = int(cab["conta_venc"])
    elif cab.get("conta_fornecedor"):
        usaconta = int(cab["conta_fornecedor"])
    else:
        usaconta = flags["conta_transf_caixa"]

    if not linhas:
        linhas = [{"custo": 1, "porcusto": cab["realdup"], "realdup": cab["realdup"],
                   "classe_rateio": None, "sub_classe_rateio": None}]

    memorando = _memorando("PAG.", "NF", dpv_codigo, cab)
    cur.execute(
        "INSERT INTO previsoes (conta,data_documento,documento,data_vencimento,favorecido,valor,tipo,"
        "memorando,frequencia,flag_transf_caixa,cod_transf_caixa) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,0,%s,10,'P',%s)",
        (usaconta, cab["dt_emissao"], dpv_codigo, cab["dt_vencimento"], favorecido,
         cab["realdup"], memorando, dpv_codigo),
    )
    codprev = cur.fetchone()["codigo"]

    for custo, classe, sub_classe, valor in _split_proporcional(linhas, float(cab["realdup"] or 0)):
        cur.execute(
            "INSERT INTO previsoes_centro_custo (codigo_prev,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'D')",
            (codprev, custo, classe or 0, sub_classe or 0, valor, memorando),
        )

    cur.execute("UPDATE duplicata_pag_venc SET transf_previsao = 'T' WHERE codigo = %s", (dpv_codigo,))
    return {"success": True}


# =============================================================================
# Movimentações já baixadas (`Case "NFR "`/`Case "NFP "`) — lança em
# `movimentacoes` (+ ajustes de juros/desconto/tarifa por centro de custo)
# E atualiza `contas.saldo_atual` de verdade.
# =============================================================================

def _lancar_ajustes_receber_sync(cur, flags: dict, cod_mov: int, drv_codigo: int, cab: dict,
                                  linhas: list, valor_liquido: float, tipo: str = "NF") -> float:
    """Lança juros/desconto/tarifa bancária como ajustes próprios em
    `movimentacoes_centro_custo` (mesmo centro de custo da 1ª linha do
    rateio) e devolve o valor que sobra pra dividir no rateio principal —
    réplica exata do trecho comum a `Case "NFR "` e `Case "NFRA"` no
    legado (mesmo cálculo, só o `cod_mov` muda entre o caminho normal — um
    por título — e o agrupado — compartilhado por vários títulos)."""
    valor_rateio = valor_liquido
    juros = _round2(cab.get("juros"))
    if juros:
        cl, sc = flags["sai_juros"]
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'C')",
            (cod_mov, linhas[0]["custo"], cl, sc, juros, _memorando("REC. JUROS", tipo, drv_codigo, cab)),
        )
        valor_rateio = _round2(valor_rateio - juros)
    descontos = _round2(cab.get("descontos"))
    if descontos:
        cl, sc = flags["sai_desconto"]
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'D')",
            (cod_mov, linhas[0]["custo"], cl, sc, descontos, _memorando("DESCONTOS", tipo, drv_codigo, cab)),
        )
        valor_rateio = _round2(valor_rateio + descontos)
    tarifa = _round2(cab.get("tarifa_banco"))
    if tarifa:
        cl, sc = flags["sai_tarifa"]
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'C')",
            (cod_mov, linhas[0]["custo"], cl, sc, tarifa, _memorando("REC. TARIFA BANCÁRIA", tipo, drv_codigo, cab)),
        )
        valor_rateio = _round2(valor_rateio - tarifa)
    return valor_rateio


def _transferir_mov_receber_sync(cur, flags: dict, drv_codigo: int) -> dict:
    cur.execute(
        "SELECT codigo FROM movimentacoes WHERE flag_transf_caixa = 'R' AND cod_transf_caixa = %s",
        (drv_codigo,),
    )
    if cur.fetchone():
        return {"success": False, "message": "Este título já foi transferido para o Fluxo de Caixa."}

    rateio = _rateio_receber_sync(cur, drv_codigo)
    if not rateio:
        return {"success": False, "message": f"Vencimento {drv_codigo} não encontrado."}
    cab, linhas = rateio

    favorecido = _upsert_favorecido_sync(cur, cab.get("cliente_nome"), cab.get("conta_contabil_cliente") or 0)

    if cab.get("conta_venc"):
        usaconta = int(cab["conta_venc"])
    elif cab.get("conta_cliente"):
        usaconta = int(cab["conta_cliente"])
    else:
        usaconta = flags["conta_transf_caixa"]

    if not linhas:
        linhas = [{"custo": 1, "porcusto": cab["realdup"], "realdup": cab["realdup"],
                   "classe_rateio": None, "sub_classe_rateio": None}]

    valor_liquido = _round2(cab["valor_pag"] if cab.get("data_pag") else cab["realdup"])
    memorando = _memorando("REC.", "NF", drv_codigo, cab)
    cur.execute(
        "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
        "favorecido,valor,tipo,memorando,flag_transf_caixa,cod_transf_caixa) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s,'R',%s)",
        (usaconta, cab["data_pag"] or cab["dt_vencimento"], drv_codigo, cab["dt_emissao"],
         cab["dt_vencimento"], favorecido, valor_liquido, memorando, drv_codigo),
    )
    cod_mov = cur.fetchone()["codigo"]
    cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s",
                (valor_liquido, usaconta))

    valor_rateio = _lancar_ajustes_receber_sync(cur, flags, cod_mov, drv_codigo, cab, linhas, valor_liquido)

    for custo, classe, sub_classe, valor in _split_proporcional(linhas, valor_rateio):
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "credito_debito) VALUES (%s,%s,%s,%s,%s,'C')",
            (cod_mov, custo, classe or 0, sub_classe or 0, valor),
        )

    cur.execute("UPDATE duplicata_rec_venc SET transf_caixa = 'T' WHERE codigo = %s", (drv_codigo,))
    cur.execute("DELETE FROM previsoes WHERE flag_transf_caixa = 'R' AND cod_transf_caixa = %s", (drv_codigo,))
    return {"success": True}


def _transferir_mov_pagar_sync(cur, flags: dict, dpv_codigo: int) -> dict:
    cur.execute(
        "SELECT codigo FROM movimentacoes WHERE flag_transf_caixa = 'P' AND cod_transf_caixa = %s",
        (dpv_codigo,),
    )
    if cur.fetchone():
        return {"success": False, "message": "Este título já foi transferido para o Fluxo de Caixa."}

    rateio = _rateio_pagar_sync(cur, dpv_codigo)
    if not rateio:
        return {"success": False, "message": f"Vencimento {dpv_codigo} não encontrado."}
    cab, linhas = rateio

    favorecido = _upsert_favorecido_sync(cur, cab.get("fornecedor_nome"), cab.get("conta_contabil_fornecedor") or 0)

    if cab.get("conta_venc"):
        usaconta = int(cab["conta_venc"])
    elif cab.get("conta_fornecedor"):
        usaconta = int(cab["conta_fornecedor"])
    else:
        usaconta = flags["conta_transf_caixa"]

    if not linhas:
        linhas = [{"custo": 1, "porcusto": cab["realdup"], "realdup": cab["realdup"],
                   "classe_rateio": None, "sub_classe_rateio": None}]

    valor_liquido = _round2(cab["valor_pag"] if cab.get("data_pag") else cab["realdup"])
    memorando = _memorando("PAG.", "NF", dpv_codigo, cab)
    cur.execute(
        "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
        "favorecido,valor,tipo,memorando,flag_transf_caixa,cod_transf_caixa) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s,'P',%s)",
        (usaconta, cab["data_pag"] or cab["dt_vencimento"], dpv_codigo, cab["dt_emissao"],
         cab["dt_vencimento"], favorecido, valor_liquido, memorando, dpv_codigo),
    )
    cod_mov = cur.fetchone()["codigo"]
    cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s",
                (valor_liquido, usaconta))

    valor_rateio = valor_liquido
    juros = _round2(cab.get("juros"))
    if juros:
        cl, sc = flags["ent_juros"]
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'D')",
            (cod_mov, linhas[0]["custo"], cl, sc, juros, _memorando("PAG. JUROS", "NF", dpv_codigo, cab)),
        )
        valor_rateio = _round2(valor_rateio - juros)
    descontos = _round2(cab.get("descontos"))
    if descontos:
        cl, sc = flags["ent_desconto"]
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'C')",
            (cod_mov, linhas[0]["custo"], cl, sc, descontos, _memorando("REC. DESCONTOS", "NF", dpv_codigo, cab)),
        )
        valor_rateio = _round2(valor_rateio + descontos)
    tarifa = _round2(cab.get("tarifa_banco"))
    if tarifa:
        cl, sc = flags["sai_tarifa"]
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,%s,'D')",
            (cod_mov, linhas[0]["custo"], cl, sc, tarifa, _memorando("PAG. TARIFA BANCÁRIA", "NF", dpv_codigo, cab)),
        )
        valor_rateio = _round2(valor_rateio - tarifa)

    for custo, classe, sub_classe, valor in _split_proporcional(linhas, valor_rateio):
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "credito_debito) VALUES (%s,%s,%s,%s,%s,'D')",
            (cod_mov, custo, classe or 0, sub_classe or 0, valor),
        )

    cur.execute("UPDATE duplicata_pag_venc SET transf_caixa = 'T' WHERE codigo = %s", (dpv_codigo,))
    cur.execute("DELETE FROM previsoes WHERE flag_transf_caixa = 'P' AND cod_transf_caixa = %s", (dpv_codigo,))
    return {"success": True}


# =============================================================================
# Entrada/Saída de Caixa (`Case "ECX "`/`Case "SCX "`) — mais simples, um
# único centro de custo (já gravado na própria linha).
# =============================================================================

def _transferir_entrada_caixa_sync(cur, flags: dict, codigo: int) -> dict:
    cur.execute(
        "SELECT ec.*, fv.descricao AS favorecido_nome FROM entrada_caixa ec "
        "JOIN favorecidos fv ON fv.codigo = ec.favorecido WHERE ec.codigo = %s",
        (codigo,),
    )
    row = cur.fetchone()
    if not row:
        return {"success": False, "message": f"Entrada de Caixa {codigo} não encontrada."}
    if (row.get("transf_caixa") or "").strip():
        return {"success": False, "message": "Esta Entrada de Caixa já foi transferida."}

    usaconta = int(row["conta"]) if row.get("conta") else flags["conta_transf_caixa"]
    valor = _round2(row["valor"])
    nome_atendente = ""
    cur.execute("SELECT nome_guerra FROM funcionarios WHERE codigo_int = %s", (row.get("atendente"),))
    fr = cur.fetchone()
    if fr:
        nome_atendente = (fr.get("nome_guerra") or "").strip()
    memorando = f"{(row.get('descricao') or '').strip()} (Entrada de Caixa por {nome_atendente})".strip()

    cur.execute(
        "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
        "favorecido,valor,tipo,memorando,flag_transf_caixa,cod_transf_caixa) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s,'E',%s)",
        (usaconta, row["data"], codigo, row["data"], row["data"], row["favorecido"], valor, memorando, codigo),
    )
    cod_mov = cur.fetchone()["codigo"]
    cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s",
                (valor, usaconta))
    cur.execute(
        "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
        "credito_debito) VALUES (%s,%s,%s,%s,%s,'C')",
        (cod_mov, row.get("centro_custo") or 1, row.get("classe") or 0, row.get("sub_classe") or 0, valor),
    )
    cur.execute("UPDATE entrada_caixa SET cod_movimentacao = %s, transf_caixa = 'T' WHERE codigo = %s",
                (cod_mov, codigo))
    return {"success": True}


def _transferir_saida_caixa_sync(cur, flags: dict, codigo: int) -> dict:
    cur.execute(
        "SELECT sc.*, fv.descricao AS favorecido_nome FROM saida_caixa sc "
        "JOIN favorecidos fv ON fv.codigo = sc.favorecido WHERE sc.codigo = %s",
        (codigo,),
    )
    row = cur.fetchone()
    if not row:
        return {"success": False, "message": f"Saída de Caixa {codigo} não encontrada."}
    if (row.get("transf_caixa") or "").strip():
        return {"success": False, "message": "Esta Saída de Caixa já foi transferida."}

    usaconta = int(row["conta"]) if row.get("conta") else flags["conta_transf_caixa"]
    valor = _round2(row["valor"])
    nome_atendente = ""
    cur.execute("SELECT nome_guerra FROM funcionarios WHERE codigo_int = %s", (row.get("atendente"),))
    fr = cur.fetchone()
    if fr:
        nome_atendente = (fr.get("nome_guerra") or "").strip()
    memorando = f"{(row.get('descricao') or '').strip()} (Saída de Caixa por {nome_atendente})".strip()

    # `transferencia = 2` no legado = saída que é a METADE de uma
    # transferência entre 2 contas (a outra metade é uma Entrada de Caixa
    # equivalente, já lançada à parte) — grava com `classe = conta destino`
    # em vez de um centro de custo real, e debita/credita as 2 contas ao
    # mesmo tempo. Réplica fiel dessa regra real (não é workaround).
    transferencia_raw = str(row.get("transferencia") or "").strip()
    transferencia = int(transferencia_raw) if transferencia_raw.isdigit() else 0
    conta_destino = row.get("classe")

    cur.execute(
        "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
        "favorecido,valor,tipo,memorando,flag_transf_caixa,cod_transf_caixa,classe) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'S',%s,%s)",
        (usaconta, row["data"], codigo, row["data"], row["data"], row["favorecido"], valor,
         2 if transferencia == 2 else 0, memorando, codigo, conta_destino if transferencia == 2 else None),
    )
    cod_mov = cur.fetchone()["codigo"]
    cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual - %s AS NUMERIC(15,2)) WHERE codigo = %s",
                (valor, usaconta))
    if transferencia == 2 and conta_destino:
        cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s",
                    (valor, conta_destino))
    else:
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "credito_debito) VALUES (%s,%s,%s,%s,%s,'D')",
            (cod_mov, row.get("centro_custo") or 1, row.get("classe") or 0, row.get("sub_classe") or 0, valor),
        )
    cur.execute("UPDATE saida_caixa SET cod_movimentacao = %s, transf_caixa = 'T' WHERE codigo = %s",
                (cod_mov, codigo))
    return {"success": True}


# =============================================================================
# Ponto de entrada — dispara vários itens numa transação só, isola falha
# por item (mesmo princípio de `transferencia_contas_service.py`).
# =============================================================================

_DISPATCH = {
    "PrevisaoReceber": _transferir_previsao_receber_sync,
    "PrevisaoPagar": _transferir_previsao_pagar_sync,
    "MovimentacaoReceber": _transferir_mov_receber_sync,
    "MovimentacaoPagar": _transferir_mov_pagar_sync,
    "EntradaCaixa": _transferir_entrada_caixa_sync,
    "SaidaCaixa": _transferir_saida_caixa_sync,
}


def _transferir_sync(servidor: str, banco: str, itens: list) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        flags = _controle_flags_sync(cur)
        if not flags["conta_transf_caixa"]:
            return {"success": False, "message": "Defina em Controle do Sistema a Conta de Transferência para o Fluxo de Caixa."}

        sucesso, falhas = [], []
        for item in itens:
            codigo = int(item["codigo"])
            flag = item["flag"]
            fn = _DISPATCH.get(flag)
            if not fn:
                falhas.append({"codigo": codigo, "flag": flag, "message": f"Tipo desconhecido: {flag}"})
                continue
            try:
                resultado = fn(cur, flags, codigo)
            except Exception as e:
                # [GLOBAL] Mensagens de Erro — Linguagem Não-Técnica: nunca
                # despejar texto cru de exceção pro usuário final.
                logger.warning("transferencia_caixa: falha ao transferir item %s (%s)", codigo, flag, exc_info=True)
                resultado = {
                    "success": False,
                    "message": f"Não foi possível transferir o item {codigo} — tente novamente ou avise o suporte se persistir.",
                }
            if resultado.get("success"):
                sucesso.append(codigo)
            else:
                falhas.append({"codigo": codigo, "flag": flag, "message": resultado.get("message")})

        conn.commit()
        cur.close()
        conn.close()
        return {"success": len(falhas) == 0, "transferidos": sucesso, "falhas": falhas}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def transferir(servidor: str, banco: str, itens: list) -> dict:
    return await asyncio.to_thread(_transferir_sync, servidor, banco, itens)


# =============================================================================
# Fase 2 — Transferir Comandas Agrupadas (`Command6_Click`) — consolida os
# itens marcados em grupos por (data_pag, forma de pagamento), 1 lançamento
# de `movimentacoes` por grupo (reaproveitado se um grupo com a mesma
# combinação já existir de uma transferência agrupada anterior — mesmo
# `SELECT codigo FROM movimentacoes WHERE ... AND flag_transf_caixa='X'
# AND cod_transf_caixa=0` do legado), rateio de centro de custo somado no
# fim de cada grupo (`agrupacentrocusto`).
# =============================================================================

def _consolidar_centro_custo_sync(cur, cod_mov: int) -> None:
    """Réplica de `Sub agrupacentrocusto` — soma as várias linhas de
    `movimentacoes_centro_custo` (uma por comanda do grupo) numa linha só
    por (centro_custo,classe,sub_classe)."""
    cur.execute("UPDATE movimentacoes_centro_custo SET codigo_mov = -1 WHERE codigo_mov = %s", (cod_mov,))
    cur.execute(
        "SELECT SUM(valor) AS total, centro_custo, classe, sub_classe FROM movimentacoes_centro_custo "
        "WHERE codigo_mov = -1 GROUP BY centro_custo, classe, sub_classe"
    )
    for linha in (cur.fetchall() or []):
        if linha.get("total") is None:
            continue
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "memorando,credito_debito) VALUES (%s,%s,%s,%s,%s,'','C')",
            (cod_mov, linha["centro_custo"], linha["classe"], linha["sub_classe"], _round2(linha["total"])),
        )
    cur.execute("DELETE FROM movimentacoes_centro_custo WHERE codigo_mov = -1")


def _transferir_item_agrupado_sync(cur, flags: dict, drv_codigo: int, cod_mov: int, usaconta_grupo: int) -> dict:
    cur.execute("SELECT codigo FROM movimentacoes_agrupadas WHERE cod_transf_comanda = %s", (drv_codigo,))
    if cur.fetchone():
        return {"success": False, "message": "Esta comanda já foi transferida (agrupada)."}

    rateio = _rateio_receber_sync(cur, drv_codigo)
    if not rateio:
        return {"success": False, "message": f"Vencimento {drv_codigo} não encontrado."}
    cab, linhas = rateio

    if not linhas:
        linhas = [{"custo": 1, "porcusto": cab["realdup"], "realdup": cab["realdup"],
                   "classe_rateio": None, "sub_classe_rateio": None}]

    # Conta de destino é por-item (cliente pode ter `conta_transf_caixa`
    # própria), mas o CABEÇALHO do grupo (a linha `movimentacoes` em si)
    # já nasceu numa conta fixa — réplica do legado, que também soma o
    # saldo na conta resolvida por item mesmo com um único `CodMov`
    # compartilhado (`Vconta_Transfere` calculado de novo por linha do
    # tb, não fixo pro grupo inteiro).
    if cab.get("conta_venc"):
        usaconta = int(cab["conta_venc"])
    elif cab.get("conta_cliente"):
        usaconta = int(cab["conta_cliente"])
    else:
        usaconta = usaconta_grupo

    cur.execute("INSERT INTO movimentacoes_agrupadas (codigo_mov, cod_transf_comanda) VALUES (%s,%s)",
                (cod_mov, drv_codigo))

    valor_liquido = _round2(cab["valor_pag"] if cab.get("data_pag") else cab["realdup"])
    cur.execute("UPDATE movimentacoes SET valor = valor + %s WHERE codigo = %s", (valor_liquido, cod_mov))
    cur.execute("UPDATE contas SET saldo_atual = CAST(saldo_atual + %s AS NUMERIC(15,2)) WHERE codigo = %s",
                (valor_liquido, usaconta))

    valor_rateio = _lancar_ajustes_receber_sync(cur, flags, cod_mov, drv_codigo, cab, linhas, valor_liquido, tipo="COMANDA")

    for custo, classe, sub_classe, valor in _split_proporcional(linhas, valor_rateio):
        cur.execute(
            "INSERT INTO movimentacoes_centro_custo (codigo_mov,centro_custo,classe,sub_classe,valor,"
            "credito_debito) VALUES (%s,%s,%s,%s,%s,'C')",
            (cod_mov, custo, classe or 0, sub_classe or 0, valor),
        )

    cur.execute("UPDATE duplicata_rec_venc SET transf_caixa = 'T' WHERE codigo = %s", (drv_codigo,))
    cur.execute("DELETE FROM previsoes WHERE flag_transf_caixa = 'R' AND cod_transf_caixa = %s", (drv_codigo,))
    return {"success": True}


def _obter_ou_criar_cabecalho_grupo_sync(cur, flags: dict, data_pag, forma_nome: str) -> int:
    """Acha (ou cria) a linha `movimentacoes` "casca" do grupo — mesma
    combinação (conta padrão, data, favorecido "MOVIMENTO <FORMA>") reusa
    o `CodMov` já existente se uma transferência agrupada anterior já
    tiver aberto esse grupo (réplica do legado: valor 0 na criação,
    `flag_transf_caixa='X'`/`cod_transf_caixa=0` como marca de "cabeçalho
    de grupo", nunca uma transferência normal usa esses valores)."""
    favorecido = _upsert_favorecido_sync(cur, f"MOVIMENTO {forma_nome}", 0)
    usaconta = flags["conta_transf_caixa"]
    cur.execute(
        "SELECT codigo FROM movimentacoes WHERE conta = %s AND data_liquidacao = %s AND favorecido = %s "
        "AND flag_transf_caixa = 'X' AND cod_transf_caixa = 0",
        (usaconta, data_pag, favorecido),
    )
    row = cur.fetchone()
    if row:
        return int(row["codigo"])
    memorando = f"Ref MOVIMENTO {forma_nome} de {data_pag}"
    cur.execute(
        "INSERT INTO movimentacoes (conta,data_liquidacao,documento,data_documento,data_vencimento,"
        "favorecido,valor,tipo,memorando,flag_transf_caixa,cod_transf_caixa) "
        "OUTPUT INSERTED.codigo VALUES (%s,%s,0,%s,%s,%s,0,1,%s,'X',0)",
        (usaconta, data_pag, data_pag, data_pag, favorecido, memorando),
    )
    return int(cur.fetchone()["codigo"])


def _transferir_agrupadas_sync(servidor: str, banco: str, itens: list) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        flags = _controle_flags_sync(cur)
        if not flags["conta_transf_caixa"]:
            return {"success": False, "message": "Defina em Controle do Sistema a Conta de Transferência para o Fluxo de Caixa."}
        config = _get_config_agrupamento_sync(cur)
        if not config["ativo"]:
            return {"success": False, "message": "Agrupamento de Comandas não está configurado/ativo."}

        # Monta os grupos (mesma chave do legado: data de pagamento + nome
        # da forma de pagamento, em maiúsculo).
        grupos: dict = {}
        falhas = []
        for codigo in itens:
            cur.execute(
                "SELECT drv.data_pag AS data_pag, fp.descricao AS forma_descricao "
                "FROM duplicata_rec_venc drv JOIN forma_pagamento fp ON fp.codigo = drv.forma_pag "
                "WHERE drv.codigo = %s",
                (codigo,),
            )
            row = cur.fetchone()
            if not row or not row.get("data_pag"):
                falhas.append({"codigo": codigo, "message": f"Vencimento {codigo} não encontrado."})
                continue
            chave = (row["data_pag"], (row.get("forma_descricao") or "").strip().upper())
            grupos.setdefault(chave, []).append(codigo)

        sucesso = []
        for (data_pag, forma_nome), codigos in grupos.items():
            cod_mov = _obter_ou_criar_cabecalho_grupo_sync(cur, flags, data_pag, forma_nome)
            for codigo in codigos:
                try:
                    resultado = _transferir_item_agrupado_sync(cur, flags, codigo, cod_mov, flags["conta_transf_caixa"])
                except Exception as e:
                    logger.warning("transferencia_caixa (agrupada): falha no item %s", codigo, exc_info=True)
                    resultado = {
                        "success": False,
                        "message": f"Não foi possível transferir o item {codigo} — tente novamente ou avise o suporte se persistir.",
                    }
                if resultado.get("success"):
                    sucesso.append(codigo)
                else:
                    falhas.append({"codigo": codigo, "message": resultado.get("message")})
            _consolidar_centro_custo_sync(cur, cod_mov)

        conn.commit()
        cur.close()
        conn.close()
        return {"success": len(falhas) == 0, "transferidos": sucesso, "falhas": falhas}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def transferir_agrupadas(servidor: str, banco: str, itens: list) -> dict:
    return await asyncio.to_thread(_transferir_agrupadas_sync, servidor, banco, itens)


def _tem_pendencia_sync(servidor: str, banco: str) -> dict:
    """Usado pelo grupo 'Pendências do Sistema' da Sidebar (contagem
    rápida, sem aplicar filtro de período — mesmo espírito de
    `useTransferenciaPendenteCount`/`transferencia_contas`)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "pendentes": 0}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM duplicata_rec_venc WHERE situacao='PG' AND ISNULL(transf_caixa,'')='') + "
            "(SELECT COUNT(*) FROM duplicata_pag_venc WHERE situacao='PG' AND ISNULL(transf_caixa,'')='') + "
            "(SELECT COUNT(*) FROM entrada_caixa WHERE ISNULL(transf_caixa,'')='') + "
            "(SELECT COUNT(*) FROM saida_caixa WHERE ISNULL(transf_caixa,'')='') AS pendentes"
        )
        r = cur.fetchone() or {}
        cur.close()
        conn.close()
        return {"success": True, "pendentes": int(r.get("pendentes") or 0)}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "pendentes": 0}


async def tem_pendencia(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_tem_pendencia_sync, servidor, banco)
