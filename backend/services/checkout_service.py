"""Checkout — venda direta de balcão (migração de FrmPafOFF.frm, "Emissão de
Cupom Fiscal"). Fase 1 (núcleo), ver PENDENCIAS.md > "Checkout" pro rastreio
completo e as fases adiadas (TEF real, importar Pedido/O.S./Orçamento como
DAV, abastecimento de posto, agenda, venda externa por ficha, emissão fiscal
automática — esta última já existe em `comanda_service.emitir_nfce_comanda`
e continua acionada manualmente pelo Gestor de Comandas depois do Fechar).

Decisão de arquitetura confirmada com o usuário (2026-08-04, precisão
corrigida 2026-08-05): Faturar em Pedido/O.S. JÁ grava `comanda` (cabeçalho)
e `movimentacao` (itens, tipo='S01', serie_nf='CM') — `_faturar_pedido_sync`/
`_faturar_os_sync` fazem o mesmo `INSERT INTO comanda ... OUTPUT
INSERTED.comanda` + `INSERT INTO movimentacao` por item que este módulo
reaproveita. O que Pedido/O.S. NUNCA grava são as 8 tabelas de DETALHE de
forma de pagamento — `comanda_dinheiro`/`comanda_cheque`/`comanda_cartao`/
`comanda_debito`/`comanda_duplicata`/`comanda_ticket`/`comanda_vale`/
`comanda_financiado` — a forma de pagamento do Pedido/O.S. vai pra
`pedido_venda_*`/`os_*`; `comanda_service.py` só LÊ essas 8 tabelas (ficam
vazias quando a comanda se origina de Pedido/O.S.). A diferença real deste
módulo é mais estreita do que "grava em vez de ler comanda": é ser o único
caminho que grava DIRETAMENTE nessas 8 tabelas de pagamento (mais
`comanda_desconto`, `comanda_acresc`, `TROCO_COMANDA` e `cancelamento`) —
o `comanda`/`movimentacao` em si não é território novo, só reaproveita o
padrão que Faturar já usa. São as mesmas tabelas que `comanda_service.py`
(Gestor de Comandas/Alterar Comanda) já sabe LER, então uma venda feita
aqui já aparece corretamente nessas telas sem nenhuma mudança lá.

Diferente do legado (que só cria a linha em `comanda` na inclusão do 1º item,
`Vende_Item`), esta migração cria o cabeçalho já na abertura da tela — mesmo
padrão já usado por Pedido/O.S. (`POST /pedidos/create`), mais adequado a uma
API stateless/SPA.

Nota sobre baixa de estoque: o legado tem a linha de baixa de `pecas.qtd` em
`Vende_Item` COMENTADA (`'dbrevenda.Execute "update pecas set ... qtd = QTD -
..."`) — ou seja, o VB6 original não baixa estoque no ato da venda direta por
este caminho específico (algum outro processo do sistema legado cobria isso,
não identificado). Esta migração decide baixar explicitamente no ato
(`_mover_estoque_direto`), mesmo princípio já usado por Pedido/O.S. (só que
sem a fase intermediária de "reservado" — a venda aqui já é definitiva no
momento da inclusão do item, não há Abrir/Fechar separado). Documentado como
decisão de arquitetura, não suposição de regra de negócio "escondida".

Divergência de schema `comanda_*` × `pedido_venda_*`/`os_*` confirmada
lendo o legado (FrmPafOFF.frm, `Finaliza_Pagamento`): a coluna de valor de
`comanda_financiado` é `valor_pago` (não `valor_pag` como em
`pedido_venda_financiado`/`os_financiado`), e `comanda_financiado` não tem
coluna de vencimento — por isso os mapas abaixo (`_CMD_VALOR_COL`/
`_CMD_VENC_COL`) são um override LOCAL, não os mesmos dicts genéricos de
`pedido_common.py` (evita arriscar o código já testado de Pedido/O.S.).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _to_json_safe, friendly_db_error, is_connection_error
from services.pedido_common import (
    FORMA_PAG_SUFIXO_TIPO,
    _is_peca,
    _liberar_reservado,
    _modulo_agenda_ativo,
    _preco_promocional,
    _resolve_produto_completo,
    decode_codigo_barras_peso_variavel,
)
from services.permissoes_service import tem_permissao
from services.posto_common import MODULO_DESATIVADO_MSG, modulo_posto_ativo

TELA = "CHECKOUT"

# ---------------------------------------------------------------------------
# Mapas de forma de pagamento -> tabela/coluna, específicos de `comanda_*`
# (ver nota de divergência no topo do módulo).
# ---------------------------------------------------------------------------
_CMD_VALOR_COL: dict[str, str] = {
    "DI": "valor_pago", "CH": "valor", "CC": "valor", "CD": "valor",
    "DU": "valor_pag", "TI": "valor", "VA": "valor", "FI": "valor_pago",
}
_CMD_VENC_COL: dict[str, Optional[str]] = {
    "DI": None, "CH": "bom_para", "CC": "bom_para", "CD": "bom_para",
    "DU": "data_venc", "TI": None, "VA": "bom_para", "FI": None,
}


def _cmd_tabela(tipo: str) -> str:
    return "comanda_" + FORMA_PAG_SUFIXO_TIPO[tipo]


# ---------------------------------------------------------------------------
# Vale de Devolução (consumo como forma de pagamento) e Cartão Presente
# (resgate) — rastreados em `FrmPafOFF.frm` (Finaliza_Pagamento) antes de
# implementar. Achado real: nenhuma das duas é seu próprio "tipo" de forma
# de pagamento no legado —
#
# - **Vale de Devolução** é um campo COMPANHEIRO opcional
#   (`forma_pagamento.vale_devolucao`, bit) de formas já existentes cujo
#   `tipo` seja DI/DU/VA — quando o cadastro da forma tem esse flag ligado,
#   o operador informa o `codvale` junto com o valor. Validado: existe,
#   `situacao='A'` (nunca `situacao` do cliente — é AO PORTADOR, o legado
#   não faz esse checkgenérico), não usado 2x na mesma venda. **Assimetria
#   real do legado, replicada fielmente (user-directed, 2026-08-06)**: só
#   DU/VA podem gerar um "vale residual" (novo `vale_devolucao` com a
#   diferença) quando o valor usado é menor que o saldo do vale — DI
#   sempre consome o vale inteiro, sem residual. Uso gravado em
#   `comanda_vale_devolucao` (tabela real do legado, já existe no schema).
#
# - **Cartão Presente NUNCA teve resgate implementado no legado** — só a
#   VENDA do cartão existe (`pecas_cartao_presente`/`comanda_cartao_
#   presente`, colunas `comanda_venda`/`id_movimentacao_venda` mortas,
#   nunca escritas — evidência de que o resgate foi planejado mas nunca
#   codificado). Decisão do usuário (`AskUserQuestion`, 2026-08-06): "TEM
#   QUE SER FIEL AO LEGADO" — como não há mecânica de resgate no legado
#   pra copiar, a nova implementação espelha o padrão mais próximo que
#   EXISTE de verdade (Vale de Devolução): tudo-ou-nada por resgate, ao
#   portador (sem checar cliente), com criação de cartão residual quando o
#   valor usado é menor que o saldo — mesma mecânica de vale residual,
#   sempre (não há assimetria por tipo aqui, já que Cartão Presente não é
#   um "tipo" de forma de pagamento no sentido DI/DU/VA, é seu próprio
#   tipo novo `CP`). Reaproveita a coluna `comanda_cartao_presente.
#   situacao` (existe no schema, mas o legado nunca a transiciona de 'A')
#   com o mesmo papel de `vale_devolucao.situacao`: 'A'=saldo disponível,
#   'F'=resgatado. Uso gravado em `comanda_cartao_presente_resgate` (tabela
#   NOVA — não existe no legado, criada de forma idempotente).
# ---------------------------------------------------------------------------
TIPO_CARTAO_PRESENTE = "CP"


def _ensure_cartao_presente_resgate_table(cur) -> None:
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'comanda_cartao_presente_resgate') "
        "CREATE TABLE comanda_cartao_presente_resgate ("
        "autonum INT IDENTITY(1,1) PRIMARY KEY, "
        "comanda INT NOT NULL, "
        "comanda_cartao_presente INT NOT NULL, "
        "valor_usado FLOAT NOT NULL)"
    )


def _validar_vale_devolucao(cur, codvale: int, valor_pagamento: float, codvales_ja_usados: set) -> tuple[bool, Optional[str], Optional[dict]]:
    if codvale in codvales_ja_usados:
        return False, f"O Vale de Devolução #{codvale} já foi usado nesta mesma venda.", None
    cur.execute("SELECT codvale, cliente, valor, situacao FROM vale_devolucao WHERE codvale=%s", (codvale,))
    vale = cur.fetchone()
    if not vale:
        return False, f"Vale de Devolução #{codvale} não encontrado.", None
    situacao = (vale.get("situacao") or "").strip().upper()
    if situacao == "F":
        return False, f"Vale de Devolução #{codvale} já foi utilizado.", None
    if situacao == "C":
        return False, f"Vale de Devolução #{codvale} está cancelado.", None
    if valor_pagamento > float(vale.get("valor") or 0) + 0.005:
        return False, (
            f"Valor informado (R$ {valor_pagamento:.2f}) é maior que o saldo "
            f"do Vale de Devolução #{codvale} (R$ {float(vale['valor']):.2f})."
        ), None
    return True, None, vale


def _consumir_vale_devolucao(cur, vale: dict, comanda: int, valor_pagamento: float, tipo: str) -> None:
    codvale = int(vale["codvale"])
    saldo = float(vale.get("valor") or 0)
    cur.execute("UPDATE vale_devolucao SET situacao='F' WHERE codvale=%s", (codvale,))
    cur.execute(
        "INSERT INTO comanda_vale_devolucao (comanda, vale_devolucao, valor_usado) VALUES (%s,%s,%s)",
        (comanda, codvale, valor_pagamento),
    )
    residual = round(saldo - valor_pagamento, 2)
    # Assimetria real do legado (replicada fielmente): só DU/VA geram vale
    # residual — DI sempre consome o vale inteiro, sem gerar diferença.
    if residual > 0.004 and tipo in ("DU", "VA"):
        cur.execute(
            "INSERT INTO vale_devolucao (cliente, valor, data, situacao, usuario) "
            "VALUES (%s, %s, CONVERT(date, GETDATE()), 'A', %s)",
            (vale.get("cliente"), residual, 0),
        )


def _validar_cartao_presente(cur, codigo_cartao: str, valor_pagamento: float, codigos_ja_usados: set) -> tuple[bool, Optional[str], Optional[dict]]:
    codigo_cartao = (codigo_cartao or "").strip()
    if not codigo_cartao:
        return False, "Informe o código do Cartão Presente.", None
    if codigo_cartao in codigos_ja_usados:
        return False, f"O Cartão Presente {codigo_cartao} já foi usado nesta mesma venda.", None
    cur.execute(
        "SELECT pecas_cartao_presente_auto, codigo_int FROM pecas_cartao_presente WHERE cartao_presente=%s",
        (codigo_cartao,),
    )
    cartao = cur.fetchone()
    if not cartao:
        return False, f"Cartão Presente {codigo_cartao} não encontrado.", None
    cur.execute(
        "SELECT comanda_cartao_presente_auto, valor_venda FROM comanda_cartao_presente "
        "WHERE cartao_presente=%s AND ISNULL(situacao,'A')='A'",
        (int(cartao["pecas_cartao_presente_auto"]),),
    )
    saldo_row = cur.fetchone()
    if not saldo_row:
        return False, f"Cartão Presente {codigo_cartao} já foi resgatado ou não tem saldo disponível.", None
    saldo = float(saldo_row.get("valor_venda") or 0)
    if valor_pagamento > saldo + 0.005:
        return False, (
            f"Valor informado (R$ {valor_pagamento:.2f}) é maior que o saldo "
            f"do Cartão Presente {codigo_cartao} (R$ {saldo:.2f})."
        ), None
    return True, None, {
        "comanda_cartao_presente_auto": int(saldo_row["comanda_cartao_presente_auto"]),
        "codigo_int": cartao["codigo_int"], "saldo": saldo, "codigo_cartao": codigo_cartao,
    }


def _consumir_cartao_presente(cur, info: dict, comanda: int, valor_pagamento: float) -> None:
    auto = info["comanda_cartao_presente_auto"]
    cur.execute("UPDATE comanda_cartao_presente SET situacao='F' WHERE comanda_cartao_presente_auto=%s", (auto,))
    _ensure_cartao_presente_resgate_table(cur)
    cur.execute(
        "INSERT INTO comanda_cartao_presente_resgate (comanda, comanda_cartao_presente, valor_usado) VALUES (%s,%s,%s)",
        (comanda, auto, valor_pagamento),
    )
    residual = round(info["saldo"] - valor_pagamento, 2)
    if residual > 0.004:
        novo_codigo = f"{info['codigo_cartao']}-R{auto}"
        cur.execute(
            "INSERT INTO pecas_cartao_presente (codigo_int, cartao_presente, disponivel) "
            "OUTPUT INSERTED.pecas_cartao_presente_auto VALUES (%s, %s, 0)",
            (info["codigo_int"], novo_codigo),
        )
        novo_auto = int(cur.fetchone()["pecas_cartao_presente_auto"])
        cur.execute(
            "INSERT INTO comanda_cartao_presente (id_movimentacao, comanda, comanda_venda, cartao_presente, situacao, valor_venda) "
            "VALUES (0, %s, 0, %s, 'A', %s)",
            (comanda, novo_auto, residual),
        )


# ---------------------------------------------------------------------------
# Helpers de baixo nível
# ---------------------------------------------------------------------------

def _situacao_comanda(cur, comanda: int) -> Optional[str]:
    cur.execute("SELECT situacao FROM comanda WHERE comanda=%s", (comanda,))
    r = cur.fetchone()
    return (r.get("situacao") or "").strip().upper() if r else None


def _cliente_diversos(cur) -> int:
    """Réplica do fallback `CodClientesDiversos` (Form_Load de FrmPafOFF) —
    cliente genérico usado quando nenhum cliente é vinculado à venda."""
    cur.execute("SELECT TOP 1 codigo FROM cliente WHERE nome='CLIENTES DIVERSOS'")
    r = cur.fetchone()
    if r:
        return int(r["codigo"])
    cur.execute(
        "INSERT INTO cliente (nome, fantasia, indpres) "
        "OUTPUT INSERTED.codigo VALUES ('CLIENTES DIVERSOS','CLIENTES DIVERSOS',1)"
    )
    return int(cur.fetchone()["codigo"])


def _mover_estoque_direto(cur, codigo: str, delta_qtd: float) -> None:
    """Vende_Item (tipo venda direta): decrementa `pecas.qtd` imediatamente
    (delta_qtd negativo estorna — cancelar item/venda). Não faz nada pra
    serviços. Ver nota de arquitetura no topo do módulo."""
    if not delta_qtd or not _is_peca(cur, codigo):
        return
    cur.execute("UPDATE pecas SET qtd = ISNULL(qtd,0) - %s WHERE codigo_int=%s", (delta_qtd, codigo))


def _preco_por_qtd(cur, codigo_int: str, qtd: float) -> Optional[float]:
    """"Preço por Quantidade" (`pecas_preco_qtd`, ListBox `PrecoPorQtd` em
    FrmPafOFF) — maior faixa de quantidade cadastrada que a quantidade
    digitada atinge. None se não há tiers cadastrados."""
    cur.execute(
        "SELECT TOP 1 P_VENDA FROM pecas_preco_qtd WHERE codigo_int=%s AND QTD<=%s ORDER BY QTD DESC",
        (codigo_int, qtd),
    )
    r = cur.fetchone()
    return float(r["P_VENDA"]) if r else None


def _recalc_comanda_sync(cur, comanda: int) -> float:
    """Recalcula `comanda.valor_venda` a partir de `movimentacao` (itens
    ainda lançados nesta venda — p_unit já é o preço líquido unitário,
    com desconto/acréscimo do item já aplicados)."""
    cur.execute(
        "SELECT ISNULL(SUM(qtd*p_unit),0) AS total FROM movimentacao WHERE num_nf=%s AND serie_nf='CM'",
        (comanda,),
    )
    total = round(float(cur.fetchone()["total"] or 0), 2)
    cur.execute("UPDATE comanda SET valor_venda=%s WHERE comanda=%s", (total, comanda))
    return total


def _limite_desconto_item(row: dict, funcao: Optional[int]) -> float:
    """Limite de desconto por item conforme a função do atendente — réplica
    do `Select Case Val(RegVenda.Funcao_Atendente)` em `RetornaDadosProduto`
    (FrmPafOFF.frm): 1=Gerente usa `desc_g`, 2 ou 4=Supervisor usa `desc_s`,
    qualquer outro (Vendedor) usa `desc_v`. `funcao` None = sem limite (0)."""
    if funcao == 1:
        return float(row.get("desc_g") or 0)
    if funcao in (2, 4):
        return float(row.get("desc_s") or 0)
    if funcao is not None:
        return float(row.get("desc_v") or 0)
    return 0.0


def _verifica_parcelamento_cartao(cur, bandeira: str, administradora: int, parcelador: str, parcelas: int):
    """Réplica fiel de `Cartao_Verifica_Parcelamento` (`Gestor_Cartoes.bas`).

    Não é um limite mínimo/máximo de parcelas — é uma checagem de CADASTRO:
    - Parcelador "A" (Administradora): só confirma que existe uma linha em
      `cartoes_configuracoes` para (administradora, bandeira, 'A') — o
      número de parcelas não entra na validação neste ramo (fiel ao legado).
    - Parcelador "L" (Loja): busca a config (administradora, bandeira, 'L'),
      depois confirma que existe uma linha em
      `cartoes_configuracoes_recebimento` pra aquele número exato de parcela.

    Retorna (ok: bool, mensagem_erro: str | None)."""
    parcelador = (parcelador or "").strip().upper()
    if parcelador == "A":
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM cartoes_configuracoes "
            "WHERE cod_administradora=%s AND cod_bandeira=%s AND cod_parcelador='A'",
            (administradora, bandeira),
        )
        if not cur.fetchone():
            return False, "Configuração de bandeira não cadastrada!"
        return True, None
    cur.execute(
        "SELECT cod_cartoes_configuracao FROM cartoes_configuracoes "
        "WHERE cod_administradora=%s AND cod_bandeira=%s AND cod_parcelador='L'",
        (administradora, bandeira),
    )
    row = cur.fetchone()
    if not row:
        return False, "Configuração de bandeira não cadastrada!"
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM cartoes_configuracoes_recebimento "
        "WHERE cod_cartoes_configuracao=%s AND cod_parcela=%s",
        (row["cod_cartoes_configuracao"], parcelas),
    )
    if not cur.fetchone():
        return False, "Configuração de bandeira não cadastrada!"
    return True, None


# ---------------------------------------------------------------------------
# Abrir venda / detalhe / buscar produto
# ---------------------------------------------------------------------------

def _abrir_venda_sync(req) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "ADD_ITEM"):
            conn.close()
            return {"success": False, "message": "Sem permissão para abrir o Checkout."}
        cliente = req.cliente or _cliente_diversos(cur)
        cur.execute(
            "INSERT INTO comanda (data, cliente, valor_venda, situacao, atendente, hora_comanda, area_atuacao) "
            "OUTPUT INSERTED.comanda "
            "VALUES (CONVERT(date, GETDATE()), %s, 0, 'A', %s, CONVERT(varchar(8), GETDATE(), 108), %s)",
            (cliente, req.atendente, req.area_atuacao or 0),
        )
        comanda = int(cur.fetchone()["comanda"])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "comanda": comanda}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        # Conexão pode cair NO MEIO da query (ex.: "DBPROCESS is dead or not
        # enabled") — achado ao vivo, 2026-08-11, KPDV contra GERDELL/
        # BARESTELA. `is_connection_error` evita aplicar a tradução amigável
        # em cima de um erro de negócio genuíno (não é isso aqui).
        msg = friendly_db_error(e) if is_connection_error(e) else f"Erro ao abrir venda: {e}"
        return {"success": False, "message": msg}


def _get_venda_sync(servidor: str, banco: str, comanda: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.comanda, c.data, c.situacao, c.valor_venda, c.cliente, c.atendente, c.area_atuacao, "
            "cl.nome AS cliente_nome, cl.fantasia AS cliente_fantasia, cl.cgc_cpf AS cliente_cgc_cpf, "
            # Nome do atendente sempre nome_guerra, com fallback pro nome
            # completo — mesma regra `[GLOBAL]` já aplicada a Pedido/O.S.
            # (ver CLAUDE.md > "Nome do Vendedor — sempre nome_guerra").
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS atendente_nome "
            "FROM comanda c "
            "LEFT JOIN cliente cl ON cl.codigo = c.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = c.atendente "
            "WHERE c.comanda=%s",
            (comanda,),
        )
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        cur.execute(
            "SELECT m.id_mov, m.codigo_int, m.qtd, m.p_unit, m.vendedor, m.tipo_dav, m.COD_AUTO_DAV, "
            "ISNULL(NULLIF(p.descricao_pdv,''), p.descricao) AS descricao_p, s.descricao AS descricao_s, "
            # `cod_fab`/`uni` — achados no rastreio do recibo não fiscal do
            # legado (`FrmPafOFF.frm`, "Cupom" impresso pela impressora
            # fiscal/ECF: colunas Código/Un usam `codigo_fab`/`uni`, não
            # `codigo_int`/vazio como este endpoint já devolvia) — usados
            # pelo recibo tabular novo do KPDV WPF (ver
            # `KPDV/src/KPDV/Utils/ReciboTexto.cs`). Serviço não tem
            # nenhum dos dois (`cod_fab`/`uni` ficam `NULL`, tratados como
            # vazio no service).
            "p.codigo_fab AS cod_fab, p.uni AS uni, "
            "d.desconto, d.PRECO_BRUTO AS preco_bruto_desc, a.acrescimo, a.PRECO_BRUTO AS preco_bruto_acr "
            "FROM movimentacao m "
            "LEFT JOIN pecas p ON p.codigo_int = m.codigo_int "
            "LEFT JOIN servicos s ON s.codigo = m.codigo_int "
            "LEFT JOIN comanda_desconto d ON d.id_mov = m.id_mov "
            "LEFT JOIN comanda_acresc a ON a.id_mov = m.id_mov "
            "WHERE m.num_nf=%s AND m.serie_nf='CM' ORDER BY m.id_mov",
            (comanda,),
        )
        itens = []
        for r in cur.fetchall():
            r = _to_json_safe(r) or {}
            preco_bruto = float(r.get("preco_bruto_desc") or r.get("preco_bruto_acr") or r.get("p_unit") or 0)
            tipo_dav_item = (r.get("tipo_dav") or "").strip().upper()
            itens.append({
                "id_mov": int(r["id_mov"]),
                "codigo": (r.get("codigo_int") or "").strip(),
                "cod_fab": (r.get("cod_fab") or "").strip(),
                "unidade": (r.get("uni") or "").strip(),
                "descricao": (r.get("descricao_p") or r.get("descricao_s") or "").strip(),
                "qtd": float(r.get("qtd") or 0),
                "p_unit": float(r.get("p_unit") or 0),
                "preco_bruto": preco_bruto,
                "vendedor": r.get("vendedor"),
                "desconto_unit": float(r.get("desconto") or 0),
                "acrescimo_unit": float(r.get("acrescimo") or 0),
                "total": round(float(r.get("qtd") or 0) * float(r.get("p_unit") or 0), 2),
                # Item vindo de importação de Pedido("P")/O.S.("O") — não
                # pode ser cancelado individualmente (ver _cancelar_item_sync).
                "origem_dav": tipo_dav_item or None,
                # Número do documento de origem (Pedido/O.S./Abastecimento/
                # Agenda) — pedido explícito do usuário, 2026-08-06
                # ("informar o número da pré-venda na lista de itens").
                "documento_dav": int(r["COD_AUTO_DAV"]) if r.get("COD_AUTO_DAV") is not None else None,
            })
        cur.execute("SELECT ped FROM COMANDA_PED WHERE comanda=%s", (comanda,))
        pedidos_importados = [int(r["ped"]) for r in cur.fetchall()]
        cur.execute("SELECT os FROM comanda_os WHERE comanda=%s", (comanda,))
        os_importadas = [int(r["os"]) for r in cur.fetchall()]
        formas = []
        situacao = (cab.get("situacao") or "").strip().upper()
        if situacao == "PG":
            for tipo, col in _CMD_VALOR_COL.items():
                cur.execute(
                    f"SELECT t.sequencia, t.forma_pag, fp.descricao, t.{col} AS valor "
                    f"FROM {_cmd_tabela(tipo)} t LEFT JOIN forma_pagamento fp ON fp.codigo = t.forma_pag "
                    f"WHERE t.comanda=%s",
                    (comanda,),
                )
                for r in cur.fetchall():
                    formas.append({
                        "tipo": tipo, "sequencia": int(r["sequencia"]),
                        "forma_pag": (r.get("forma_pag") or "").strip(),
                        "descricao": (r.get("descricao") or "").strip(),
                        "valor": float(r.get("valor") or 0),
                    })
        cur.execute("SELECT ISNULL(SUM(valor_troco),0) AS troco FROM TROCO_COMANDA WHERE comanda=%s", (comanda,))
        troco = float((cur.fetchone() or {}).get("troco") or 0)
        cur.close()
        conn.close()
        cab = _to_json_safe(cab) or {}
        return {
            "success": True,
            "comanda": int(cab["comanda"]),
            "data": cab.get("data"),
            "situacao": situacao,
            "valor_venda": float(cab.get("valor_venda") or 0),
            "cliente": cab.get("cliente"),
            "cliente_nome": (cab.get("cliente_fantasia") or cab.get("cliente_nome") or "").strip(),
            "cliente_cgc_cpf": (cab.get("cliente_cgc_cpf") or "").strip(),
            "atendente": cab.get("atendente"),
            "atendente_nome": (cab.get("atendente_nome") or "").strip(),
            "itens": itens,
            "formas_pagamento": formas,
            "troco": troco,
            "pedidos_importados": pedidos_importados,
            "os_importadas": os_importadas,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _buscar_produto_sync(servidor: str, banco: str, codigo: str, qtd: float = 1) -> dict:
    """Resolve produto/serviço pra pré-visualização no campo de código (busca
    por código interno/fábrica/barras — via `_resolve_produto_completo`,
    já testado pelo Pedido Completo — mais serviço), já aplicando preço
    promocional (`pecas_promocao`, mesma tabela/regra de "Variações de
    Preços" do Produto Completo) e Preço por Quantidade quando aplicável.

    Simplificação registrada em PENDENCIAS.md: não implementa o fluxo do
    legado de digitar o CÓDIGO DA PROMOÇÃO diretamente (em vez do código do
    produto) — caso de uso de baixo volume, fora do escopo desta fase.

    Automação Comercial (2026-08-10): se `codigo` for um código de barras de
    peso variável (EAN-13, prefixo "2" — etiqueta impressa por balança de
    pré-pesagem), decodifica e resolve pelo código do PRODUTO embutido nele,
    não pelo código de barras cru — ver `decode_codigo_barras_peso_variavel`
    em `pedido_common.py` pro aviso de confiança (best-effort, não validado
    contra etiqueta real)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        codigo_digitado = (codigo or "").strip()
        peso_barras = decode_codigo_barras_peso_variavel(codigo_digitado)
        codigo_resolver = peso_barras["codigo_produto"] if peso_barras else codigo_digitado
        produto = _resolve_produto_completo(cur, codigo_resolver)
        if not produto:
            cur.close(); conn.close()
            return {"success": False, "message": "Produto ou Serviço não cadastrado!"}
        preco = produto["valor"]
        promocao = None
        if produto["tipo"] == "P":
            promo = _preco_promocional(cur, produto["codigo"], qtd)
            if promo:
                preco = promo["p_venda"]
                promocao = promo["descricao_promocao"]
            else:
                tier = _preco_por_qtd(cur, produto["codigo"], qtd)
                if tier is not None:
                    preco = tier
        estoque = None
        imagem_codigo = None
        if produto["tipo"] == "P":
            cur.execute("SELECT qtd FROM pecas WHERE codigo_int=%s", (produto["codigo"],))
            r = cur.fetchone()
            estoque = float(r["qtd"]) if r else 0
            # Foto de produto (KPDV — exibida no rodapé do menu lateral ao
            # adicionar um item, 2026-08-27) — mesma consulta já usada em
            # produtos_service.py/itens_service.py, nunca duplicado como
            # LEFT JOIN aqui porque este SELECT já resolve por 4 colunas
            # diferentes (codigo_fab/codigo_int/codigo_bar/CODBARRA_AUXILIAR)
            # em _resolve_produto_completo — mais simples resolver a imagem
            # à parte, já com o codigo_int definitivo em mãos.
            cur.execute(
                "SELECT codigo FROM produto_imagem WHERE codigo_int=%s AND principal=1 AND situacao='A'",
                (produto["codigo"],),
            )
            r_img = cur.fetchone()
            imagem_codigo = int(r_img["codigo"]) if r_img else None
        limites = _limites_desconto(cur, produto)
        cur.close()
        conn.close()
        return {
            "success": True,
            "codigo": produto["codigo"],
            "cod_fab": produto["cod_fab"],
            "descricao": produto["descricao"],
            "imagem_codigo": imagem_codigo,
            "tipo": produto["tipo"],
            "unidade": produto["unidade"],
            "preco": preco,
            "promocao": promocao,
            "estoque": estoque,
            "peso_variado": produto.get("peso_variado", False),
            "peso_kg": peso_barras["peso_kg"] if peso_barras else None,
            **limites,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _limites_desconto(cur, produto: dict) -> dict:
    if produto["tipo"] == "P":
        cur.execute("SELECT desc_g, desc_s, desc_v FROM pecas WHERE codigo_int=%s", (produto["codigo"],))
    else:
        cur.execute("SELECT desc_g, desc_s, desc_v FROM servicos WHERE codigo=%s", (produto["codigo"],))
    r = cur.fetchone() or {}
    return {"desc_g": float(r.get("desc_g") or 0), "desc_s": float(r.get("desc_s") or 0), "desc_v": float(r.get("desc_v") or 0)}


# ---------------------------------------------------------------------------
# Adicionar / cancelar item
# ---------------------------------------------------------------------------

def _verifica_taxa_nfce(cur, cod_icms: str) -> tuple[bool, Optional[str]]:
    """Réplica de `RetornaDadosProduto` (`FrmPafOFF.frm`, chamada por
    `Campo_Validate` ao sair do campo Código) — checa se existe uma linha em
    `taxas_nfce` pra este produto/serviço antes de deixar incluir o item na
    venda. Rastreado ao vivo via agente de pesquisa, 2026-08-06.

    Query real do legado: `SELECT * FROM taxas_nfce WHERE Destino=<UF do
    Controle> AND Cod_Icms=<cod_icms do produto/serviço> AND Tipo_Mov='S01'`
    — `Destino` é a UF do PRÓPRIO estabelecimento (`controle.uf`, não a UF
    do cliente da venda). Mensagem de bloqueio do legado: "Operação não
    Cadastrada na Tabela de Taxas ou Indisponível no ECF !" — adaptada aqui
    sem a referência a "ECF" (impressora fiscal antiga, não existe nesta
    arquitetura).

    **Gating por `controle.emite_nf_comanda`, decisão explícita do usuário
    (2026-08-06), DIVERGE do legado de propósito**: no VB6 essa checagem
    roda SEMPRE, incondicionalmente — inclusive bloqueando uma empresa
    configurada como não-fiscal (confirmado por rastreio: nenhuma leitura
    de `emite_nf_comanda`/`IMPRIME_NFCE_NAO_FISCAL` dentro de
    `RetornaDadosProduto`/`Campo_Validate`, uma inconsistência real do
    legado). O usuário escolheu NÃO replicar essa inconsistência aqui —
    só bloqueia quando a empresa realmente emite NF direto. O caller
    (`_add_item_sync`) é responsável por checar `emite_nf_comanda` antes de
    chamar esta função; ela mesma não repete essa checagem."""
    if not cod_icms:
        return True, None
    cur.execute("SELECT TOP 1 uf FROM controle")
    row = cur.fetchone()
    uf = (row.get("uf") or "").strip() if row else ""
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM taxas_nfce WHERE Destino=%s AND Cod_Icms=%s AND Tipo_Mov='S01'",
        (uf, cod_icms),
    )
    if cur.fetchone():
        return True, None
    return False, "Esta operação não está cadastrada na Tabela de Taxas (NFCe) para este produto/serviço e UF."


def _add_item_sync(req, comanda: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "ADD_ITEM"):
            conn.close()
            return {"success": False, "message": "Sem permissão para adicionar item."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada/cancelada."}

        produto = _resolve_produto_completo(cur, (req.codigo or "").strip())
        if not produto:
            conn.close()
            return {"success": False, "message": "Produto ou Serviço não cadastrado!"}

        # Checagem de Taxa (taxas_nfce) — réplica de `RetornaDadosProduto`
        # (FrmPafOFF.frm), só quando a empresa emite NF direto pra comanda
        # (`controle.emite_nf_comanda`) — decisão explícita do usuário,
        # 2026-08-06, de NÃO replicar a inconsistência do legado (lá roda
        # sempre, mesmo pra empresa não-fiscal). Ver _verifica_taxa_nfce.
        cur.execute("SELECT TOP 1 emite_nf_comanda FROM controle")
        row_controle = cur.fetchone()
        if row_controle and row_controle.get("emite_nf_comanda"):
            taxa_ok, taxa_erro = _verifica_taxa_nfce(cur, produto.get("cod_icms") or "")
            if not taxa_ok:
                conn.close()
                return {"success": False, "message": taxa_erro}

        qtd = float(req.qtd or 1)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade inválida!"}

        preco_bruto = produto["valor"]
        if produto["tipo"] == "P":
            promo = _preco_promocional(cur, produto["codigo"], qtd)
            if promo:
                preco_bruto = promo["p_venda"]
            else:
                tier = _preco_por_qtd(cur, produto["codigo"], qtd)
                if tier is not None:
                    preco_bruto = tier

        limites = _limites_desconto(cur, produto)
        limite = _limite_desconto_item(limites, req.funcao)
        desconto_pct = float(req.desconto_percentual or 0)
        acrescimo_pct = float(req.acrescimo_percentual or 0)
        if desconto_pct > limite and not req.autorizado_por:
            conn.close()
            return {"success": False, "message": "Desconto maior que o permitido!"}

        desconto_unit = round(preco_bruto * desconto_pct / 100, 2) if desconto_pct else 0.0
        acrescimo_unit = round(preco_bruto * acrescimo_pct / 100, 2) if acrescimo_pct else 0.0
        p_unit = round(preco_bruto + acrescimo_unit - desconto_unit, 4)
        if p_unit <= 0:
            conn.close()
            return {"success": False, "message": "O valor de venda não pode ser igual ou inferior a zero!"}

        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, vendedor, p_unit, num_nf, serie_nf, custo_mov, item_paga_comissao) "
            "OUTPUT INSERTED.id_mov "
            "VALUES (CONVERT(date, GETDATE()), 'S01', %s, %s, %s, %s, %s, 'CM', %s, 1)",
            (produto["codigo"], qtd, req.vendedor, p_unit, comanda, produto["custo"]),
        )
        id_mov = int(cur.fetchone()["id_mov"])

        if desconto_unit > 0:
            cur.execute(
                "INSERT INTO comanda_desconto (comanda, codigo_int, desconto, id_mov, PRECO_BRUTO, USUARIO_DESCONTO) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (comanda, produto["codigo"], desconto_unit, id_mov, preco_bruto, req.autorizado_por or req.usuario_alteracao or 0),
            )
        if acrescimo_unit > 0:
            cur.execute(
                "INSERT INTO comanda_acresc (comanda, codigo_int, acrescimo, id_mov, PRECO_BRUTO) VALUES (%s,%s,%s,%s,%s)",
                (comanda, produto["codigo"], acrescimo_unit, id_mov, preco_bruto),
            )

        _mover_estoque_direto(cur, produto["codigo"], qtd)
        if produto["tipo"] == "P":
            cur.execute("UPDATE pecas SET data_ultima_venda = CONVERT(date, GETDATE()) WHERE codigo_int=%s", (produto["codigo"],))
        total = _recalc_comanda_sync(cur, comanda)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id_mov": id_mov, "valor_venda": total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _list_dav_pendentes_sync(servidor: str, banco: str, tipo_dav: str) -> dict:
    """Lista Pedidos de Venda ou O.S. já Fechados, prontos pra importar como
    DAV nesta venda (`_importar_dav_sync`) — evita que o operador precise
    saber/digitar o número do documento de cor (pedido explícito do
    usuário: "Ao clicar, listar as pré-venda sem precisar procurar,
    conforme no legado" — `FrmPafOFF.frm` já lista em "Dav's disponíveis").
    Mesmo critério de elegibilidade já usado por `_importar_dav_sync`
    (situação = 'F'), só que aqui é uma LISTA em vez de uma busca por
    número — a validação real de novo continua acontecendo no import.

    Retry único em caso de timeout de conexão — achado ao vivo, 2026-08-06,
    testando contra BD_PAJE: tanto a versão original (subquery correlacionada
    por linha de `os`) quanto a reescrita em JOIN+GROUP BY (geralmente mais
    rápida em bloco, mantida por ser a prática melhor de qualquer forma)
    falhavam de forma intermitente (~50-60% das tentativas) com o MESMO erro
    ("DBPROCESS is dead or not enabled") e o MESMO tempo (~10.8-11s) — sinal
    de que não é a complexidade da query que causa isso, e sim uma
    instabilidade real e recorrente de rede/carga no servidor `minimachine`
    (compartilhado por ~14 bancos de teste, 44+ sessões concorrentes no
    momento do teste). Como uma 2ª tentativa quase sempre resolve
    (comprovado ao vivo, repetidas vezes), a mitigação certa aqui é reter
    uma vez com conexão nova — não existe ajuste de query que eliminasse a
    causa raiz de fato."""
    tipo_dav = (tipo_dav or "").strip().upper()
    if tipo_dav not in ("PED", "OS"):
        return {"success": False, "message": "Tipo de documento inválido."}

    ultimo_erro = None
    for tentativa in range(2):
        try:
            conn = _open_conn(servidor, banco)
        except Exception as e:
            return {"success": False, "message": f"Falha conexão: {e}"}
        try:
            cur = conn.cursor(as_dict=True)
            if tipo_dav == "PED":
                cur.execute(
                    "SELECT p.pedido AS documento, p.data, p.total AS valor, "
                    "COALESCE(c.nome, p.NOME_CLIENTE) AS cliente_nome "
                    "FROM pedido_venda p "
                    "LEFT JOIN cliente c ON c.codigo = p.cliente "
                    "WHERE p.situacao = 'F' "
                    "ORDER BY p.data DESC, p.pedido DESC"
                )
            else:
                cur.execute(
                    "SELECT o.codigo AS documento, o.data_entrada AS data, "
                    "ISNULL(SUM(op.quant * op.p_venda), 0) AS valor, "
                    "c.nome AS cliente_nome "
                    "FROM os o "
                    "LEFT JOIN cliente c ON c.codigo = o.cliente "
                    "LEFT JOIN os_produto op ON op.os = o.codigo AND ISNULL(op.item_cancelado,0)=0 "
                    "WHERE o.situacao = 'F' "
                    "GROUP BY o.codigo, o.data_entrada, c.nome "
                    "ORDER BY o.data_entrada DESC, o.codigo DESC"
                )
            items = cur.fetchall()
            conn.close()
            return {"success": True, "items": items}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            ultimo_erro = e
    return {"success": False, "message": f"Erro ao listar documentos: {ultimo_erro}"}


def _importar_dav_sync(req, comanda: int) -> dict:
    """Importa um Pedido de Venda ou O.S. já Fechado pra dentro da venda do
    Checkout — réplica de `Insere_Dav` (`FrmPafOFF.frm`, F4/F8; F7/Orçamento
    não existe como caso separado nesta migração, ver nota no topo do
    módulo). Os itens entram em `movimentacao` marcados com `tipo_dav`/
    `COD_AUTO_DAV` (mesmas colunas que o legado já usa) — isso é o que
    permite bloquear cancelamento individual desses itens depois
    (`_cancelar_item_sync`), igual ao legado ("Este item pertence a um DAV
    ou Pré-Venda! Cancelamento não permitido!").

    O documento de origem é marcado como Faturado (situação='PG') e
    vinculado via `COMANDA_PED`/`COMANDA_OS` — o MESMO efeito que Faturar já
    produz pra Pedido/O.S. avulsos (`_faturar_pedido_sync`/`_faturar_os_sync`
    em pedidos_service.py/os_service.py), só que a `comanda` de destino é a
    venda do Checkout já aberta, não uma criada na hora.

    Simplificações registradas (ver PENDENCIAS.md > "Checkout" > "Fase 2"):
    itens já cancelados no documento de origem são simplesmente ignorados
    (não copiados) — o legado tem um comportamento inconsistente aqui (soma
    no total sem gravar movimentação), não replicado de propósito. Preço/
    desconto/acréscimo por item são copiados como já calculados no
    documento de origem, sem recomputar promoção/tier. Área de atuação do
    funcionário não é checada. Faturamento de O.S. com bloco Garantia/
    Interno/Contrato não é suportado — só o bloco "cliente" (os_produto.
    situacao=0) é importado."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "ADD_ITEM"):
            conn.close()
            return {"success": False, "message": "Sem permissão para importar Pedido/O.S."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada/cancelada."}

        tipo_dav = (req.tipo_dav or "").strip().upper()
        if tipo_dav not in ("PED", "OS"):
            conn.close()
            return {"success": False, "message": "Tipo de documento inválido."}

        if tipo_dav == "PED":
            cur.execute(
                "SELECT situacao, cliente, area_atuacao, vendedor FROM pedido_venda WHERE pedido=%s",
                (req.documento,),
            )
            doc = cur.fetchone()
            if not doc:
                conn.close()
                return {"success": False, "message": "Número de Pedido não cadastrado."}
            sit_doc = (doc.get("situacao") or "").strip().upper()
            if sit_doc == "PG":
                conn.close()
                return {"success": False, "message": "Este Pedido já foi faturado."}
            if sit_doc != "F":
                conn.close()
                return {"success": False, "message": "Só são permitidas vendas de Pedidos com situação Fechado."}
            cur.execute(
                "SELECT codauto, produto, qtd_pedida AS qtd, p_venda AS p_unit, p_normal AS preco_bruto, "
                "desconto, acrescimo FROM pedido_venda_prod "
                "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
                (req.documento,),
            )
            itens_doc = cur.fetchall()
            if not itens_doc:
                conn.close()
                return {"success": False, "message": "Pedido sem produtos registrados."}
            vendedor_doc = doc.get("vendedor") or 0
        else:
            cur.execute("SELECT TOP 1 comanda FROM comanda_os WHERE os=%s", (req.documento,))
            ja_vinculada = cur.fetchone()
            if ja_vinculada:
                conn.close()
                return {
                    "success": False,
                    "message": f"Esta O.S. já está vinculada à comanda nº {ja_vinculada['comanda']}. "
                               "Cancele aquela comanda antes de importar de novo.",
                }
            cur.execute("SELECT situacao, cliente, area_atuacao FROM os WHERE codigo=%s", (req.documento,))
            doc = cur.fetchone()
            if not doc:
                conn.close()
                return {"success": False, "message": "Número de O.S. não cadastrado."}
            sit_doc = (doc.get("situacao") or "").strip().upper()
            if sit_doc == "PG":
                conn.close()
                return {"success": False, "message": "Esta O.S. já foi faturada."}
            if sit_doc != "F":
                conn.close()
                return {"success": False, "message": "Só são permitidas vendas de O.S. com situação Fechado."}
            cur.execute(
                "SELECT cod_os_prod, codigo_interno AS produto, quant AS qtd, preco_unitario AS p_unit, "
                "p_venda AS preco_bruto, desconto, acrescimo, vendedor FROM os_produto "
                "WHERE os=%s AND situacao=0 AND ISNULL(item_cancelado,0)=0",
                (req.documento,),
            )
            itens_doc = cur.fetchall()
            if not itens_doc:
                conn.close()
                return {"success": False, "message": "O.S. sem produtos registrados (bloco cliente)."}
            vendedor_doc = None

        letra_dav = "P" if tipo_dav == "PED" else "O"
        usuario = req.usuario_alteracao or 0
        for it in itens_doc:
            produto_codigo = (it.get("produto") or "").strip()
            qtd = float(it.get("qtd") or 0)
            p_unit = float(it.get("p_unit") or 0)
            preco_bruto = float(it.get("preco_bruto") or p_unit)
            vendedor_item = vendedor_doc if tipo_dav == "PED" else (it.get("vendedor") or 0)
            cod_auto = int(it.get("codauto") if tipo_dav == "PED" else it.get("cod_os_prod"))

            cur.execute(
                "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, vendedor, p_unit, num_nf, serie_nf, "
                "tipo_dav, COD_AUTO_DAV, item_paga_comissao) "
                "OUTPUT INSERTED.id_mov "
                "VALUES (CONVERT(date, GETDATE()), 'S01', %s, %s, %s, %s, %s, 'CM', %s, %s, 1)",
                (produto_codigo, qtd, vendedor_item, p_unit, comanda, letra_dav, cod_auto),
            )
            id_mov = int(cur.fetchone()["id_mov"])

            desconto_unit = float(it.get("desconto") or 0)
            acrescimo_unit = float(it.get("acrescimo") or 0)
            if desconto_unit > 0:
                cur.execute(
                    "INSERT INTO comanda_desconto (comanda, codigo_int, desconto, id_mov, PRECO_BRUTO, USUARIO_DESCONTO) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (comanda, produto_codigo, desconto_unit, id_mov, preco_bruto, usuario),
                )
            if acrescimo_unit > 0:
                cur.execute(
                    "INSERT INTO comanda_acresc (comanda, codigo_int, acrescimo, id_mov, PRECO_BRUTO) VALUES (%s,%s,%s,%s,%s)",
                    (comanda, produto_codigo, acrescimo_unit, id_mov, preco_bruto),
                )

            campo_reservado = "reservado" if tipo_dav == "PED" else "reservado_os"
            _liberar_reservado(cur, produto_codigo, qtd, campo_reservado)

        if tipo_dav == "PED":
            cur.execute("INSERT INTO COMANDA_PED (comanda, ped) VALUES (%s, %s)", (comanda, req.documento))
            cur.execute("UPDATE pedido_venda SET situacao='PG' WHERE pedido=%s", (req.documento,))
        else:
            cur.execute("INSERT INTO comanda_os (comanda, os) VALUES (%s, %s)", (comanda, req.documento))
            cur.execute("UPDATE os SET situacao='PG' WHERE codigo=%s", (req.documento,))

        # Mesma regra do legado (`RegVenda.codcliente = TmpClienteDav`) —
        # o cliente do documento importado assume a venda.
        if doc.get("cliente"):
            cur.execute("UPDATE comanda SET cliente=%s WHERE comanda=%s", (doc["cliente"], comanda))

        total = _recalc_comanda_sync(cur, comanda)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "valor_venda": total, "itens_importados": len(itens_doc)}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao importar documento: {e}"}


def _list_abastecimentos_pendentes_sync(servidor: str, banco: str) -> dict:
    """Lista abastecimentos pendentes de venda — réplica de
    `Mostra_Abastecimentos`/`Recolhe_Abastecimento` (FrmPafOFF.frm).

    Hoje a tabela `abastecimento` só é populada pela integração de hardware
    Wayne Fusion (concentrador de bombas, Fase 2 — não implementada nesta
    migração, ver memória de projeto "Posto de Combustível") — esta lista
    fica vazia até essa automação existir; a tela funciona normalmente
    quando acontecer, sem precisar de mudança nenhuma aqui."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            conn.close()
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT abastecimento.num, "
            "ISNULL(NULLIF(pecas.descricao_pdv,''), pecas.descricao) AS descricao, "
            "abastecimento.preco_un, abastecimento.volume, abastecimento.valor, "
            "abastecimento.data, abastecimento.hora "
            "FROM abastecimento "
            "JOIN bomba ON bomba.ponto = abastecimento.ponto AND bomba.posicao = abastecimento.posicao "
            "JOIN pecas ON LTRIM(RTRIM(pecas.codigo_fab)) = LTRIM(RTRIM(STR(bomba.combustivel))) "
            "WHERE abastecimento.status_abastecimento = 'PENDENTE' "
            "ORDER BY abastecimento.num DESC"
        )
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _importar_abastecimento_sync(req, comanda: int) -> dict:
    """Traz 1 abastecimento PENDENTE pra dentro da venda aberta do
    Checkout — réplica de `Command10_Click` (FrmPafOFF.frm), acionado a
    partir de `Mostra_Abastecimentos`.

    Diferente do legado (que só marca a origem numa ListBox em memória,
    `ItemData=-5` — não sobrevive, não é persistido), esta migração grava
    `movimentacao.tipo_dav='ABA'` + `COD_AUTO_DAV=abastecimento.num` —
    mesmo padrão já usado por Pedido/O.S. importado (`_importar_dav_sync`)
    — pra poder bloquear cancelamento individual e reverter corretamente
    ao cancelar a venda inteira (ver `_cancelar_item_sync`/
    `_cancelar_venda_sync`). Ver "Não replicar truques VB6" em CLAUDE.md —
    o esquema do legado aqui é gambiarra de linguagem antiga, não regra de
    negócio a preservar.

    Não decrementa `pecas.qtd`: o combustível já saiu fisicamente do
    tanque (é isso que o registro de `abastecimento` representa),
    contabilizado por outro caminho (Mov. Encerrantes/Tanque-Estoque) —
    mesmo princípio já usado pra itens de DAV (estoque já contabilizado
    alhures, aqui só se registra a venda)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            conn.close()
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "ADD_ITEM"):
            conn.close()
            return {"success": False, "message": "Sem permissão para importar abastecimento."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada/cancelada."}

        cur.execute(
            "SELECT pecas.codigo_int, abastecimento.preco_un, abastecimento.volume, "
            "abastecimento.status_abastecimento "
            "FROM abastecimento "
            "JOIN bomba ON bomba.ponto = abastecimento.ponto AND bomba.posicao = abastecimento.posicao "
            "JOIN pecas ON LTRIM(RTRIM(pecas.codigo_fab)) = LTRIM(RTRIM(STR(bomba.combustivel))) "
            "WHERE abastecimento.num = %s",
            (req.num_abastecimento,),
        )
        ab = cur.fetchone()
        if not ab:
            conn.close()
            return {"success": False, "message": "Abastecimento não encontrado."}
        if (ab.get("status_abastecimento") or "").strip().upper() != "PENDENTE":
            conn.close()
            return {"success": False, "message": "Este abastecimento já foi lançado em outra venda."}

        codigo = (ab.get("codigo_int") or "").strip()
        qtd = float(ab.get("volume") or 0)
        p_unit = float(ab.get("preco_un") or 0)
        if qtd <= 0 or p_unit <= 0:
            conn.close()
            return {"success": False, "message": "Abastecimento sem quantidade/valor válidos."}

        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, vendedor, p_unit, num_nf, serie_nf, "
            "tipo_dav, COD_AUTO_DAV, item_paga_comissao) "
            "OUTPUT INSERTED.id_mov "
            "VALUES (CONVERT(date, GETDATE()), 'S01', %s, %s, %s, %s, %s, 'CM', %s, %s, 1)",
            (codigo, qtd, req.vendedor, p_unit, comanda, "ABA", req.num_abastecimento),
        )
        id_mov = int(cur.fetchone()["id_mov"])
        cur.execute(
            "UPDATE abastecimento SET status_abastecimento='EMITIDO CF' WHERE num=%s",
            (req.num_abastecimento,),
        )
        total = _recalc_comanda_sync(cur, comanda)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id_mov": id_mov, "valor_venda": total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao importar abastecimento: {e}"}


def _list_agendamentos_pendentes_sync(servidor: str, banco: str) -> dict:
    """Lista agendamentos pendentes de faturamento avulso — réplica de
    `Mostra_Agenda`/`Recolhe_Agenda` (FrmPafOFF.frm): `situacao_caixa`
    Aberto, não vinculado a Pedido/O.S. (`AGENDA_PEDIDO`/`AGENDA_OS` —
    esses são faturados só pelo próprio Pedido/O.S., nunca avulso pelo
    Checkout), situação de atendimento diferente de Desistência."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_agenda_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Agenda (Clínica/Assistência) está desativado.", "items": []}
        cur.execute(
            "SELECT a.codagenda, a.data, a.hora_ini, a.valor, "
            "COALESCE(c.fantasia, c.nome, 'Cliente Avulso') AS cliente_nome, "
            "s.descricao AS servico_descricao, "
            "COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS profissional "
            "FROM AGENDA a "
            "JOIN funcionarios f ON f.codigo_int = a.funcionario "
            "LEFT JOIN cliente c ON c.codigo = a.cliente "
            "LEFT JOIN servicos s ON s.codigo = a.servico "
            "WHERE UPPER(ISNULL(a.situacao_atendimento,'')) <> 'DESISTÊNCIA' "
            "AND ISNULL(a.situacao_caixa,'') = 'A' "
            "AND a.codagenda NOT IN (SELECT CODAGENDA FROM AGENDA_PEDIDO) "
            "AND a.codagenda NOT IN (SELECT CODAGENDA FROM AGENDA_OS) "
            "ORDER BY a.data, a.hora_ini"
        )
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _importar_agendamento_sync(req, comanda: int) -> dict:
    """Traz 1 agendamento pendente de faturamento pra dentro da venda
    aberta do Checkout — réplica de `Command19_Click` (FrmPafOFF.frm),
    acionado a partir de `Mostra_Agenda`. O item lançado é o SERVIÇO do
    próprio agendamento (qtd=1, valor=`agenda.valor`).

    Grava `movimentacao.tipo_dav='AGE'` + `COD_AUTO_DAV=codagenda` (mesmo
    padrão de `_importar_dav_sync`) e o vínculo real `agenda_comanda` —
    mesma tabela já usada por `agenda_service._faturar_avulso_sync`,
    reaproveitada aqui sem duplicar lógica de faturamento: aquela função
    fecha uma comanda NOVA de 1 item só (faturamento direto pela tela de
    Agenda); esta soma o item numa comanda JÁ aberta do Checkout, podendo
    misturar com outros produtos/serviços do mesmo cupom — mesma diferença
    de propósito que já existe entre `_faturar_pedido_sync` e
    `_importar_dav_sync`.

    Diferente do legado (`RegVenda.codcliente = agendamento.cliente`),
    esta migração NÃO troca o cliente da venda automaticamente pelo
    cliente do agendamento — trocar cliente "por baixo" silenciosamente é
    o tipo de comportamento implícito que fica melhor como escolha
    explícita do operador (usar o campo Cliente do próprio Checkout, se
    quiser)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not _modulo_agenda_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Agenda (Clínica/Assistência) está desativado."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "ADD_ITEM"):
            conn.close()
            return {"success": False, "message": "Sem permissão para importar agendamento."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada/cancelada."}

        cur.execute(
            "SELECT servico, valor, situacao_atendimento, situacao_caixa FROM AGENDA WHERE codagenda=%s",
            (req.codagenda,),
        )
        ag = cur.fetchone()
        if not ag:
            conn.close()
            return {"success": False, "message": "Agendamento não encontrado."}
        if (ag.get("situacao_caixa") or "").strip().upper() != "A":
            conn.close()
            return {"success": False, "message": "Este agendamento já foi faturado."}
        cur.execute("SELECT TOP 1 1 AS ok FROM agenda_comanda WHERE codagenda=%s", (req.codagenda,))
        if cur.fetchone():
            conn.close()
            return {"success": False, "message": "Este agendamento já foi faturado anteriormente."}

        servico = (ag.get("servico") or "").strip()
        valor = float(ag.get("valor") or 0)
        if not servico or valor <= 0:
            conn.close()
            return {"success": False, "message": "Agendamento sem serviço/valor válidos."}

        cur.execute(
            "INSERT INTO movimentacao (data, tipo, codigo_int, qtd, vendedor, p_unit, num_nf, serie_nf, "
            "tipo_dav, COD_AUTO_DAV, item_paga_comissao) "
            "OUTPUT INSERTED.id_mov "
            "VALUES (CONVERT(date, GETDATE()), 'S01', %s, 1, %s, %s, %s, 'CM', %s, %s, 1)",
            (servico, req.vendedor, valor, comanda, "AGE", req.codagenda),
        )
        id_mov = int(cur.fetchone()["id_mov"])
        cur.execute(
            "INSERT INTO agenda_comanda (codagenda, codcomanda, situacao_atendimento, ID_MOVIMENTACAO) "
            "VALUES (%s,%s,%s,%s)",
            (req.codagenda, comanda, ag.get("situacao_atendimento") or "", id_mov),
        )
        cur.execute("UPDATE AGENDA SET situacao_caixa='P' WHERE codagenda=%s", (req.codagenda,))
        total = _recalc_comanda_sync(cur, comanda)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id_mov": id_mov, "valor_venda": total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao importar agendamento: {e}"}


def _cancelar_item_sync(req, comanda: int, id_mov: int) -> dict:
    """Cancela um item já lançado — a venda ainda está Aberta (nada fiscal
    emitido), então o legado simplesmente APAGA a linha de `movimentacao`
    (`CancelaItemECF`), em vez de marcar um flag de cancelado."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "DEL_ITEM"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar item."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda não permite mais cancelar itens."}
        cur.execute("SELECT codigo_int, qtd, tipo_dav FROM movimentacao WHERE id_mov=%s AND num_nf=%s AND serie_nf='CM'", (id_mov, comanda))
        item = cur.fetchone()
        if not item:
            conn.close()
            return {"success": False, "message": "Item não encontrado."}
        if (item.get("tipo_dav") or "").strip():
            conn.close()
            return {
                "success": False,
                "message": "Este item veio de outra origem (Pedido/O.S./Abastecimento/Agendamento) importada — "
                            "cancelamento individual não permitido. Cancele a venda inteira se precisar desfazer.",
            }
        # Nota: o legado só libera cancelar item sem senha de gerente quando
        # `Permite_Item_Cancelamento` (flag por função do atendente) está
        # ligado — não modelado nesta fase; o gate real aqui é a permissão
        # de grupo `DEL_ITEM` já checada acima (mesmo princípio de
        # "permissão de grupo no lugar de senha de gerente" já usado em
        # `pedidos_service._cancelar_pedido_sync`). Ver PENDENCIAS.md.
        cur.execute("DELETE FROM comanda_desconto WHERE id_mov=%s", (id_mov,))
        cur.execute("DELETE FROM comanda_acresc WHERE id_mov=%s", (id_mov,))
        cur.execute("DELETE FROM movimentacao WHERE id_mov=%s", (id_mov,))
        _mover_estoque_direto(cur, (item.get("codigo_int") or "").strip(), -float(item.get("qtd") or 0))
        total = _recalc_comanda_sync(cur, comanda)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "valor_venda": total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar item: {e}"}


# ---------------------------------------------------------------------------
# Desconto geral / cliente
# ---------------------------------------------------------------------------

def _desconto_geral_sync(req, comanda: int) -> dict:
    """Desconto Geral da Venda — réplica simplificada de
    `ProcessaDescontoGeral`: redistribui o percentual proporcionalmente
    entre os itens ainda lançados, sem zerar/negativar nenhum item (mesma
    regra do legado). Simplificação registrada em PENDENCIAS.md: não
    replica o loop de ajuste centavo-a-centavo nem o "joga a sobra no maior
    item" do legado — a soma pode divergir em poucos centavos do valor
    'redondo' pedido; o usuário pode reajustar manualmente se precisar de
    exatidão."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "DESC_GERAL"):
            conn.close()
            return {"success": False, "message": "Sem permissão para desconto geral."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda não permite mais desconto geral."}
        pct = float(req.desconto_percentual or 0)
        if pct <= 0:
            conn.close()
            return {"success": False, "message": "Informe um percentual de desconto maior que zero."}
        cur.execute("SELECT desconto_pdv_gerente, desconto_pdv_supervisor, desconto_pdv_vendedor FROM controle")
        c = cur.fetchone() or {}
        limite = {
            1: float(c.get("desconto_pdv_gerente") or 0),
            2: float(c.get("desconto_pdv_supervisor") or 0),
            4: float(c.get("desconto_pdv_supervisor") or 0),
        }.get(req.funcao, float(c.get("desconto_pdv_vendedor") or 0))
        if pct > limite and not req.autorizado_por:
            conn.close()
            return {"success": False, "message": "Desconto maior que o permitido!"}
        cur.execute("SELECT id_mov, codigo_int, qtd, p_unit FROM movimentacao WHERE num_nf=%s AND serie_nf='CM'", (comanda,))
        itens = cur.fetchall()
        if not itens:
            conn.close()
            return {"success": False, "message": "Nenhum item lançado."}
        usuario = req.autorizado_por or req.usuario_alteracao or 0
        for it in itens:
            qtd = float(it["qtd"] or 0)
            p_unit_atual = float(it["p_unit"] or 0)
            if qtd <= 0:
                continue
            desconto_total_item = round(qtd * p_unit_atual * pct / 100, 2)
            desconto_unit = round(desconto_total_item / qtd, 2)
            novo_p_unit = p_unit_atual - desconto_unit
            if novo_p_unit <= 0:
                continue
            cur.execute("UPDATE movimentacao SET p_unit=%s WHERE id_mov=%s", (novo_p_unit, it["id_mov"]))
            cur.execute(
                "INSERT INTO comanda_desconto (comanda, codigo_int, desconto, id_mov, PRECO_BRUTO, USUARIO_DESCONTO) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (comanda, it["codigo_int"], desconto_unit, it["id_mov"], p_unit_atual, usuario),
            )
        total = _recalc_comanda_sync(cur, comanda)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "valor_venda": total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao aplicar desconto geral: {e}"}


def _definir_cliente_sync(req, comanda: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada/cancelada."}
        cliente = req.cliente or _cliente_diversos(cur)
        cur.execute("UPDATE comanda SET cliente=%s WHERE comanda=%s", (cliente, comanda))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao definir cliente: {e}"}


# ---------------------------------------------------------------------------
# Fechar / cancelar venda
# ---------------------------------------------------------------------------

def _fechar_venda_sync(req, comanda: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "FECHAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar a venda."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada/cancelada."}
        cur.execute("SELECT COUNT(*) AS c FROM movimentacao WHERE num_nf=%s AND serie_nf='CM'", (comanda,))
        if int(cur.fetchone()["c"] or 0) == 0:
            conn.close()
            return {"success": False, "message": "Valor Total de Venda Zerado! Impossível prosseguir!"}
        cur.execute("SELECT valor_venda FROM comanda WHERE comanda=%s", (comanda,))
        total_devido = float(cur.fetchone()["valor_venda"] or 0)

        if not req.formas:
            conn.close()
            return {"success": False, "message": "Defina a Forma de Pagamento corretamente!"}

        total_pago = 0.0
        codvales_usados: set = set()
        cartoes_usados: set = set()
        # Guarda o resultado já validado de cada linha (índice alinhado com
        # req.formas) pra reaproveitar no laço de gravação abaixo — evita
        # reconsultar e evita que a checagem de duplicidade na mesma venda
        # perca o efeito (o segundo laço não repete a validação sozinho).
        info_cartao_por_forma: list = [None] * len(req.formas)
        vale_por_forma: list = [None] * len(req.formas)
        for idx, forma in enumerate(req.formas):
            tipo = (forma.tipo or "").strip().upper()
            valor = float(forma.valor or 0)
            if valor <= 0:
                conn.close()
                return {"success": False, "message": "Informe um valor maior que zero."}
            if tipo == TIPO_CARTAO_PRESENTE:
                ok, erro, info = _validar_cartao_presente(cur, forma.codigo_cartao_presente, valor, cartoes_usados)
                if not ok:
                    conn.close()
                    return {"success": False, "message": erro}
                cartoes_usados.add((forma.codigo_cartao_presente or "").strip())
                info_cartao_por_forma[idx] = info
                total_pago += valor
                continue
            if tipo not in FORMA_PAG_SUFIXO_TIPO:
                conn.close()
                return {"success": False, "message": f"Tipo de forma de pagamento inválido: {tipo}"}
            if not (forma.forma_pag or "").strip():
                conn.close()
                return {"success": False, "message": "Selecione a forma de pagamento."}
            # Crivo de Administradora/Parcelador (`_verifica_parcelamento_cartao`)
            # DESATIVADO nesta versão — pedido explícito do usuário, 2026-08-06
            # ("não fazer o crivo da administradora e parcelador nessa
            # versão"). Os campos continuam existindo (gravados como vierem,
            # inclusive vazios) — só a validação bloqueante foi removida. A
            # função em si não foi apagada, só parou de ser chamada aqui, pra
            # facilitar reativar depois se for pedido.
            if forma.codigo_vale_devolucao and tipo in ("DI", "DU", "VA"):
                ok, erro, vale = _validar_vale_devolucao(cur, forma.codigo_vale_devolucao, valor, codvales_usados)
                if not ok:
                    conn.close()
                    return {"success": False, "message": erro}
                codvales_usados.add(forma.codigo_vale_devolucao)
                vale_por_forma[idx] = vale
            total_pago += valor

        if total_pago + 0.005 < total_devido:
            falta = round(total_devido - total_pago, 2)
            conn.close()
            return {"success": False, "message": f"Falta R$ {falta:.2f} para completar o pagamento."}

        for idx, forma in enumerate(req.formas):
            tipo = (forma.tipo or "").strip().upper()
            if tipo == TIPO_CARTAO_PRESENTE:
                # Já validado (existe, saldo suficiente, sem duplicidade na
                # mesma venda) no laço acima — reaproveita o resultado, não
                # reconsulta. Ao portador — não checa cliente.
                _consumir_cartao_presente(cur, info_cartao_por_forma[idx], comanda, float(forma.valor))
                continue
            tabela = _cmd_tabela(tipo)
            col = _CMD_VALOR_COL[tipo]
            venc_col = _CMD_VENC_COL[tipo]
            campos = ["comanda", "forma_pag", col]
            valores: list = [comanda, forma.forma_pag, forma.valor]
            if venc_col:
                campos.append(venc_col)
                valores.append(forma.vencimento or None)
            if tipo == "CH":
                campos += ["banco", "agencia", "conta", "numero_ch", "telefone", "nome_cheque"]
                valores += [forma.cod_banco, forma.agencia, forma.conta, forma.numero_ch, forma.telefone, forma.nome_cheque]
            elif tipo == "CC":
                campos += ["num_cartao1", "num_cartao2", "num_cartao3", "num_cartao4", "mes_validade",
                           "ano_validade", "Parcelas", "COD_ADMINISTRADORA", "COD_PARCELADOR"]
                valores += [forma.num_cartao1, forma.num_cartao2, forma.num_cartao3, forma.num_cartao4,
                            forma.mes_validade, forma.ano_validade, forma.parcelas, forma.cod_administradora, forma.cod_parcelador]
            elif tipo == "CD":
                campos += ["banco", "agencia", "conta", "Parcelas", "COD_ADMINISTRADORA", "COD_PARCELADOR"]
                valores += [forma.cod_banco, forma.agencia, forma.conta, forma.parcelas, forma.cod_administradora, forma.cod_parcelador]
            placeholders = ",".join(["%s"] * len(valores))
            cur.execute(f"INSERT INTO {tabela} ({','.join(campos)}) VALUES ({placeholders})", tuple(valores))

            if vale_por_forma[idx] is not None:
                _consumir_vale_devolucao(cur, vale_por_forma[idx], comanda, float(forma.valor), tipo)

        troco = round(total_pago - total_devido, 2)
        if troco > 0.004:
            cur.execute("INSERT INTO TROCO_COMANDA (comanda, valor_troco) VALUES (%s,%s)", (comanda, troco))

        cur.execute("UPDATE comanda SET situacao='PG' WHERE comanda=%s", (comanda,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "comanda": comanda, "total_pago": round(total_pago, 2), "troco": max(troco, 0)}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar venda: {e}"}


def _cancelar_venda_sync(req, comanda: int) -> dict:
    """Cancela a venda inteira (`CancelaVenda`/`CancelaCupom`) — só permitido
    enquanto Aberta (nada fiscal emitido ainda; cancelar uma venda já Fechada/
    Faturada/com NFC-e é papel do Gestor de Comandas, que já sabe reverter
    protocolo SEFAZ e as 8 tabelas de pagamento). Mantém a linha de `comanda`
    (situacao='C', valor_venda=0 — mesmo padrão final de
    `comanda_service._cancelar_comanda_sync`), pra manter o histórico/
    auditoria, em vez de apagar o registro.

    Itens vindos de importação de DAV (`tipo_dav` preenchido, ver
    `_importar_dav_sync`) são revertidos de forma diferente dos itens
    diretos: o estoque desses itens já foi baixado quando o Pedido/O.S. de
    origem foi Fechado (não na importação em si, que só libera a reserva) —
    cancelar aqui precisa DEVOLVER a reserva (`reservado`/`reservado_os`),
    não mexer em `pecas.qtd`, e reverter o próprio Pedido/O.S. de volta pra
    Fechado (`situacao='F'`) + remover o vínculo `COMANDA_PED`/`comanda_os`.
    Mantém a decisão já tomada na Fase 1 de gerenciar estoque explicitamente
    em código (o legado deixa o equivalente comentado/incompleto em
    `CancelaCupom` — não replicado)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "CANCELAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar a venda."}
        situacao = _situacao_comanda(cur, comanda)
        if situacao is None:
            conn.close()
            return {"success": False, "message": "Venda não encontrada."}
        if situacao != "A":
            conn.close()
            return {"success": False, "message": "Esta venda já foi fechada — cancele pelo Gestor de Comandas."}
        cur.execute(
            "SELECT codigo_int, qtd, tipo_dav, COD_AUTO_DAV FROM movimentacao WHERE num_nf=%s AND serie_nf='CM'",
            (comanda,),
        )
        itens = cur.fetchall()
        for it in itens:
            codigo = (it.get("codigo_int") or "").strip()
            qtd = float(it.get("qtd") or 0)
            origem = (it.get("tipo_dav") or "").strip().upper()
            cod_auto = it.get("COD_AUTO_DAV")
            if not origem:
                _mover_estoque_direto(cur, codigo, -qtd)
            elif origem == "P":
                _liberar_reservado(cur, codigo, -qtd, "reservado")
            elif origem == "O":
                _liberar_reservado(cur, codigo, -qtd, "reservado_os")
            elif origem == "ABA":
                # Abastecimento: volta a ficar disponível pra ser lançado
                # em outra venda — não mexe em `pecas.qtd` (nunca foi
                # decrementado por este caminho, ver `_importar_
                # abastecimento_sync`).
                cur.execute(
                    "UPDATE abastecimento SET status_abastecimento='PENDENTE' WHERE num=%s",
                    (cod_auto,),
                )
            elif origem == "AGE":
                # Agenda: desfaz o vínculo de faturamento, libera o
                # agendamento pra ser faturado de novo (por aqui ou pela
                # própria tela de Agenda).
                cur.execute("DELETE FROM agenda_comanda WHERE codagenda=%s", (cod_auto,))
                cur.execute("UPDATE AGENDA SET situacao_caixa='A' WHERE codagenda=%s", (cod_auto,))
        cur.execute(
            "DELETE FROM comanda_desconto WHERE id_mov IN (SELECT id_mov FROM movimentacao WHERE num_nf=%s AND serie_nf='CM')",
            (comanda,),
        )
        cur.execute(
            "DELETE FROM comanda_acresc WHERE id_mov IN (SELECT id_mov FROM movimentacao WHERE num_nf=%s AND serie_nf='CM')",
            (comanda,),
        )
        cur.execute("UPDATE pedido_venda SET situacao='F' WHERE pedido IN (SELECT ped FROM COMANDA_PED WHERE comanda=%s)", (comanda,))
        cur.execute("UPDATE os SET situacao='F' WHERE codigo IN (SELECT os FROM comanda_os WHERE comanda=%s)", (comanda,))
        cur.execute("DELETE FROM COMANDA_PED WHERE comanda=%s", (comanda,))
        cur.execute("DELETE FROM comanda_os WHERE comanda=%s", (comanda,))
        cur.execute("DELETE FROM movimentacao WHERE num_nf=%s AND serie_nf='CM'", (comanda,))
        cur.execute(
            "INSERT INTO cancelamento (comanda, cupom, usuario, data, hora, motivo) "
            "VALUES (%s, 0, %s, CONVERT(date, GETDATE()), CONVERT(varchar(8), GETDATE(), 108), %s)",
            (comanda, req.usuario_alteracao or 0, req.motivo or ""),
        )
        cur.execute("UPDATE comanda SET situacao='C', valor_venda=0 WHERE comanda=%s", (comanda,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar venda: {e}"}


# ---------------------------------------------------------------------------
# Cartões — administradoras/parcelas (lookups pro fechamento)
# ---------------------------------------------------------------------------

def _list_administradoras_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_administradora AS codigo, descricao_administradora AS descricao "
            "FROM cartoes_administradoras WHERE ISNULL(situacao,'A')='A' ORDER BY descricao_administradora"
        )
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _list_parcelas_sync(servidor: str, banco: str, administradora: int, bandeira: str, parcelador: str) -> dict:
    """Lista as parcelas cadastradas pra (administradora, bandeira) quando o
    parcelamento é pela Loja (`cartoes_configuracoes_recebimento`) — no modo
    Administradora o legado não limita por parcela (ver
    `_verifica_parcelamento_cartao`), então devolve lista vazia (frontend
    aceita qualquer nº de parcelas nesse modo)."""
    if (parcelador or "").strip().upper() != "L":
        return {"success": True, "items": []}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_parcela FROM cartoes_configuracoes cc "
            "JOIN cartoes_configuracoes_recebimento r ON r.cod_cartoes_configuracao = cc.cod_cartoes_configuracao "
            "WHERE cc.cod_administradora=%s AND cc.cod_bandeira=%s AND cc.cod_parcelador='L' "
            "ORDER BY cod_parcela",
            (administradora, bandeira),
        )
        items = [int(r["cod_parcela"]) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


# ---------------------------------------------------------------------------
# Wrappers async
# ---------------------------------------------------------------------------

async def abrir_venda(req) -> dict:
    return await asyncio.to_thread(_abrir_venda_sync, req)


async def get_venda(servidor: str, banco: str, comanda: int) -> dict:
    return await asyncio.to_thread(_get_venda_sync, servidor, banco, comanda)


async def buscar_produto(servidor: str, banco: str, codigo: str, qtd: float = 1) -> dict:
    return await asyncio.to_thread(_buscar_produto_sync, servidor, banco, codigo, qtd)


async def add_item(req, comanda: int) -> dict:
    return await asyncio.to_thread(_add_item_sync, req, comanda)


async def list_dav_pendentes(servidor: str, banco: str, tipo_dav: str) -> dict:
    return await asyncio.to_thread(_list_dav_pendentes_sync, servidor, banco, tipo_dav)


async def importar_dav(req, comanda: int) -> dict:
    return await asyncio.to_thread(_importar_dav_sync, req, comanda)


async def list_abastecimentos_pendentes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_abastecimentos_pendentes_sync, servidor, banco)


async def importar_abastecimento(req, comanda: int) -> dict:
    return await asyncio.to_thread(_importar_abastecimento_sync, req, comanda)


async def list_agendamentos_pendentes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_agendamentos_pendentes_sync, servidor, banco)


async def importar_agendamento(req, comanda: int) -> dict:
    return await asyncio.to_thread(_importar_agendamento_sync, req, comanda)


async def cancelar_item(req, comanda: int, id_mov: int) -> dict:
    return await asyncio.to_thread(_cancelar_item_sync, req, comanda, id_mov)


async def desconto_geral(req, comanda: int) -> dict:
    return await asyncio.to_thread(_desconto_geral_sync, req, comanda)


async def definir_cliente(req, comanda: int) -> dict:
    return await asyncio.to_thread(_definir_cliente_sync, req, comanda)


async def fechar_venda(req, comanda: int) -> dict:
    return await asyncio.to_thread(_fechar_venda_sync, req, comanda)


async def cancelar_venda(req, comanda: int) -> dict:
    return await asyncio.to_thread(_cancelar_venda_sync, req, comanda)


async def list_administradoras(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_administradoras_sync, servidor, banco)


async def list_parcelas(servidor: str, banco: str, administradora: int, bandeira: str, parcelador: str) -> dict:
    return await asyncio.to_thread(_list_parcelas_sync, servidor, banco, administradora, bandeira, parcelador)
