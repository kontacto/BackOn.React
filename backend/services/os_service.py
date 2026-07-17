"""Ordem de Serviço (tabela `os`) — listagem, leitura e CRUD do cabeçalho.

Diferenças importantes em relação ao pedido_venda:
  • `os.codigo` NÃO é IDENTITY → geramos MAX(codigo)+1 dentro da transação.
  • Vendedor/executor ficam no nível do ITEM (os_produto), não no cabeçalho.
  • Colunas NOT NULL sem default: codigo, km, OS_ORIGINAL → preenchidas no insert.
Situações reutilizam os mesmos códigos do pedido (A/F/PG/C).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import OSListRequest, OSSaveRequest, FecharRequest, FormaPagSimplesRequest
from services.constants import SITUACAO_LABEL
from services.pedido_common import _check_cliente_ativo, DavPagamento, DAV_OS, _fecha_fpag_dav, _qtd_formas
from services.permissoes_service import tem_permissao


def _list_os_sync(req: OSListRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        where_parts: list[str] = []
        params: list = []
        term = (req.search or "").strip()
        if term:
            like = f"%{term}%"
            where_parts.append(
                "(c.nome LIKE %s OR c.cgc_cpf LIKE %s OR CAST(o.codigo AS NVARCHAR(20)) LIKE %s)"
            )
            params.extend([like, like, like])
        if req.situacao:
            where_parts.append("o.situacao = %s")
            params.append(req.situacao)
        if req.data_ini:
            where_parts.append("o.data_entrada >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where_parts.append("o.data_entrada <= %s")
            params.append(req.data_fim)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        cur.execute(
            f"SELECT COUNT(*) c FROM os o LEFT JOIN cliente c ON c.codigo = o.cliente {where}",
            params,
        )
        total = int(cur.fetchone()["c"] or 0)

        offset = max(0, (req.page - 1) * req.size)
        cur.execute(
            f"SELECT o.codigo, o.cliente, o.data_entrada, o.hora_entrada, o.situacao, o.valor, "
            f"       o.area_atuacao, c.nome AS cliente_nome "
            f"FROM os o "
            f"LEFT JOIN cliente c ON c.codigo = o.cliente "
            f"{where} "
            f"ORDER BY o.codigo DESC OFFSET {offset} ROWS FETCH NEXT {req.size} ROWS ONLY",
            params,
        )
        items: list[dict] = []
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip()
            items.append({
                "codigo": int(r["codigo"] or 0),
                "cliente": int(r["cliente"] or 0) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "data": r["data_entrada"].isoformat() if r.get("data_entrada") else None,
                "hora": (r.get("hora_entrada") or "").strip(),
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(r.get("valor") or 0),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": total, "page": req.page, "size": req.size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


def _get_os_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT o.codigo, o.cliente, o.data_entrada, o.hora_entrada, o.situacao, o.valor, "
            "       o.area_atuacao, o.descricao_cliente, o.obs, o.resumo, o.status_os, o.atendente, "
            "       o.placa, o.marca, o.modelo, o.km, o.ano, o.chassi, o.numero_de_serie, "
            "       o.forma_pagamento, fp.descricao AS forma_pagamento_descricao, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       a.descricao AS area_descricao, "
            "       f.nome AS atendente_nome, f.nome_guerra AS atendente_guerra "
            "FROM os o "
            "LEFT JOIN cliente c ON c.codigo = o.cliente "
            "LEFT JOIN area_atuacao a ON a.area = o.area_atuacao "
            "LEFT JOIN funcionarios f ON f.codigo_int = o.atendente "
            "LEFT JOIN forma_pagamento fp ON fp.codigo = o.forma_pagamento "
            "WHERE o.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "OS não encontrada."}
        sit = (row.get("situacao") or "").strip()
        return {
            "success": True,
            "os": {
                "codigo": int(row["codigo"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data_entrada"].isoformat() if row.get("data_entrada") else None,
                "hora": (row.get("hora_entrada") or "").strip(),
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(row.get("valor") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
                "descricao_cliente": row.get("descricao_cliente") or "",
                "obs": row.get("obs") or "",
                "resumo": row.get("resumo") or "",
                "status_os": int(row["status_os"]) if row.get("status_os") is not None else None,
                "atendente": int(row["atendente"]) if row.get("atendente") else None,
                "atendente_nome": (row.get("atendente_guerra") or row.get("atendente_nome") or "").strip(),
                "placa": (row.get("placa") or "").strip(),
                "marca": (row.get("marca") or "").strip(),
                "modelo": (row.get("modelo") or "").strip(),
                "km": int(row["km"]) if row.get("km") is not None else None,
                "ano": (row.get("ano") or "").strip(),
                "chassi": (row.get("chassi") or "").strip(),
                "numero_de_serie": (row.get("numero_de_serie") or "").strip(),
                "forma_pagamento": (row.get("forma_pagamento") or "").strip(),
                "forma_pagamento_descricao": (row.get("forma_pagamento_descricao") or "").strip(),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_os_sync(req: OSSaveRequest, codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        # Update: só OS Aberta ('A') pode ser alterada.
        if codigo is not None:
            cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            if sit_atual != "A":
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"OS com situação '{label}' não pode ser alterada."}
        else:
            # Nova O.S. — cliente com STATUS_CLIENTE diferente de Ativo não pode
            # gerar movimentação (venda/pré-venda).
            ok, label = _check_cliente_ativo(cur, req.cliente)
            if not ok:
                conn.close()
                return {
                    "success": False,
                    "message": f"Cliente com situação '{label}' não pode gerar nova O.S.",
                }

        sizes = _get_col_sizes(conn, req.banco, "os")
        descricao_cliente = req.descricao_cliente or ""
        obs = req.obs or ""
        resumo = req.resumo or ""
        placa = _trunc(req.placa or "", sizes, "placa", 8)
        marca = _trunc(req.marca or "", sizes, "marca", 3)
        modelo = _trunc(req.modelo or "", sizes, "modelo", 3)
        ano = _trunc(req.ano or "", sizes, "ano", 9)
        chassi = _trunc(req.chassi or "", sizes, "chassi", 20)
        num_serie = _trunc(req.numero_de_serie or "", sizes, "numero_de_serie", 20)
        km = int(req.km) if req.km is not None else 0
        status_os = req.status_os if req.status_os is not None else 0
        situacao = (req.situacao or "A").strip().upper() if req.situacao else "A"

        forma_pagamento = (req.forma_pagamento or "")[:3]

        if codigo is None:
            # codigo NÃO é identity → gera MAX+1. km e OS_ORIGINAL são NOT NULL.
            cur.execute("SELECT ISNULL(MAX(codigo),0)+1 AS novo FROM os")
            novo = int(cur.fetchone()["novo"] or 1)
            cur.execute(
                "INSERT INTO os "
                "(codigo, cliente, data_entrada, hora_entrada, situacao, valor, "
                " area_atuacao, descricao_cliente, obs, resumo, status_os, atendente, "
                " placa, marca, modelo, km, ano, chassi, numero_de_serie, forma_pagamento, OS_ORIGINAL) "
                "VALUES (%s, %s, CAST(GETDATE() AS DATE), CONVERT(NVARCHAR(8), GETDATE(), 108), "
                "        %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)",
                (novo, req.cliente, situacao, req.area_atuacao, descricao_cliente, obs, resumo,
                 status_os, req.atendente, placa, marca, modelo, km, ano, chassi, num_serie, forma_pagamento),
            )
            os_id = novo
        else:
            cur.execute(
                "UPDATE os SET cliente=%s, area_atuacao=%s, descricao_cliente=%s, obs=%s, "
                " resumo=%s, status_os=%s, atendente=%s, situacao=%s, "
                " placa=%s, marca=%s, modelo=%s, km=%s, ano=%s, chassi=%s, numero_de_serie=%s, "
                " forma_pagamento=%s "
                "WHERE codigo=%s",
                (req.cliente, req.area_atuacao, descricao_cliente, obs, resumo, status_os,
                 req.atendente, situacao, placa, marca, modelo, km, ano, chassi, num_serie,
                 forma_pagamento, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            os_id = codigo
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": os_id}
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


def _set_forma_pag_simples_sync(req: FormaPagSimplesRequest, codigo: int) -> dict:
    """Combobox simples 'Forma de Pagamento' do cabeçalho — grava direto ao
    trocar, fora do fluxo normal de Gravar. Mesmo raciocínio/nome de
    `pedidos_service._set_forma_pag_simples_sync`, só a tabela/coluna
    muda (`os.forma_pagamento`, não `pedido_venda.forma_pag`)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit not in ("A", "F"):
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterada."}
        forma_pag = (req.forma_pag or "")[:3] or None
        cur.execute("UPDATE os SET forma_pagamento=%s WHERE codigo=%s", (forma_pag, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar forma de pagamento: {e}"}


async def list_os(req: OSListRequest) -> dict:
    return await asyncio.to_thread(_list_os_sync, req)


async def get_os(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_os_sync, servidor, banco, codigo)


async def save_os(req: OSSaveRequest, codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_os_sync, req, codigo)


async def set_forma_pag_simples(req: FormaPagSimplesRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_set_forma_pag_simples_sync, req, codigo)



def _fechar_os_sync(req: FecharRequest, codigo: int) -> dict:
    """Fecha a O.S. (situação A -> F). Valida itens, permissão e forma de
    pagamento (réplica de `Fecha_FPAG_Dav`, mesmo `Type_FormaPagPedOS`
    compartilhado com o Pedido — ver `pedido_common.DavPagamento`).
    O estoque das peças já foi movido na INCLUSÃO do item (reservado_os),
    portanto o fechamento NÃO movimenta estoque novamente."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao, valor, forma_pagamento FROM os WHERE codigo=%s", (codigo,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "OS não encontrada."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"OS '{SITUACAO_LABEL.get(sit, sit)}' não pode ser fechada."}
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "OS", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar a O.S."}
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM os_produto WHERE os=%s AND ISNULL(item_cancelado,0)=0",
            (codigo,),
        )
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Inclua pelo menos um produto ou serviço antes de fechar."}
        subtotal = float(ex.get("valor") or 0)
        forma_padrao = (ex.get("forma_pagamento") or "").strip()
        dav = DavPagamento(tipo=DAV_OS, documento=codigo, situacao="A", valor=subtotal, forma_padrao=forma_padrao)
        erro = _fecha_fpag_dav(cur, dav)
        if erro:
            conn.close()
            return {"success": False, "message": erro}
        if _qtd_formas(cur, dav) == 0 and subtotal > 0:
            conn.close()
            return {"success": False, "message": "Defina a Forma de Pagamento da O.S.!"}
        cur.execute("UPDATE os SET situacao='F' WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pré-venda Fechada.", "situacao": "F"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar: {e}"}


async def fechar_os(req: FecharRequest, codigo: int) -> dict:
    return await asyncio.to_thread(_fechar_os_sync, req, codigo)