"""Itens do Pedido (pedido_venda_prod) — listagem e CRUD.

Relacionamentos:
  pedido_venda.pedido = pedido_venda_prod.pedido
  pedido_venda_prod.produto = pecas.codigo_int  (produto)  -> tipo 'P'
  pedido_venda_prod.produto = servicos.codigo    (serviço)  -> tipo 'S'
Política: só pedido com situacao='A' (Aberto) permite CRUD de itens.
Total do item = qtd_pedida * p_venda - desconto + acrescimo
pedido_venda.total = SUM dos itens não cancelados.
"""
import asyncio

from db.connection import _open_conn
from models.schemas import ItemSaveRequest, TaxaServicoRequest
from services.constants import SITUACAO_LABEL
from services.descontos_service import _validar_limite_desconto, _log_desconto_item
from services.pedido_common import (
    _item_total, _recalc_pedido_total, _check_pedido_aberto, _resolve_produto,
    _modulo_servicos_ativo, _ensure_hora_inclusao_item_col,
)

# Código reservado do serviço "Taxa de Serviço" (10%) — convenção fixa herdada
# do legado (FrmManPedBar.frm, Command50_Click, hardcoded como 'S002' em todo
# o form). Não é uma tela/lookup configurável; replicado como está. Só pode
# ser incluída/atualizada pelo botão dedicado "Tx Serviço"
# (`_add_taxa_servico_sync`) — nunca pelo fluxo genérico de adicionar item,
# pra nunca existir mais de uma linha S002 no mesmo pedido.
TAXA_SERVICO_CODIGO = "S002"
TAXA_SERVICO_PCT = 0.10


def _list_itens_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "subtotal": 0}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado.", "items": [], "subtotal": 0}
        _ensure_hora_inclusao_item_col(cur)
        conn.commit()
        cur.execute(
            "SELECT i.codauto, i.produto, i.qtd_pedida, i.p_venda, i.p_normal, i.desconto, i.acrescimo, "
            "       i.descricao_produto, i.unidade_pedido, i.data_inclusao_item, i.hora_inclusao_item, "
            "       pe.descricao AS peca_desc, pe.codigo_fab AS peca_fab, "
            "       sv.descricao AS serv_desc, tp.descricao AS finalidade_desc "
            "FROM pedido_venda_prod i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "LEFT JOIN tipo_peca tp ON tp.codigo = pe.tipo_peca "
            "WHERE i.pedido = %s AND ISNULL(i.item_cancelado,0) = 0 "
            # Taxa de Serviço (S002) sempre por último, independente de quando
            # foi incluída/atualizada — pedido explícito do usuário.
            "ORDER BY CASE WHEN i.produto=%s THEN 1 ELSE 0 END, i.codauto",
            (pedido, TAXA_SERVICO_CODIGO),
        )
        items = []
        subtotal = 0.0
        for r in cur.fetchall():
            is_peca = r.get("peca_desc") is not None
            tipo = "P" if is_peca else ("S" if r.get("serv_desc") is not None else "?")
            base_desc = (r.get("peca_desc") if is_peca else r.get("serv_desc")) or ""
            complemento = (r.get("descricao_produto") or "").strip()
            qtd = float(r.get("qtd_pedida") or 0)
            pv = float(r.get("p_venda") or 0)
            pnorm = float(r.get("p_normal") or 0)
            desc = float(r.get("desconto") or 0)
            acr = float(r.get("acrescimo") or 0)
            tot = _item_total(qtd, pv)
            subtotal += tot
            items.append({
                "codauto": int(r["codauto"]),
                "produto": (r.get("produto") or "").strip(),
                "tipo": tipo,
                "descricao": base_desc.strip(),
                "complemento": complemento,
                "cod_fab": (r.get("peca_fab") or r.get("produto") or "").strip(),
                "unidade": (r.get("unidade_pedido") or "").strip(),
                "qtd": qtd,
                "p_normal": pnorm,
                "valor_unitario": pv,
                "desconto": desc,
                "acrescimo": acr,
                "total": tot,
                "data_inclusao": r["data_inclusao_item"].isoformat() if r.get("data_inclusao_item") else None,
                "hora_inclusao": (r.get("hora_inclusao_item") or "").strip(),
                # Finalidade (Cozinha/Bebidas/Materiais...) — só produtos têm
                # (pecas.tipo_peca); usada como rótulo no ticket de impressão
                # de item (ver PENDENCIAS.md > "Pedido Bar" > "Impressão de item").
                "finalidade_descricao": (r.get("finalidade_desc") or "").strip(),
            })
        cur.close()
        conn.close()
        return {
            "success": True,
            "items": items,
            "subtotal": round(subtotal, 2),
            "situacao": sit,
            "editavel": sit == "A",
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "subtotal": 0}


def _add_item_sync(req: ItemSaveRequest, pedido: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        codigo = (req.produto or "").strip()
        if not codigo:
            conn.close()
            return {"success": False, "message": "Produto/serviço obrigatório."}
        if codigo.upper() == TAXA_SERVICO_CODIGO:
            conn.close()
            return {
                "success": False,
                "message": "Taxa de Serviço não pode ser adicionada manualmente — use o botão 'Tx Serviço'.",
            }
        prod = _resolve_produto(cur, codigo)
        if not prod:
            conn.close()
            return {"success": False, "message": f"Produto/serviço '{codigo}' não encontrado."}
        if prod["tipo"] == "S" and not _modulo_servicos_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Serviço está desativado — não é possível incluir serviços no Pedido."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        # valor_unitario = p_normal (preço base/tabela no momento). desconto/acrescimo são UNITÁRIOS.
        p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
        p_normal = float(p_normal or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)  # preço líquido unitário
        complemento = (req.complemento or "").strip()
        unidade = prod["unidade"]
        custo = float(prod.get("custo") or 0)  # pecas.custo_reposicao no momento da venda
        # Defesa em profundidade: valida limite de desconto por função (master ignora)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}

        _ensure_hora_inclusao_item_col(cur)
        cur.execute(
            "INSERT INTO pedido_venda_prod "
            "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
            " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
            " hora_inclusao_item) "
            "OUTPUT INSERTED.codauto "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
            "        CONVERT(NVARCHAR(8), GETDATE(), 108))",
            (pedido, codigo, qtd, p_venda, p_normal, desc, acr, custo, complemento, unidade),
        )
        row = cur.fetchone()
        codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        # `codigo` nunca é TAXA_SERVICO_CODIGO aqui — bloqueado mais acima.
        sincroniza_taxa_servico_apos_alteracao(cur, pedido)
        novo_total = _recalc_pedido_total(cur, pedido)

        # Finalidade do item (pecas.tipo_peca) — devolvida junto pra quem
        # chamou decidir, sem round-trip extra, se deve disparar a impressão
        # automática de item por grupo de produto (ver
        # project_impressao_automatica_finalidade / PENDENCIAS.md).
        tipo_peca = prod.get("tipo_peca")
        finalidade_descricao = ""
        if tipo_peca is not None:
            cur.execute("SELECT descricao FROM tipo_peca WHERE codigo=%s", (tipo_peca,))
            tp_row = cur.fetchone()
            finalidade_descricao = ((tp_row.get("descricao") if tp_row else None) or "").strip()

        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "codauto": codauto, "total": novo_total,
            "tipo_peca": tipo_peca, "finalidade_descricao": finalidade_descricao,
            "item": {
                "codauto": codauto, "produto": codigo, "tipo": prod["tipo"],
                "descricao": prod["descricao"], "complemento": complemento,
                "cod_fab": prod["cod_fab"], "unidade": unidade, "qtd": qtd,
                "finalidade_descricao": finalidade_descricao,
            },
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _recalc_valor_taxa_servico(cur, pedido: int) -> float:
    """10% do subtotal atual do pedido, excluindo a própria linha de Taxa de
    Serviço (senão um recálculo em cima de uma taxa já incluída infla o
    valor sobre si mesmo)."""
    cur.execute(
        "SELECT ISNULL(SUM(qtd_pedida*p_venda),0) s FROM pedido_venda_prod "
        "WHERE pedido=%s AND produto<>%s AND ISNULL(item_cancelado,0)=0",
        (pedido, TAXA_SERVICO_CODIGO),
    )
    subtotal = float(cur.fetchone()["s"] or 0)
    return round(subtotal * TAXA_SERVICO_PCT, 2)


def sincroniza_taxa_servico_apos_alteracao(cur, pedido: int) -> None:
    """Se já existe uma linha de Taxa de Serviço (S002) no pedido, recalcula
    e atualiza seu valor — chamado depois de incluir outro item (produto ou
    serviço), pra manter a taxa sempre em dia com o subtotal real. Não cria
    uma linha nova se não existir — inclusão da taxa em si só acontece pelo
    botão dedicado (`_add_taxa_servico_sync`). Pedido explícito do usuário,
    2026-07-15."""
    cur.execute(
        "SELECT codauto FROM pedido_venda_prod "
        "WHERE pedido=%s AND produto=%s AND ISNULL(item_cancelado,0)=0",
        (pedido, TAXA_SERVICO_CODIGO),
    )
    row = cur.fetchone()
    if not row:
        return
    codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
    valor = _recalc_valor_taxa_servico(cur, pedido)
    cur.execute(
        "UPDATE pedido_venda_prod SET qtd_pedida=1, p_normal=%s, p_venda=%s WHERE codauto=%s",
        (valor, valor, codauto),
    )


def _add_taxa_servico_sync(req: TaxaServicoRequest, pedido: int) -> dict:
    """Botão 'Incluir Tx Serviço [F10]' do Pedido Bar — inclui/atualiza uma
    linha de 10% do subtotal (excluindo a própria taxa) como serviço `S002`.
    Rastreado de `Command50_Click` (o handler real do botão/F10 —
    `Inclui_Tx_Servico()`, definida no mesmo .frm, nunca é chamada de lugar
    nenhum e foi tratada como código morto, não como a rotina real).

    **Correção 2026-07-15, user-directed**: o legado (`Command50_Click`)
    empilhava uma nova linha a cada clique se já existisse uma — decisão
    explícita do usuário foi NÃO replicar esse comportamento. Aqui é
    idempotente: se já existe uma linha `S002`, um novo clique
    **atualiza o valor** dela (recalculado sobre o subtotal atual, sempre
    excluindo a própria taxa da base de cálculo — senão cada clique
    inflaria o valor sobre si mesmo); se não existe, inclui uma nova."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        cur.execute("SELECT descricao FROM servicos WHERE codigo=%s", (TAXA_SERVICO_CODIGO,))
        serv = cur.fetchone()
        if not serv:
            conn.close()
            return {
                "success": False,
                "message": f"Serviço de Taxa de Serviço (código '{TAXA_SERVICO_CODIGO}') não está cadastrado.",
            }

        # Não permite incluir Taxa de Serviço num pedido sem nenhum item de
        # produto/serviço lançado (excluindo a própria S002) — pedido
        # explícito do usuário, 2026-07-17: taxa de 10% sobre um subtotal
        # zerado não faz sentido.
        cur.execute(
            "SELECT COUNT(*) c FROM pedido_venda_prod "
            "WHERE pedido=%s AND produto<>%s AND ISNULL(item_cancelado,0)=0",
            (pedido, TAXA_SERVICO_CODIGO),
        )
        if int(cur.fetchone()["c"] or 0) == 0:
            conn.close()
            return {"success": False, "message": "Inclua ao menos um item no pedido antes de lançar a Taxa de Serviço."}

        valor_servico = _recalc_valor_taxa_servico(cur, pedido)
        descricao = (serv.get("descricao") or "").strip() or "Taxa de Serviço"

        cur.execute(
            "SELECT codauto FROM pedido_venda_prod "
            "WHERE pedido=%s AND produto=%s AND ISNULL(item_cancelado,0)=0 "
            "ORDER BY codauto",
            (pedido, TAXA_SERVICO_CODIGO),
        )
        existentes = [int(r["codauto"]) for r in cur.fetchall()]

        atualizado = len(existentes) > 0
        if len(existentes) > 1:
            # Defensivo: nunca deveria acontecer daqui pra frente (idempotente
            # desde já), mas se sobrar mais de uma linha de uma versão
            # anterior, consolida numa só em vez de deixar duplicatas.
            cur.execute(
                "DELETE FROM pedido_venda_prod WHERE codauto IN (" +
                ",".join(str(c) for c in existentes[1:]) + ")"
            )

        if atualizado:
            codauto = existentes[0]
            cur.execute(
                "UPDATE pedido_venda_prod SET qtd_pedida=1, p_normal=%s, p_venda=%s "
                "WHERE codauto=%s",
                (valor_servico, valor_servico, codauto),
            )
        else:
            _ensure_hora_inclusao_item_col(cur)
            cur.execute(
                "INSERT INTO pedido_venda_prod "
                "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                " hora_inclusao_item) "
                "OUTPUT INSERTED.codauto "
                "VALUES (%s,%s,1,%s,%s,0,0,0,%s,'UN','A',0,CAST(GETDATE() AS DATE),"
                "        CONVERT(NVARCHAR(8), GETDATE(), 108))",
                (pedido, TAXA_SERVICO_CODIGO, valor_servico, valor_servico, descricao),
            )
            row = cur.fetchone()
            codauto = int(row["codauto"] if isinstance(row, dict) else row[0])

        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "codauto": codauto, "valor": valor_servico,
            "total": novo_total, "atualizado": atualizado,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao incluir taxa de serviço: {e}"}


def _update_item_sync(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        cur.execute("SELECT produto FROM pedido_venda_prod WHERE codauto=%s AND pedido=%s", (codauto, pedido))
        row_atual = cur.fetchone()
        if not row_atual:
            conn.close()
            return {"success": False, "message": "Item não encontrado."}
        produto_atual = ((row_atual.get("produto") if isinstance(row_atual, dict) else row_atual[0]) or "").strip().upper()

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        if produto_atual == TAXA_SERVICO_CODIGO and qtd != 1:
            conn.close()
            return {"success": False, "message": "Taxa de Serviço deve ter sempre 1 unidade."}
        # valor_unitario = p_normal (preço base). desconto/acrescimo são UNITÁRIOS.
        p_normal = float(req.valor_unitario or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        # Defesa em profundidade: valida limite de desconto por função (master ignora)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}
        p_venda = round(p_normal - desc + acr, 4)  # preço líquido unitário
        complemento = (req.complemento or "").strip()

        cur.execute(
            "UPDATE pedido_venda_prod SET "
            " qtd_pedida=%s, p_normal=%s, p_venda=%s, desconto=%s, acrescimo=%s, "
            " descricao_produto=%s, data_alteracao_item=CAST(GETDATE() AS DATE) "
            "WHERE codauto=%s AND pedido=%s",
            (qtd, p_normal, p_venda, desc, acr, complemento, codauto, pedido),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar item: {e}"}


def _delete_item_sync(servidor: str, banco: str, pedido: int, codauto: int) -> dict:
    """Exclui um item do pedido. Se este pedido é FILHO de uma divisão
    (Dividir Pedido — `pedido_venda.num_ped_cliente` aponta pra um pedido
    original numérico) e o original ainda existe e está Aberto, o item não
    é simplesmente descartado: volta pro pedido original (soma na linha já
    existente do mesmo produto, se houver, ou cria uma nova) — pedido
    explícito do usuário, 2026-07-17. Taxa de Serviço (S002) nunca é
    devolvida (é recalculada automaticamente em cada pedido, nunca uma
    linha "dona" que faça sentido mover). Se o original não existir mais ou
    não estiver Aberto, cai no comportamento normal (exclui sem devolver)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        cur.execute(
            "SELECT produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
            "descricao_produto, unidade_pedido FROM pedido_venda_prod WHERE codauto=%s AND pedido=%s",
            (codauto, pedido),
        )
        item = cur.fetchone()
        if not item:
            conn.close()
            return {"success": False, "message": "Item não encontrado."}

        devolvido_para = None
        produto = (item.get("produto") or "").strip()
        if produto.upper() != TAXA_SERVICO_CODIGO:
            cur.execute("SELECT num_ped_cliente FROM pedido_venda WHERE pedido=%s", (pedido,))
            ref_row = cur.fetchone()
            referencia = (ref_row.get("num_ped_cliente") or "").strip() if ref_row else ""
            if referencia.isdigit():
                original = int(referencia)
                existe_orig, sit_orig = _check_pedido_aberto(cur, original)
                if existe_orig and sit_orig == "A":
                    _ensure_hora_inclusao_item_col(cur)
                    cur.execute(
                        "SELECT codauto, qtd_pedida FROM pedido_venda_prod "
                        "WHERE pedido=%s AND produto=%s AND ISNULL(item_cancelado,0)=0",
                        (original, produto),
                    )
                    existente = cur.fetchone()
                    if existente:
                        nova_qtd = float(existente["qtd_pedida"] or 0) + float(item["qtd_pedida"] or 0)
                        cur.execute(
                            "UPDATE pedido_venda_prod SET qtd_pedida=%s WHERE codauto=%s",
                            (nova_qtd, int(existente["codauto"])),
                        )
                    else:
                        cur.execute(
                            "INSERT INTO pedido_venda_prod "
                            "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                            " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                            " hora_inclusao_item) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                            "        CONVERT(NVARCHAR(8), GETDATE(), 108))",
                            (
                                original, produto, item["qtd_pedida"], item["p_venda"], item["p_normal"],
                                item["desconto"], item["acrescimo"], item["custo_ped"],
                                item.get("descricao_produto"), item.get("unidade_pedido"),
                            ),
                        )
                    devolvido_para = original

        cur.execute("DELETE FROM pedido_venda_prod WHERE codauto=%s AND pedido=%s", (codauto, pedido))
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        cur.execute(
            "DELETE FROM descontos_concedidos "
            "WHERE TIPO='PED' AND CODIGO=%s AND CODIGO_PRODUTO=%s AND TIPO_DESCONTO='I'",
            (pedido, codauto),
        )
        sincroniza_taxa_servico_apos_alteracao(cur, pedido)
        novo_total = _recalc_pedido_total(cur, pedido)

        if devolvido_para is not None:
            sincroniza_taxa_servico_apos_alteracao(cur, devolvido_para)
            _recalc_pedido_total(cur, devolvido_para)

        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total, "devolvido_para": devolvido_para}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover item: {e}"}


async def list_itens(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_list_itens_sync, servidor, banco, pedido)


async def add_item(req: ItemSaveRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_add_item_sync, req, pedido)


async def add_taxa_servico(req: TaxaServicoRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_add_taxa_servico_sync, req, pedido)


async def update_item(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    return await asyncio.to_thread(_update_item_sync, req, pedido, codauto)


async def delete_item(servidor: str, banco: str, pedido: int, codauto: int) -> dict:
    return await asyncio.to_thread(_delete_item_sync, servidor, banco, pedido, codauto)
