"""Transações > Notas Fiscais > **Recebimento de Mercadoria** — migração de
`Geral\\FrmtraRec.frm` (14.069 linhas, o maior form do sistema). Protocolo
Gauntlet acionado (Kelvin+Carlos+Thomé). Ver PENDENCIAS.md > "Recebimento
de Mercadoria" pro racional completo (achados da fonte, citação exata).

**Fase 1 desta migração (confirmada com o usuário 2026-08-20/21): digitação
manual completa** — cabeçalho + itens + vencimentos, crítica de
recebimento, custo médio ponderado, atualização real de estoque, baixa
FIFO de Pedido de Compra. **Importação de XML de NF-e de entrada fica pra
uma Fase 2 futura** (mesmo padrão de faseamento já usado em "NF-e Avulsa":
digitação primeiro, importação depois).

**Arquitetura**: mesmo padrão rascunho→promoção já usado em
`nfe_avulsa_service.py` (o precedente estrutural mais próximo) — enquanto
sendo digitado, tudo fica em `nf_recebimento`/`nf_recebimento_itens`/
`nf_recebimento_vencimento` (schema confirmado ao vivo via
`INFORMATION_SCHEMA.COLUMNS`, GERDELL/BARESTELA, 2026-08-21); só ao
"Atualizar" promove pra `n_fiscal`/`n_fiscal_itens`/`nf_vencimento`
(tabelas definitivas, mesmas usadas por Notas Fiscais/NF-e Avulsa/NF-e
Agrupada).

**Achados-chave da fonte, replicados aqui** (citação exata no plano
aprovado / PENDENCIAS.md):

1. **Crítica de recebimento** (`CmdCritica_Click`, `FrmtraRec.frm:7918`):
   compara cada total do cabeçalho contra a soma do mesmo campo nos itens.
   Diferença dentro de `controle.valor_libera_critica` → ajusta o ITEM de
   MAIOR valor daquele campo pela diferença (nunca mexe no cabeçalho,
   nunca distribui entre vários itens). Fora da tolerância → bloqueia
   "Atualizar".
2. **Custo médio ponderado** (`FrmtraRec.frm:7196-7255`):
   `CustoMedio = (EstoquePos×CustoPos + EstoqueAnt×CustoAnt) / (EstoqueAnt+EstoquePos)`
   — `CustoAnt` é `pecas.custo_reposicao` (não `custo_medio`!). Só grava
   `p_custo`/`custo_reposicao`/`custo_inventario` quando
   `tipo_mov.altera_custo` é verdadeiro (coluna real por tipo de
   movimentação, confirmada ao vivo — bit).
3. **Preço de venda por margem** (`FrmtraRec.frm:7290-7311`, gated por
   `tipo_mov.altera_venda` **e** um MODO de gating real por instalação —
   `controle_aux.Altera_preco_venda_tela` (confirmada ao vivo, GERDELL/
   BARESTELA=1, o padrão). Modo 1 (padrão): o preço só atualiza se
   `pecas.politica_preco='E'` (Entrada, campo "Tipo Preço" do Cadastro de
   Produtos) — o checkbox "Atualiza Preço" do item é ignorado. Modo 2: o
   inverso — só o checkbox por item conta, `politica_preco` é ignorado.
   **Achado tardio, 2026-08-21, motivado por pergunta direta do usuário**:
   a Fase 1 original só implementava o Modo 2 (checkbox), sem checar
   `politica_preco` — como GERDELL/BARESTELA está no Modo 1 (o padrão),
   isso significava que NENHUM produto teria o preço atualizado no
   Recebimento até esta correção, mesmo com "Tipo Preço = Entrada"
   marcado no cadastro. Corrigido lendo o modo uma vez por promoção.
   Fórmula em si: variante simples, mesma já portada em Produto Completo
   (`custo_reposicao × (1 + margem/100)`) — a variante `PrecoCLD` (deduz
   PIS/COFINS/Simples/Outras Despesas) não é replicada, mesma
   simplificação já documentada lá.
4. **Baixa FIFO de Pedido de Compra** (`BaixaPedidoCompra`,
   `FrmtraRec.frm:13772`): consome `pedido_itens` com `pedido.situacao IN
   ('F','RP')`, mesmo fornecedor+`codigo_int`, `ORDER BY pedido.codigo`
   (mais antigo primeiro). Transição de `situacao` F/RP→R/RP não
   encontrada literalmente na fonte — implementada por inferência
   razoável (todas as linhas do pedido com `qtd=qtd_recebida` → `'R'`,
   senão `'RP'`).
5. **Estoque** só atualiza se `tipo_mov.atualiza_est='S'`.

**Simplificações desta fase, documentadas**: o rateio de "frete fora da
nota" (`pfre`) usa só a variante proporcional ao valor de cada item — a
variante "NF de frete vinculada" (`nf_recebimento_frete`) não foi
implementada (tabela existe, sem uso nesta rodada). Crédito de ICMS na
composição do custo de inventário usa o valor de ICMS do próprio item
(não um rateio mais fino). Ramos de Veículo/Serviço no cálculo de custo
não são replicados — só Peças (`pecas`) recebem atualização de
custo/estoque; item que não bate com nenhuma Peça ainda é gravado em
`n_fiscal_itens` normalmente, só sem o efeito colateral de custo/estoque.
Resumo tributário (`nf_recebimento_icms`) e centro de custo
(`nf_recebimento_custo`) — tabelas de staging confirmadas no schema, sem
tela/endpoint de edição nesta rodada (mesmo padrão de "Fora de escopo").

**NUNCA testado ao vivo contra banco real além das consultas de schema
desta rodada** — mesma ressalva de todo o resto do pacote fiscal desta
migração.

**Fase 2 (2026-08-21): Importação de XML de NF-e de entrada** — a outra
metade de `FrmtraRec.frm`, fonte lida por completo desta vez:
`Geral\\Mdl_Imp_XML.bas::Inicia_Importacao_XML` (parsing, linhas 127-599) +
`FrmtraRec.frm::ImportaXML` (orquestração/gravação, linhas 13187-13758).

**Achados-chave, replicados abaixo**: (1) o legado faz parsing por
string-matching manual (`InStr`/`Mid`) — aqui usa-se `xml.etree.
ElementTree` (biblioteca padrão) em vez disso, mesmo reforço já sinalizado
pelo usuário sobre nunca montar SQL por concatenação de valor vindo do
XML; (2) cascata de ICMS por CST (regime normal) ou CSOSN (Simples
Nacional); (3) resolução de fornecedor por CNPJ com auto-criação
(`fornecedor`+`fornecedor_end`, schema confirmado ao vivo); (4) cascata de
vínculo de produto em 3 níveis (EAN via `pecas_xml`, código de fábrica,
EAN via `cProd`) — item sem vínculo fica para o usuário resolver
manualmente (mesmo padrão de `ProdutoSearchModal` já usado no resto do
projeto); (5) conversão de CFOP via `cfop_xml` (com fallback de prefixo);
(6) cascata de tributação PIS/COFINS via `cfop_pis_cofins`.

**Decisão de arquitetura, diferente do legado**: `FrmtraRec.frm` grava
`nf_recebimento`/`_itens`/`_vencimento` DIRETO ao confirmar a importação,
sem passar pelo ciclo rascunho→crítica→atualizar que a própria tela já
tem pra digitação manual. Esta migração reaproveita o rascunho da Fase 1
em vez de duplicar um segundo caminho de gravação — `_importar_xml_sync`
é read-only pro DOCUMENTO em si (nunca grava em `nf_recebimento`/`_itens`/
`_vencimento`), devolve `{header, itens, itens_sem_vinculo}` pro frontend
aplicar no rascunho já aberto, e o usuário confirma com os mesmos botões
"Salvar Rascunho"/"Criticar"/"Atualizar" já existentes — mesmo princípio
das 6 sub-rotinas de importação de "NF-e Avulsa"
(`nfe_avulsa_service.py`). **Exceção deliberada**: resolução de entidade
(criar fornecedor por CNPJ se não existir, gravar vínculo produto↔EAN em
`pecas_xml`, atualizar `pecas.codigo_bar`/`codigo_mercosul` quando vazios)
GRAVA imediatamente, mesmo antes de "Salvar Rascunho" — mesmo princípio já
usado em Cliente/Fornecedor (`CLAUDE.md` > "Global Entity Rules",
auto-load/auto-create por CPF/CNPJ), essas são tabelas de cadastro/lookup
reaproveitáveis, não o documento fiscal em si.

**Simplificações documentadas desta fase**: bloco Veículo (`<veicProd>`)
não replicado (mesma decisão da Fase 1 pro ramo Veículo); ICMS
desonerado (`vICMSDeson`/`vICMSSTDeson`) e retenção anterior (CST 60,
`vBCSTRet`/`vICMSSTRet`) não entram na composição de custo (cosmético/
contábil, fora do que a Fase 1 usa pra custo médio); cascata de NCM→
`ncm_cest` simplificada pra 1 tentativa (sem truncamento progressivo de
dígitos); branch `<dest>` da função de parsing (usado por outra tela, não
Recebimento) não implementado."""
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional

from db.connection import _open_conn
from services.permissoes_service import tem_permissao

_CAB_CAMPOS = [
    "fornecedor", "num_nf", "serie_nf", "especie", "tipo_doc", "cfop", "tipo_sintegra", "uf",
    "data", "data_mov", "valor_total",
    "base_icms", "valor_icms", "base_ipi", "valor_ipi",
    "base_pis", "valor_pis", "base_cofins", "valor_cofins",
    "base_sub", "seguro", "frete", "despesas", "frete_fora", "valor_sub",
    "base_iss", "valor_iss", "desconto", "mov", "obs", "data_saida",
    "cnpj_transportadora", "placa", "volumes", "especie_volume", "peso_bruto", "peso_liquido",
    "selo_fiscal", "passe_fiscal", "chave_acesso",
    "BASE_FCP", "VALOR_FCP", "BASE_FCP_ST", "VALOR_FCP_ST", "BASE_FCP_RETIDO", "VALOR_FCP_RETIDO",
    "total_pis_st", "total_cofins_st",
]

_ITEM_CAMPOS = [
    "codigo_int", "cod_fiscal", "cod_contabil", "tributacao",
    "qtd", "qtd_un_compra", "p_unit",
    "base_icms", "valor_icms", "alqt_icms", "reducao_base_icms",
    "base_ipi", "alqt_ipi", "valor_ipi",
    "base_sub", "valor_sub", "seguro", "frete", "despesas", "frete_fora",
    "base_iss", "valor_iss", "desconto", "valor_total",
    "base_pis_st", "valor_pis_st", "base_cofins_st", "valor_cofins_st", "VALOR_FCP_ST",
    "atualiza_preco", "numero_pedido",
    # PIS/COFINS regulares (não-ST) — adicionados na Fase 2 (Importação de
    # XML), único produtor real de valores não-zero por ora; a Fase 1
    # (digitação manual) nunca expôs esses campos na UI, mesmo motivo de
    # não entrarem na fórmula de custo médio (achado 2, só PIS-ST/
    # COFINS-ST entram).
    "tributacao_pis", "base_pis", "alqt_pis", "valor_pis",
    "tributacao_cofins", "base_cofins", "alqt_cofins", "valor_cofins",
]

# Campos comparados na crítica de recebimento (achado 1) — cabeçalho vs.
# soma do mesmo campo em todos os itens da nota.
_CAMPOS_CRITICA = [
    "valor_total", "base_icms", "valor_icms", "base_ipi", "valor_ipi",
    "base_sub", "valor_sub", "base_iss", "valor_iss",
    "frete", "seguro", "despesas", "desconto",
]


def _ensure_nf_recebimento_gerado_col(cur) -> None:
    """Rastreia qual `n_fiscal.codigo` foi gerado ao promover este
    recebimento — sem equivalente no schema legado (que usa só
    `nf_recebimento.situacao`), necessário aqui pra saber quando um
    rascunho já foi promovido (mesmo papel de `nf_aux.num_nf` em
    `nfe_avulsa_service.py`) e pra rastreabilidade. Migração idempotente,
    registrada em `schema_ensure.py` (ver CLAUDE.md > "Cada app precisa se
    auto-atualizar no banco")."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='n_fiscal_gerado' AND Object_ID=Object_ID('nf_recebimento')) "
        "ALTER TABLE nf_recebimento ADD n_fiscal_gerado INT NULL"
    )


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "RECEBIMENTO", comando)


# ---------------------------------------------------------------------------
# Rascunho (nf_recebimento/nf_recebimento_itens/nf_recebimento_vencimento)
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
            return {"success": False, "message": "Sem permissão para lançar Recebimento de Mercadoria."}
        _ensure_nf_recebimento_gerado_col(cur)
        cur.execute("INSERT INTO nf_recebimento (valor_total) OUTPUT INSERTED.codigo VALUES (0)")
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
        cols = ", ".join(["codigo", "situacao", "n_fiscal_gerado"] + _CAB_CAMPOS)
        cur.execute(f"SELECT {cols} FROM nf_recebimento WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Recebimento não encontrado."}
        cur.execute(
            f"SELECT codautonum, {', '.join(_ITEM_CAMPOS)} FROM nf_recebimento_itens "
            "WHERE codigo=%s ORDER BY codautonum",
            (codigo,),
        )
        itens = list(cur.fetchall())
        cur.execute(
            "SELECT sequencia, data_venc, valor FROM nf_recebimento_vencimento "
            "WHERE codigo=%s ORDER BY data_venc",
            (codigo,),
        )
        vencimentos = list(cur.fetchall())
        conn.close()
        return {
            "success": True, "cabecalho": row, "itens": itens, "vencimentos": vencimentos,
            "promovida": bool(row.get("n_fiscal_gerado")),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_cabecalho_rascunho_sync(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    if not codigo:
        return {"success": False, "message": "Recebimento inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Recebimento não encontrado."}
        if atual.get("n_fiscal_gerado"):
            conn.close()
            return {"success": False, "message": "Este recebimento já foi atualizado — não é possível editar."}

        sets = ", ".join(f"{c}=%s" for c in _CAB_CAMPOS)
        valores = [dados.get(c) for c in _CAB_CAMPOS]
        cur.execute(f"UPDATE nf_recebimento SET {sets} WHERE codigo=%s", (*valores, codigo))
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
        return {"success": False, "message": "Grave o cabeçalho do recebimento antes de lançar itens."}
    for it in itens:
        if not (it.get("codigo_int") or "").strip():
            return {"success": False, "message": "Todo item precisa de um Código de Produto."}
        if not it.get("qtd"):
            return {"success": False, "message": "Todo item precisa de Quantidade maior que zero."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Recebimento não encontrado."}
        if atual.get("n_fiscal_gerado"):
            conn.close()
            return {"success": False, "message": "Este recebimento já foi atualizado — não é possível editar."}

        cur.execute("DELETE FROM nf_recebimento_itens WHERE codigo=%s", (codigo,))
        cols = ", ".join(_ITEM_CAMPOS)
        marcas = ", ".join(["%s"] * len(_ITEM_CAMPOS))
        for it in itens:
            valores = [it.get(c) for c in _ITEM_CAMPOS]
            cur.execute(f"INSERT INTO nf_recebimento_itens (codigo, {cols}) VALUES (%s, {marcas})", (codigo, *valores))
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
        return {"success": False, "message": "Grave o cabeçalho do recebimento antes de lançar vencimentos."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM nf_recebimento_vencimento WHERE codigo=%s", (codigo,))
        for v in vencimentos:
            cur.execute(
                "INSERT INTO nf_recebimento_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
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
# Crítica de recebimento (achado 1)
# ---------------------------------------------------------------------------

def _aplicar_critica_sync(cur, codigo: int, tolerancia: float) -> dict:
    """Compara cada campo de `_CAMPOS_CRITICA` no cabeçalho contra a soma
    do mesmo campo nos itens. Diferença dentro da tolerância → auto-ajusta
    o ITEM de MAIOR valor daquele campo (nunca o cabeçalho, nunca vários
    itens). Fora da tolerância → registra divergência (bloqueia
    "Atualizar" no chamador)."""
    cols_cab = ", ".join(_CAMPOS_CRITICA)
    cur.execute(f"SELECT {cols_cab} FROM nf_recebimento WHERE codigo=%s", (codigo,))
    cab = cur.fetchone() or {}
    divergencias = []
    ajustes = []
    for campo in _CAMPOS_CRITICA:
        cur.execute(f"SELECT codautonum, {campo} FROM nf_recebimento_itens WHERE codigo=%s", (codigo,))
        linhas = cur.fetchall()
        soma_itens = sum(float(r.get(campo) or 0) for r in linhas)
        valor_cab = float(cab.get(campo) or 0)
        diff = round(valor_cab - soma_itens, 2)
        if diff == 0:
            continue
        if linhas and abs(diff) <= tolerancia:
            maior = max(linhas, key=lambda r: float(r.get(campo) or 0))
            novo_valor = round(float(maior.get(campo) or 0) + diff, 2)
            cur.execute(f"UPDATE nf_recebimento_itens SET {campo}=%s WHERE codautonum=%s", (novo_valor, maior["codautonum"]))
            ajustes.append({"campo": campo, "diferenca": diff, "item": maior["codautonum"], "novo_valor": novo_valor})
        else:
            divergencias.append({
                "campo": campo, "valor_cabecalho": valor_cab, "soma_itens": round(soma_itens, 2), "diferenca": diff,
            })
    return {"divergencias": divergencias, "ajustes": ajustes}


def _criticar_sync(servidor: str, banco: str, codigo: int, *, classe: Optional[int] = None, master: bool = False) -> dict:
    if not codigo:
        return {"success": False, "message": "Recebimento inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="CRITICAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para criticar o recebimento."}
        cur.execute("SELECT n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Recebimento não encontrado."}
        if atual.get("n_fiscal_gerado"):
            conn.close()
            return {"success": False, "message": "Este recebimento já foi atualizado."}

        cur.execute("SELECT valor_libera_critica FROM controle")
        ctrl = cur.fetchone() or {}
        tolerancia = float(ctrl.get("valor_libera_critica") or 0)

        resultado = _aplicar_critica_sync(cur, codigo, tolerancia)
        nova_situacao = "E" if resultado["divergencias"] else "A"
        cur.execute("UPDATE nf_recebimento SET situacao=%s WHERE codigo=%s", (nova_situacao, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "situacao": nova_situacao, **resultado}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao criticar: {e}"}


# ---------------------------------------------------------------------------
# Baixa FIFO de Pedido de Compra (achado 4)
# ---------------------------------------------------------------------------

def _baixar_pedido_compra_sync(cur, recebimento_codigo: int, fornecedor, codigo_int: str, qtd_recebida: float) -> None:
    restante = float(qtd_recebida or 0)
    if restante <= 0 or not fornecedor:
        return
    cur.execute(
        "SELECT pi.SEQUENCIA_PEDIDO_ITENS AS seq, pi.codigo, pi.qtd, pi.qtd_recebida, pi.p_unit "
        "FROM pedido_itens pi JOIN pedido p ON p.codigo = pi.codigo "
        "WHERE p.fornecedor=%s AND pi.codigo_int=%s AND p.situacao IN ('F','RP') "
        "AND pi.qtd > ISNULL(pi.qtd_recebida, 0) ORDER BY pi.codigo ASC",
        (fornecedor, codigo_int),
    )
    linhas = cur.fetchall()
    pedidos_tocados = set()
    for linha in linhas:
        if restante <= 0:
            break
        qtd_recebida_atual = float(linha.get("qtd_recebida") or 0)
        disponivel = float(linha["qtd"]) - qtd_recebida_atual
        if disponivel <= 0:
            continue
        consumido = min(disponivel, restante)
        nova_qtd_recebida = round(qtd_recebida_atual + consumido, 4)
        cur.execute("UPDATE pedido_itens SET qtd_recebida=%s WHERE SEQUENCIA_PEDIDO_ITENS=%s", (nova_qtd_recebida, linha["seq"]))
        cur.execute(
            "INSERT INTO nf_recebimento_pedido (recebimento, pedido, item, quant, quant_p) VALUES (%s,%s,%s,%s,%s)",
            (recebimento_codigo, linha["codigo"], codigo_int, consumido, round(consumido * float(linha.get("p_unit") or 0), 2)),
        )
        pedidos_tocados.add(linha["codigo"])
        restante -= consumido

    for ped_codigo in pedidos_tocados:
        cur.execute("SELECT COUNT(*) AS n FROM pedido_itens WHERE codigo=%s AND qtd > ISNULL(qtd_recebida, 0)", (ped_codigo,))
        pendentes = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute("UPDATE pedido SET situacao=%s WHERE codigo=%s", ("RP" if pendentes > 0 else "R", ped_codigo))


# ---------------------------------------------------------------------------
# Atualizar — promove nf_recebimento/_itens/_vencimento pra n_fiscal/
# n_fiscal_itens/nf_vencimento, calcula custo médio, preço por margem,
# estoque e baixa de Pedido de Compra (achados 2-5).
# ---------------------------------------------------------------------------

def _atualizar_sync(
    servidor: str, banco: str, codigo: int, *, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    if not codigo:
        return {"success": False, "message": "Recebimento inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para atualizar o recebimento."}

        cols = ", ".join(["codigo", "n_fiscal_gerado"] + _CAB_CAMPOS)
        cur.execute(f"SELECT {cols} FROM nf_recebimento WHERE codigo=%s", (codigo,))
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Recebimento não encontrado."}
        if cab.get("n_fiscal_gerado"):
            conn.close()
            return {"success": False, "message": "Este recebimento já foi atualizado — reprocessamento não é suportado nesta fase."}

        fornecedor = cab.get("fornecedor")
        mov = (cab.get("mov") or "").strip()
        num_nf = cab.get("num_nf")
        serie_nf = (cab.get("serie_nf") or "").strip()
        if not fornecedor or not mov or not num_nf or not cab.get("data"):
            conn.close()
            return {"success": False, "message": "Preencha Fornecedor, Tipo de Movimentação, Número da Nota e Data de Emissão antes de atualizar."}

        cur.execute("SELECT atualiza_est, altera_custo, altera_venda FROM tipo_mov WHERE codigo=%s", (mov,))
        tm = cur.fetchone()
        if not tm:
            conn.close()
            return {"success": False, "message": "Tipo de Movimentação não cadastrado."}

        cur.execute(
            "SELECT TOP 1 codigo FROM n_fiscal WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s",
            (num_nf, serie_nf, fornecedor),
        )
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Já existe uma Nota Fiscal com este Número/Série/Fornecedor."}

        cur.execute(
            f"SELECT codautonum, {', '.join(_ITEM_CAMPOS)} FROM nf_recebimento_itens WHERE codigo=%s ORDER BY codautonum",
            (codigo,),
        )
        itens = cur.fetchall()
        if not itens:
            conn.close()
            return {"success": False, "message": "Nenhum item lançado — nada a atualizar."}

        cur.execute("SELECT valor_libera_critica FROM controle")
        ctrl = cur.fetchone() or {}
        tolerancia = float(ctrl.get("valor_libera_critica") or 0)

        # Modo de gating do preço de venda (achado 3, `FrmtraRec.frm:7290-
        # 7311`) — configuração real por instalação, `controle_aux.
        # Altera_preco_venda_tela` (confirmada ao vivo, GERDELL/BARESTELA=1,
        # o padrão). Modo 1 (padrão): preço só atualiza se `pecas.
        # politica_preco='E'` (Entrada) no cadastro do PRODUTO — o checkbox
        # "Atualiza Preço" do item é ignorado neste modo. Modo 2: o inverso
        # — só o checkbox por item conta, `politica_preco` é ignorado.
        cur.execute("SELECT Altera_preco_venda_tela FROM controle_aux")
        cfg_aux = cur.fetchone() or {}
        modo_preco_por_item = int(cfg_aux.get("Altera_preco_venda_tela") or 1) == 2

        critica = _aplicar_critica_sync(cur, codigo, tolerancia)
        if critica["divergencias"]:
            conn.close()
            return {
                "success": False,
                "message": "A crítica encontrou divergências fora da tolerância — corrija antes de atualizar.",
                "divergencias": critica["divergencias"],
            }
        if critica["ajustes"]:
            cur.execute(
                f"SELECT codautonum, {', '.join(_ITEM_CAMPOS)} FROM nf_recebimento_itens WHERE codigo=%s ORDER BY codautonum",
                (codigo,),
            )
            itens = cur.fetchall()

        cur.execute("SELECT SUM(valor) AS soma FROM nf_recebimento_vencimento WHERE codigo=%s", (codigo,))
        soma_venc = float((cur.fetchone() or {}).get("soma") or 0)
        valor_total = float(cab.get("valor_total") or 0)
        if round(soma_venc, 2) != round(valor_total, 2):
            conn.close()
            return {
                "success": False,
                "message": (
                    f"Os vencimentos somam {soma_venc:.2f}, mas o Valor Total da nota é "
                    f"{valor_total:.2f} — ajuste antes de atualizar."
                ),
            }

        # ---- 1) Promove cabeçalho ----
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, fornecedor, especie, tipo_doc, cfop, tipo_sintegra, uf, "
            "data_nf, data_mov, valor_total, base_icms, valor_icms, base_ipi, valor_ipi, base_pis, valor_pis, "
            "base_cofins, valor_cofins, base_sub, seguro, frete, despesas, frete_fora, valor_sub, base_iss, "
            "valor_iss, desconto, mov, obs, data_saida, cnpj_transportadora, placa, volumes, especie_volume, "
            "peso_bruto, peso_liquido, selo_fiscal, passe_fiscal, chave_acesso, situacao, "
            "BASE_FCP, VALOR_FCP, BASE_FCP_ST, VALOR_FCP_ST, BASE_FCP_RETIDO, VALOR_FCP_RETIDO, "
            "total_pis_st, total_cofins_st) "
            "OUTPUT INSERTED.codigo VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                num_nf, serie_nf, fornecedor, cab.get("especie"), cab.get("tipo_doc"), cab.get("cfop"),
                cab.get("tipo_sintegra"), cab.get("uf"), cab.get("data"), cab.get("data_mov"),
                valor_total, cab.get("base_icms"), cab.get("valor_icms"), cab.get("base_ipi"), cab.get("valor_ipi"),
                cab.get("base_pis"), cab.get("valor_pis"), cab.get("base_cofins"), cab.get("valor_cofins"),
                cab.get("base_sub"), cab.get("seguro"), cab.get("frete"), cab.get("despesas"), cab.get("frete_fora"),
                cab.get("valor_sub"), cab.get("base_iss"), cab.get("valor_iss"), cab.get("desconto"), mov,
                cab.get("obs"), cab.get("data_saida"), cab.get("cnpj_transportadora"), cab.get("placa"),
                cab.get("volumes"), cab.get("especie_volume"), cab.get("peso_bruto"), cab.get("peso_liquido"),
                cab.get("selo_fiscal"), cab.get("passe_fiscal"), cab.get("chave_acesso"), "A",
                cab.get("BASE_FCP"), cab.get("VALOR_FCP"), cab.get("BASE_FCP_ST"), cab.get("VALOR_FCP_ST"),
                cab.get("BASE_FCP_RETIDO"), cab.get("VALOR_FCP_RETIDO"), cab.get("total_pis_st"), cab.get("total_cofins_st"),
            ),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])

        soma_valor_itens = sum(
            float(it.get("valor_total") or (float(it.get("qtd") or 0) * float(it.get("p_unit") or 0))) for it in itens
        ) or 1.0
        frete_fora_total = float(cab.get("frete_fora") or 0)

        # ---- 2) Itens (promoção + custo/estoque só para Peças + baixa de Pedido de Compra) ----
        for item in itens:
            codigo_int = (item.get("codigo_int") or "").strip()
            qtd = float(item.get("qtd") or 0)
            qtd_un_compra = float(item.get("qtd_un_compra") or 1) or 1
            p_unit = float(item.get("p_unit") or 0)
            valor_total_item = float(item.get("valor_total") or round(qtd * p_unit, 2))
            valor_produto = round(qtd * p_unit, 2)

            cur.execute(
                "INSERT INTO n_fiscal_itens (codigo, codigo_int, cod_fiscal, cod_contabil, tributacao, qtd, "
                "qtd_un_compra, p_unit, base_icms, valor_icms, alqt_icms, reducao_base_icms, base_ipi, alqt_ipi, "
                "valor_ipi, base_sub, valor_sub, seguro, frete, despesas, frete_fora, base_iss, valor_iss, "
                "desconto, valor_total, valor_produto, numero_pedido, base_pis_st, valor_pis_st, "
                "base_cofins_st, valor_cofins_st, VALOR_FCP_ST, tributacao_pis, base_pis, alqt_pis, valor_pis, "
                "tributacao_cofins, base_cofins, alqt_cofins, valor_cofins) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo_n_fiscal, codigo_int, item.get("cod_fiscal"), item.get("cod_contabil"), item.get("tributacao"),
                    qtd, qtd_un_compra, p_unit, item.get("base_icms"), item.get("valor_icms"), item.get("alqt_icms"),
                    item.get("reducao_base_icms"), item.get("base_ipi"), item.get("alqt_ipi"), item.get("valor_ipi"),
                    item.get("base_sub"), item.get("valor_sub"), item.get("seguro"), item.get("frete"),
                    item.get("despesas"), item.get("frete_fora"), item.get("base_iss"), item.get("valor_iss"),
                    item.get("desconto"), valor_total_item, valor_produto, item.get("numero_pedido"),
                    item.get("base_pis_st"), item.get("valor_pis_st"), item.get("base_cofins_st"),
                    item.get("valor_cofins_st"), item.get("VALOR_FCP_ST"),
                    item.get("tributacao_pis"), item.get("base_pis"), item.get("alqt_pis"), item.get("valor_pis"),
                    item.get("tributacao_cofins"), item.get("base_cofins"), item.get("alqt_cofins"), item.get("valor_cofins"),
                ),
            )

            cur.execute(
                "SELECT qtd, custo_reposicao, p_custo, margem_lucro, margem_tabela, politica_preco FROM pecas WHERE codigo_int=%s",
                (codigo_int,),
            )
            peca = cur.fetchone()
            if peca:
                qtd_recebida_real = qtd * qtd_un_compra
                if qtd_recebida_real > 0:
                    icms_item = float(item.get("valor_icms") or 0)
                    base_sub_item = float(item.get("base_sub") or 0)
                    pis_st = float(item.get("valor_pis_st") or 0)
                    cofins_st = float(item.get("valor_cofins_st") or 0)
                    fcp_st = float(item.get("VALOR_FCP_ST") or 0)
                    frete_item = float(item.get("frete") or 0)
                    seguro_item = float(item.get("seguro") or 0)
                    despesas_item = float(item.get("despesas") or 0)
                    desconto_item = float(item.get("desconto") or 0)
                    valor_sub_item = float(item.get("valor_sub") or 0)
                    iss_item = float(item.get("valor_iss") or 0)

                    cr = (
                        valor_total_item + frete_item + seguro_item + despesas_item
                        + fcp_st + pis_st + cofins_st + iss_item + valor_sub_item - desconto_item
                    ) / qtd_recebida_real

                    # "frete fora da nota" — só variante proporcional ao valor
                    # de cada item (ver docstring do módulo, simplificação
                    # documentada: NF de frete vinculada não implementada).
                    pfre = (valor_total_item / soma_valor_itens) * frete_fora_total / qtd_recebida_real if frete_fora_total else 0.0
                    custo_pos = cr + pfre

                    estoque_ant = float(peca.get("qtd") or 0)
                    custo_ant = float(peca.get("custo_reposicao") or 0)
                    estoque_pos = qtd_recebida_real
                    if (estoque_ant + estoque_pos) > 0:
                        custo_medio_novo = (estoque_pos * custo_pos + estoque_ant * custo_ant) / (estoque_ant + estoque_pos)
                    else:
                        custo_medio_novo = custo_pos

                    icms_credito_unit = (icms_item / qtd_recebida_real) if base_sub_item <= 0 else 0.0
                    ci = custo_pos - icms_credito_unit if base_sub_item <= 0 else custo_pos

                    sets = ["custo_medio=%s", "qtd_un_compra=%s", "alterado=1", "data_ultima_compra=%s"]
                    valores: list = [round(custo_medio_novo, 4), qtd_un_compra, cab.get("data")]
                    if (tm.get("atualiza_est") or "").strip().upper() == "S":
                        sets.append("qtd=%s")
                        valores.append(round(estoque_ant + estoque_pos, 4))
                    custo_base_venda = custo_ant
                    if tm.get("altera_custo"):
                        sets += ["p_custo=%s", "custo_reposicao=%s", "custo_inventario=%s", "custo_alterado=1"]
                        valores += [round(cr, 4), round(cr, 4), round(ci, 4)]
                        custo_base_venda = cr
                        cur.execute(
                            "UPDATE nf_recebimento_itens SET custo_anterior=%s WHERE codautonum=%s",
                            (custo_ant, item.get("codautonum")),
                        )
                    permite_preco = (
                        bool(item.get("atualiza_preco")) if modo_preco_por_item
                        else (peca.get("politica_preco") or "").strip().upper() == "E"
                    )
                    if tm.get("altera_venda") and permite_preco:
                        custo_base = custo_base_venda if custo_base_venda else float(peca.get("p_custo") or 0)
                        margem_lucro = float(peca.get("margem_lucro") or 0)
                        margem_tabela = float(peca.get("margem_tabela") or 0)
                        sets += ["p_venda=%s", "preco_lista=%s"]
                        valores += [
                            round(custo_base + custo_base * margem_lucro / 100, 2),
                            round(custo_base + custo_base * margem_tabela / 100, 2),
                        ]

                    valores.append(codigo_int)
                    cur.execute(f"UPDATE pecas SET {', '.join(sets)} WHERE codigo_int=%s", tuple(valores))

                _baixar_pedido_compra_sync(cur, codigo, fornecedor, codigo_int, qtd)

        # ---- 3) Vencimentos ----
        cur.execute("SELECT data_venc, valor FROM nf_recebimento_vencimento WHERE codigo=%s", (codigo,))
        for v in cur.fetchall():
            cur.execute(
                "INSERT INTO nf_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
                (codigo_n_fiscal, v["data_venc"], v["valor"]),
            )

        cur.execute("UPDATE nf_recebimento SET situacao=%s, n_fiscal_gerado=%s WHERE codigo=%s", ("P", codigo_n_fiscal, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "n_fiscal": codigo_n_fiscal,
            "message": f"Recebimento atualizado — Nota Fiscal nº {codigo_n_fiscal} gerada.",
        }
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar: {e}"}


# ---------------------------------------------------------------------------
# Importação de XML de NF-e de entrada (Fase 2) — ver docstring do módulo.
# `_parse_xml_nfe` é pura (sem cursor, sem I/O) — parseia com `xml.etree.
# ElementTree` em vez do string-matching frágil do legado. As demais
# funções desta seção resolvem entidades (fornecedor/produto/CFOP/PIS-
# COFINS) contra o banco; `_importar_xml_sync` NUNCA escreve em
# `nf_recebimento`/`_itens`/`_vencimento` — devolve o resultado pro
# frontend aplicar no rascunho já aberto via os endpoints de save da
# Fase 1 (mesmo princípio das 6 sub-rotinas de importação de NF-e Avulsa).
# ---------------------------------------------------------------------------

def _xt(el, tag: str, default=None):
    if el is None:
        return default
    found = el.find(tag)
    if found is None or found.text is None:
        return default
    v = found.text.strip()
    return v if v else default


def _xf(el, tag: str, default: float = 0.0) -> float:
    v = _xt(el, tag)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _to_data_iso(v) -> Optional[str]:
    if not v:
        return None
    v = v.strip()
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return v[:10]
    return None


def _to_int_or_zero(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _parse_item_prod(prod_el) -> dict:
    return {
        "cProd": _xt(prod_el, "cProd", ""), "cEAN": _xt(prod_el, "cEAN", ""),
        "xProd": _xt(prod_el, "xProd", ""), "NCM": _xt(prod_el, "NCM", ""),
        "cfop_xml": _xt(prod_el, "CFOP", ""),
        "qtd": _xf(prod_el, "qCom"), "p_unit": _xf(prod_el, "vUnCom"),
        "vProd": _xf(prod_el, "vProd"), "frete": _xf(prod_el, "vFrete"),
        "seguro": _xf(prod_el, "vSeg"), "desconto": _xf(prod_el, "vDesc"),
        "despesas": _xf(prod_el, "vOutro"),
    }


def _parse_item_icms(icms_el) -> dict:
    """Cascata por `CST` (regime normal) ou `CSOSN` (Simples Nacional) —
    achado 2 (`Mdl_Imp_XML.bas:263-379`). Desonerado (`vICMSDeson`/
    `vICMSSTDeson`) e retenção anterior (CST 60) não entram — simplificação
    documentada no cabeçalho do módulo."""
    resultado = {
        "base_icms": 0.0, "valor_icms": 0.0, "alqt_icms": 0.0, "reducao_base_icms": 0.0,
        "base_sub": 0.0, "valor_sub": 0.0, "VALOR_FCP_ST": 0.0,
    }
    filhos = list(icms_el) if icms_el is not None else []
    if not filhos:
        return resultado
    grupo = filhos[0]
    resultado["VALOR_FCP_ST"] = _xf(grupo, "vFCPST")
    csosn = _xt(grupo, "CSOSN")
    if csosn is not None:
        if csosn in ("101", "201", "900"):
            resultado["alqt_icms"] = _xf(grupo, "pCredSN")
            resultado["valor_icms"] = _xf(grupo, "vCredICMSSN")
        if csosn in ("201", "202", "500", "900"):
            resultado["base_sub"] = _xf(grupo, "vBCST")
            resultado["valor_sub"] = _xf(grupo, "vICMSST")
        return resultado
    cst = _xt(grupo, "CST", "")
    resultado["reducao_base_icms"] = _xf(grupo, "pRedBC")
    if cst in ("00", "20", "51"):
        resultado["base_icms"] = _xf(grupo, "vBC")
        resultado["alqt_icms"] = _xf(grupo, "pICMS")
        resultado["valor_icms"] = _xf(grupo, "vICMS")
    elif cst in ("10", "70", "90"):
        resultado["base_icms"] = _xf(grupo, "vBC")
        resultado["alqt_icms"] = _xf(grupo, "pICMS")
        resultado["valor_icms"] = _xf(grupo, "vICMS")
        resultado["base_sub"] = _xf(grupo, "vBCST")
        resultado["valor_sub"] = _xf(grupo, "vICMSST")
    elif cst == "30":
        resultado["base_sub"] = _xf(grupo, "vBCST")
        resultado["valor_sub"] = _xf(grupo, "vICMSST")
    return resultado


def _parse_item_ipi(imposto_el) -> dict:
    ipi_el = imposto_el.find("IPI") if imposto_el is not None else None
    return {"base_ipi": _xf(ipi_el, ".//vBC"), "alqt_ipi": _xf(ipi_el, ".//pIPI"), "valor_ipi": _xf(ipi_el, ".//vIPI")}


def _parse_item_pis_cofins(grupo_el, prefixo: str) -> dict:
    """`prefixo` = "PIS" ou "COFINS" — as 4 variantes reais (`Aliq`/`Qtde`/
    `NT`/`Outr`) têm o mesmo shape de tags nos dois tributos."""
    chave_trib, chave_base, chave_alqt, chave_valor = f"tributacao_{prefixo.lower()}", f"base_{prefixo.lower()}", f"alqt_{prefixo.lower()}", f"valor_{prefixo.lower()}"
    resultado = {chave_trib: "", chave_base: 0.0, chave_alqt: 0.0, chave_valor: 0.0}
    filhos = list(grupo_el) if grupo_el is not None else []
    if not filhos:
        return resultado
    grupo = filhos[0]
    tag = grupo.tag
    resultado[chave_trib] = _xt(grupo, "CST", "")
    if tag == f"{prefixo}Qtde":
        resultado[chave_base] = _xf(grupo, "qBCProd")
        resultado[chave_alqt] = _xf(grupo, "vAliqProd")
        resultado[chave_valor] = _xf(grupo, f"v{prefixo}")
    elif tag in (f"{prefixo}Aliq", f"{prefixo}Outr"):
        resultado[chave_base] = _xf(grupo, "vBC")
        resultado[chave_alqt] = _xf(grupo, f"p{prefixo}")
        resultado[chave_valor] = _xf(grupo, f"v{prefixo}")
    return resultado


def _parse_item_xml(det_el) -> dict:
    prod_el = det_el.find("prod")
    imposto_el = det_el.find("imposto")
    icms_el = imposto_el.find("ICMS") if imposto_el is not None else None
    pis_el = imposto_el.find("PIS") if imposto_el is not None else None
    cofins_el = imposto_el.find("COFINS") if imposto_el is not None else None
    pis_st_el = imposto_el.find("PISST") if imposto_el is not None else None
    cofins_st_el = imposto_el.find("COFINSST") if imposto_el is not None else None

    item = _parse_item_prod(prod_el)
    item.update(_parse_item_icms(icms_el))
    item.update(_parse_item_ipi(imposto_el))
    item.update(_parse_item_pis_cofins(pis_el, "PIS"))
    item.update(_parse_item_pis_cofins(cofins_el, "COFINS"))
    item["base_pis_st"] = _xf(pis_st_el, "vBC")
    item["valor_pis_st"] = _xf(pis_st_el, "vPIS")
    item["base_cofins_st"] = _xf(cofins_st_el, "vBC")
    item["valor_cofins_st"] = _xf(cofins_st_el, "vCOFINS")

    valor_total = (
        item["vProd"] + item["frete"] + item["seguro"] + item["despesas"]
        + item["valor_ipi"] + item["valor_sub"] + item["VALOR_FCP_ST"] - item["desconto"]
    )
    if _xt(pis_st_el, "indSomaPISST") == "1":
        valor_total += item["valor_pis_st"]
    if _xt(cofins_st_el, "indSomaCOFINSST") == "1":
        valor_total += item["valor_cofins_st"]
    item["valor_total"] = round(valor_total, 2)
    return item


def _parse_header_xml(root) -> dict:
    total_el = root.find(".//total/ICMSTot")
    ide_el = root.find(".//ide")
    emit_el = root.find(".//emit")
    ender_emit_el = emit_el.find("enderEmit") if emit_el is not None else None
    inf_nfe_el = root.find(".//infNFe")

    chave = ""
    if inf_nfe_el is not None:
        id_attr = (inf_nfe_el.get("Id") or "").strip()
        chave = id_attr[3:47] if id_attr.upper().startswith("NFE") else id_attr[-44:]
    if not chave:
        chave = _xt(root, ".//chNFe", "") or ""

    return {
        "num_nf": _xt(ide_el, "nNF"), "serie_nf": _xt(ide_el, "serie"),
        "data": _to_data_iso(_xt(ide_el, "dhEmi") or _xt(ide_el, "dEmi")),
        "data_saida": _to_data_iso(_xt(ide_el, "dhSaiEnt") or _xt(ide_el, "dEmi")),
        "chave_acesso": chave,
        "cnpj_fornecedor": _xt(emit_el, "CNPJ") or _xt(emit_el, "CPF") or "",
        "razao_social": _xt(emit_el, "xNome", ""), "fantasia": _xt(emit_el, "xFant", ""),
        "ie": _xt(emit_el, "IE", ""),
        "endereco": _xt(ender_emit_el, "xLgr", ""), "numero": _xt(ender_emit_el, "nro", ""),
        "complemento": _xt(ender_emit_el, "xCpl", ""), "bairro": _xt(ender_emit_el, "xBairro", ""),
        "municipio": _xt(ender_emit_el, "xMun", ""), "uf": _xt(ender_emit_el, "UF", ""),
        "cep": _xt(ender_emit_el, "CEP", ""), "pais": _xt(ender_emit_el, "xPais", "BRASIL"),
        "base_icms": _xf(total_el, "vBC"), "valor_icms": _xf(total_el, "vICMS"),
        "base_sub": _xf(total_el, "vBCST"), "valor_sub": _xf(total_el, "vST"),
        "frete": _xf(total_el, "vFrete"), "seguro": _xf(total_el, "vSeg"),
        "desconto": _xf(total_el, "vDesc"), "despesas": _xf(total_el, "vOutro"),
        "valor_ipi": _xf(total_el, "vIPI"), "valor_total": _xf(total_el, "vNF"),
        # base_fcp/base_fcp_st/base_fcp_retido sempre 0 no legado (só o
        # valor total é conhecido no bloco <total>, réplica de
        # `FrmtraRec.frm:13433-13434`).
        "BASE_FCP": 0.0, "VALOR_FCP": _xf(total_el, "vFCP"),
        "BASE_FCP_ST": 0.0, "VALOR_FCP_ST": _xf(total_el, "vFCPST"),
        "BASE_FCP_RETIDO": 0.0, "VALOR_FCP_RETIDO": _xf(total_el, "vFCPRet"),
    }


def _parse_vencimentos_xml(root, valor_total_nf: float) -> list:
    vencimentos = []
    for dup_el in root.findall(".//cobr/dup"):
        vencimentos.append({"data_venc": _to_data_iso(_xt(dup_el, "dVenc")), "valor": _xf(dup_el, "vDup")})
    soma = round(sum(v["valor"] for v in vencimentos), 2)
    if vencimentos and round(valor_total_nf, 2) != soma:
        # A diferença inteira é jogada na 1ª parcela — achado 3
        # (`Mdl_Imp_XML.bas:539-543`), comportamento real do legado.
        vencimentos[0]["valor"] = round(vencimentos[0]["valor"] + (valor_total_nf - soma), 2)
    return vencimentos


def _parse_xml_nfe(conteudo_xml: str) -> dict:
    """Função pura — sem cursor, sem I/O. Usa `xml.etree.ElementTree` (não
    o string-matching frágil do legado, ver docstring do módulo)."""
    root = ET.fromstring(conteudo_xml)
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    header = _parse_header_xml(root)
    itens = [_parse_item_xml(det) for det in root.findall(".//det")]
    vencimentos = _parse_vencimentos_xml(root, header.get("valor_total") or 0.0)
    return {"header": header, "itens": itens, "vencimentos": vencimentos}


def _resolver_produto_xml_sync(cur, item: dict, fornecedor_id: int) -> dict:
    """Cascata de 3 níveis (achado 6, `FrmtraRec.frm:13276-13323`): (a) EAN
    via `pecas_xml`; (b) código de fábrica (`pecas.codigo_fab`); (c) EAN de
    novo, mas contra `pecas_xml.codigo_xml=cProd` (item sem EAN
    reaproveitando o próprio código do produto)."""
    ean = (item.get("cEAN") or "").strip()
    cprod = (item.get("cProd") or "").strip()
    if ean and ean.upper() != "SEM GTIN":
        cur.execute(
            "SELECT pecas.codigo_int, pecas.descricao, pecas.qtd_un_compra FROM pecas_xml "
            "JOIN pecas ON pecas.codigo_int = pecas_xml.codigo_int "
            "WHERE pecas_xml.codigo_xml=%s AND pecas.situacao='A'",
            (ean,),
        )
        row = cur.fetchone()
        if row:
            return {"vinculado": True, "codigo_int": row["codigo_int"], "descricao": row["descricao"], "qtd_un_compra": row.get("qtd_un_compra") or 1}
    if cprod:
        cur.execute("SELECT codigo_int, descricao, qtd_un_compra FROM pecas WHERE codigo_fab=%s AND situacao='A'", (cprod,))
        row = cur.fetchone()
        if row:
            return {"vinculado": True, "codigo_int": row["codigo_int"], "descricao": row["descricao"], "qtd_un_compra": row.get("qtd_un_compra") or 1}
        cur.execute(
            "SELECT pecas.codigo_int, pecas.descricao, pecas.qtd_un_compra FROM pecas_xml "
            "JOIN pecas ON pecas.codigo_int = pecas_xml.codigo_int "
            "WHERE pecas_xml.codigo_xml=%s AND pecas.situacao='A'",
            (cprod,),
        )
        row = cur.fetchone()
        if row:
            return {"vinculado": True, "codigo_int": row["codigo_int"], "descricao": row["descricao"], "qtd_un_compra": row.get("qtd_un_compra") or 1}
    return {"vinculado": False, "codigo_int": None, "descricao": item.get("xProd") or cprod, "qtd_un_compra": 1}


def _resolver_cfop_xml_sync(cur, cfop_xml: str) -> str:
    """CFOP do XML → CFOP interno (achado 7) via `cfop_xml` (tabela 1:1);
    sem linha cadastrada, fallback por prefixo (`6→2`/outro `→1` + 3
    dígitos finais)."""
    cfop_xml = (cfop_xml or "").strip()
    if not cfop_xml:
        return ""
    cur.execute("SELECT cfop FROM cfop_xml WHERE cfop_xml=%s", (cfop_xml,))
    row = cur.fetchone()
    if row:
        return row["cfop"]
    if len(cfop_xml) < 4:
        return cfop_xml
    prefixo = "2" if cfop_xml[0] == "6" else "1"
    return prefixo + cfop_xml[1:4]


def _atualizar_cadastro_produto_xml_sync(cur, codigo_int, item: dict) -> None:
    """NCM/EAN — só preenche se o cadastro ainda estiver vazio (achado 7).
    Cascata de truncamento de `ncm_cest` simplificada pra 1 tentativa
    (sem cortar dígitos progressivamente) — simplificação documentada."""
    ncm = (item.get("NCM") or "").strip()
    if ncm:
        cur.execute("SELECT codigo_mercosul FROM pecas WHERE codigo_int=%s", (codigo_int,))
        row = cur.fetchone()
        if row and not (row.get("codigo_mercosul") or "").strip():
            cur.execute("UPDATE pecas SET codigo_mercosul=%s WHERE codigo_int=%s", (ncm, codigo_int))
    ean = (item.get("cEAN") or "").strip()
    if ean and ean.upper() != "SEM GTIN":
        cur.execute("SELECT codigo_bar FROM pecas WHERE codigo_int=%s", (codigo_int,))
        row = cur.fetchone()
        if row and not (row.get("codigo_bar") or "").strip():
            cur.execute("UPDATE pecas SET codigo_bar=%s WHERE codigo_int=%s", (ean, codigo_int))
        cur.execute("SELECT 1 AS ok FROM codbarra_auxiliar WHERE codigo_bar=%s", (ean,))
        if not cur.fetchone():
            cur.execute("INSERT INTO codbarra_auxiliar (codigo_int, codigo_bar) VALUES (%s,%s)", (codigo_int, ean))


def _resolver_pis_cofins_xml_sync(cur, item_final: dict, codigo_int, cfop_interno: str) -> None:
    """Cascata de tributação PIS/COFINS via `cfop_pis_cofins` (achado 7):
    achando linha com `Acatar_nfe=1`, mantém os valores já extraídos do
    XML; achando com `Acatar_nfe=0`, recalcula local (por quantidade ou
    por percentual sobre o valor); não achando, cai num fallback por faixa
    de CST do próprio XML."""
    cur.execute("SELECT cod_grupo_pis_cofins FROM pecas WHERE codigo_int=%s", (codigo_int,))
    peca = cur.fetchone()
    grupo = (peca or {}).get("cod_grupo_pis_cofins")
    if grupo:
        cur.execute(
            "SELECT tributacao_pis, tributacao_cofins, acatar_nfe, tributacao_qtd, perc_valor_pis, perc_valor_cofins "
            "FROM cfop_pis_cofins WHERE grupo_pis_cofins=%s AND cfop=%s",
            (grupo, cfop_interno),
        )
        cfg = cur.fetchone()
        if cfg:
            item_final["tributacao_pis"] = cfg.get("tributacao_pis")
            item_final["tributacao_cofins"] = cfg.get("tributacao_cofins")
            if cfg.get("acatar_nfe"):
                return
            if cfg.get("tributacao_qtd"):
                base = round(float(item_final.get("qtd") or 0) / 1000, 2)
                item_final["base_pis"] = base
                item_final["base_cofins"] = base
                item_final["valor_pis"] = round(base * float(cfg.get("perc_valor_pis") or 0), 2)
                item_final["alqt_pis"] = item_final["valor_pis"]
                item_final["valor_cofins"] = round(base * float(cfg.get("perc_valor_cofins") or 0), 2)
                item_final["alqt_cofins"] = item_final["valor_cofins"]
            else:
                base = round(float(item_final.get("qtd") or 0) * float(item_final.get("p_unit") or 0), 2)
                item_final["base_pis"] = base
                item_final["base_cofins"] = base
                item_final["valor_pis"] = round(base * float(cfg.get("perc_valor_pis") or 0) / 100, 2)
                item_final["alqt_pis"] = cfg.get("perc_valor_pis")
                item_final["valor_cofins"] = round(base * float(cfg.get("perc_valor_cofins") or 0) / 100, 2)
                item_final["alqt_cofins"] = cfg.get("perc_valor_cofins")
            return
    cst_pis = int(item_final.get("tributacao_pis") or 0) if str(item_final.get("tributacao_pis") or "").isdigit() else 99
    item_final["tributacao_pis"] = "50" if cst_pis <= 3 else "70"
    cst_cofins = int(item_final.get("tributacao_cofins") or 0) if str(item_final.get("tributacao_cofins") or "").isdigit() else 99
    item_final["tributacao_cofins"] = "50" if cst_cofins <= 3 else "70"


def _importar_xml_sync(
    servidor: str, banco: str, *, codigo_rascunho: int, conteudo_xml: str,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    if not codigo_rascunho:
        return {"success": False, "message": "Recebimento inválido."}
    try:
        parsed = _parse_xml_nfe(conteudo_xml)
    except ET.ParseError as e:
        return {"success": False, "message": f"XML inválido: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Não foi possível interpretar o XML: {e}"}

    itens_xml = parsed.get("itens") or []
    if not itens_xml:
        return {"success": False, "message": "Nenhum item encontrado no XML."}
    header = parsed["header"]

    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para importar XML de recebimento."}

        cur.execute("SELECT n_fiscal_gerado FROM nf_recebimento WHERE codigo=%s", (codigo_rascunho,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Recebimento não encontrado."}
        if atual.get("n_fiscal_gerado"):
            conn.close()
            return {"success": False, "message": "Este recebimento já foi atualizado — não é possível importar XML."}

        cnpj = (header.get("cnpj_fornecedor") or "").strip()
        if not cnpj:
            conn.close()
            return {"success": False, "message": "XML sem CNPJ do emitente — não é possível resolver o fornecedor."}

        cur.execute("SELECT codigo_int FROM fornecedor WHERE codigo=%s", (cnpj,))
        forn = cur.fetchone()
        if forn:
            fornecedor_id = int(forn["codigo_int"])
        else:
            cur.execute(
                "INSERT INTO fornecedor (codigo, nome, fantasia, data, situacao, inscr_est) "
                "OUTPUT INSERTED.codigo_int VALUES (%s,%s,%s,GETDATE(),'A',%s)",
                (cnpj, header.get("razao_social") or cnpj, header.get("fantasia") or "", header.get("ie") or ""),
            )
            fornecedor_id = int(cur.fetchone()["codigo_int"])
            cur.execute(
                "INSERT INTO fornecedor_end (codigo, endereco, numero, complemento, bairro, cidade, uf, cep, pais, tipo_endereco) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)",
                (
                    fornecedor_id, header.get("endereco") or "", _to_int_or_zero(header.get("numero")),
                    header.get("complemento") or "", header.get("bairro") or "", header.get("municipio") or "",
                    header.get("uf") or "", header.get("cep") or "", header.get("pais") or "BRASIL",
                ),
            )

        num_nf = header.get("num_nf")
        serie_nf = header.get("serie_nf") or ""
        cur.execute(
            "SELECT TOP 1 codigo FROM n_fiscal WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s",
            (num_nf, serie_nf, fornecedor_id),
        )
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Já existe uma Nota Fiscal com este Número/Série/Fornecedor."}
        cur.execute(
            "SELECT TOP 1 codigo FROM nf_recebimento WHERE num_nf=%s AND serie_nf=%s AND fornecedor=%s AND codigo<>%s",
            (num_nf, serie_nf, fornecedor_id, codigo_rascunho),
        )
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Este XML já foi importado em outro recebimento."}

        itens_resolvidos = []
        soma_base_ipi = 0.0
        for item in itens_xml:
            vinculo = _resolver_produto_xml_sync(cur, item, fornecedor_id)
            cfop_interno = _resolver_cfop_xml_sync(cur, item.get("cfop_xml") or "")
            item_final = dict(item)
            item_final["cod_fiscal"] = cfop_interno
            item_final["codigo_int"] = vinculo["codigo_int"]
            item_final["vinculado"] = vinculo["vinculado"]
            item_final["descricao"] = vinculo["descricao"]
            item_final["qtd_un_compra"] = vinculo.get("qtd_un_compra") or 1
            if vinculo["codigo_int"]:
                _resolver_pis_cofins_xml_sync(cur, item_final, vinculo["codigo_int"], cfop_interno)
                _atualizar_cadastro_produto_xml_sync(cur, vinculo["codigo_int"], item)
            soma_base_ipi += float(item_final.get("base_ipi") or 0)
            itens_resolvidos.append(item_final)

        header["base_ipi"] = round(soma_base_ipi, 2)
        header["fornecedor"] = fornecedor_id

        conn.commit()
        cur.close()
        conn.close()
        itens_sem_vinculo = [
            {"cProd": i.get("cProd"), "xProd": i.get("xProd")} for i in itens_resolvidos if not i["vinculado"]
        ]
        return {
            "success": True, "header": header, "itens": itens_resolvidos,
            "itens_sem_vinculo": itens_sem_vinculo, "vencimentos": parsed["vencimentos"],
        }
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao importar XML: {e}"}


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


async def criticar(servidor: str, banco: str, codigo: int, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_criticar_sync, servidor, banco, codigo, classe=classe, master=master)


async def atualizar(
    servidor: str, banco: str, codigo: int, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(_atualizar_sync, servidor, banco, codigo, usuario=usuario, classe=classe, master=master)


async def importar_xml(
    servidor: str, banco: str, codigo_rascunho: int, conteudo_xml: str,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _importar_xml_sync, servidor, banco, codigo_rascunho=codigo_rascunho, conteudo_xml=conteudo_xml,
        classe=classe, master=master,
    )
