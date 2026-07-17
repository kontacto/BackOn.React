"""Pedido Completo (web) — cabeçalho + itens sobre a MESMA tabela
`pedido_venda`/`pedido_venda_prod` do Pedido rápido mobile
(`pedidos_service.py`/`itens_service.py`), Fase A (núcleo) do plano
faseado em PENDENCIAS.md > "Transações" > "Pedido Completo".

Arquivo próprio, deliberadamente sem alterar `pedidos_service.py`/
`itens_service.py` — a tela rápida mobile continua com seu próprio
conjunto (menor) de campos e sua própria lógica de Fechar, comprovada em
uso. Aqui vive só o que é genuinamente NOVO/maior pro Pedido Completo:
- Cabeçalho com o conjunto de campos real de `frmmanpedfor.frm` (Frame2):
  forma_pag, local_entrega, previsao_entrega, num_ped_cliente, infoentrega
  — nenhum existe no fluxo rápido.
- Item com a cadeia de resolução mais rica (`_resolve_produto_completo`) e
  expansão de kit (`_kit_componentes`), ver `pedido_common.py`.
- Cancelar (não existe no fluxo rápido).
Consulta/edição/exclusão de item individual, e o Fechar em si (mesma regra
A->F, mesma baixa de estoque), são idênticos ao fluxo rápido — reaproveitados
diretamente de `itens_service`/`pedidos_service` pelas rotas
(`routes/pedido_completo.py`), não duplicados aqui.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import PedidoCompletoSaveRequest, ItemSaveRequest, FecharRequest
from services.constants import SITUACAO_LABEL
from services.descontos_service import _validar_limite_desconto, _log_desconto_item
from services.pedido_common import (
    _check_cliente_ativo, _check_pedido_aberto, _item_total, _recalc_pedido_total,
    _modulo_servicos_ativo, _mover_estoque, _resolve_produto_completo, _kit_componentes,
    _ensure_hora_inclusao_item_col, _fechar_pedido_itens,
)
from services.permissoes_service import tem_permissao
from services.itens_service import TAXA_SERVICO_CODIGO, sincroniza_taxa_servico_apos_alteracao


def _get_pedido_completo_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.pedido, p.cliente, p.data, p.validade, p.vendedor, p.hora_aberto, "
            "       p.obs, p.situacao, p.total, p.NOME_CLIENTE, p.TELEFONE_CLIENTE, p.area_atuacao, "
            "       p.forma_pag, p.local_entrega, p.previsao_entrega, p.num_ped_cliente, p.infoentrega, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       f.nome AS vendedor_nome, a.descricao AS area_descricao, fp.descricao AS forma_pag_descricao "
            "FROM pedido_venda p "
            "LEFT JOIN cliente c ON c.codigo = p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            "LEFT JOIN area_atuacao a ON a.area = p.area_atuacao "
            "LEFT JOIN forma_pagamento fp ON fp.codigo = p.forma_pag "
            "WHERE p.pedido = %s",
            (pedido,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (row.get("situacao") or "").strip().upper()
        return {
            "success": True,
            "pedido": {
                "pedido": int(row["pedido"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or row.get("NOME_CLIENTE") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data"].isoformat() if row.get("data") else None,
                "validade": row["validade"].isoformat() if row.get("validade") else None,
                "vendedor": int(row["vendedor"] or 0) if row.get("vendedor") else None,
                "vendedor_nome": (row.get("vendedor_nome") or "").strip(),
                "hora_aberto": (row.get("hora_aberto") or "").strip(),
                "obs": row.get("obs") or "",
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(row.get("total") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
                "forma_pag": (row.get("forma_pag") or "").strip(),
                "forma_pag_descricao": (row.get("forma_pag_descricao") or "").strip(),
                "local_entrega": row.get("local_entrega") or "",
                "previsao_entrega": row["previsao_entrega"].isoformat() if row.get("previsao_entrega") else None,
                "num_ped_cliente": (row.get("num_ped_cliente") or "").strip(),
                "infoentrega": row.get("infoentrega") or "",
                "editavel": sit == "A",
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_pedido_completo_sync(req: PedidoCompletoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        sit_atual = None
        if pedido_codigo is not None:
            cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido_codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            # Regra real (frmmanpedfor.frm): pedido Fechado só permite editar
            # vendedor/forma de pagamento; Aberto permite editar tudo.
            if sit_atual not in ("A", "F"):
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"Pedido com situação '{label}' não pode ser alterado."}
        else:
            ok, label = _check_cliente_ativo(cur, req.cliente)
            if not ok:
                conn.close()
                return {
                    "success": False,
                    "message": f"Cliente com situação '{label}' não pode gerar novo pedido.",
                }

        cur.execute(
            "SELECT TOP 1 c.nome, "
            "  COALESCE((SELECT TOP 1 LTRIM(RTRIM(CAST(ddd AS NVARCHAR(4))) + tel) "
            "            FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia), "
            "           LTRIM(RTRIM(CAST(c.ddd_cli AS NVARCHAR(4))) + ISNULL(c.telefone_cli,''))) AS tel "
            "FROM cliente c WHERE c.codigo = %s",
            (req.cliente,),
        )
        cli_row = cur.fetchone() or {}
        nome_cli = (cli_row.get("nome") or "").strip()[:60]
        tel_cli = (cli_row.get("tel") or "").strip()[:60]

        validade = req.validade or None
        previsao_entrega = req.previsao_entrega or None
        obs = req.obs or ""
        forma_pag = (req.forma_pag or "")[:3]
        local_entrega = req.local_entrega or ""
        infoentrega = req.infoentrega or ""
        num_ped_cliente = (req.num_ped_cliente or "")[:64]

        if pedido_codigo is None:
            cur.execute(
                "INSERT INTO pedido_venda "
                "(cliente, data, validade, vendedor, forma_pag, previsao_entrega, local_entrega, "
                " infoentrega, num_ped_cliente, hora_aberto, obs, situacao, "
                " NOME_CLIENTE, TELEFONE_CLIENTE, abertopor, total, tipo, area_atuacao) "
                "OUTPUT INSERTED.pedido "
                "VALUES (%s, CAST(GETDATE() AS DATE), %s, %s, %s, %s, %s, "
                "        %s, %s, CONVERT(NVARCHAR(8), GETDATE(), 108), %s, 'A', %s, %s, %s, 0, 0, %s)",
                (
                    req.cliente, validade, req.vendedor, forma_pag, previsao_entrega, local_entrega,
                    infoentrega, num_ped_cliente, obs, nome_cli, tel_cli, req.vendedor, req.area_atuacao,
                ),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter número do pedido."}
            pedido_id = int(row["pedido"] if isinstance(row, dict) else row[0])
        elif sit_atual == "F":
            # Fechado: só vendedor/forma_pag são editáveis (regra real do legado).
            cur.execute(
                "UPDATE pedido_venda SET vendedor=%s, forma_pag=%s WHERE pedido=%s",
                (req.vendedor, forma_pag, pedido_codigo),
            )
            pedido_id = pedido_codigo
        else:
            cur.execute(
                "UPDATE pedido_venda SET "
                " cliente=%s, validade=%s, vendedor=%s, forma_pag=%s, previsao_entrega=%s, "
                " local_entrega=%s, infoentrega=%s, num_ped_cliente=%s, obs=%s, "
                " NOME_CLIENTE=%s, TELEFONE_CLIENTE=%s, area_atuacao=%s "
                "WHERE pedido=%s",
                (
                    req.cliente, validade, req.vendedor, forma_pag, previsao_entrega,
                    local_entrega, infoentrega, num_ped_cliente, obs,
                    nome_cli, tel_cli, req.area_atuacao, pedido_codigo,
                ),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            pedido_id = pedido_codigo
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "pedido": pedido_id}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _add_item_completo_sync(req: ItemSaveRequest, pedido: int) -> dict:
    """Como `itens_service._add_item_sync`, mas com a cadeia de resolução
    mais rica (`_resolve_produto_completo`) e expansão de kit
    (`produtos_compostos`) — ver docstring do módulo."""
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
        _ensure_hora_inclusao_item_col(cur)

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
        prod = _resolve_produto_completo(cur, codigo)
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

        componentes = _kit_componentes(cur, prod["codigo"]) if prod["tipo"] == "P" else []
        codautos: list[int] = []

        if componentes:
            # Kit: expande em N linhas (uma por componente), sem gravar linha
            # própria pro código principal — regra real (não workaround), ver
            # PENDENCIAS.md > "Pedido Completo" item 3.
            for comp in componentes:
                sub_codigo = (comp.get("vinculado") or "").strip()
                sub = _resolve_produto_completo(cur, sub_codigo)
                if not sub:
                    conn.rollback()
                    conn.close()
                    return {"success": False, "message": f"Componente '{sub_codigo}' do kit '{prod['codigo']}' não encontrado."}
                sub_qtd = round(qtd * float(comp.get("qtd") or 0), 4)
                if sub_qtd <= 0:
                    continue
                valor_no_kit = comp.get("valor_no_kit")
                p_normal = float(valor_no_kit) if valor_no_kit is not None else sub["valor"]
                p_venda = round(p_normal, 4)
                descricao = (comp.get("descricao_no_kit") or "").strip() or sub["descricao"]
                cur.execute(
                    "INSERT INTO pedido_venda_prod "
                    "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                    " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                    " hora_inclusao_item, Produto_composto) "
                    "OUTPUT INSERTED.codauto "
                    "VALUES (%s,%s,%s,%s,%s,0,0,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                    "        CONVERT(NVARCHAR(8), GETDATE(), 108),%s)",
                    (pedido, sub["codigo"], sub_qtd, p_venda, p_normal, sub["custo"], descricao, sub["unidade"], prod["codigo"][:8]),
                )
                row = cur.fetchone()
                codautos.append(int(row["codauto"] if isinstance(row, dict) else row[0]))
            if not codautos:
                conn.close()
                return {"success": False, "message": "Kit sem componentes válidos para a quantidade informada."}
        else:
            p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
            p_normal = float(p_normal or 0)
            desc = float(req.desconto or 0)
            acr = float(req.acrescimo or 0)
            if desc and not prod.get("aceita_desconto", True):
                conn.close()
                return {"success": False, "message": f"Produto '{prod['codigo']}' não aceita desconto."}
            lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
            if lim_err:
                conn.close()
                return {"success": False, "message": lim_err}
            p_venda = round(p_normal - desc + acr, 4)
            complemento = (req.complemento or "").strip()
            cur.execute(
                "INSERT INTO pedido_venda_prod "
                "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
                " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item, "
                " hora_inclusao_item) "
                "OUTPUT INSERTED.codauto "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE),"
                "        CONVERT(NVARCHAR(8), GETDATE(), 108))",
                (pedido, prod["codigo"], qtd, p_venda, p_normal, desc, acr, prod["custo"], complemento, prod["unidade"]),
            )
            row = cur.fetchone()
            codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
            codautos.append(codauto)
            _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)

        # `prod["codigo"]`/componentes do kit nunca são TAXA_SERVICO_CODIGO
        # aqui — bloqueado mais acima.
        sincroniza_taxa_servico_apos_alteracao(cur, pedido)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codautos": codautos, "kit": bool(componentes), "total": novo_total}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _fechar_pedido_completo_sync(req: FecharRequest, pedido: int) -> dict:
    """Igual à regra de Fechar do Pedido rápido (A->F + valida/ajusta forma
    de pagamento + baixa de estoque das peças — via `_fechar_pedido_itens`,
    compartilhado com `pedidos_service.py` pra não duplicar a lógica), mas
    checando a permissão própria da tela PEDIDO_COMP."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, total, forma_pag FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser fechado."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO_COMP", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar o pedido."}
        erro = _fechar_pedido_itens(cur, pedido, float(ex.get("total") or 0), (ex.get("forma_pag") or "").strip())
        if erro:
            conn.close()
            return {"success": False, "message": erro}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pedido Fechado.", "situacao": "F"}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar: {e}"}


def _cancelar_pedido_completo_sync(req: FecharRequest, pedido: int) -> dict:
    """Cancela o pedido (situação -> 'C'), alcançável de 'A' ou 'F' (regra
    real, ver PENDENCIAS.md item 11). Se estava Fechado, estorna a reserva de
    estoque das peças (reverso exato de `_mover_estoque` no Fechar).

    Deliberadamente NÃO replicados (workaround/fora de escopo Fase A, ver
    "Não replicar truques VB6" e PENDENCIAS.md): senha de gerente (substituída
    pelo sistema de permissões já existente), limpeza de agendamento vinculado
    (módulo Clínica não migrado ainda) e cancelamento prévio no Tray
    (integração Tray não migrada ainda — pedidos desta fase nunca têm origem
    Tray)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser cancelado."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO_COMP", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para cancelar o pedido."}
        if sit == "F":
            cur.execute(
                "SELECT produto, qtd_pedida FROM pedido_venda_prod "
                "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
                (pedido,),
            )
            for it in cur.fetchall():
                _mover_estoque(cur, (it.get("produto") or "").strip(), -float(it.get("qtd_pedida") or 0), "reservado")
        cur.execute("UPDATE pedido_venda SET situacao='C' WHERE pedido=%s", (pedido,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pedido Cancelado.", "situacao": "C"}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao cancelar: {e}"}


async def get_pedido_completo(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_get_pedido_completo_sync, servidor, banco, pedido)


async def save_pedido_completo(req: PedidoCompletoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_pedido_completo_sync, req, pedido_codigo)


async def add_item_completo(req: ItemSaveRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_add_item_completo_sync, req, pedido)


async def fechar_pedido_completo(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_fechar_pedido_completo_sync, req, pedido)


async def cancelar_pedido_completo(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_cancelar_pedido_completo_sync, req, pedido)
