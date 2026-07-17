"""Helpers de baixo nível compartilhados pelos serviços de itens e descontos.

Todas as funções recebem um cursor (`cur`) já aberto — não abrem conexão.
Mantidas em módulo próprio para evitar import circular entre itens_service e
descontos_service.
"""
from dataclasses import dataclass
from typing import Optional

from services.constants import STATUS_CLIENTE_LABEL


def _check_cliente_ativo(cur, cliente_codigo: int) -> tuple[bool, str]:
    """Bloqueia nova movimentação (Pedido/O.S.) para cliente com STATUS_CLIENTE
    diferente de 'A' (Ativo). Cliente sem status definido (NULL/'') é tratado
    como Ativo (dado legado, coluna sem valor). Retorna (permitido, label)."""
    cur.execute("SELECT STATUS_CLIENTE FROM cliente WHERE codigo=%s", (cliente_codigo,))
    row = cur.fetchone()
    status = ((row.get("STATUS_CLIENTE") if row else None) or "").strip().upper()
    if not status or status == "A":
        return True, ""
    return False, STATUS_CLIENTE_LABEL.get(status, status)


def _item_total(qtd, pv) -> float:
    # p_venda já é o preço líquido unitário (= p_normal - desconto + acrescimo)
    return round(float(qtd or 0) * float(pv or 0), 2)


def _recalc_pedido_total(cur, pedido: int) -> float:
    cur.execute(
        "UPDATE pedido_venda SET total = ISNULL(("
        "  SELECT SUM(qtd_pedida * p_venda) "
        "  FROM pedido_venda_prod WHERE pedido=%s AND ISNULL(item_cancelado,0)=0"
        "), 0) WHERE pedido=%s",
        (pedido, pedido),
    )
    cur.execute("SELECT total FROM pedido_venda WHERE pedido=%s", (pedido,))
    r = cur.fetchone()
    return float((r.get("total") if isinstance(r, dict) else (r[0] if r else 0)) or 0)


def _check_pedido_aberto(cur, pedido: int) -> tuple[bool, str]:
    """Retorna (existe, situacao). Não levanta exceção."""
    cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
    row = cur.fetchone()
    if not row:
        return (False, "")
    return (True, (row.get("situacao") or "").strip().upper())


def _ensure_hora_inclusao_item_col(cur) -> None:
    """Migração idempotente: coluna `hora_inclusao_item` em `pedido_venda_prod`
    (hora de inclusão do item, formato HH:MM:SS via CONVERT(...,108) — mesmo
    padrão já usado em `pedido_venda.hora_aberto`). `data_inclusao_item` já
    existe na tabela desde o legado; só a hora é nova.

    Adicionada sob demanda (checa `sys.columns` e só faz ALTER TABLE se
    faltar) porque este backend atende múltiplas empresas — um `servidor`+
    `banco` por conexão — sem um executor de migração central. Mesmo padrão
    já usado em `services/whatsapp/repository.py::ensure_tables`."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='hora_inclusao_item' AND Object_ID=Object_ID('pedido_venda_prod')) "
        "ALTER TABLE pedido_venda_prod ADD hora_inclusao_item NVARCHAR(8) NULL"
    )


def _modulo_servicos_ativo(cur) -> bool:
    """True se o módulo "Serviço" está ligado em Configurações de Módulo do
    Sistema (controle_configuracao.servicos). Cadastro/consulta/movimentação
    de Serviço só é permitido com o módulo ativo — usado para bloquear a
    inclusão de item do tipo Serviço em Pedido/O.S. quando desligado."""
    cur.execute("SELECT TOP 1 servicos FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("servicos") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def _resolve_produto(cur, codigo: str) -> Optional[dict]:
    """Procura primeiro em pecas, depois em servicos. Retorna dados padrão do item."""
    cur.execute(
        "SELECT codigo_int AS codigo, descricao, codigo_fab, p_venda AS valor, uni, "
        "       custo_reposicao, tipo_peca FROM pecas WHERE codigo_int=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        return {
            "tipo": "P",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo_fab") or "").strip(),
            "valor": float(r.get("valor") or 0),
            "unidade": (r.get("uni") or "").strip()[:2] or "UN",
            "custo": float(r.get("custo_reposicao") or 0),
            # Finalidade (Cozinha/Bebidas/Materiais, etc.) — usada pra decidir
            # impressão automática de item por grupo de produto (ver
            # project_impressao_automatica_finalidade). None se não definida.
            "tipo_peca": int(r["tipo_peca"]) if r.get("tipo_peca") is not None else None,
        }
    cur.execute(
        "SELECT codigo, descricao, valor_hora AS valor FROM servicos WHERE codigo=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        valor = float(r.get("valor") or 0)
        return {
            "tipo": "S",
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo") or "").strip(),
            "valor": valor,
            "unidade": "HR",
            "custo": valor,  # serviço: custo = valor_hora (regra de negócio)
            "tipo_peca": None,  # Finalidade é coluna só de pecas — serviço nunca tem.
        }
    return None



def _resolve_produto_completo(cur, codigo: str) -> Optional[dict]:
    """Cadeia de resolução mais rica usada pelo Pedido Completo (web),
    espelhando `frmmanpedfor.frm`: Serviço (se prefixo 'S') -> pecas.codigo_fab
    -> pecas.codigo_int -> pecas.codigo_bar -> CODBARRA_AUXILIAR (códigos de
    barra secundários) -> Serviço (sem prefixo, fallback final).

    Deliberadamente uma função NOVA, não uma alteração de `_resolve_produto`
    — aquela é usada pelo fluxo rápido mobile (Pedido/O.S.) já em uso, e essa
    cadeia mais rica não deve mudar o comportamento de telas já em produção.
    Ver PENDENCIAS.md > "Transações" > "Pedido Completo" pro rastreio de onde
    essa cadeia vem (`Campo1_LostFocus`/`Campo_KeyPress` em frmmanpedfor.frm).
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return None

    if codigo.upper().startswith("S"):
        cur.execute("SELECT codigo, descricao, valor_hora AS valor FROM servicos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        if r:
            valor = float(r.get("valor") or 0)
            return {
                "tipo": "S", "codigo": (r.get("codigo") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "cod_fab": (r.get("codigo") or "").strip(), "valor": valor,
                "unidade": "HR", "custo": valor, "controla_num_serie": False,
            }

    for coluna in ("codigo_fab", "codigo_int", "codigo_bar"):
        cur.execute(
            f"SELECT codigo_int AS codigo, descricao, codigo_fab, p_venda AS valor, uni, "
            f"       custo_reposicao, controla_num_serie, aceita_desconto "
            f"FROM pecas WHERE {coluna}=%s",
            (codigo,),
        )
        r = cur.fetchone()
        if r:
            return _linha_peca_completo(r)

    cur.execute(
        "SELECT p.codigo_int AS codigo, p.descricao, p.codigo_fab, p.p_venda AS valor, p.uni, "
        "       p.custo_reposicao, p.controla_num_serie, p.aceita_desconto "
        "FROM CODBARRA_AUXILIAR cb JOIN pecas p ON p.codigo_int = cb.codigo_int WHERE cb.codigo_bar=%s",
        (codigo,),
    )
    r = cur.fetchone()
    if r:
        return _linha_peca_completo(r)

    cur.execute("SELECT codigo, descricao, valor_hora AS valor FROM servicos WHERE codigo=%s", (codigo,))
    r = cur.fetchone()
    if r:
        valor = float(r.get("valor") or 0)
        return {
            "tipo": "S", "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "cod_fab": (r.get("codigo") or "").strip(), "valor": valor,
            "unidade": "HR", "custo": valor, "controla_num_serie": False,
        }
    return None


def _linha_peca_completo(r: dict) -> dict:
    return {
        "tipo": "P",
        "codigo": (r.get("codigo") or "").strip(),
        "descricao": (r.get("descricao") or "").strip(),
        "cod_fab": (r.get("codigo_fab") or "").strip(),
        "valor": float(r.get("valor") or 0),
        "unidade": (r.get("uni") or "").strip()[:2] or "UN",
        "custo": float(r.get("custo_reposicao") or 0),
        "controla_num_serie": bool(r.get("controla_num_serie")),
        "aceita_desconto": r.get("aceita_desconto") is None or bool(r.get("aceita_desconto")),
    }


def _kit_componentes(cur, codigo_principal: str) -> list:
    """Componentes de um kit/produto composto (`produtos_compostos.principal`).

    Mesma tabela já usada por Serviços > Previsão de Produtos
    (`produtos_compostos_service.py`, ported de FrmManReceita.frm) — no
    legado essa tabela serve os dois propósitos (previsão de material em
    Serviço, e expansão de kit em Pedido); aqui é o segundo uso, novo nesta
    migração. `produtos_compostos` não tem coluna de custo própria — o custo
    de cada componente vem do próprio cadastro do produto (`pecas.
    custo_reposicao`), resolvido via `_resolve_produto_completo`.
    """
    cur.execute(
        "SELECT vinculado, qtd, valor_no_kit, descricao_no_kit FROM produtos_compostos WHERE principal=%s",
        (codigo_principal,),
    )
    return [dict(r) for r in cur.fetchall()]


def _is_peca(cur, codigo: str) -> bool:
    """True se o código pertence a uma peça (movimenta estoque)."""
    cur.execute("SELECT 1 AS ok FROM pecas WHERE codigo_int=%s", (codigo,))
    return cur.fetchone() is not None


def _mover_estoque(cur, codigo: str, delta_qtd: float, campo_reservado: str) -> None:
    """Movimenta o estoque de uma PEÇA dentro da transação corrente.

    Efeito: pecas.qtd -= delta_qtd ; pecas.<campo_reservado> += delta_qtd.
    `campo_reservado` deve ser 'reservado' (Pedido) ou 'reservado_os' (O.S.).
    Não faz nada para serviços/itens inexistentes. delta_qtd pode ser negativo
    (estorno ao remover/reduzir item).
    """
    if campo_reservado not in ("reservado", "reservado_os"):
        raise ValueError("campo_reservado inválido")
    if not delta_qtd or not _is_peca(cur, codigo):
        return
    cur.execute(
        f"UPDATE pecas SET qtd = ISNULL(qtd,0) - %s, "
        f"{campo_reservado} = ISNULL({campo_reservado},0) + %s "
        f"WHERE codigo_int=%s",
        (delta_qtd, delta_qtd, codigo),
    )


# Forma de Pagamento (FrmForPag.frm + FormaPagamentoDAV.bas) — tela
# genérica no legado, reaproveitada por Pedido, O.S. e Agenda via uma
# struct global só (`Type_FormaPagPedOS` — Tipo/Documento/Situacao/valor/
# Forma_Padrao). Portamos o mesmo desenho: um "tipo de DAV" central
# (DAV_PED/DAV_OS) mapeando pra onde os dados vivem — mesmo padrão já usado
# em `gestor_documentos_service.py` (`GRUPO_*`/`_JUNCAO`) pra grupo de
# anexos. Agenda (AGE) não está em uso em nenhuma tela migrada — não
# incluído no mapa; adicionar quando/se for pedido.
DAV_PED = "PED"
DAV_OS = "OS"

# tipo de DAV -> prefixo das tabelas de forma de pagamento + coluna FK.
DAV_CONFIG: dict[str, dict[str, str]] = {
    DAV_PED: {"prefixo": "pedido_venda_", "fk": "pedido_venda"},
    DAV_OS: {"prefixo": "os_", "fk": "os"},
}

# tipo de forma de pagamento (`forma_pagamento.tipo`) -> sufixo de tabela +
# coluna de valor + coluna de vencimento (None = sem vencimento). Sufixo e
# colunas são idênticos entre pedido_venda_* e os_* (mesmo schema, só o
# prefixo/FK mudam) — confirmado ao vivo em `gibanweb.database.windows.net/
# BDREACTAPP` antes de escrever este código.
FORMA_PAG_SUFIXO_TIPO: dict[str, str] = {
    "DI": "dinheiro", "CH": "cheque", "CC": "cartao", "CD": "debito",
    "DU": "duplicata", "TI": "ticket", "VA": "vale", "FI": "financiado",
}
FORMA_PAG_VALOR_COL: dict[str, str] = {
    "DI": "valor_pago", "CH": "valor", "CC": "valor", "CD": "valor",
    "DU": "valor_pag", "TI": "valor", "VA": "valor", "FI": "valor_pag",
}
FORMA_PAG_VENC_COL: dict[str, Optional[str]] = {
    "DI": None, "CH": "bom_para", "CC": "bom_para", "CD": "bom_para",
    "DU": "data_venc", "TI": None, "VA": "bom_para", "FI": "data_venc",
}


@dataclass
class DavPagamento:
    """Réplica do `Type_FormaPagPedOS` global do legado (`mdl_proc.bas`) —
    contexto genérico de "um documento que tem forma de pagamento". Toda a
    lógica de totalização/validação abaixo recebe esse objeto em vez de
    parâmetros soltos, pra funcionar igual pra Pedido e O.S. sem duplicar
    código por tela."""
    tipo: str          # DAV_PED ou DAV_OS
    documento: int      # pedido_venda.pedido OU os.codigo
    situacao: str
    valor: float         # subtotal/total do documento
    forma_padrao: str    # forma_pagamento.codigo escolhida no combobox simples do cabeçalho (pode ser "")

    def tabela(self, tipo_forma: str) -> str:
        return DAV_CONFIG[self.tipo]["prefixo"] + FORMA_PAG_SUFIXO_TIPO[tipo_forma]

    @property
    def fk(self) -> str:
        return DAV_CONFIG[self.tipo]["fk"]


def _totaliza_dav(cur, dav: DavPagamento) -> float:
    """Soma o valor lançado em TODAS as tabelas de forma de pagamento do
    documento — réplica de `TotalizaDav`/`TotalFPDAV` (FormaPagamentoDAV.bas
    / FrmForPag.frm)."""
    total = 0.0
    for tipo_forma, col in FORMA_PAG_VALOR_COL.items():
        cur.execute(f"SELECT SUM({col}) AS s FROM {dav.tabela(tipo_forma)} WHERE {dav.fk}=%s", (dav.documento,))
        r = cur.fetchone()
        total += float((r.get("s") if r else None) or 0)
    return round(total, 2)


def _qtd_formas(cur, dav: DavPagamento) -> int:
    """Conta quantas linhas de forma de pagamento (somando as 8 tabelas)
    existem pro documento — réplica de `QtdFormas`."""
    qtd = 0
    for tipo_forma in FORMA_PAG_SUFIXO_TIPO:
        cur.execute(f"SELECT COUNT(*) AS c FROM {dav.tabela(tipo_forma)} WHERE {dav.fk}=%s", (dav.documento,))
        r = cur.fetchone()
        qtd += int((r.get("c") if r else None) or 0)
    return qtd


def _unica_forma_existente(cur, dav: DavPagamento) -> Optional[tuple[str, int]]:
    """Retorna (tipo, sequencia) da forma de pagamento se existir EXATAMENTE
    uma linha lançada pro documento (somando as 8 tabelas), ou None caso
    contrário (0 ou 2+ linhas)."""
    encontrados: list[tuple[str, int]] = []
    for tipo_forma in FORMA_PAG_SUFIXO_TIPO:
        cur.execute(f"SELECT sequencia FROM {dav.tabela(tipo_forma)} WHERE {dav.fk}=%s", (dav.documento,))
        for r in cur.fetchall():
            encontrados.append((tipo_forma, int(r.get("sequencia"))))
            if len(encontrados) > 1:
                return None
    return encontrados[0] if len(encontrados) == 1 else None


def _atualiza_valor_forma(cur, dav: DavPagamento, tipo_forma: str, sequencia: int, valor: float) -> None:
    col = FORMA_PAG_VALOR_COL[tipo_forma]
    cur.execute(f"UPDATE {dav.tabela(tipo_forma)} SET {col}=%s WHERE sequencia=%s", (valor, sequencia))


def _insere_duplicata_parcelada(cur, dav: DavPagamento, forma_pag: str, valor: float) -> None:
    """Insere 1+ linhas na tabela de duplicata do documento — se a forma de
    pagamento tem prazos cadastrados em `forma_pag_prazo`, rateia o valor
    por `percentual` (1 linha por prazo, vencimento = hoje + prazo, última
    parcela absorve o arredondamento). Sem prazo cadastrado, insere 1 linha
    só com vencimento hoje (a grade de rateio manual do legado, `FrmFaturado`,
    não foi portada — ver PENDENCIAS.md, o usuário ajusta o vencimento
    editando a linha depois). Réplica do `Case "DU"` em `Command5_Click`/
    `CadastraFPAutomatica` (FrmForPag.frm)."""
    tabela = dav.tabela("DU")
    cur.execute(
        "SELECT prazo, percentual FROM forma_pag_prazo WHERE forma_pag=%s ORDER BY prazo",
        (forma_pag,),
    )
    prazos = cur.fetchall()
    if not prazos:
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, valor_pag, data_venc) "
            f"VALUES (%s, %s, %s, CONVERT(date, GETDATE()))",
            (dav.documento, forma_pag, valor),
        )
        return
    restante = valor
    for i, p in enumerate(prazos):
        pct = float(p.get("percentual") or 0)
        prazo_dias = int(p.get("prazo") or 0)
        parcela = round(restante, 2) if i == len(prazos) - 1 else round(valor * pct / 100, 2)
        restante -= parcela
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, valor_pag, data_venc) "
            f"VALUES (%s, %s, %s, DATEADD(day, %s, CONVERT(date, GETDATE())))",
            (dav.documento, forma_pag, parcela, prazo_dias),
        )


def _cadastra_forma_automatica(cur, dav: DavPagamento, forma_pag: str, valor: float) -> None:
    """Lança automaticamente `valor` na forma de pagamento padrão (combobox
    simples do cabeçalho) quando nenhuma forma ainda foi lançada
    manualmente — réplica de `CadastraDavFormaPagamento`/`CadastraFPAutomatica`."""
    cur.execute("SELECT tipo FROM forma_pagamento WHERE codigo=%s", (forma_pag,))
    row = cur.fetchone()
    tipo_forma = ((row.get("tipo") if row else None) or "").strip().upper()
    if tipo_forma not in FORMA_PAG_SUFIXO_TIPO:
        return
    if tipo_forma == "DU":
        _insere_duplicata_parcelada(cur, dav, forma_pag, valor)
        return
    tabela = dav.tabela(tipo_forma)
    col = FORMA_PAG_VALOR_COL[tipo_forma]
    venc_col = FORMA_PAG_VENC_COL[tipo_forma]
    if venc_col:
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, {col}, {venc_col}) "
            f"VALUES (%s, %s, %s, CONVERT(date, GETDATE()))",
            (dav.documento, forma_pag, valor),
        )
    else:
        cur.execute(
            f"INSERT INTO {tabela} ({dav.fk}, forma_pag, {col}) VALUES (%s, %s, %s)",
            (dav.documento, forma_pag, valor),
        )


def _fecha_fpag_dav(cur, dav: DavPagamento) -> Optional[str]:
    """Réplica de `Fecha_FPAG_Dav` (FormaPagamentoDAV.bas): garante que o
    total lançado nas tabelas de forma de pagamento bate com `dav.valor`
    (subtotal do documento). Se não bate e existe EXATAMENTE 1 forma
    lançada, corrige o valor dela automaticamente (ajuste de arredondamento).
    Se não bate, não há nada lançado ainda e uma forma padrão foi informada
    (combobox simples do cabeçalho), lança automaticamente. Se 2+ formas
    divergem, bloqueia — usuário precisa acertar manualmente pelo modal.
    Retorna None se ok, ou a mensagem de erro (igual ao legado) se bloqueado."""
    total_lancado = _totaliza_dav(cur, dav)
    if abs(total_lancado - dav.valor) < 0.005:
        return None
    unica = _unica_forma_existente(cur, dav)
    if unica:
        _atualiza_valor_forma(cur, dav, unica[0], unica[1], dav.valor)
        return None
    if total_lancado == 0 and (dav.forma_padrao or "").strip():
        _cadastra_forma_automatica(cur, dav, dav.forma_padrao.strip(), dav.valor)
        return None
    if _qtd_formas(cur, dav) == 0:
        # Sem nenhuma forma lançada e sem forma padrão — quem chama decide a
        # mensagem (Command111_Click faz essa checagem separada, com
        # "Defina a Forma de Pagamento", só quando valor > 0).
        return None
    return "Informar a Forma de Pagamento corretamente!"


def _fechar_pedido_itens(cur, pedido: int, subtotal: float = 0.0, forma_padrao: Optional[str] = None) -> Optional[str]:
    """Fecha o Pedido (situação A -> F) dentro da transação corrente: exige
    pelo menos 1 item, valida/ajusta a forma de pagamento (réplica de
    `Fecha_FPAG_Dav` + a checagem `QtdFormas=0` de `Command111_Click`) e move
    o estoque das PEÇAS (qtd -= q ; reservado += q). Retorna uma mensagem de
    erro (str) se bloqueado, ou None se ok — quem chama decide se
    comita/desfaz a transação. Compartilhado entre o Fechar isolado
    (`/pedidos/{pedido}/fechar`) e o Faturar (`/pedidos/{pedido}/faturar`,
    que fecha-e-fatura num clique só quando o pedido ainda está Aberto —
    mesmo comportamento de `Command111_Click` no legado)."""
    cur.execute(
        "SELECT produto, qtd_pedida FROM pedido_venda_prod "
        "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
        (pedido,),
    )
    itens = cur.fetchall()
    if not itens:
        return "Inclua pelo menos um produto ou serviço antes de fechar."
    dav = DavPagamento(tipo=DAV_PED, documento=pedido, situacao="A", valor=subtotal, forma_padrao=forma_padrao or "")
    erro = _fecha_fpag_dav(cur, dav)
    if erro:
        return erro
    if _qtd_formas(cur, dav) == 0 and subtotal > 0:
        return "Defina a Forma de Pagamento do Pedido!"
    for it in itens:
        _mover_estoque(cur, (it.get("produto") or "").strip(), float(it.get("qtd_pedida") or 0), "reservado")
    cur.execute("UPDATE pedido_venda SET situacao='F' WHERE pedido=%s", (pedido,))
    return None


def _liberar_reservado(cur, codigo: str, delta_qtd: float) -> None:
    """Libera o estoque RESERVADO de uma PEÇA ao faturar (Comanda) — a baixa
    de `qtd` já aconteceu no Fechar (ver `_mover_estoque`), aqui só se
    desfaz a reserva. Efeito: pecas.reservado -= delta_qtd. Não faz nada
    para serviços/itens inexistentes."""
    if not delta_qtd or not _is_peca(cur, codigo):
        return
    cur.execute(
        "UPDATE pecas SET reservado = ISNULL(reservado,0) - %s WHERE codigo_int=%s",
        (delta_qtd, codigo),
    )