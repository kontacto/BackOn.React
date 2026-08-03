"""Itens da Ordem de Serviço (os_produto) — listagem e CRUD.

Relacionamentos:
  os.codigo = os_produto.os
  os_produto.codigo_interno = pecas.codigo_int (produto 'P') ou servicos.codigo (serviço 'S')
Regras:
  • Só OS com situacao='A' (Aberta) permite CRUD de itens.
  • vendedor e executor ficam POR ITEM (diferente do pedido_venda).
  • Total do item = quant * p_venda; p_venda = preco_unitario - desconto + acrescimo.
  • os.valor = SUM dos itens não cancelados.
"""
import asyncio

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import OSItemSaveRequest, PontuacaoSaveRequest, AutorizacaoItensRequest, AlterarExecutorRequest
from services.constants import SITUACAO_LABEL
from services.pedido_common import (
    _resolve_produto, _mover_estoque, _modulo_servicos_ativo, _modulo_agenda_ativo,
    _exige_aprovacao_itens_os_ativo, _exige_expedicao_itens_os_ativo,
    _ensure_agenda_os_table,
)


def _check_os_aberta(cur, codigo: int) -> tuple[bool, str]:
    cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
    row = cur.fetchone()
    if not row:
        return (False, "")
    return (True, (row.get("situacao") or "").strip().upper())


def _recalc_os_total(cur, codigo: int) -> float:
    cur.execute(
        "UPDATE os SET valor = ISNULL(("
        "  SELECT SUM(quant * p_venda) FROM os_produto "
        "  WHERE os=%s AND ISNULL(item_cancelado,0)=0), 0) WHERE codigo=%s",
        (codigo, codigo),
    )
    cur.execute("SELECT valor FROM os WHERE codigo=%s", (codigo,))
    r = cur.fetchone()
    return float((r.get("valor") if isinstance(r, dict) else (r[0] if r else 0)) or 0)


def _list_itens_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "subtotal": 0}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada.", "items": [], "subtotal": 0}
        cur.execute(
            "SELECT i.cod_os_prod, i.codigo_interno, i.quant, i.p_venda, i.preco_unitario, "
            "       i.desconto, i.acrescimo, i.vendedor, i.executor, i.descricao_produto_os, i.situacao, "
            "       i.Pontuacao_A, i.Pontuacao_E, i.Pontuacao_V, "
            "       i.usuario_autorizacao, i.data_autorizacao, i.hora_autorizacao, i.qtd_autorizada, "
            "       i.usuario_expedicao, i.data_expedicao, i.hora_expedicao, "
            "       pe.descricao AS peca_desc, pe.codigo_fab AS peca_fab, pe.uni AS peca_uni, "
            "       sv.descricao AS serv_desc, "
            "       fv.nome AS vend_nome, fv.nome_guerra AS vend_guerra, "
            "       fe.nome AS exec_nome, fe.nome_guerra AS exec_guerra, "
            "       fa.nome AS aut_nome, fa.nome_guerra AS aut_guerra, "
            "       fx.nome AS exp_nome, fx.nome_guerra AS exp_guerra "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "LEFT JOIN funcionarios fv ON fv.codigo_int = i.vendedor "
            "LEFT JOIN funcionarios fe ON fe.codigo_int = i.executor "
            "LEFT JOIN funcionarios fa ON fa.codigo_int = i.usuario_autorizacao "
            "LEFT JOIN funcionarios fx ON fx.codigo_int = i.usuario_expedicao "
            "WHERE i.os = %s AND ISNULL(i.item_cancelado,0) = 0 "
            "ORDER BY i.cod_os_prod",
            (codigo,),
        )
        items = []
        subtotal = 0.0
        for r in cur.fetchall():
            is_peca = r.get("peca_desc") is not None
            tipo = "P" if is_peca else ("S" if r.get("serv_desc") is not None else "?")
            base_desc = (r.get("peca_desc") if is_peca else r.get("serv_desc")) or ""
            qtd = float(r.get("quant") or 0)
            pv = float(r.get("p_venda") or 0)
            pnorm = float(r.get("preco_unitario") or 0)
            desc = float(r.get("desconto") or 0)
            acr = float(r.get("acrescimo") or 0)
            tot = round(qtd * pv, 2)
            subtotal += tot
            items.append({
                "cod_os_prod": int(r["cod_os_prod"]),
                "produto": (r.get("codigo_interno") or "").strip(),
                "tipo": tipo,
                "descricao": base_desc.strip(),
                "complemento": (r.get("descricao_produto_os") or "").strip(),
                "cod_fab": (r.get("peca_fab") or r.get("codigo_interno") or "").strip(),
                "unidade": (r.get("peca_uni") or ("HR" if tipo == "S" else "")).strip(),
                "qtd": qtd,
                "p_normal": pnorm,
                "valor_unitario": pv,
                "desconto": desc,
                "acrescimo": acr,
                "total": tot,
                "vendedor": int(r["vendedor"]) if r.get("vendedor") else None,
                "vendedor_nome": (r.get("vend_guerra") or r.get("vend_nome") or "").strip(),
                "executor": int(r["executor"]) if r.get("executor") else None,
                "executor_nome": (r.get("exec_guerra") or r.get("exec_nome") or "").strip(),
                "situacao": int(r.get("situacao") or 0),
                "pontuacao_a": int(r["Pontuacao_A"]) if r.get("Pontuacao_A") is not None else None,
                "pontuacao_e": int(r["Pontuacao_E"]) if r.get("Pontuacao_E") is not None else None,
                "pontuacao_v": int(r["Pontuacao_V"]) if r.get("Pontuacao_V") is not None else None,
                # Autorização/Expedição de Itens (aba "Autorização de Itens",
                # FrmTraOsNew.frm) — presença de `data_autorizacao`/
                # `data_expedicao` decide o estado do item pra Autorizar/
                # Expedir, ver `os-completo/.../autorizar-itens` etc.
                "usuario_autorizacao": int(r["usuario_autorizacao"]) if r.get("usuario_autorizacao") else None,
                "usuario_autorizacao_nome": (r.get("aut_guerra") or r.get("aut_nome") or "").strip(),
                "data_autorizacao": r["data_autorizacao"].isoformat() if r.get("data_autorizacao") else None,
                "hora_autorizacao": (r.get("hora_autorizacao") or "").strip(),
                "qtd_autorizada": float(r["qtd_autorizada"]) if r.get("qtd_autorizada") is not None else 0.0,
                "usuario_expedicao": int(r["usuario_expedicao"]) if r.get("usuario_expedicao") else None,
                "usuario_expedicao_nome": (r.get("exp_guerra") or r.get("exp_nome") or "").strip(),
                "data_expedicao": r["data_expedicao"].isoformat() if r.get("data_expedicao") else None,
                "hora_expedicao": (r.get("hora_expedicao") or "").strip(),
            })

        # Agendamento (módulo Assistência, `AGENDA`/`AGENDA_OS` — mesmo
        # padrão de enriquecimento já usado em
        # `pedido_completo_service._get_pedido_completo_sync` pro Pedido
        # Geral, `AGENDA`/`AGENDA_PEDIDO`). Ver `agenda_service.py`.
        # `_ensure_agenda_os_table` garante que a tabela existe (idempotente,
        # `IF NOT EXISTS`) antes do SELECT — sem isso, uma instalação que
        # nunca agendou nenhum item de O.S. quebraria a listagem inteira de
        # itens (tabela ainda inexistente).
        _ensure_agenda_os_table(cur)
        cur.execute(
            "SELECT ao.CODOS AS cod_os_prod, a.codagenda, a.data, a.hora_ini, a.situacao_atendimento, "
            "       a.funcionario, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS profissional "
            "FROM AGENDA_OS ao "
            "JOIN AGENDA a ON a.codagenda = ao.CODAGENDA "
            "JOIN funcionarios f ON f.codigo_int = a.funcionario "
            "JOIN os_produto i ON i.cod_os_prod = ao.CODOS "
            "WHERE i.os = %s",
            (codigo,),
        )
        for r in cur.fetchall():
            data_v = r.get("data")
            hora_v = r.get("hora_ini")
            agendamento = {
                "codagenda": int(r["codagenda"]),
                "data": data_v.isoformat() if hasattr(data_v, "isoformat") else str(data_v),
                "hora_ini": hora_v.strftime("%H:%M") if hasattr(hora_v, "strftime") else str(hora_v)[:5],
                "profissional": (r.get("profissional") or "").strip(),
                "funcionario": int(r["funcionario"]),
                "situacao": (r.get("situacao_atendimento") or "").strip(),
            }
            cod_os_prod = int(r["cod_os_prod"])
            for item in items:
                if item.get("cod_os_prod") == cod_os_prod:
                    item["agendamento"] = agendamento
                    break

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


def _add_item_sync(req: OSItemSaveRequest, codigo: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        prod_cod = (req.produto or "").strip()
        if not prod_cod:
            conn.close()
            return {"success": False, "message": "Produto/serviço obrigatório."}
        prod = _resolve_produto(cur, prod_cod)
        if not prod:
            conn.close()
            return {"success": False, "message": f"Produto/serviço '{prod_cod}' não encontrado."}
        if prod["tipo"] == "S" and not _modulo_servicos_ativo(cur):
            conn.close()
            return {"success": False, "message": "Módulo Serviço está desativado — não é possível incluir serviços na O.S."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
        p_normal = float(p_normal or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)
        complemento = (req.complemento or "").strip()
        custo = float(prod.get("custo") or 0)
        situacao_item = int(req.situacao) if req.situacao is not None else 0

        # Agendar item de Serviço (módulo Assistência — mesmo comportamento
        # já usado pelo Pedido Geral, `clinica_split` em
        # `pedido_completo_service._add_item_completo_sync`, réplica de
        # `frmmanpedfor.frm:8241-8280`): item de Serviço com o módulo Agenda
        # ativo vira N linhas (quant=1 cada), uma por unidade — cada linha
        # é 1 atendimento agendável (ex.: 3 manutenções no mês, datas
        # diferentes, mesma O.S.), em vez de 1 linha só com quant=N. Ver
        # PENDENCIAS.md > "O.S. Completa" > "Agendar item de Serviço".
        os_agenda_split = prod["tipo"] == "S" and _modulo_agenda_ativo(cur)
        cod_os_prods: list[int] = []

        if os_agenda_split:
            if qtd != int(qtd):
                conn.close()
                return {
                    "success": False,
                    "message": "Quantidade deve ser um número inteiro para item de Serviço (cada unidade vira um atendimento agendável).",
                }
            for _ in range(int(qtd)):
                cur.execute(
                    "INSERT INTO os_produto "
                    "(os, codigo_interno, quant, p_venda, preco_unitario, desconto, acrescimo, custo_os, "
                    " vendedor, executor, descricao_produto_os, situacao, item_cancelado, faturado, data_inclusao_item) "
                    "OUTPUT INSERTED.cod_os_prod "
                    "VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,CAST(GETDATE() AS DATE))",
                    (codigo, prod_cod, p_venda, p_normal, desc, acr, custo,
                     req.vendedor, req.executor, complemento, situacao_item),
                )
                row = cur.fetchone()
                cod_os_prods.append(int(row["cod_os_prod"] if isinstance(row, dict) else row[0]))
            # Sempre item de Serviço aqui — `_mover_estoque` ignora
            # serviços automaticamente (`_is_peca` retorna False), chamar
            # N vezes seria N no-ops sem efeito nenhum.
        else:
            cur.execute(
                "INSERT INTO os_produto "
                "(os, codigo_interno, quant, p_venda, preco_unitario, desconto, acrescimo, custo_os, "
                " vendedor, executor, descricao_produto_os, situacao, item_cancelado, faturado, data_inclusao_item) "
                "OUTPUT INSERTED.cod_os_prod "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,CAST(GETDATE() AS DATE))",
                (codigo, prod_cod, qtd, p_venda, p_normal, desc, acr, custo,
                 req.vendedor, req.executor, complemento, situacao_item),
            )
            row = cur.fetchone()
            cod_os_prods.append(int(row["cod_os_prod"] if isinstance(row, dict) else row[0]))
            # Estoque: OS aberta reserva imediatamente (qtd -= q ; reservado_os += q)
            # — EXCETO quando a empresa exige Autorização de Itens
            # (`controle_aux.exige_aprovacao_itens_os`), caso em que o estoque só
            # é reservado quando o item é AUTORIZADO (ver `_autorizar_itens_sync`
            # abaixo) — confirmado pelo usuário, 2026-08-01, réplica de
            # `FrmTraOsNew.frm`. _mover_estoque ignora serviços automaticamente.
            if not _exige_aprovacao_itens_os_ativo(cur):
                _mover_estoque(cur, prod_cod, qtd, "reservado_os")

        novo_total = _recalc_os_total(cur, codigo)
        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True, "cod_os_prod": cod_os_prods[0], "cod_os_prods": cod_os_prods,
            "os_agenda_split": os_agenda_split, "total": novo_total,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _update_item_sync(req: OSItemSaveRequest, codigo: int, cod_os_prod: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        p_normal = float(req.valor_unitario or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)
        complemento = (req.complemento or "").strip()

        # Quantidade anterior p/ ajustar estoque reservado (somente peças).
        cur.execute("SELECT quant, codigo_interno, data_autorizacao FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                    (cod_os_prod, codigo))
        old = cur.fetchone()
        if not old:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        old_qtd = float(old.get("quant") or 0)
        old_cod = (old.get("codigo_interno") or "").strip()
        # Com Autorização de Itens exigida, um item ainda NÃO autorizado nunca
        # reservou estoque (ver `_add_item_sync`) — não há o que ajustar aqui.
        # Um item já autorizado JÁ reservou estoque de verdade, então o ajuste
        # pela diferença de quantidade continua necessário normalmente.
        ajustar_estoque = not (_exige_aprovacao_itens_os_ativo(cur) and old.get("data_autorizacao") is None)

        situacao_item = int(req.situacao) if req.situacao is not None else 0
        cur.execute(
            "UPDATE os_produto SET "
            " quant=%s, preco_unitario=%s, p_venda=%s, desconto=%s, acrescimo=%s, "
            " vendedor=%s, executor=%s, descricao_produto_os=%s, situacao=%s, "
            " data_alteracao_item=CAST(GETDATE() AS DATE) "
            "WHERE cod_os_prod=%s AND os=%s",
            (qtd, p_normal, p_venda, desc, acr, req.vendedor, req.executor,
             complemento, situacao_item, cod_os_prod, codigo),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        # Ajusta a reserva pela diferença de quantidade (só se já reservada).
        if ajustar_estoque:
            _mover_estoque(cur, old_cod, qtd - old_qtd, "reservado_os")
        novo_total = _recalc_os_total(cur, codigo)
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


def _delete_item_sync(servidor: str, banco: str, codigo: int, cod_os_prod: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        # Captura qtd/produto antes de excluir p/ estornar a reserva de estoque.
        cur.execute("SELECT quant, codigo_interno, data_autorizacao FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                    (cod_os_prod, codigo))
        old = cur.fetchone()
        if not old:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        ja_autorizado = old.get("data_autorizacao") is not None
        estornar_estoque = not (_exige_aprovacao_itens_os_ativo(cur) and not ja_autorizado)
        if ja_autorizado:
            # Limpeza da trilha de auditoria — o item que ela referencia não
            # vai mais existir (mesmo espírito do CmdRemAut_Click do legado,
            # que também remove a linha de os_autorizacao_itens ao desfazer).
            cur.execute("DELETE FROM os_autorizacao_itens WHERE cod_os_prod_autorizacao=%s", (cod_os_prod,))
        cur.execute("DELETE FROM os_produto WHERE cod_os_prod=%s AND os=%s", (cod_os_prod, codigo))
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        # Estorno: qtd += quant ; reservado_os -= quant (delta negativo) — só
        # quando o item de fato tinha reserva de estoque (ver `_add_item_sync`).
        if estornar_estoque:
            _mover_estoque(cur, (old.get("codigo_interno") or "").strip(),
                           -float(old.get("quant") or 0), "reservado_os")
        novo_total = _recalc_os_total(cur, codigo)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover item: {e}"}


def _tem_area_estoque(cur, produto: str, usuario: "int | None") -> bool:
    """True se `usuario` pode autorizar/expedir itens da área de estoque do
    `produto` (`pecas.area` -> `funcionarios_area.func/area`, migração de
    `FrmTraOsNew.frm`'s checagem "funcionario nao tem permissao para
    autorizar itens dessa area de estoque"). Sentinelas de sistema (master
    -2, ou usuário não informado) sempre passam — mesmo espírito de "Master
    tem acesso total" já usado no resto do projeto; aqui é uma restrição de
    ESCOPO DE DADOS por funcionário comum, não uma permissão de tela."""
    if not usuario or usuario <= 0:
        return True
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM pecas p JOIN funcionarios_area fa ON fa.area = p.area "
        "WHERE p.codigo_int=%s AND fa.func=%s",
        (produto, usuario),
    )
    return cur.fetchone() is not None


def _autorizar_itens_sync(req: AutorizacaoItensRequest, codigo: int) -> dict:
    """Autorizar itens (Command..._Click "Autorizar", aba "Autorização de
    Itens") — em lote. Só autoriza item ainda não autorizado (e, quando a
    empresa exige Expedição, já expedido antes — ordem confirmada no
    código-fonte: Expedição sempre vem antes da Autorização em si). É AQUI
    que o estoque de fato é reservado quando `exige_aprovacao_itens_os`
    está ligada (ver `_add_item_sync`, que pula a reserva na inclusão
    nesse caso). Cria 1 registro em `os_autorizacao` por lote + 1 linha em
    `os_autorizacao_itens` por item autorizado (trilha de auditoria,
    mesma estrutura do legado)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        if not req.cod_os_prod:
            conn.close()
            return {"success": False, "message": "Nenhum item selecionado."}
        exige_exp = _exige_expedicao_itens_os_ativo(cur)
        cod_autorizacao = None
        autorizados: list[int] = []
        bloqueados: list[int] = []
        for cod_os_prod in req.cod_os_prod:
            cur.execute(
                "SELECT quant, codigo_interno, data_autorizacao, data_expedicao FROM os_produto "
                "WHERE cod_os_prod=%s AND os=%s AND ISNULL(item_cancelado,0)=0",
                (cod_os_prod, codigo),
            )
            item = cur.fetchone()
            if not item or item.get("data_autorizacao") is not None:
                bloqueados.append(cod_os_prod)
                continue
            if exige_exp and item.get("data_expedicao") is None:
                bloqueados.append(cod_os_prod)
                continue
            produto = (item.get("codigo_interno") or "").strip()
            if not _tem_area_estoque(cur, produto, req.usuario_alteracao):
                bloqueados.append(cod_os_prod)
                continue
            if cod_autorizacao is None:
                cur.execute(
                    "INSERT INTO os_autorizacao (computador, info) OUTPUT INSERTED.cod_os_autorizacao VALUES (%s, %s)",
                    ("WEB", f"OS {codigo} autorizada via web"),
                )
                row = cur.fetchone()
                cod_autorizacao = int(row["cod_os_autorizacao"] if isinstance(row, dict) else row[0])
            cur.execute(
                "INSERT INTO os_autorizacao_itens (cod_os_autorizacao, cod_os_prod_autorizacao) VALUES (%s, %s)",
                (cod_autorizacao, cod_os_prod),
            )
            cur.execute(
                "UPDATE os_produto SET usuario_autorizacao=%s, hora_autorizacao=CONVERT(NVARCHAR(8),GETDATE(),108), "
                " data_autorizacao=CAST(GETDATE() AS DATE), qtd_autorizada=quant WHERE cod_os_prod=%s",
                (req.usuario_alteracao, cod_os_prod),
            )
            _mover_estoque(cur, produto, float(item.get("quant") or 0), "reservado_os")
            autorizados.append(cod_os_prod)
        conn.commit()
        cur.close()
        conn.close()
        message = None
        if bloqueados:
            message = (
                "Alguns itens não foram autorizados: já autorizados, sem autorização de expedição "
                "prévia (quando exigida), ou funcionário sem permissão para a área de estoque do produto."
            )
        return {"success": True, "autorizados": autorizados, "bloqueados": bloqueados, "message": message}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao autorizar itens: {e}"}


def _remover_autorizacao_sync(req: AutorizacaoItensRequest, codigo: int) -> dict:
    """Remover Autorização (CmdRemAut_Click) — desfaz a autorização de
    itens já autorizados, removendo a trilha de auditoria e estornando o
    estoque reservado na Autorização."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        removidos: list[int] = []
        for cod_os_prod in req.cod_os_prod:
            cur.execute(
                "SELECT quant, codigo_interno, data_autorizacao FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                (cod_os_prod, codigo),
            )
            item = cur.fetchone()
            if not item or item.get("data_autorizacao") is None:
                continue
            cur.execute("DELETE FROM os_autorizacao_itens WHERE cod_os_prod_autorizacao=%s", (cod_os_prod,))
            cur.execute(
                "UPDATE os_produto SET usuario_autorizacao=NULL, hora_autorizacao=NULL, "
                " data_autorizacao=NULL, qtd_autorizada=0 WHERE cod_os_prod=%s",
                (cod_os_prod,),
            )
            _mover_estoque(cur, (item.get("codigo_interno") or "").strip(), -float(item.get("quant") or 0), "reservado_os")
            removidos.append(cod_os_prod)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "removidos": removidos}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover autorização: {e}"}


def _expedir_itens_sync(req: AutorizacaoItensRequest, codigo: int) -> dict:
    """Autorização de Expedição (CmdExpedicao_Click) — registra o
    picking/separação física do item no estoque. NÃO movimenta estoque
    (confirmado no código-fonte — a linha de movimentação de estoque desse
    botão está desativada/comentada no legado); só a Autorização em si
    move o estoque de verdade. Só permite item ainda não autorizado e
    ainda não expedido."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        expedidos: list[int] = []
        bloqueados: list[int] = []
        for cod_os_prod in req.cod_os_prod:
            cur.execute(
                "SELECT codigo_interno, data_autorizacao, data_expedicao FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                (cod_os_prod, codigo),
            )
            item = cur.fetchone()
            if not item or item.get("data_autorizacao") is not None or item.get("data_expedicao") is not None:
                bloqueados.append(cod_os_prod)
                continue
            produto = (item.get("codigo_interno") or "").strip()
            if not _tem_area_estoque(cur, produto, req.usuario_alteracao):
                bloqueados.append(cod_os_prod)
                continue
            cur.execute(
                "UPDATE os_produto SET usuario_expedicao=%s, hora_expedicao=CONVERT(NVARCHAR(8),GETDATE(),108), "
                " data_expedicao=CAST(GETDATE() AS DATE) WHERE cod_os_prod=%s",
                (req.usuario_alteracao, cod_os_prod),
            )
            expedidos.append(cod_os_prod)
        conn.commit()
        cur.close()
        conn.close()
        message = None
        if bloqueados:
            message = "Alguns itens não foram expedidos: já autorizados/expedidos, ou funcionário sem permissão para a área de estoque do produto."
        return {"success": True, "expedidos": expedidos, "bloqueados": bloqueados, "message": message}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao expedir itens: {e}"}


def _remover_expedicao_sync(req: AutorizacaoItensRequest, codigo: int) -> dict:
    """Remover Autorização de Expedição (CmdRemExpedicao_Click) — só item
    já expedido e ainda não autorizado (uma vez autorizado, a expedição
    não pode mais ser desfeita isoladamente — precisa remover a
    autorização primeiro). Não mexe em estoque (expedição nunca mexeu)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        removidos: list[int] = []
        for cod_os_prod in req.cod_os_prod:
            cur.execute(
                "SELECT data_expedicao, data_autorizacao FROM os_produto WHERE cod_os_prod=%s AND os=%s",
                (cod_os_prod, codigo),
            )
            item = cur.fetchone()
            if not item or item.get("data_expedicao") is None or item.get("data_autorizacao") is not None:
                continue
            cur.execute(
                "UPDATE os_produto SET usuario_expedicao=NULL, hora_expedicao=NULL, "
                " data_expedicao=NULL, qtd_autorizada=0 WHERE cod_os_prod=%s",
                (cod_os_prod,),
            )
            removidos.append(cod_os_prod)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "removidos": removidos}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover autorização de expedição: {e}"}


async def autorizar_itens(req: AutorizacaoItensRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_autorizar_itens_sync, req, codigo)


async def remover_autorizacao_itens(req: AutorizacaoItensRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_remover_autorizacao_sync, req, codigo)


async def expedir_itens(req: AutorizacaoItensRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_expedir_itens_sync, req, codigo)


async def remover_expedicao_itens(req: AutorizacaoItensRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_remover_expedicao_sync, req, codigo)


def _save_pontuacao_sync(req: PontuacaoSaveRequest, codigo: int, cod_os_prod: int) -> dict:
    """Pontuação de Técnicos (migração de Command36_Click, frame
    "Pontuação" em `frmtraosa.frm`) — nota 0-999 (máscara "999" do
    legado) pro Executor/Vendedor/Atendente daquele item. Diferente do
    CRUD normal de item, NÃO exige a O.S. estar Aberta — o legado permite
    pontuar itens de qualquer situação (a pontuação é uma avaliação de
    desempenho, não uma alteração do pedido em si)."""
    for campo, valor in (("Executor", req.pontuacao_e), ("Vendedor", req.pontuacao_v), ("Atendente", req.pontuacao_a)):
        if valor is not None and not (0 <= valor <= 999):
            return {"success": False, "message": f"Pontuação de {campo} deve estar entre 0 e 999."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os_produto WHERE cod_os_prod=%s AND os=%s", (cod_os_prod, codigo))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Item não encontrado."}
        cur.execute(
            "UPDATE os_produto SET Pontuacao_E=%s, Pontuacao_V=%s, Pontuacao_A=%s WHERE cod_os_prod=%s AND os=%s",
            (req.pontuacao_e, req.pontuacao_v, req.pontuacao_a, cod_os_prod, codigo),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar pontuação: {e}"}


async def save_pontuacao(req: PontuacaoSaveRequest, codigo: int, cod_os_prod: int) -> dict:
    return await asyncio.to_thread(_save_pontuacao_sync, req, codigo, cod_os_prod)


async def list_itens(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_itens_sync, servidor, banco, codigo)


async def add_item(req: OSItemSaveRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_add_item_sync, req, codigo)


async def update_item(req: OSItemSaveRequest, codigo: int, cod_os_prod: int) -> dict:
    return await asyncio.to_thread(_update_item_sync, req, codigo, cod_os_prod)


async def delete_item(servidor: str, banco: str, codigo: int, cod_os_prod: int) -> dict:
    return await asyncio.to_thread(_delete_item_sync, servidor, banco, codigo, cod_os_prod)


# ---------- Descontos concedidos & Análise de margem ----------
def _list_descontos_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Lê os itens da OS com desconto > 0 (descontos concedidos)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.cod_os_prod, i.codigo_interno, i.quant, i.preco_unitario, i.desconto, "
            "       pe.descricao AS peca_desc, sv.descricao AS serv_desc "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE i.os=%s AND ISNULL(i.item_cancelado,0)=0 AND ISNULL(i.desconto,0) > 0 "
            "ORDER BY i.cod_os_prod",
            (codigo,),
        )
        items = []
        total = 0.0
        for r in cur.fetchall():
            qtd = float(r.get("quant") or 0)
            desc_unit = float(r.get("desconto") or 0)
            p_normal = float(r.get("preco_unitario") or 0)
            valor_total = round(desc_unit * qtd, 2)
            total += valor_total
            pct = round(desc_unit / p_normal * 100, 2) if p_normal > 0 else 0
            desc = (r.get("peca_desc") or r.get("serv_desc") or r.get("codigo_interno") or "Item")
            items.append({
                "cod": int(r["cod_os_prod"]),
                "tipo_label": "Item",
                "descricao": (desc or "").strip(),
                "percentual": pct,
                "valor_unitario": desc_unit,
                "qtd": qtd,
                "valor_total": valor_total,
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": round(total, 2)}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


def _analise_sync(servidor: str, banco: str, codigo: int) -> dict:
    """Análise de margem & descontos da OS, calculada a partir de os_produto.
    venda = quant*p_venda; desconto = quant*desconto; custo = quant*custo_os."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT i.cod_os_prod, i.codigo_interno, i.quant, i.p_venda, i.preco_unitario, "
            "       i.desconto, i.custo_os, "
            "       pe.descricao AS peca_desc, sv.descricao AS serv_desc "
            "FROM os_produto i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE i.os=%s AND ISNULL(i.item_cancelado,0)=0 "
            "ORDER BY i.cod_os_prod",
            (codigo,),
        )
        itens = []
        t_venda = t_desc = t_custo = 0.0
        for r in cur.fetchall():
            qtd = float(r.get("quant") or 0)
            pv = float(r.get("p_venda") or 0)
            desc_unit = float(r.get("desconto") or 0)
            custo_unit = float(r.get("custo_os") or 0)
            venda = round(qtd * pv, 2)
            desconto = round(qtd * desc_unit, 2)
            custo = round(qtd * custo_unit, 2)
            margem = round(venda - custo, 2)
            margem_pct = round(margem / venda * 100, 2) if venda > 0 else 0.0
            t_venda += venda
            t_desc += desconto
            t_custo += custo
            desc = (r.get("peca_desc") or r.get("serv_desc") or r.get("codigo_interno") or "Item")
            itens.append({
                "cod": int(r["cod_os_prod"]),
                "descricao": (desc or "").strip(),
                "qtd": qtd,
                "venda": venda,
                "desconto": desconto,
                "custo": custo,
                "margem": margem,
                "margem_pct": margem_pct,
            })
        cur.close()
        conn.close()
        t_margem = round(t_venda - t_custo, 2)
        t_pct = round(t_margem / t_venda * 100, 2) if t_venda > 0 else 0.0
        return {
            "success": True,
            "itens": itens,
            "totais": {
                "venda": round(t_venda, 2),
                "desconto": round(t_desc, 2),
                "custo": round(t_custo, 2),
                "margem": t_margem,
                "margem_pct": t_pct,
                "qtd_itens": len(itens),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def list_descontos(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_descontos_sync, servidor, banco, codigo)


async def analise(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_analise_sync, servidor, banco, codigo)


# ---------- Desconto geral (distribuído entre os itens) ----------
def _aplicar_desconto_geral_sync(req, codigo: int) -> dict:
    from services.controle_service import _get_limites_sync
    from services.descontos_service import _limite_por_funcao
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}

        valor = float(req.valor or 0)
        if valor < 0:
            conn.close()
            return {"success": False, "message": "Valor inválido."}

        cur.execute(
            "SELECT cod_os_prod, preco_unitario, acrescimo, quant FROM os_produto "
            "WHERE os=%s AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
        itens = cur.fetchall()
        if not itens:
            conn.close()
            return {"success": False, "message": "OS sem itens para aplicar desconto."}

        # base = soma dos itens a preço cheio (preco_unitario * quant)
        base = sum(float(it.get("preco_unitario") or 0) * float(it.get("quant") or 0) for it in itens)
        if valor > 0 and base <= 0:
            conn.close()
            return {"success": False, "message": "Itens sem valor para distribuir o desconto."}

        pct_efetivo = round(valor / base * 100, 4) if base > 0 else 0
        if valor > 0:
            lim = _get_limites_sync(req.servidor, req.banco)
            limite = _limite_por_funcao(lim, int(req.funcao or 1))
            usuario = req.usuario_codigo if req.usuario_codigo is not None else -2
            if usuario != -2 and limite > 0 and pct_efetivo > limite + 1e-6:
                conn.close()
                return {"success": False, "message": f"Desconto ({pct_efetivo:g}%) acima do limite ({limite:g}%) para sua função."}
            if valor > base + 1e-6:
                conn.close()
                return {"success": False, "message": "Desconto maior que o total dos itens."}

        for it in itens:
            cod = int(it["cod_os_prod"])
            p_normal = float(it.get("preco_unitario") or 0)
            acr = float(it.get("acrescimo") or 0)
            desconto_unit = round(valor * p_normal / base, 2) if (valor > 0 and base > 0) else 0.0
            p_venda = round(p_normal - desconto_unit + acr, 4)
            cur.execute(
                "UPDATE os_produto SET desconto=%s, p_venda=%s, "
                "data_alteracao_item=CAST(GETDATE() AS DATE) WHERE cod_os_prod=%s AND os=%s",
                (desconto_unit, p_venda, cod, codigo),
            )
        novo_total = _recalc_os_total(cur, codigo)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total, "valor": valor, "percentual": pct_efetivo}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao aplicar desconto geral: {e}"}


async def aplicar_desconto_geral(req, codigo: int) -> dict:
    return await asyncio.to_thread(_aplicar_desconto_geral_sync, req, codigo)


def _alterar_executor_sync(req: AlterarExecutorRequest, codigo: int, cod_os_prod: int) -> dict:
    """Alteração de Executor/Vendedor pós-fechamento (`CmdAltExec`, branch
    F/PG de `CmDaltera_Click`, `Revenda\\FrmTraOsNew.frm`, linhas
    7815-7877) — corrige o técnico executor (e o vendedor) de um item já
    lançado, com a O.S. Fechada ou Faturada, sem reabrir a O.S. Só esses 2
    campos — diferente da edição normal do item (`_update_item_sync`),
    que exige `situacao='A'` e mexe em preço/quantidade/desconto.

    **Só permitida com a O.S. Fechada ('F') ou Faturada ('PG')** — 'A' usa
    a edição normal (já cobre vendedor/executor); 'C' bloqueia sempre
    (mesma checagem do legado).

    Propagação opcional (`propagar_demais`): réplica de "Deseja Alterar os
    demais executores/vendedores?" do legado — aplica o mesmo novo valor
    aos DEMAIS itens da mesma O.S. que tinham o MESMO valor anterior. Só
    propaga um campo se ele de fato mudou E o valor anterior não era vazio
    (evita um `UPDATE` largo demais pegando todo item sem
    executor/vendedor definido — o legado não tinha essa segunda guarda,
    mas sem ela um item com executor NULL "contaminaria" outros itens
    também sem executor, o que não é a intenção da propagação).

    Sem checagem de permissão server-side — mesmo padrão do resto deste
    arquivo (ADD_ITEM/EDIT_ITEM/PONTUACAO/AUTORIZAR também só gateiam no
    frontend, via `can("OS_COMP.ALT_EXECUTOR")`).

    **Não implementado** (sem equivalente nesta migração — nenhum módulo
    de comissão existe ainda): `ITEM_COMISSAO_VENDEDOR`/
    `ITEM_COMISSAO_EXECUTOR`, `movimentacao.item_paga_comissao`,
    `MOVIMENTACAO.VENDEDOR` via `COMANDA_OS`. Ver PENDENCIAS.md > "O.S.
    Completa" > "Alteração de Executor pós-fechamento" pro racional
    completo (inclusive o achado de que a comissão no legado é calculada
    AO VIVO de `os_produto.executor`, então essa troca lá tem efeito
    retroativo real em qualquer cálculo de comissão rodado depois)."""
    if req.vendedor is None and req.executor is None:
        return {"success": False, "message": "Nada para alterar."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
        os_row = cur.fetchone()
        if not os_row:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (os_row.get("situacao") or "").strip().upper()
        if sit not in ("F", "PG"):
            conn.close()
            return {
                "success": False,
                "message": "Alteração de Executor pós-fechamento só é permitida com a O.S. Fechada ou Faturada.",
            }

        cur.execute(
            "SELECT vendedor, executor FROM os_produto WHERE cod_os_prod=%s AND os=%s",
            (cod_os_prod, codigo),
        )
        item = cur.fetchone()
        if not item:
            conn.close()
            return {"success": False, "message": "Item não encontrado."}

        exec_anterior = item.get("executor")
        vend_anterior = item.get("vendedor")
        novo_executor = req.executor if req.executor is not None else exec_anterior
        novo_vendedor = req.vendedor if req.vendedor is not None else vend_anterior

        cur.execute(
            "UPDATE os_produto SET executor=%s, vendedor=%s WHERE cod_os_prod=%s AND os=%s",
            (novo_executor, novo_vendedor, cod_os_prod, codigo),
        )

        propagados: list[int] = []
        if req.propagar_demais:
            if novo_executor != exec_anterior and exec_anterior:
                cur.execute(
                    "SELECT cod_os_prod FROM os_produto WHERE os=%s AND executor=%s AND cod_os_prod<>%s",
                    (codigo, exec_anterior, cod_os_prod),
                )
                outros = [int(r["cod_os_prod"]) for r in cur.fetchall()]
                if outros:
                    cur.execute(
                        "UPDATE os_produto SET executor=%s WHERE os=%s AND executor=%s AND cod_os_prod<>%s",
                        (novo_executor, codigo, exec_anterior, cod_os_prod),
                    )
                    propagados.extend(outros)
            if novo_vendedor != vend_anterior and vend_anterior:
                cur.execute(
                    "SELECT cod_os_prod FROM os_produto WHERE os=%s AND vendedor=%s AND cod_os_prod<>%s",
                    (codigo, vend_anterior, cod_os_prod),
                )
                outros_v = [int(r["cod_os_prod"]) for r in cur.fetchall()]
                if outros_v:
                    cur.execute(
                        "UPDATE os_produto SET vendedor=%s WHERE os=%s AND vendedor=%s AND cod_os_prod<>%s",
                        (novo_vendedor, codigo, vend_anterior, cod_os_prod),
                    )
                    for c in outros_v:
                        if c not in propagados:
                            propagados.append(c)

        conn.commit()
        cur.close()
        conn.close()
        return {
            "success": True,
            "executor_anterior": exec_anterior,
            "vendedor_anterior": vend_anterior,
            "propagados": propagados,
        }
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao alterar executor/vendedor: {e}"}


async def alterar_executor(req: AlterarExecutorRequest, codigo: int, cod_os_prod: int) -> dict:
    return await asyncio.to_thread(_alterar_executor_sync, req, codigo, cod_os_prod)
