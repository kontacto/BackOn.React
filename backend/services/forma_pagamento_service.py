"""Forma de Pagamento (FrmForPag.frm) — lançamento de múltiplas formas
quando o combobox simples do cabeçalho (`forma_pag`/`forma_pagamento`) não
é suficiente. Tela genérica no legado (`Type_FormaPagPedOS`), reaproveitada
por Pedido Bar, Pedido Completo e O.S. — aqui replicada com o mesmo
`tipo_dav` (PED/OS) central que `pedido_common.DavPagamento` já usa pras
funções de totalização/validação (mesmo "type global" do Gestor de
Documentos, `GRUPO_*`/`_JUNCAO`, aplicado a este domínio).

8 tipos (`forma_pagamento.tipo`), cada um numa tabela própria com colunas
específicas — mapas em `pedido_common.py`. Este service é a camada de CRUD
por trás do modal (listar/lançar/editar/excluir); a validação de total no
fechamento do documento vive em `_fecha_fpag_dav`/`_fechar_pedido_itens`
(pedido_common.py) — não duplicada aqui.

Simplificações conscientes em relação ao legado (registradas em
PENDENCIAS.md): a grade de rateio manual de parcelas sem `forma_pag_prazo`
cadastrado (`FrmFaturado`) não foi portada — Duplicata sem prazo configurado
grava 1 parcela só, com vencimento ajustável depois editando a linha. O
vínculo com `*_vale_devolucao` (campo condicional "Vale de Devolução")
também não foi portado — feature de baixo uso, fora do escopo desta rodada.
"""
import asyncio

from db.connection import _open_conn, _to_json_safe
from models.schemas import FormaPagamentoAddRequest, FormaPagamentoUpdateRequest, FormaPagamentoDeleteRequest
from services.pedido_common import (
    DAV_PED, DAV_OS, DavPagamento,
    FORMA_PAG_SUFIXO_TIPO, FORMA_PAG_VALOR_COL, FORMA_PAG_VENC_COL,
    _insere_duplicata_parcelada,
)
from services.permissoes_service import tem_permissao

# tipo_dav -> tela do catálogo de permissões (nomes já estabelecidos:
# "PEDIDO" pro Pedido Bar/Completo, "OS" pra Ordem de Serviço).
_TELA_POR_DAV = {DAV_PED: "PEDIDO", DAV_OS: "OS"}


def _campos_extra_tipo(tipo: str, req) -> tuple[list[str], list]:
    """Colunas específicas de cada tipo (além de <fk>/forma_pag/valor/
    vencimento, já tratados genericamente pelo chamador)."""
    if tipo == "CH":
        return (
            ["banco", "agencia", "conta", "numero_ch", "nome_cheque", "telefone"],
            [req.cod_banco, req.agencia, req.conta, req.numero_ch, req.nome_cheque, req.telefone],
        )
    if tipo == "CC":
        return (
            ["num_cartao1", "num_cartao2", "num_cartao3", "num_cartao4", "mes_validade",
             "ano_validade", "parcelas", "COD_ADMINISTRADORA", "COD_PARCELADOR"],
            [req.num_cartao1, req.num_cartao2, req.num_cartao3, req.num_cartao4, req.mes_validade,
             req.ano_validade, req.parcelas, req.cod_administradora, req.cod_parcelador],
        )
    if tipo == "CD":
        return (
            ["banco", "agencia", "conta", "parcelas", "COD_ADMINISTRADORA", "COD_PARCELADOR"],
            [req.cod_banco, req.agencia, req.conta, req.parcelas, req.cod_administradora, req.cod_parcelador],
        )
    if tipo == "FI":
        return (
            ["num_cartao1", "num_cartao2", "num_cartao3", "num_cartao4", "mes_validade", "ano_validade"],
            [req.num_cartao1, req.num_cartao2, req.num_cartao3, req.num_cartao4, req.mes_validade, req.ano_validade],
        )
    return ([], [])


def _insere_forma_manual(cur, dav: DavPagamento, tipo: str, req) -> None:
    tabela = dav.tabela(tipo)
    col = FORMA_PAG_VALOR_COL[tipo]
    venc_col = FORMA_PAG_VENC_COL[tipo]
    campos = [dav.fk, "forma_pag", col]
    valores: list = [dav.documento, req.forma_pag, req.valor]
    if venc_col:
        campos.append(venc_col)
        valores.append(req.vencimento or None)
    extra_campos, extra_valores = _campos_extra_tipo(tipo, req)
    campos += extra_campos
    valores += extra_valores
    placeholders = ",".join(["%s"] * len(valores))
    cur.execute(f"INSERT INTO {tabela} ({','.join(campos)}) VALUES ({placeholders})", tuple(valores))


def _atualiza_forma_manual(cur, dav: DavPagamento, tipo: str, sequencia: int, req) -> int:
    tabela = dav.tabela(tipo)
    col = FORMA_PAG_VALOR_COL[tipo]
    venc_col = FORMA_PAG_VENC_COL[tipo]
    sets = ["forma_pag=%s", f"{col}=%s"]
    valores: list = [req.forma_pag, req.valor]
    if venc_col:
        sets.append(f"{venc_col}=%s")
        valores.append(req.vencimento or None)
    extra_campos, extra_valores = _campos_extra_tipo(tipo, req)
    sets += [f"{c}=%s" for c in extra_campos]
    valores += extra_valores
    valores.append(sequencia)
    cur.execute(f"UPDATE {tabela} SET {','.join(sets)} WHERE sequencia=%s", tuple(valores))
    return cur.rowcount


def _list_formas_pagamento_sync(servidor: str, banco: str, tipo_dav: str, documento: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        dav = DavPagamento(tipo=tipo_dav, documento=documento, situacao="", valor=0, forma_padrao="")
        itens = []
        for tipo, venc_col in FORMA_PAG_VENC_COL.items():
            col = FORMA_PAG_VALOR_COL[tipo]
            venc_sel = f"t.{venc_col} AS vencimento" if venc_col else "NULL AS vencimento"
            cur.execute(
                f"SELECT t.sequencia, t.forma_pag, fp.descricao, t.{col} AS valor, {venc_sel} "
                f"FROM {dav.tabela(tipo)} t LEFT JOIN forma_pagamento fp ON fp.codigo = t.forma_pag "
                f"WHERE t.{dav.fk}=%s ORDER BY t.sequencia",
                (documento,),
            )
            for r in cur.fetchall():
                row = _to_json_safe(r) or {}
                itens.append({
                    "tipo": tipo,
                    "sequencia": int(row["sequencia"]),
                    "forma_pag": (row.get("forma_pag") or "").strip(),
                    "descricao": (row.get("descricao") or "").strip(),
                    "valor": float(row.get("valor") or 0),
                    "vencimento": row.get("vencimento"),
                })
        tabela_doc, col_pk, col_total = (
            ("pedido_venda", "pedido", "total") if tipo_dav == DAV_PED else ("os", "codigo", "valor")
        )
        cur.execute(f"SELECT {col_total} AS total FROM {tabela_doc} WHERE {col_pk}=%s", (documento,))
        prow = cur.fetchone()
        total_documento = float((prow or {}).get("total") or 0)
        total_lancado = round(sum(i["valor"] for i in itens), 2)
        cur.close()
        conn.close()
        return {
            "success": True, "items": itens,
            "total_documento": total_documento, "total_lancado": total_lancado,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _add_forma_pagamento_sync(req: FormaPagamentoAddRequest, documento: int) -> dict:
    tipo = (req.tipo or "").strip().upper()
    if tipo not in FORMA_PAG_SUFIXO_TIPO:
        return {"success": False, "message": "Tipo de forma de pagamento inválido."}
    if not (req.forma_pag or "").strip():
        return {"success": False, "message": "Selecione a forma de pagamento."}
    if not req.valor or req.valor <= 0:
        return {"success": False, "message": "Informe um valor maior que zero."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        tela = req.tela or _TELA_POR_DAV.get(req.tipo_dav, "PEDIDO")
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "FORMA_PAG"):
            conn.close()
            return {"success": False, "message": "Sem permissão para lançar forma de pagamento."}
        dav = DavPagamento(tipo=req.tipo_dav, documento=documento, situacao="", valor=0, forma_padrao="")
        if tipo == "DU":
            _insere_duplicata_parcelada(cur, dav, req.forma_pag, req.valor)
        else:
            _insere_forma_manual(cur, dav, tipo, req)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Forma de pagamento lançada."}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao lançar: {e}"}


def _update_forma_pagamento_sync(req: FormaPagamentoUpdateRequest, documento: int) -> dict:
    tipo = (req.tipo or "").strip().upper()
    if tipo not in FORMA_PAG_SUFIXO_TIPO:
        return {"success": False, "message": "Tipo de forma de pagamento inválido."}
    if not req.valor or req.valor <= 0:
        return {"success": False, "message": "Informe um valor maior que zero."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        tela = req.tela or _TELA_POR_DAV.get(req.tipo_dav, "PEDIDO")
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "FORMA_PAG"):
            conn.close()
            return {"success": False, "message": "Sem permissão para alterar forma de pagamento."}
        dav = DavPagamento(tipo=req.tipo_dav, documento=documento, situacao="", valor=0, forma_padrao="")
        rowcount = _atualiza_forma_manual(cur, dav, tipo, req.sequencia, req)
        if rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Lançamento não encontrado."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Forma de pagamento atualizada."}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar: {e}"}


def _delete_forma_pagamento_sync(req: FormaPagamentoDeleteRequest, documento: int) -> dict:
    tipo = (req.tipo or "").strip().upper()
    if tipo not in FORMA_PAG_SUFIXO_TIPO:
        return {"success": False, "message": "Tipo de forma de pagamento inválido."}
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        tela = req.tela or _TELA_POR_DAV.get(req.tipo_dav, "PEDIDO")
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, tela, "FORMA_PAG"):
            conn.close()
            return {"success": False, "message": "Sem permissão para excluir forma de pagamento."}
        dav = DavPagamento(tipo=req.tipo_dav, documento=documento, situacao="", valor=0, forma_padrao="")
        cur.execute(f"DELETE FROM {dav.tabela(tipo)} WHERE sequencia=%s AND {dav.fk}=%s", (req.sequencia, documento))
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Lançamento não encontrado."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Forma de pagamento excluída."}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}


async def list_formas_pagamento(servidor: str, banco: str, tipo_dav: str, documento: int) -> dict:
    return await asyncio.to_thread(_list_formas_pagamento_sync, servidor, banco, tipo_dav, documento)


async def add_forma_pagamento(req: FormaPagamentoAddRequest, documento: int) -> dict:
    return await asyncio.to_thread(_add_forma_pagamento_sync, req, documento)


async def update_forma_pagamento(req: FormaPagamentoUpdateRequest, documento: int) -> dict:
    return await asyncio.to_thread(_update_forma_pagamento_sync, req, documento)


async def delete_forma_pagamento(req: FormaPagamentoDeleteRequest, documento: int) -> dict:
    return await asyncio.to_thread(_delete_forma_pagamento_sync, req, documento)
