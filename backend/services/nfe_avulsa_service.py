"""Transações > Notas Fiscais > **Gerar NFe** (NF-e Avulsa, modelo 55) —
migração de `NFe\\frmtranfe.frm`, rastreada por completo 2026-08-19/20 —
ver PENDENCIAS.md > "Rastreio completo de `frmtranfe.frm`" pro racional
completo. Protocolo Gauntlet acionado (Leandro+Carlos+Thomé, Apoio Fisco
na tela). **NÃO confundir com `notas_fiscais_service.py`** ("Manutenção
de Notas Fiscais", migração de `FrmManRec.frm`) — essa é tela de
CONSULTA + ações pós-emissão (DANFE/cancelar/carta de correção/XML),
nunca tocada por este módulo; esta feature (`nfe_avulsa_service.py`) é a
tela de GERAR/EMITIR uma nota nova, digitada livremente.

**Achados-chave da fonte, replicados aqui**:
- Cabeçalho + itens digitados livremente, pra QUALQUER tipo de
  movimentação (`tipo_mov`, entrada ou saída) — destinatário é cliente OU
  fornecedor conforme `tipo_mov.origem_destino`.
- Arquitetura real é rascunho→definitivo: enquanto sendo digitada, tudo
  fica em `nf_aux`/`nf_aux_itens`/`nf_aux_vencimento` (tabelas espelho,
  confirmadas via `INFORMATION_SCHEMA.COLUMNS` real 2026-08-20 — nomes de
  coluna abaixo não são presumidos); só ao Emitir promove pra `n_fiscal`/
  `n_fiscal_itens`/`nf_vencimento`.

**3 decisões de negócio confirmadas com o usuário (2026-08-20)**:
1. ICMS/IPI/ISS por item são SUGERIDOS via cascata de tributação
   (`nfe_emissao_service._resolver_tributacao_sync`, mesma já usada por
   NFC-e/NF-e agrupada) mas livremente editáveis antes de gravar o
   rascunho.
2. PIS/COFINS NUNCA é digitável — calculado só no momento de Emitir,
   direto em `n_fiscal_itens` (não existe coluna pra isso em
   `nf_aux_itens`, confirmado no schema real).
3. **Revertido 2026-08-20, mesmo dia** (mesmo princípio aplicado em
   `nfe_agrupada_service.py`, achado ao investigar um bug real de
   assinatura perdida lá): IBS/CBS agora é calculado JUNTO com o resto
   da tributação (ICMS/PIS/COFINS), **antes** de `emitir_nfe_sync` —
   embutido no XML original que sai assinado/transmitido, nunca um
   enriquecimento à parte depois. "IBS/CBS não é nada mais que um grupo
   dentro do XML, como qualquer outro" (orientação direta do usuário).
   As colunas estruturadas de `n_fiscal_itens` (`CST_IBS_UF`/`VALOR_IBS_
   UF`/`CST_CBS`/`VALOR_CBS`/etc.) e `n_fiscal.XML_TOT_IBS_CBS` continuam
   gravadas (úteis pra consulta/relatório sem parsear XML), mas com o
   MESMO valor já calculado antes da emissão — nunca recalculado de
   novo depois.

**Simplificações desta fase, documentadas** (ver PENDENCIAS.md pra lista
completa): CFOP é só de cabeçalho (não por item — `nf_aux` não tem CFOP
por item neste desenho); sem reemissão de rascunho já promovido; sem
`nf_coligada`/`n_fiscal_vinculada`.

**PIS/COFINS cruzado linha-a-linha contra `SetaPisCofins`/`LancaPisCofins`
2026-08-22** (`NFe\\frmtranfe.frm:8811/8311`, chamadas por `Calcula()` —
a rotina que roda no fechamento/emissão, não `JogaV()`, que só sugere na
tela) — ver `_calcular_pis_cofins_item`. Achado real: a versão anterior
só implementava o caminho `taxas.CST_TRIB_PIS`/`ALQT_TRIB_PIS`
("Caminho A"), tratando `CST_TRIB_PIS` vazio como CST 07/R$0,00. O
legado, quando esse campo vem vazio, cai inteiro pro cadastro do próprio
produto/serviço (`pecas`/`servicos`.`tributacao_pis`/`perc_valor_pis`/
etc., "Caminho B") — confirmado real (não teórico) ao vivo contra ARGEN
TESTE: **82/82 linhas de `taxas` têm `CST_TRIB_PIS` vazio** (Caminho A
nunca resolvia nessa instalação) e 2670/2681 produtos têm valor real só
no Caminho B — sem o fix, toda NF-e Avulsa emitida ali sairia com PIS/
COFINS zerado e CST errado em todo item. Uma única divergência
deliberada da fonte (não replicação 1:1): o VB6 usa uma variável
`basepiscofins` compartilhada entre PIS e COFINS, então zerar a base do
PIS também zera a do COFINS por efeito colateral de reuso de variável
(nenhuma razão tributária real) — replicado aqui como dois cálculos
independentes, ver docstring da função.

**As 6 sub-rotinas de importação automática (Pedido/Devolução/Compra/
Requisição/Nota Fiscal/Complementar) foram implementadas 2026-08-20** —
ver seção "Importação automática" mais abaixo neste arquivo e
PENDENCIAS.md > "6 sub-rotinas de importação automática" pro racional
completo (schema real confirmado ao vivo, achados sobre CFOP não
resolvido automaticamente pra Pedido/Compra/Requisição, FCP 2%
hardcoded confirmado na fonte).

**NUNCA testado contra o SEFAZ real** — mesma ressalva de todo o resto
do pacote fiscal desta migração.

**Reauditoria 2026-08-21** (ver PENDENCIAS.md > "🔴 FRENTE ATIVA" e
CLAUDE.md > "Toda ramificação condicional..."): achado real corrigido —
`controle.soma_iss` (`CmdOk_Click`, `frmtranfe.frm:5612-5615`) zera o
ISS de TODO item quando desligado, nunca era checado aqui. Corrigido em
`_save_itens_rascunho_sync` (reforçado no servidor, não confia só no
frontend)."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services import contingencia_nfe_service, ibs_cbs_service, nfe_emissao_service, nfe_fiscal_common
from services.permissoes_service import tem_permissao

_CAB_CAMPOS_AUX = [
    "cod_fiscal", "fornecedor", "mov", "cfop",
    "data", "data_mov", "data_saida", "hora_saida",
    "valor_total", "base_icms", "valor_icms", "base_ipi", "valor_ipi",
    "base_iss", "valor_iss", "base_sub", "valor_sub",
    "frete", "seguro", "despesas", "desconto", "prazo",
    "BASE_FCP", "VALOR_FCP", "ALQT_FCP",
    "BASE_FCP_RETIDO", "VALOR_FCP_RETIDO", "ALQT_FCP_RETIDO",
    "BASE_FCP_ST", "VALOR_FCP_ST", "ALQT_FCP_ST",
    "cnpj_transportadora", "placa", "motorista", "volumes", "especie_volume",
    "peso_bruto", "peso_liquido", "paga_frete",
    "ids_devolucao_origem",
]

_ITEM_CAMPOS_AUX = [
    "codigo_int", "cod_fiscal", "tributacao",
    "qtd", "p_unit", "desconto", "desconto_perc", "valor_total",
    "alqt_icms", "reducao_base_icms", "base_icms", "valor_icms",
    "base_ipi", "alqt_ipi", "valor_ipi",
    "base_sub", "valor_sub", "base_iss", "valor_iss",
    "frete", "seguro", "despesas", "obs_item_nf",
]


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "NFE_AVULSA", comando)


def _ensure_nf_aux_paga_frete_col(cur) -> None:
    """Migração idempotente: coluna `paga_frete` em `nf_aux` (tabela
    legada, `smallint`, mesmo tipo/semântica de `n_fiscal.paga_frete` —
    confirmado real 2026-08-21, ver `nfe_emissao_service._resolver_mod_
    frete`). `frmtranfe.frm` (fonte desta tela) nunca grava esse campo
    (não tem seletor de frete) — coluna nova aditiva, não conflita com
    nada que o legado já faça nesta tabela."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='paga_frete' AND Object_ID=Object_ID('nf_aux')) "
        "ALTER TABLE nf_aux ADD paga_frete SMALLINT NULL"
    )


def _ensure_nf_aux_ids_devolucao_origem_col(cur) -> None:
    """Migração idempotente: `nf_aux.ids_devolucao_origem` (NVARCHAR,
    lista de `devolucao_itens.id_devolucao` separados por vírgula) — SEM
    equivalente direto no legado (lá, `VetDevolucao` é um array só em
    memória, transiente durante o clique único de "Emitir Nfe de
    Devolução"; aqui o rascunho pode ficar em edição por mais tempo antes
    de emitir, então precisa sobreviver no banco). Preenchido por
    `_importar_devolucao_sync` (múltiplos ids, uma NF-e consolidada — real
    achado de fonte: `Command14_Click`/`FrmManDev.frm` monta um array
    `VetDevolucao` com 1+ devoluções, possivelmente de vendas/comandas
    diferentes do MESMO cliente). Lido de volta na emissão
    (`_emitir_nfe_avulsa_sync`) pra atualizar `devolucao_itens.Nfe` com o
    `n_fiscal.codigo` real gerado — mesmo UPDATE que o legado faz
    (`frmtranfe.frm:4453`) logo após confirmar o `Codigo_NF`."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='ids_devolucao_origem' AND Object_ID=Object_ID('nf_aux')) "
        "ALTER TABLE nf_aux ADD ids_devolucao_origem NVARCHAR(200) NULL"
    )


# ---------------------------------------------------------------------------
# Rascunho (nf_aux/nf_aux_itens/nf_aux_vencimento)
# ---------------------------------------------------------------------------

def _novo_rascunho_sync(servidor: str, banco: str, *, classe: Optional[int] = None, master: bool = False) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gerar NF-e avulsa."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        cur.execute("INSERT INTO nf_aux (valor_total) OUTPUT INSERTED.codigo VALUES (0)")
        codigo = int(cur.fetchone()["codigo"])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _get_rascunho_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cols = ", ".join(["codigo", "num_nf"] + _CAB_CAMPOS_AUX)
        cur.execute(f"SELECT {cols} FROM nf_aux WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        cur.execute(
            f"SELECT id_nf_aux, {', '.join(_ITEM_CAMPOS_AUX)} FROM nf_aux_itens "
            "WHERE codigo=%s ORDER BY id_nf_aux",
            (codigo,),
        )
        itens = list(cur.fetchall())
        cur.execute(
            "SELECT SEQUENCIA_NF_AUX_VENCIMENTO AS sequencia, data_venc, valor "
            "FROM nf_aux_vencimento WHERE codigo=%s ORDER BY data_venc",
            (codigo,),
        )
        vencimentos = list(cur.fetchall())
        conn.close()
        return {
            "success": True, "cabecalho": row, "itens": itens, "vencimentos": vencimentos,
            "promovida": bool(row.get("num_nf")),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_cabecalho_rascunho_sync(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    if not codigo:
        return {"success": False, "message": "Rascunho inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT num_nf FROM nf_aux WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        if atual.get("num_nf"):
            conn.close()
            return {"success": False, "message": "Esta NF-e já foi emitida — não é possível editar o rascunho."}

        sets = ", ".join(f"{c}=%s" for c in _CAB_CAMPOS_AUX)
        valores = [dados.get(c) for c in _CAB_CAMPOS_AUX]
        cur.execute(f"UPDATE nf_aux SET {sets} WHERE codigo=%s", (*valores, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _save_itens_rascunho_sync(servidor: str, banco: str, codigo: int, itens: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da NF-e antes de lançar itens."}
    for it in itens:
        if not (it.get("codigo_int") or "").strip():
            return {"success": False, "message": "Todo item precisa de um Código de Produto/Serviço."}
        if not it.get("qtd"):
            return {"success": False, "message": "Todo item precisa de Quantidade maior que zero."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT num_nf FROM nf_aux WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        if atual.get("num_nf"):
            conn.close()
            return {"success": False, "message": "Esta NF-e já foi emitida — não é possível editar o rascunho."}

        # Achado real, `NFe\frmtranfe.frm:5612-5615` (`CmdOk_Click`, o
        # "Confirmar Item"): `controle.soma_iss` (config real por
        # instalação) zera o ISS de TODO item quando desligada — "If Not
        # Soma_Iss Then Camp(13)=0: Camp(12)=0". Reforçado aqui no
        # servidor (não confia só no frontend), mesmo princípio já usado
        # noutras configs deste projeto.
        cur.execute("SELECT soma_iss FROM controle")
        ctrl = cur.fetchone() or {}
        soma_iss = bool(ctrl.get("soma_iss"))

        cur.execute("DELETE FROM nf_aux_itens WHERE codigo=%s", (codigo,))
        cols = ", ".join(_ITEM_CAMPOS_AUX)
        marcas = ", ".join(["%s"] * len(_ITEM_CAMPOS_AUX))
        for it in itens:
            if not soma_iss:
                it = {**it, "base_iss": 0, "valor_iss": 0}
            valores = [it.get(c) for c in _ITEM_CAMPOS_AUX]
            cur.execute(f"INSERT INTO nf_aux_itens (codigo, {cols}) VALUES (%s, {marcas})", (codigo, *valores))
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
        return {"success": False, "message": f"Erro ao gravar itens: {e}"}


def _save_vencimentos_rascunho_sync(servidor: str, banco: str, codigo: int, vencimentos: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da NF-e antes de lançar vencimentos."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM nf_aux_vencimento WHERE codigo=%s", (codigo,))
        for v in vencimentos:
            cur.execute(
                "INSERT INTO nf_aux_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
                (codigo, v["data_venc"], v["valor"]),
            )
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
        return {"success": False, "message": f"Erro ao gravar vencimentos: {e}"}


# ---------------------------------------------------------------------------
# Importação automática (6 sub-rotinas de `NFe\frmtranfe.frm`) — ver
# PENDENCIAS.md > "6 sub-rotinas de importação automática" pro racional
# completo. Todas READ-ONLY: nunca escrevem em `nf_aux`/`nf_aux_itens`,
# só resolvem o documento de origem e devolvem `{header, itens}` prontos
# pro frontend aplicar no rascunho já em edição (mesmo formato de
# `_CAB_CAMPOS_AUX`/`_ITEM_CAMPOS_AUX`, mais `descricao` por item — campo
# só de exibição no frontend, nunca persistido em `nf_aux_itens`, mesmo
# padrão já usado pra item adicionado manualmente). O usuário revisa/
# ajusta e confirma com "Salvar Rascunho"/"Emitir" já existentes — nenhum
# fluxo de persistência novo.
#
# Nem toda importação resolve 100% do cabeçalho — só quando a fonte real
# permite sem inventar regra (ver cada função). Onde a fonte não dá pra
# resolver com confiança (ex.: CFOP de Pedido/Compra, destinatário de
# Requisição), o campo fica em branco pro usuário completar, igual já
# acontece hoje pra um rascunho todo digitado à mão — não é regressão.
# ---------------------------------------------------------------------------

def _importar_pedido_sync(servidor: str, banco: str, pedido: int) -> dict:
    """`ImportaPedido(NumPed)` (`frmtranfe.frm:7987-8125`) — `pedido_venda`+
    `pedido_venda_prod`. Mapeamento de `pedido_venda.tipo` pro `tipo_mov`
    replicado 1:1 da fonte (5→S09 venda c/ reposição, 2→S08 consignada,
    3→S07 saída consignação, demais→S01 venda normal) — sem a gambiarra
    `App.EXEName="JAMER"` (achado anterior, é workaround por binário
    específico de cliente, não regra de negócio geral).

    **CFOP não é resolvido automaticamente** — a fonte ajusta o prefixo
    5/6 conforme a UF do cliente bater ou não com a UF da empresa, mas
    nenhuma tabela de configuração equivalente a `devolucao_config`/
    `requisicao_config_nfe` foi encontrada pra Pedido; usuário completa
    manualmente antes de emitir (mesma exigência que já existe hoje pra
    qualquer rascunho digitado à mão)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cliente, tipo FROM pedido_venda WHERE pedido=%s", (pedido,))
        ped = cur.fetchone()
        if not ped:
            conn.close()
            return {"success": False, "message": "Pedido de Venda não encontrado."}

        mapa_mov = {5: "S09", 2: "S08", 3: "S07"}
        mov = mapa_mov.get(int(ped.get("tipo") or 0), "S01")

        cur.execute("SELECT produto, qtd_pedida, p_venda FROM pedido_venda_prod WHERE pedido=%s", (pedido,))
        linhas = cur.fetchall()
        if not linhas:
            conn.close()
            return {"success": False, "message": "Este Pedido de Venda não tem itens."}

        itens = []
        for r in linhas:
            codigo_int = (r.get("produto") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            qtd = float(r.get("qtd_pedida") or 0)
            p_unit = float(r.get("p_venda") or 0)
            itens.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"],
                "qtd": qtd, "p_unit": p_unit, "valor_total": round(qtd * p_unit, 2),
            })
        conn.close()
        return {"success": True, "header": {"fornecedor": ped.get("cliente"), "tipo_pessoa": "C", "mov": mov}, "itens": itens}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _importar_devolucao_sync(servidor: str, banco: str, ids_devolucao: list[int]) -> dict:
    """`ImportaDevolucao()` (`frmtranfe.frm:8407-8557`) — sempre pra
    CLIENTE (confirmado na fonte: "Valida endereço do cliente"). Cadeia
    de resolução do cliente: `devolucao_itens.CodMov` → `movimentacao.
    id_mov`, `movimentacao.num_nf` → `comanda.comanda`, `comanda.
    cliente` (mesma cadeia já usada em `notas_fiscais_service.py`'s
    cancelamento). CFOP/tipo_mov resolvidos via `devolucao_config` por
    UF do cliente (`Destino`), schema confirmado ao vivo nesta rodada
    (`INFORMATION_SCHEMA.COLUMNS`, 2026-08-20).

    **Achado 2026-08-24, corrigido**: a fonte real (`Command14_Click`,
    `FrmManDev.frm` — "Emitir Nfe de Devolução do(s) item(ns)
    selecionado(s)") monta um ARRAY de `id_devolucao` (`VetDevolucao`,
    podem vir de comandas/vendas diferentes) — nunca um único id digitado
    à mão. A 1ª versão desta função só aceitava 1 id (mal-adaptada do
    fluxo manual de "Importar de..."), que é justamente o que o usuário
    reportou não servir pro caso real. Agora consolida 1+ devoluções numa
    única NF-e — exige que TODAS pertençam ao MESMO cliente (a fonte usa
    um único campo de destinatário pra todo o lote; não há lógica de
    "resolver cliente por item" a replicar — nunca inventar essa regra,
    bloquear com erro claro em vez de adivinhar qual cliente usar)."""
    ids_devolucao = [int(i) for i in (ids_devolucao or []) if i]
    if not ids_devolucao:
        return {"success": False, "message": "Nenhuma devolução informada."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        placeholders = ",".join(["%s"] * len(ids_devolucao))
        cur.execute(
            f"SELECT d.id_devolucao, d.CodMov, d.Qtd_Devolvida, m.codigo_int, m.p_unit, m.num_nf "
            f"FROM devolucao_itens d JOIN movimentacao m ON m.id_mov = d.CodMov "
            f"WHERE d.id_devolucao IN ({placeholders})",
            tuple(ids_devolucao),
        )
        devs = cur.fetchall()
        if not devs:
            conn.close()
            return {"success": False, "message": "Devolução não encontrada."}
        achados = {int(d["id_devolucao"]) for d in devs}
        faltando = [i for i in ids_devolucao if i not in achados]
        if faltando:
            conn.close()
            return {"success": False, "message": f"Devolução(ões) não encontrada(s): {faltando}."}

        # Resolve o cliente de cada devolução (via comanda) e exige que
        # TODAS sejam do mesmo — a NF-e só tem 1 destinatário.
        clientes_por_comanda: dict[int, Optional[int]] = {}
        cliente_id: Optional[int] = None
        for d in devs:
            num_nf = d.get("num_nf")
            if num_nf not in clientes_por_comanda:
                cur.execute("SELECT cliente FROM comanda WHERE comanda=%s", (num_nf,))
                row = cur.fetchone()
                clientes_por_comanda[num_nf] = (row or {}).get("cliente")
            cli = clientes_por_comanda[num_nf]
            if not cli:
                conn.close()
                return {"success": False, "message": f"Não foi possível identificar o cliente da devolução {d['id_devolucao']}."}
            if cliente_id is None:
                cliente_id = cli
            elif cliente_id != cli:
                conn.close()
                return {
                    "success": False,
                    "message": "As devoluções selecionadas pertencem a clientes diferentes — "
                               "uma NF-e de devolução só pode ter um destinatário.",
                }

        dest = nfe_fiscal_common.resolver_destinatario_cliente_sync(cur, cliente_id)
        if not dest.get("success"):
            conn.close()
            return dest
        uf_cliente = (dest["destinatario"].get("uf") or "").strip().upper()

        # **Achado real 2026-08-24, corrigido** (releitura completa de
        # `frmtranfe.frm:8422-8443`): `devolucao_config.Destino` NUNCA
        # guarda o UF literal do cliente — só 2 valores possíveis por
        # instalação: a UF da própria empresa (`controle.UF`, operação
        # "dentro do estado") ou o literal `'XX'` (qualquer outro estado,
        # catch-all interestadual). A versão anterior desta função
        # buscava `Destino=<UF do cliente>` diretamente — funcionava só
        # por coincidência quando o cliente é do mesmo estado da empresa;
        # pra QUALQUER cliente de outro estado, bloqueava a importação com
        # "Sem configuração... para a UF X" mesmo a instalação tendo a
        # configuração certa (linha `Destino='XX'`). Confirmado ao vivo
        # contra ARGEN TESTE: `controle.UF='RJ'`, `devolucao_config` só
        # tem linhas `Destino IN ('RJ','XX')` — nunca 'MG'/'SP'/etc.
        cur.execute("SELECT uf FROM controle")
        uf_empresa = ((cur.fetchone() or {}).get("uf") or "").strip().upper()
        uf_dev = uf_cliente if uf_cliente == uf_empresa else "XX"

        cur.execute("SELECT TOP 1 CFOP, Tipo_Mov FROM devolucao_config WHERE Destino=%s", (uf_dev,))
        cfg = cur.fetchone()
        if not cfg:
            conn.close()
            return {"success": False, "message": f"Sem configuração de Devolução cadastrada para {'a UF ' + uf_dev if uf_dev != 'XX' else 'operação interestadual (XX)'}."}
        tipo_mov = cfg.get("Tipo_Mov")

        # CFOP real por item, achado real ao reler a fonte
        # (`frmtranfe.frm:8514`): o JOIN de verdade casa
        # `devolucao_config.cod_icms = pecas.cod_icms` — o CFOP pode
        # variar por item, não só por UF. Resolvido por item abaixo
        # (`nf_aux_itens.cod_fiscal`, já suportado pelo resto do pipeline
        # desde a correção de `_emitir_nfe_avulsa_sync` no mesmo dia — ver
        # PENDENCIAS.md > "CFOP por item"). Item cujo `cod_icms` não tem
        # config cadastrada é uma lacuna REAL de configuração — bloqueia
        # em vez de importar parcialmente sem avisar (o legado, por usar
        # INNER JOIN, simplesmente omitia esse item da nota sem avisar
        # ninguém; decisão consciente de não replicar esse silêncio).
        itens = []
        sem_config: list[str] = []
        for d in devs:
            codigo_int = (d.get("codigo_int") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            qtd = float(d.get("Qtd_Devolvida") or 0)
            p_unit = float(d.get("p_unit") or 0)
            cur.execute(
                "SELECT CFOP FROM devolucao_config WHERE Destino=%s AND Tipo_Mov=%s AND Cod_Icms=%s",
                (uf_dev, tipo_mov, produto.get("cod_icms") or ""),
            )
            cfg_item = cur.fetchone()
            if not cfg_item:
                sem_config.append(f"{codigo_int} (Cód. ICMS '{produto.get('cod_icms') or ''}')")
                continue
            itens.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"],
                "qtd": qtd, "p_unit": p_unit, "valor_total": round(qtd * p_unit, 2),
                "cod_fiscal": cfg_item.get("CFOP"),
            })
        if sem_config:
            conn.close()
            return {
                "success": False,
                "message": "Sem configuração de Devolução (CFOP por Cód. ICMS) para: " + "; ".join(sem_config) +
                            ". Cadastre a combinação em Devolução (Configuração) antes de importar.",
            }
        conn.close()
        return {
            "success": True,
            "header": {
                "fornecedor": cliente_id, "tipo_pessoa": "C", "mov": cfg.get("Tipo_Mov"), "cfop": cfg.get("CFOP"),
                "ids_devolucao_origem": ",".join(str(i) for i in ids_devolucao),
            },
            "itens": itens,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _importar_compra_sync(servidor: str, banco: str, pedido_compra: int) -> dict:
    """`ImportaCompraPedido()` (`frmtranfe.frm:8559-8595`) — só roda com
    `OD=True` (fornecedor), sem tela de seleção no legado (`InputBox`
    direto). Desconto aplicado uniformemente a partir do cadastro do
    fornecedor (`fornecedor.desconto`), réplica direta. **CFOP/tipo_mov
    não resolvidos automaticamente** — nenhuma tabela de configuração
    equivalente encontrada pra Compra; usuário completa manualmente."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT fornecedor FROM pedido WHERE codigo=%s", (pedido_compra,))
        ped = cur.fetchone()
        if not ped or not ped.get("fornecedor"):
            conn.close()
            return {"success": False, "message": "Pedido de Compra não encontrado."}

        cur.execute("SELECT desconto FROM fornecedor WHERE codigo_int=%s", (ped["fornecedor"],))
        forn = cur.fetchone() or {}
        desconto_perc = float(forn.get("desconto") or 0)

        cur.execute("SELECT codigo_int, qtd, p_unit FROM pedido_itens WHERE codigo=%s", (pedido_compra,))
        linhas = cur.fetchall()
        if not linhas:
            conn.close()
            return {"success": False, "message": "Este Pedido de Compra não tem itens."}

        itens = []
        for r in linhas:
            codigo_int = (r.get("codigo_int") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            qtd = float(r.get("qtd") or 0)
            p_unit = float(r.get("p_unit") or 0)
            valor_total = round(qtd * p_unit, 2)
            desconto = round(valor_total * desconto_perc / 100, 2) if desconto_perc else 0
            itens.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"],
                "qtd": qtd, "p_unit": p_unit, "desconto_perc": desconto_perc,
                "desconto": desconto, "valor_total": valor_total - desconto,
            })
        conn.close()
        return {"success": True, "header": {"fornecedor": ped["fornecedor"], "tipo_pessoa": "F"}, "itens": itens}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _importar_requisicao_sync(servidor: str, banco: str, requisicao: int) -> dict:
    """`ImportaRequisicao()` (`frmtranfe.frm:8597-8692`) — `rec_prod`, sem
    desconto (réplica — a tabela não tem coluna de desconto). **Cabeçalho
    (destinatário/tipo_mov/CFOP) não é resolvido automaticamente** — a
    tabela `requisicao` (schema real confirmado ao vivo nesta rodada) não
    tem FK de cliente/fornecedor própria, então a resolução por UF via
    `requisicao_config_nfe` (também confirmada) não pode ser feita sem um
    destinatário já escolhido — usuário completa cabeçalho manualmente,
    só os itens vêm importados."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo FROM requisicao WHERE codigo=%s", (requisicao,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Requisição não encontrada."}

        cur.execute("SELECT prod, qtd, p_unit FROM rec_prod WHERE requisicao=%s", (requisicao,))
        linhas = cur.fetchall()
        if not linhas:
            conn.close()
            return {"success": False, "message": "Esta Requisição não tem itens."}

        itens = []
        for r in linhas:
            codigo_int = (r.get("prod") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            qtd = float(r.get("qtd") or 0)
            p_unit = float(r.get("p_unit") or 0)
            itens.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"],
                "qtd": qtd, "p_unit": p_unit, "valor_total": round(qtd * p_unit, 2),
            })
        conn.close()
        return {"success": True, "header": {}, "itens": itens}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _importar_nota_fiscal_sync(servidor: str, banco: str, codigo_nf: int) -> dict:
    """`ImportaNF(CodigoNota)` (`frmtranfe.frm:8767-8808`) — só roda com
    `OD=True`. A mais "cópia direta" das 6: copia os campos fiscais de
    `n_fiscal_itens` que TAMBÉM existem em `nf_aux_itens` (qtd/p_unit/
    desconto/bases-valores ICMS/IPI/ICMS-ST — não PIS/COFINS/IBS-CBS, que
    `nf_aux_itens` não tem, mesmo limite de schema já documentado no
    módulo), sem recalcular CFOP/tributação — assume que a origem já
    está correta, mesmo comportamento da fonte."""
    campos_copiaveis = [
        "codigo_int", "cod_fiscal", "tributacao", "qtd", "p_unit", "desconto", "valor_total",
        "alqt_icms", "reducao_base_icms", "base_icms", "valor_icms",
        "base_ipi", "alqt_ipi", "valor_ipi", "base_sub", "valor_sub", "base_iss", "valor_iss",
        "frete", "seguro", "despesas",
    ]
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT fornecedor, mov, cfop, uf FROM n_fiscal WHERE codigo=%s", (codigo_nf,))
        nf = cur.fetchone()
        if not nf:
            conn.close()
            return {"success": False, "message": "Nota Fiscal de origem não encontrada."}

        cur.execute("SELECT origem_destino FROM tipo_mov WHERE codigo=%s", (nf.get("mov"),))
        tm = cur.fetchone() or {}
        tipo_pessoa = "F" if (tm.get("origem_destino") or "").strip().upper() == "F" else "C"

        cur.execute(
            f"SELECT {', '.join(campos_copiaveis)} FROM n_fiscal_itens WHERE codigo=%s",
            (codigo_nf,),
        )
        linhas = cur.fetchall()
        if not linhas:
            conn.close()
            return {"success": False, "message": "Esta Nota Fiscal de origem não tem itens."}

        itens = []
        for r in linhas:
            produto = _resolver_item_produto_sync(cur, (r.get("codigo_int") or "").strip())
            item = dict(r)
            item["descricao"] = produto["descricao"]
            itens.append(item)
        conn.close()
        return {
            "success": True,
            "header": {
                "fornecedor": nf.get("fornecedor"), "tipo_pessoa": tipo_pessoa,
                "mov": nf.get("mov"), "cfop": nf.get("cfop"),
            },
            "itens": itens,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _importar_complementar_sync(servidor: str, banco: str, comanda: int) -> dict:
    """`ImportaComplementar(Codigo)` (`frmtranfe.frm:8918-9008`) — parte de
    uma Comanda, não de outro documento fiscal, pra cobrar a diferença de
    FCP não destacada na NFC-e original. `tipo_mov` fixo `S50`, CFOP fixo
    `5102` (réplica da fonte). Filtra itens de `comanda_nfce_detalhe` por
    `pecas.cod_icms='6'` — **JOIN via `produto`, não uma coluna própria**
    (achado desta rodada: `comanda_nfce_detalhe` não tem `COD_ICMS` local,
    confirmado no schema real). Item gravado com quantidade e preço
    zerados; o valor de FCP vira campo de CABEÇALHO (`BASE_FCP`/
    `VALOR_FCP`, alíquota **2% hardcoded confirmada na fonte**
    — `frmtranfe.frm:8999`, `precoFCP * 2 / 100` — literal, não config).

    **Não replica o endereço hardcoded do VB6** ("Rua Vitor Meireles 221,
    Riachuelo/RJ") — é dado de uma instalação específica, não regra de
    negócio (ver "Não replicar truques VB6" em CLAUDE.md). O destinatário
    é resolvido normalmente a partir do `cliente` real da comanda."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cliente FROM comanda WHERE comanda=%s", (comanda,))
        cab = cur.fetchone()
        if not cab or not cab.get("cliente"):
            conn.close()
            return {"success": False, "message": "Comanda não encontrada ou sem cliente vinculado."}

        cur.execute(
            "SELECT d.produto, d.qtd, d.p_unit FROM comanda_nfce_detalhe d "
            "JOIN pecas p ON p.codigo_int = d.produto "
            "WHERE d.comanda=%s AND p.cod_icms='6'",
            (comanda,),
        )
        linhas = cur.fetchall()
        if not linhas:
            conn.close()
            return {"success": False, "message": "Nenhum item com ICMS código 6 encontrado nesta comanda."}

        base_fcp = round(sum(float(r.get("qtd") or 0) * float(r.get("p_unit") or 0) for r in linhas), 2)
        valor_fcp = round(base_fcp * 0.02, 2)

        itens = []
        for r in linhas:
            codigo_int = (r.get("produto") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            itens.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"],
                "qtd": 0, "p_unit": 0, "valor_total": 0,
            })
        conn.close()
        return {
            "success": True,
            "header": {
                "fornecedor": cab["cliente"], "tipo_pessoa": "C", "mov": "S50", "cfop": "5102",
                "BASE_FCP": base_fcp, "VALOR_FCP": valor_fcp,
            },
            "itens": itens,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Sugestão de tributação (ICMS/IPI/ISS) — nunca grava sozinha, só sugere;
# PIS/COFINS nunca aparece aqui (decisão 2, calculado só na emissão).
# ---------------------------------------------------------------------------

def _sugerir_tributacao_sync(
    servidor: str, banco: str, *, codigo_int: str, mov: str, uf_destino: str,
    nao_contribuinte: bool, simples_nacional_cliente: bool, consumidor_final: bool,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod_icms FROM pecas WHERE codigo_int=%s", (codigo_int,))
        p = cur.fetchone()
        if not p:
            conn.close()
            return {"success": False, "message": "Produto não encontrado — sugestão de tributação é só para Peças."}
        cod_icms = (p.get("cod_icms") or "").strip()

        cur.execute("SELECT uf FROM controle")
        controle = cur.fetchone() or {}
        uf_controle = (controle.get("uf") or "").strip().upper()

        cur.execute("SELECT TOP 1 1 AS ok FROM PECAS_PROTOCOLO_ST WHERE uf=%s AND codigo_int=%s", (uf_destino, codigo_int))
        protocolo_st = cur.fetchone() is not None

        tributos = nfe_emissao_service._resolver_tributacao_sync(
            cur, cod_icms=cod_icms, cfop_cupom_fiscal="", tipo_mov=mov,
            uf_destino=uf_destino, uf_controle=uf_controle, nao_contribuinte=nao_contribuinte,
            simples_nacional_cliente=simples_nacional_cliente, consumidor_final=consumidor_final,
            protocolo_st=protocolo_st,
        )
        conn.close()
        if not tributos:
            return {"success": False, "message": "Sem tributação cadastrada em Taxas (Tabelas Auxiliares) para este produto/UF."}
        return {
            "success": True,
            "sugestao": {
                "tributacao": tributos.get("tributacao"),
                "alqt_icms": tributos.get("aliquota_icms") or tributos.get("alqt_icms") or 0,
                "base_iss": 0, "valor_iss": 0,
                "cfop_livro": tributos.get("cfop_livro"),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Emissão — promove nf_aux/nf_aux_itens/nf_aux_vencimento pra n_fiscal/
# n_fiscal_itens/nf_vencimento, calcula PIS/COFINS e IBS/CBS só agora.
# ---------------------------------------------------------------------------

def _resolver_item_produto_sync(cur, codigo_int: str) -> dict:
    """Descrição/NCM/unidade/cod_icms não existem em `nf_aux_itens` — resolve
    via `pecas` (produto) ou `servicos` (serviço), mesmo padrão de cascata já
    usado em `_buscar_produto_sync`/`notas_fiscais_service.py`.

    `tributacao_pis`/`perc_valor_pis`/`tributacao_cofins`/`perc_valor_cofins`
    — achado 2026-08-22 (ver `_calcular_pis_cofins_item`): cadastro de PIS/
    COFINS por produto/serviço, fallback real usado pelo legado quando
    `taxas.CST_TRIB_PIS` está vazio. Ficam ausentes do dict (não `0`) quando
    nem `pecas` nem `servicos` casam — `_calcular_pis_cofins_item` trata
    ausência como "não encontrado" (CST 06), mesmo efeito do legado."""
    cur.execute(
        "SELECT descricao, codigo_mercosul AS ncm, uni AS unidade, cod_icms, origem, "
        "tributacao_pis, perc_valor_pis, tributacao_cofins, perc_valor_cofins "
        "FROM pecas WHERE codigo_int=%s",
        (codigo_int,),
    )
    row = cur.fetchone()
    if row:
        return {
            "descricao": (row.get("descricao") or "").strip(), "ncm": (row.get("ncm") or "").strip(),
            "unidade": (row.get("unidade") or "UN").strip(), "cod_icms": (row.get("cod_icms") or "").strip(),
            "origem": int(row.get("origem") or 0),
            "tributacao_pis": row.get("tributacao_pis"), "perc_valor_pis": row.get("perc_valor_pis"),
            "tributacao_cofins": row.get("tributacao_cofins"), "perc_valor_cofins": row.get("perc_valor_cofins"),
        }
    cur.execute(
        "SELECT descricao, tributacao_pis, perc_valor_pis, tributacao_cofins, perc_valor_cofins "
        "FROM servicos WHERE codigo=%s",
        (codigo_int,),
    )
    row = cur.fetchone()
    if row:
        return {
            "descricao": (row.get("descricao") or "").strip(), "ncm": "", "unidade": "UN", "cod_icms": "", "origem": 0,
            "tributacao_pis": row.get("tributacao_pis"), "perc_valor_pis": row.get("perc_valor_pis"),
            "tributacao_cofins": row.get("tributacao_cofins"), "perc_valor_cofins": row.get("perc_valor_cofins"),
        }
    return {"descricao": codigo_int, "ncm": "", "unidade": "UN", "cod_icms": "", "origem": 0}


def _calcular_pis_cofins_item(taxa: dict, produto: dict, base: float) -> dict:
    """Réplica de `SetaPisCofins`+`LancaPisCofins` (`NFe\\frmtranfe.frm:
    8811`/`8311`, chamadas por `Calcula()`, a rotina que roda no
    fechamento/emissão — não `JogaV()`, que só sugere valor na tela
    durante a digitação, fora de escopo aqui, mesmo já documentado:
    "PIS/COFINS NUNCA é digitável — calculado só no momento de Emitir").

    **Achado real 2026-08-22** (reauditoria > "Simplificações", item 4):
    a versão anterior desta função só implementava o Caminho A abaixo,
    e tratava `taxas.CST_TRIB_PIS`/`CST_TRIB_COFINS` vazio como "CST 07
    (Isenta), R$0,00" — errado. O legado, quando esses 2 campos vêm
    vazios (`Trim(TaxaCstPis)<>"" And Trim(TaxaCstCofins)<>""` falha),
    NUNCA usa um default fixo — cai inteiro pro Caminho B, um cadastro
    PRÓPRIO de PIS/COFINS por produto/serviço (`pecas`/`servicos`.
    `tributacao_pis`/`perc_valor_pis`/`tributacao_cofins`/
    `perc_valor_cofins`), com `taxas.reducao_base_pis_cofins` reduzindo a
    base ANTES do cálculo só nesse caminho. **Confirmado que este é o
    caminho REAL, não teórico**: em ARGEN TESTE, 82/82 linhas de `taxas`
    têm `CST_TRIB_PIS` vazio (Caminho A nunca resolve nessa instalação) e
    2670/2681 produtos têm `tributacao_pis`/`perc_valor_pis` reais
    (`99`/`0.30%` — Caminho B é o único caminho que produz valor
    correto). Sem este fix, TODO item de TODA NF-e Avulsa emitida nesta
    instalação sairia com PIS/COFINS zerados e CST errado.

    **Divergência deliberada da fonte, não um replicar 1:1** (ver
    CLAUDE.md > "Não replicar truques VB6"): o VB6 usa uma única
    variável `basepiscofins` compartilhada entre o cálculo de PIS e o de
    COFINS — zerar a base do PIS (quando `TaxaAqltPis`/`perc_valor_pis`
    é 0) também zera silenciosamente a base do COFINS mesmo que a
    alíquota de COFINS seja diferente de zero (efeito colateral de reuso
    de variável, sem nenhuma razão tributária — nenhuma legislação liga
    "PIS a 0%" a "COFINS também vira 0%"). Replicado aqui como dois
    cálculos INDEPENDENTES (cada imposto só zera a própria base quando a
    própria alíquota é 0) — mesmo julgamento já usado pra outros
    "truques" de variável reaproveitada do legado."""
    cst_pis_taxa = str(taxa.get("CST_TRIB_PIS") or taxa.get("cst_trib_pis") or "").strip()
    cst_cofins_taxa = str(taxa.get("CST_TRIB_COFINS") or taxa.get("cst_trib_cofins") or "").strip()

    if cst_pis_taxa and cst_cofins_taxa:
        # Caminho A — `taxas.CST_TRIB_PIS`/`ALQT_TRIB_PIS` (DAO_NFE em
        # torno de `Trim(TaxaCstPis)<>"" And Trim(TaxaCstCofins)<>""`).
        cst_pis = cst_pis_taxa.zfill(2)
        alqt_pis = float(taxa.get("ALQT_TRIB_PIS") or taxa.get("alqt_trib_pis") or 0)
        base_pis = base if alqt_pis else 0.0
        cst_cofins = cst_cofins_taxa.zfill(2)
        alqt_cofins = float(taxa.get("ALQT_TRIB_COFINS") or taxa.get("alqt_trib_cofins") or 0)
        base_cofins = base if alqt_cofins else 0.0
    else:
        # Caminho B — cadastro do produto/serviço, com redução de base.
        reducao = float(taxa.get("REDUCAO_BASE_PIS_COFINS") or taxa.get("reducao_base_pis_cofins") or 0)
        base_reduzida = round(base - (base * reducao / 100), 2) if reducao > 0 else base

        trib_pis = int(produto.get("tributacao_pis") or 0)
        if trib_pis:
            cst_pis = str(trib_pis).zfill(2)
            alqt_pis = float(produto.get("perc_valor_pis") or 0)
            base_pis = base_reduzida if alqt_pis else 0.0
        else:
            cst_pis, alqt_pis, base_pis = "06", 0.0, 0.0

        trib_cofins = int(produto.get("tributacao_cofins") or 0)
        if trib_cofins:
            cst_cofins = str(trib_cofins).zfill(2)
            alqt_cofins = float(produto.get("perc_valor_cofins") or 0)
            base_cofins = base_reduzida if alqt_cofins else 0.0
        else:
            cst_cofins, alqt_cofins, base_cofins = "06", 0.0, 0.0

    valor_pis = round(base_pis * alqt_pis / 100, 2)
    valor_cofins = round(base_cofins * alqt_cofins / 100, 2)
    return {
        "cst_pis": cst_pis, "base_pis": base_pis, "alqt_pis": alqt_pis, "valor_pis": valor_pis,
        "cst_cofins": cst_cofins, "base_cofins": base_cofins, "alqt_cofins": alqt_cofins, "valor_cofins": valor_cofins,
    }


def _emitir_nfe_avulsa_sync(
    servidor: str, banco: str, *, codigo: int, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    if not codigo:
        return {"success": False, "message": "Rascunho inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para emitir NF-e avulsa."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}

        cols = ", ".join(["codigo", "num_nf"] + _CAB_CAMPOS_AUX)
        cur.execute(f"SELECT {cols} FROM nf_aux WHERE codigo=%s", (codigo,))
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        if cab.get("num_nf"):
            conn.close()
            return {"success": False, "message": "Esta NF-e já foi emitida — reemissão não é suportada nesta fase."}

        pessoa_id = cab.get("fornecedor")
        mov = (cab.get("mov") or "").strip()
        cfop_cabecalho = (cab.get("cfop") or "").strip()
        if not pessoa_id or not mov or not cfop_cabecalho or not cab.get("data"):
            conn.close()
            return {"success": False, "message": "Preencha Cliente/Fornecedor, Tipo de Movimentação, CFOP e Data de Emissão antes de emitir."}

        cur.execute("SELECT codigo, origem_destino, atualiza_est FROM tipo_mov WHERE codigo=%s", (mov,))
        tm = cur.fetchone()
        if not tm:
            conn.close()
            return {"success": False, "message": "Tipo de Movimentação não cadastrado."}
        is_fornecedor = (tm.get("origem_destino") or "").strip().upper() == "F"
        # Baixa/reposição de estoque — achado real 2026-08-24 (Leandro,
        # confirmando ao vivo): "O Gerar NFE Avulsa emite notas de
        # qualquer natureza... A baixa de estoque acontece após a emissão
        # da nota, dependendo do flag da tabela tipo_mov.atualiza_est".
        # Rastreado até `frmtranfe.frm::Atualiz`/`CmdOk_Click` (linhas
        # 4849-4854/7955-7969): quando `atualiza_est='S'`, cada item da
        # NF soma OU subtrai de `pecas.qtd` conforme `Left(Tipo_Mov,1)`
        # ("S" Saída subtrai, qualquer outro — tipicamente "E" Entrada —
        # soma). NUNCA implementado antes nesta migração (achado ao
        # investigar por que uma NF-e de Devolução não repunha estoque —
        # não é um mecanismo específico de devolução, é geral pra
        # qualquer natureza de NF-e Avulsa).
        atualiza_est = (tm.get("atualiza_est") or "").strip().upper() == "S"
        soma_estoque = (mov[:1].strip().upper() != "S") if mov else True

        if is_fornecedor:
            dest_resultado = nfe_fiscal_common.resolver_destinatario_fornecedor_sync(cur, pessoa_id)
        else:
            dest_resultado = nfe_fiscal_common.resolver_destinatario_cliente_sync(cur, pessoa_id)
        if not dest_resultado.get("success"):
            conn.close()
            return dest_resultado
        destinatario = dest_resultado["destinatario"]
        consumidor_final = dest_resultado["consumidor_final"]
        simples_nacional_cliente = dest_resultado["simples_nacional_cliente"]

        cur.execute(
            f"SELECT id_nf_aux, {', '.join(_ITEM_CAMPOS_AUX)} FROM nf_aux_itens WHERE codigo=%s ORDER BY id_nf_aux",
            (codigo,),
        )
        itens_aux = cur.fetchall()
        if not itens_aux:
            conn.close()
            return {"success": False, "message": "Nenhum item lançado — nada a emitir."}

        cur.execute("SELECT cgc, uf, rz_social, numero_nf, serie_nf FROM controle")
        controle = cur.fetchone() or {}
        uf_sigla = (controle.get("uf") or "").strip().upper()

        cur.execute("SELECT descricao FROM tipo_mov WHERE codigo=%s", (mov,))
        tm_desc = cur.fetchone()
        natureza_operacao = (tm_desc.get("descricao") or "Nota Fiscal").strip() if tm_desc else "Nota Fiscal"

        itens_resolvidos = []
        pis_cofins_por_item = []
        ibs_cbs_por_item = []
        valor_total = 0.0
        for item in itens_aux:
            codigo_int = (item.get("codigo_int") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            qtd = float(item.get("qtd") or 0)
            valor_unitario = float(item.get("p_unit") or 0)
            valor_item = round(item.get("valor_total") or (qtd * valor_unitario), 2)
            valor_total += valor_item

            cur.execute("SELECT TOP 1 1 AS ok FROM PECAS_PROTOCOLO_ST WHERE uf=%s AND codigo_int=%s", (uf_sigla, codigo_int))
            protocolo_st = cur.fetchone() is not None
            tributos = nfe_emissao_service._resolver_tributacao_sync(
                cur, cod_icms=produto["cod_icms"], cfop_cupom_fiscal="", tipo_mov=mov,
                uf_destino=destinatario.get("uf") or uf_sigla, uf_controle=uf_sigla,
                nao_contribuinte=not destinatario.get("ie"),
                simples_nacional_cliente=simples_nacional_cliente, consumidor_final=consumidor_final,
                protocolo_st=protocolo_st,
            )
            if not tributos:
                conn.close()
                return {"success": False, "message": f"Produto '{codigo_int}' sem tributação cadastrada em Taxas (Tabelas Auxiliares)."}

            pis_cofins = _calcular_pis_cofins_item(tributos, produto, valor_item)
            pis_cofins_por_item.append(pis_cofins)

            # IBS/CBS calculado JUNTO com o resto da tributação — é só mais
            # um grupo de tags do XML, como ICMS/PIS/COFINS, embutido no
            # MESMO XML que sai assinado/transmitido (mesmo princípio já
            # aplicado em `nfe_agrupada_service.py` 2026-08-20 — nunca mais
            # um enriquecimento pós-emissão). As colunas estruturadas de
            # `n_fiscal_itens` continuam gravadas depois do INSERT (útil
            # pra consulta/relatório sem parsear XML), mas com o MESMO
            # valor já calculado aqui — nunca recalculado de novo.
            taxa_nfce = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(
                cur, cod_icms=produto["cod_icms"], destino=destinatario.get("uf") or uf_sigla,
            )
            ibs_cbs_item = (
                ibs_cbs_service.calcular_item_ibs_cbs(qtd=qtd, p_unit=valor_unitario, codigo_int=codigo_int, taxa=taxa_nfce)
                if taxa_nfce else None
            )
            ibs_cbs_por_item.append(ibs_cbs_item)

            # CFOP por item, achado real 2026-08-24 (ver PENDENCIAS.md >
            # "CFOP por item"): `nf_aux_itens.cod_fiscal` já é persistido
            # por item (rascunho/emissão sempre gravaram essa coluna),
            # mas até aqui o XML transmitido usava SEMPRE `cfop_cabecalho`
            # pra todo item, ignorando esse valor — divergência real entre
            # o que ficava salvo em `n_fiscal_itens.cod_fiscal` (correto,
            # por item) e o que ia pro XML/SEFAZ (sempre o cabeçalho).
            # Corrigido: item com CFOP próprio usa o seu; vazio cai pro
            # cabeçalho, comportamento de antes preservado.
            cfop_item = (item.get("cod_fiscal") or "").strip() or cfop_cabecalho
            itens_resolvidos.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"], "ncm": produto["ncm"],
                "cfop": cfop_item, "unidade": produto["unidade"], "qtd": qtd, "valor_unitario": valor_unitario,
                "valor_total": valor_item, "origem": produto["origem"],
                "csosn": "102" if simples_nacional_cliente else "400",
                "cst_pis": pis_cofins["cst_pis"], "cst_cofins": pis_cofins["cst_cofins"],
                "ibs_cbs_xml": (ibs_cbs_item or {}).get("xml_item") or "",
                # Colunas DIFAL de `taxas`, já resolvidas em `tributos` —
                # ver nfe_regras_fiscais.py (achado 2026-08-28: grupo
                # ICMSUFDest nunca era montado por faltar esse threading).
                "aliquota_interestadual": tributos.get("aliquota_interestadual") or 0,
                "aliquota_interna_destino": tributos.get("aliquota_interna_destino") or 0,
                "percentual_origem": tributos.get("percentual_origem") or 0,
                "fundo_pobreza": tributos.get("fundo_pobreza") or 0,
                # campos já confirmados/editados pelo usuário no rascunho (ICMS/IPI/ISS) —
                # não recalculados aqui (decisão 1), só repassados pra gravação em n_fiscal_itens.
                "_alqt_icms": item.get("alqt_icms"), "_reducao_base_icms": item.get("reducao_base_icms"),
                "_base_icms": item.get("base_icms"), "_valor_icms": item.get("valor_icms"),
                "_base_ipi": item.get("base_ipi"), "_alqt_ipi": item.get("alqt_ipi"), "_valor_ipi": item.get("valor_ipi"),
                "_base_sub": item.get("base_sub"), "_valor_sub": item.get("valor_sub"),
                "_base_iss": item.get("base_iss"), "_valor_iss": item.get("valor_iss"),
                "_frete": item.get("frete"), "_seguro": item.get("seguro"), "_despesas": item.get("despesas"),
                "_desconto": item.get("desconto"), "_tributacao": item.get("tributacao"),
                "_cod_fiscal": item.get("cod_fiscal"), "_obs_item_nf": item.get("obs_item_nf"),
            })

        ibs_cbs_totais_xml = ibs_cbs_service.calcular_totais_ibs_cbs(ibs_cbs_por_item)["xml_totais"]

        proximo_numero = int(controle.get("numero_nf") or 0) + 1
        serie = str(controle.get("serie_nf") or "1")

        # Transportador/Veículo/Volumes — achado 2026-08-22 (varredura de
        # simplificações pendentes): `nf_aux` já captura esses campos
        # desde a Fase 1 (2026-08-20), mas nunca chegavam ao XML nem ao
        # DANFE. `cnpj_transportadora` é só o documento (nf_aux não tem
        # nome/IE do transportador) — busca best-effort em `fornecedor`
        # pelo `codigo` (CNPJ/CPF, mesma convenção já usada nesta tabela)
        # pra completar nome/IE quando o transportador também é um
        # fornecedor cadastrado; sem cadastro correspondente, o XML ainda
        # sai válido só com o documento (todos os campos de `transporta`
        # são opcionais no XSD).
        transportador = None
        cnpj_transportadora = (cab.get("cnpj_transportadora") or "").strip()
        if cnpj_transportadora:
            cur.execute("SELECT nome, inscr_est FROM fornecedor WHERE codigo=%s", (cnpj_transportadora,))
            forn = cur.fetchone() or {}
            transportador = {"cgc_cpf": cnpj_transportadora, "nome": forn.get("nome"), "ie": forn.get("inscr_est")}
        veiculo = {"placa": cab.get("placa")} if (cab.get("placa") or "").strip() else None
        volumes = None
        if any(cab.get(k) for k in ("volumes", "especie_volume", "peso_bruto", "peso_liquido")):
            volumes = {
                "qtd": cab.get("volumes"), "especie": cab.get("especie_volume"),
                "peso_bruto": cab.get("peso_bruto"), "peso_liquido": cab.get("peso_liquido"),
            }

        # Contingência — mesma conexão feita em `nfe_agrupada_service.py`
        # no mesmo dia. Ver docstring de `nfe_emissao_service.emitir_nfe_
        # sync` e `contingencia_nfe_service.listar_pendentes`/`validar_
        # pendentes` (transmissão real, mais tarde).
        contingencia = contingencia_nfe_service.contingencia_aberta_sync(cur)
        resultado = nfe_emissao_service.emitir_nfe_sync(
            cur, cnpj_emit=(controle.get("cgc") or ""), nome_emit=(controle.get("rz_social") or ""),
            uf_sigla=uf_sigla, proximo_numero=proximo_numero, serie=serie, destinatario=destinatario,
            itens_resolvidos=itens_resolvidos, valor_total=round(valor_total, 2),
            tp_amb=nfe_fiscal_common.resolver_tp_amb_sync(cur),
            natureza_operacao=natureza_operacao, indFinal="1" if consumidor_final else "0",
            ibs_cbs_totais_xml=ibs_cbs_totais_xml, contingencia=contingencia, paga_frete=cab.get("paga_frete"),
            transportador=transportador, veiculo=veiculo, volumes=volumes,
            servidor=servidor, banco=banco,
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        situacao_n_fiscal = resultado.get("situacao") or "A"
        cstat_n_fiscal = resultado.get("cstat") or "100"
        # `dh_recbto` cru do SEFAZ (ISO 8601 com offset) quebra numa
        # coluna DATETIME e derruba a transação DEPOIS do sucesso já
        # confirmado — mesmo bug achado ao vivo no MDF-e 2026-08-23,
        # corrigido aqui 2026-08-24 (ver `nfe_fiscal_common.parse_dh_sefaz`).
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, fornecedor, mov, cfop, uf, data_nf, data_mov, data_saida, "
            "valor_total, frete, seguro, despesas, desconto, nf_aux, situacao, chave_acesso, protocolo_sefaz, "
            "dhRecbto, cstat, xml, XML_TOT_IBS_CBS, paga_frete, "
            "cnpj_transportadora, placa, motorista, volumes, especie_volume, peso_bruto, peso_liquido) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                resultado["numero"], resultado["serie"], pessoa_id, mov, cfop_cabecalho, uf_sigla,
                cab.get("data"), cab.get("data_mov"), cab.get("data_saida"),
                round(valor_total, 2), cab.get("frete"), cab.get("seguro"), cab.get("despesas"),
                cab.get("desconto"), codigo, situacao_n_fiscal,
                resultado["chave_acesso"], resultado["protocolo_sefaz"], nfe_fiscal_common.parse_dh_sefaz(resultado.get("dh_recbto")),
                cstat_n_fiscal, resultado["xml"], ibs_cbs_totais_xml, cab.get("paga_frete"),
                cab.get("cnpj_transportadora"), cab.get("placa"), cab.get("motorista"),
                cab.get("volumes"), cab.get("especie_volume"), cab.get("peso_bruto"), cab.get("peso_liquido"),
            ),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])

        for item, pis_cofins, ibs_cbs_item in zip(itens_resolvidos, pis_cofins_por_item, ibs_cbs_por_item):
            cur.execute(
                "INSERT INTO n_fiscal_itens (codigo, codigo_int, cod_fiscal, tributacao, qtd, p_unit, "
                "alqt_icms, reducao_base_icms, base_icms, valor_icms, base_ipi, alqt_ipi, valor_ipi, "
                "base_sub, valor_sub, base_iss, valor_iss, frete, seguro, despesas, desconto, valor_total, "
                "tributacao_pis, base_pis, alqt_pis, valor_pis, tributacao_cofins, base_cofins, alqt_cofins, valor_cofins, "
                "obs_item_nf, aliquota_interestadual, aliquota_interna_destino, percentual_origem, fundo_pobreza) "
                "OUTPUT INSERTED.id "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo_n_fiscal, item["codigo_int"], item["_cod_fiscal"], item["_tributacao"],
                    item["qtd"], item["valor_unitario"],
                    item["_alqt_icms"], item["_reducao_base_icms"], item["_base_icms"], item["_valor_icms"],
                    item["_base_ipi"], item["_alqt_ipi"], item["_valor_ipi"],
                    item["_base_sub"], item["_valor_sub"], item["_base_iss"], item["_valor_iss"],
                    item["_frete"], item["_seguro"], item["_despesas"], item["_desconto"], item["valor_total"],
                    pis_cofins["cst_pis"], pis_cofins["base_pis"], pis_cofins["alqt_pis"], pis_cofins["valor_pis"],
                    pis_cofins["cst_cofins"], pis_cofins["base_cofins"], pis_cofins["alqt_cofins"], pis_cofins["valor_cofins"],
                    item["_obs_item_nf"],
                    # DIFAL (2026-08-28) — mesmas 4 colunas já lidas por
                    # apuracao_fiscal_service.py::_calc_difal (Apuração
                    # Fiscal, modo DIFAL) — persistidas aqui pela 1ª vez
                    # pra essa view não mostrar zerado numa nota emitida
                    # por este service.
                    item.get("aliquota_interestadual") or 0, item.get("aliquota_interna_destino") or 0,
                    item.get("percentual_origem") or 0, item.get("fundo_pobreza") or 0,
                ),
            )
            id_item = int(cur.fetchone()["id"])
            if ibs_cbs_item:
                cur.execute(
                    "UPDATE n_fiscal_itens SET CST_IBS_UF=%s, CLASSTRIB_IBS_UF=%s, BASE_IBS_UF=%s, ALQT_IBS_UF=%s, "
                    "VALOR_IBS_UF=%s, CST_IBS_MUNICIPIO=%s, CLASSTRIB_IBS_MUNICIPIO=%s, BASE_IBS_MUNICIPIO=%s, "
                    "ALQT_IBS_MUNICIPIO=%s, VALOR_IBS_MUNICIPIO=%s, CST_CBS=%s, CLASSTRIB_CBS=%s, BASE_CBS=%s, "
                    "ALQT_CBS=%s, VALOR_CBS=%s WHERE id=%s",
                    (
                        ibs_cbs_item["cst_ibs_uf"], ibs_cbs_item["classtrib_ibs_uf"], ibs_cbs_item["base_ibs_uf"],
                        ibs_cbs_item["alqt_ibs_uf"], ibs_cbs_item["valor_ibs_uf"],
                        ibs_cbs_item["cst_ibs_municipio"], ibs_cbs_item["classtrib_ibs_municipio"],
                        ibs_cbs_item["base_ibs_municipio"], ibs_cbs_item["alqt_ibs_municipio"], ibs_cbs_item["valor_ibs_municipio"],
                        ibs_cbs_item["cst_cbs"], ibs_cbs_item["classtrib_cbs"], ibs_cbs_item["base_cbs"],
                        ibs_cbs_item["alqt_cbs"], ibs_cbs_item["valor_cbs"], id_item,
                    ),
                )

        cur.execute(
            "SELECT SEQUENCIA_NF_AUX_VENCIMENTO, data_venc, valor FROM nf_aux_vencimento WHERE codigo=%s",
            (codigo,),
        )
        for v in cur.fetchall():
            cur.execute(
                "INSERT INTO nf_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
                (codigo_n_fiscal, v["data_venc"], v["valor"]),
            )

        if atualiza_est:
            for item in itens_resolvidos:
                cod_int = (item.get("codigo_int") or "").strip()
                qtd_item = float(item.get("qtd") or 0)
                if not cod_int or not qtd_item:
                    continue
                if soma_estoque:
                    cur.execute("UPDATE pecas SET qtd = qtd + %s WHERE codigo_int=%s", (qtd_item, cod_int))
                else:
                    cur.execute("UPDATE pecas SET qtd = qtd - %s WHERE codigo_int=%s", (qtd_item, cod_int))

        # Fecha o ciclo de uma NF-e importada de Devolução (`ids_devolucao_
        # origem`, ver `_ensure_nf_aux_ids_devolucao_origem_col`) — mesmo
        # UPDATE que a fonte faz logo após confirmar `Codigo_NF`
        # (`frmtranfe.frm:4453`), vinculando cada `devolucao_itens` ao
        # `n_fiscal.codigo` real gerado (não o número da nota, o código
        # interno — mesma convenção já usada em `_cancelar_devolucao_
        # sync`'s checagem de `Nfe`).
        ids_devolucao_origem = (cab.get("ids_devolucao_origem") or "").strip()
        if ids_devolucao_origem:
            ids_dev = [int(i) for i in ids_devolucao_origem.split(",") if i.strip().isdigit()]
            if ids_dev:
                placeholders_dev = ",".join(["%s"] * len(ids_dev))
                cur.execute(
                    f"UPDATE devolucao_itens SET Nfe=%s WHERE id_devolucao IN ({placeholders_dev})",
                    tuple([codigo_n_fiscal] + ids_dev),
                )

        cur.execute("UPDATE nf_aux SET num_nf=%s WHERE codigo=%s", (codigo_n_fiscal, codigo))
        cur.execute("UPDATE controle SET numero_nf=%s", (resultado["numero"],))
        conn.commit()
        cur.close()
        conn.close()
        resultado["nota_fisc"] = codigo_n_fiscal
        resultado["rascunho"] = codigo
        return resultado
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Wrappers async
# ---------------------------------------------------------------------------

async def novo_rascunho(servidor: str, banco: str, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_novo_rascunho_sync, servidor, banco, classe=classe, master=master)


async def get_rascunho(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_rascunho_sync, servidor, banco, codigo)


async def save_cabecalho_rascunho(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    return await asyncio.to_thread(_save_cabecalho_rascunho_sync, servidor, banco, codigo, dados)


async def save_itens_rascunho(servidor: str, banco: str, codigo: int, itens: list) -> dict:
    return await asyncio.to_thread(_save_itens_rascunho_sync, servidor, banco, codigo, itens)


async def save_vencimentos_rascunho(servidor: str, banco: str, codigo: int, vencimentos: list) -> dict:
    return await asyncio.to_thread(_save_vencimentos_rascunho_sync, servidor, banco, codigo, vencimentos)


async def importar_pedido(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_importar_pedido_sync, servidor, banco, pedido)


async def importar_devolucao(servidor: str, banco: str, ids_devolucao: list[int]) -> dict:
    return await asyncio.to_thread(_importar_devolucao_sync, servidor, banco, ids_devolucao)


async def importar_compra(servidor: str, banco: str, pedido_compra: int) -> dict:
    return await asyncio.to_thread(_importar_compra_sync, servidor, banco, pedido_compra)


async def importar_requisicao(servidor: str, banco: str, requisicao: int) -> dict:
    return await asyncio.to_thread(_importar_requisicao_sync, servidor, banco, requisicao)


async def importar_nota_fiscal(servidor: str, banco: str, codigo_nf: int) -> dict:
    return await asyncio.to_thread(_importar_nota_fiscal_sync, servidor, banco, codigo_nf)


async def importar_complementar(servidor: str, banco: str, comanda: int) -> dict:
    return await asyncio.to_thread(_importar_complementar_sync, servidor, banco, comanda)


async def sugerir_tributacao(
    servidor: str, banco: str, codigo_int: str, mov: str, uf_destino: str,
    nao_contribuinte: bool, simples_nacional_cliente: bool, consumidor_final: bool,
) -> dict:
    return await asyncio.to_thread(
        _sugerir_tributacao_sync, servidor, banco, codigo_int=codigo_int, mov=mov, uf_destino=uf_destino,
        nao_contribuinte=nao_contribuinte, simples_nacional_cliente=simples_nacional_cliente,
        consumidor_final=consumidor_final,
    )


async def emitir_nfe_avulsa(
    servidor: str, banco: str, codigo: int, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _emitir_nfe_avulsa_sync, servidor, banco, codigo=codigo, usuario=usuario, classe=classe, master=master,
    )
