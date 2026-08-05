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

from db.connection import _open_conn, _to_json_safe
from services.pedido_common import (
    FORMA_PAG_SUFIXO_TIPO,
    _is_peca,
    _liberar_reservado,
    _preco_promocional,
    _resolve_produto_completo,
)
from services.permissoes_service import tem_permissao

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
        return {"success": False, "message": f"Erro ao abrir venda: {e}"}


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
            "ISNULL(p.descricao_pdv, p.descricao) AS descricao_p, s.descricao AS descricao_s, "
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
    produto) — caso de uso de baixo volume, fora do escopo desta fase."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        produto = _resolve_produto_completo(cur, (codigo or "").strip())
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
        if produto["tipo"] == "P":
            cur.execute("SELECT qtd FROM pecas WHERE codigo_int=%s", (produto["codigo"],))
            r = cur.fetchone()
            estoque = float(r["qtd"]) if r else 0
        limites = _limites_desconto(cur, produto)
        cur.close()
        conn.close()
        return {
            "success": True,
            "codigo": produto["codigo"],
            "cod_fab": produto["cod_fab"],
            "descricao": produto["descricao"],
            "tipo": produto["tipo"],
            "unidade": produto["unidade"],
            "preco": preco,
            "promocao": promocao,
            "estoque": estoque,
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
            return {"success": False, "message": "Este item pertence a um Pedido/O.S. importado! Cancelamento não permitido."}
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
        for forma in req.formas:
            tipo = (forma.tipo or "").strip().upper()
            if tipo not in FORMA_PAG_SUFIXO_TIPO:
                conn.close()
                return {"success": False, "message": f"Tipo de forma de pagamento inválido: {tipo}"}
            if not (forma.forma_pag or "").strip():
                conn.close()
                return {"success": False, "message": "Selecione a forma de pagamento."}
            valor = float(forma.valor or 0)
            if valor <= 0:
                conn.close()
                return {"success": False, "message": "Informe um valor maior que zero."}
            if tipo in ("CC", "CD"):
                if not forma.cod_administradora or not forma.cod_parcelador:
                    conn.close()
                    return {"success": False, "message": "Defina a administradora e o parcelador!"}
                ok, erro = _verifica_parcelamento_cartao(
                    cur, forma.forma_pag, forma.cod_administradora, forma.cod_parcelador, forma.parcelas or 1,
                )
                if not ok:
                    conn.close()
                    return {"success": False, "message": erro}
            total_pago += valor

        if total_pago + 0.005 < total_devido:
            falta = round(total_devido - total_pago, 2)
            conn.close()
            return {"success": False, "message": f"Falta R$ {falta:.2f} para completar o pagamento."}

        for forma in req.formas:
            tipo = (forma.tipo or "").strip().upper()
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
        cur.execute("SELECT codigo_int, qtd, tipo_dav FROM movimentacao WHERE num_nf=%s AND serie_nf='CM'", (comanda,))
        itens = cur.fetchall()
        for it in itens:
            codigo = (it.get("codigo_int") or "").strip()
            qtd = float(it.get("qtd") or 0)
            origem = (it.get("tipo_dav") or "").strip().upper()
            if not origem:
                _mover_estoque_direto(cur, codigo, -qtd)
            elif origem == "P":
                _liberar_reservado(cur, codigo, -qtd, "reservado")
            elif origem == "O":
                _liberar_reservado(cur, codigo, -qtd, "reservado_os")
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


async def importar_dav(req, comanda: int) -> dict:
    return await asyncio.to_thread(_importar_dav_sync, req, comanda)


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
