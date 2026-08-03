"""Envio de Equipamentos para Terceiros (migração de `FrmManRet.frm`).

Tabela `retifica` (já existente, compartilhada com o legado VB6):
  num IDENTITY, os int, marca/modelo nvarchar(3), cliente/fornecedor
  nvarchar(14) (guardam o código numérico como texto — mesma tabela do
  legado, sem migração de schema), numero_de_serie nvarchar(20),
  entrada/saida date, valor real, obs nvarchar(MAX).

Rastreado campo-a-campo em `FrmManRet.frm` (Kontacto\\frmmanret.frm):
  - "Entrada" (`retifica.entrada`) = data em que o equipamento foi ENVIADO
    ao terceiro (gravada ao clicar "Envio p/ Terceiro", Command4_Click) —
    nome de coluna enganoso, mantido por ser o nome real da coluna no
    banco compartilhado com o legado.
  - "Saída" (`retifica.saida`) = data em que o equipamento RETORNOU do
    terceiro (gravada ao clicar "Retorno/Terceiro", Command3_Click).
  - "Terceiro" é sempre um FORNECEDOR (`fornecedor.codigo_int`), não texto
    livre — confirmado pelo JOIN `val(retifica.fornecedor) =
    fornecedor.codigo_int` usado em toda consulta do form original.
  - Exclusão é HARD DELETE (`Delete * from Retifica Where Num = ...`,
    Command2_Click) — diferente de Pedido/O.S. (que só mudam situação),
    esta tabela realmente não tem outro mecanismo no legado. Replicado
    como está — regra real confirmada no código-fonte, não suposição.
  - O check de duplicidade do legado (`Procura(3, Protocolos, "")` antes de
    Inserir) compara por `num` (sempre vazio num registro novo) em vez de
    por `os`/`numero_de_serie` como o texto do MsgBox sugere — bug do
    código original (nunca dispara na prática). Não replicado (ver "Não
    replicar truques VB6" no CLAUDE.md).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import RetificaSaveRequest, RetificaRetornoRequest


def _list_sync(
    servidor: str, banco: str, search: Optional[str], somente_abertos: bool,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if somente_abertos:
            where.append("r.saida IS NULL")
        term = (search or "").strip()
        if term:
            like = f"%{term}%"
            where.append(
                "(CAST(r.os AS NVARCHAR(20)) LIKE %s OR r.numero_de_serie LIKE %s "
                " OR f.nome LIKE %s OR f.fantasia LIKE %s OR c.nome LIKE %s OR c.fantasia LIKE %s)"
            )
            params += [like, like, like, like, like, like]
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            f"SELECT r.num, r.os, r.marca, r.modelo, r.numero_de_serie, r.entrada, r.saida, "
            f"       r.valor, r.obs, "
            f"       TRY_CAST(r.fornecedor AS INT) AS fornecedor_codigo, "
            f"       COALESCE(NULLIF(f.fantasia,''), f.nome) AS fornecedor_nome, "
            f"       TRY_CAST(r.cliente AS INT) AS cliente_codigo, "
            f"       COALESCE(NULLIF(c.fantasia,''), c.nome) AS cliente_nome, "
            f"       ma.descricao AS marca_descricao, mo.descricao AS modelo_descricao "
            f"FROM retifica r "
            f"LEFT JOIN fornecedor f ON f.codigo_int = TRY_CAST(r.fornecedor AS INT) "
            f"LEFT JOIN cliente c ON c.codigo = TRY_CAST(r.cliente AS INT) "
            f"LEFT JOIN marcas ma ON ma.codigo = r.marca "
            f"LEFT JOIN modelos mo ON mo.codigo = r.modelo AND mo.cod_marca = r.marca "
            f"{where_sql} "
            f"ORDER BY (CASE WHEN r.saida IS NULL THEN 0 ELSE 1 END), r.num DESC",
            tuple(params),
        )
        items = [{
            "num": int(r["num"]),
            "os": int(r["os"]) if r.get("os") is not None else None,
            "marca": (r.get("marca") or "").strip(),
            "marca_descricao": (r.get("marca_descricao") or "").strip(),
            "modelo": (r.get("modelo") or "").strip(),
            "modelo_descricao": (r.get("modelo_descricao") or "").strip(),
            "numero_de_serie": (r.get("numero_de_serie") or "").strip(),
            "entrada": r["entrada"].isoformat() if r.get("entrada") else None,
            "saida": r["saida"].isoformat() if r.get("saida") else None,
            "valor": float(r.get("valor") or 0),
            "obs": r.get("obs") or "",
            "fornecedor": r.get("fornecedor_codigo"),
            "fornecedor_nome": (r.get("fornecedor_nome") or "").strip(),
            "cliente": r.get("cliente_codigo"),
            "cliente_nome": (r.get("cliente_nome") or "").strip(),
            "aberto": r.get("saida") is None,
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _save_sync(req: RetificaSaveRequest) -> dict:
    """Envio p/ Terceiro (Command4_Click) — cria o protocolo de envio.
    `saida` fica NULL até o Retorno."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM os WHERE codigo=%s", (req.os,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Número de O.S. inexistente."}
        num_serie = (req.numero_de_serie or "").strip()
        if not num_serie:
            conn.close()
            return {"success": False, "message": "Preencha o Número de Série corretamente."}
        sizes = _get_col_sizes(conn, req.banco, "retifica")
        num_serie = _trunc(num_serie, sizes, "numero_de_serie", 20)
        cur.execute(
            "INSERT INTO retifica (os, marca, modelo, cliente, fornecedor, numero_de_serie, entrada, valor, obs) "
            "OUTPUT INSERTED.num "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                req.os, (req.marca or "")[:3], (req.modelo or "")[:3],
                _trunc(str(req.cliente), sizes, "cliente", 14), _trunc(str(req.fornecedor), sizes, "fornecedor", 14),
                num_serie, req.entrada, req.valor or 0, req.obs or "",
            ),
        )
        row = cur.fetchone()
        num = int(row["num"] if isinstance(row, dict) else row[0])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "num": num}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _update_sync(req: RetificaSaveRequest, num: int) -> dict:
    """Alterar (Command1_Click) — edita um protocolo já existente (Envio
    OU Retorno, o legado permite editar os dois em conjunto aqui)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM retifica WHERE num=%s", (num,))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Protocolo não encontrado."}
        sizes = _get_col_sizes(conn, req.banco, "retifica")
        num_serie = _trunc((req.numero_de_serie or "").strip(), sizes, "numero_de_serie", 20)
        cur.execute(
            "UPDATE retifica SET os=%s, marca=%s, modelo=%s, cliente=%s, fornecedor=%s, "
            " numero_de_serie=%s, entrada=%s, valor=%s, obs=%s WHERE num=%s",
            (
                req.os, (req.marca or "")[:3], (req.modelo or "")[:3],
                _trunc(str(req.cliente), sizes, "cliente", 14), _trunc(str(req.fornecedor), sizes, "fornecedor", 14),
                num_serie, req.entrada, req.valor or 0, req.obs or "", num,
            ),
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
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _retorno_sync(req: RetificaRetornoRequest, num: int) -> dict:
    """Retorno/Terceiro (Command3_Click) — grava a data de retorno
    (`saida`) e, opcionalmente, reajusta o valor cobrado. Permite
    sobrescrever um retorno já lançado (mesmo "novo retorno" do legado —
    confirma via `valor`/`saida` recebidos, sem bloquear)."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT valor FROM retifica WHERE num=%s", (num,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Protocolo não encontrado."}
        valor = req.valor if req.valor is not None else float(row.get("valor") or 0)
        cur.execute(
            "UPDATE retifica SET saida=%s, valor=%s WHERE num=%s",
            (req.saida, valor, num),
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
        return {"success": False, "message": f"Erro ao gravar retorno: {e}"}


def _delete_sync(servidor: str, banco: str, num: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM retifica WHERE num=%s", (num,))
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Protocolo não encontrado."}
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}


# ---------------- async wrappers ----------------
async def list_retifica(servidor: str, banco: str, search: Optional[str] = None, somente_abertos: bool = False) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, search, somente_abertos)


async def save_retifica(req: RetificaSaveRequest) -> dict:
    return await asyncio.to_thread(_save_sync, req)


async def update_retifica(req: RetificaSaveRequest, num: int) -> dict:
    return await asyncio.to_thread(_update_sync, req, num)


async def retorno_retifica(req: RetificaRetornoRequest, num: int) -> dict:
    return await asyncio.to_thread(_retorno_sync, req, num)


async def delete_retifica(servidor: str, banco: str, num: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, num)
