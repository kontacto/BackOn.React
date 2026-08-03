"""Tempo Gasto por Serviço (tabela `os_tempo`) — lançamento de horário de
início/fim de atendimento por serviço + técnico dentro de uma O.S.

Migração do frame "Tempo Gasto" (`Command30_Click`/`Command57_Click`/
`Command56_Click`) em `Revenda\\FrmTraOsNew.frm` (a única cópia rastreada com
essa feature de fato implementada — `Geral\\FrmTraOs.frm` não tem, ver
PENDENCIAS.md > "Tempo Gasto por Serviço"). `os_tempo` já existe no schema
(referenciada até agora só como guard de integridade em
`funcionarios_service.py`), esta é a primeira vez que ganha CRUD próprio.

Regras confirmadas no rastreio:
  • Só permite Incluir/Alterar/Excluir com a O.S. Aberta (situacao='A') — o
    legado bloqueia SILENCIOSAMENTE (sem mensagem) nesse caso; aqui optamos
    por retornar uma mensagem clara em vez de replicar o silêncio, que é um
    atalho de UI da era VB6, não a regra de negócio em si (ver "Não
    replicar truques VB6" no CLAUDE.md) — a regra real (bloquear) é mantida.
  • Consulta (listar) é permitida em qualquer situação da O.S.
  • Tempo Gasto é sempre DERIVADO (hora_fim - hora_inicio), nunca uma
    coluna própria persistida — mesmo comportamento do legado
    (`Diferenca()`, recalculado a cada exibição).
  • Sem checagem de permissão server-side (`tem_permissao`) — mesmo padrão
    já usado por TODO o resto de `os_itens_service.py` (ADD_ITEM/EDIT_ITEM/
    DEL_ITEM/PONTUACAO/AUTORIZAR/EXPEDIR também não checam server-side),
    só client-side via `can("OS_COMP.TEMPO")`. Não é uma omissão desta
    rodada, é consistência com o restante do arquivo-irmão.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn, _get_col_sizes, _trunc
from models.schemas import OSTempoSaveRequest
from services.constants import SITUACAO_LABEL
from services.os_itens_service import _check_os_aberta


def _tempo_gasto_min(hora_inicio: str, hora_fim: str) -> Optional[int]:
    """Diferença em minutos entre hora_inicio e hora_fim (HH:MM[:SS]).
    Assume virada de meia-noite quando hora_fim < hora_inicio (turno
    noturno) — mesmo espírito do `Diferenca()` do legado."""
    if not hora_inicio or not hora_fim:
        return None
    try:
        h1, m1 = (int(x) for x in hora_inicio.split(":")[:2])
        h2, m2 = (int(x) for x in hora_fim.split(":")[:2])
        diff = (h2 * 60 + m2) - (h1 * 60 + m1)
        if diff < 0:
            diff += 24 * 60
        return diff
    except Exception:
        return None


def _list_tempo_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_os_aberta(cur, codigo)
        if not existe:
            conn.close()
            return {"success": False, "message": "OS não encontrada.", "items": []}
        cur.execute(
            "SELECT ot.codigo, ot.codigo_interno, ot.funcionario, ot.data, "
            "       ot.hora_inicio, ot.hora_fim, ot.obs, "
            "       COALESCE(sv.descricao, pe.descricao) AS item_descricao, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS funcionario_nome "
            "FROM os_tempo ot "
            "LEFT JOIN servicos sv ON sv.codigo = ot.codigo_interno "
            "LEFT JOIN pecas pe ON pe.codigo_int = ot.codigo_interno "
            "LEFT JOIN funcionarios f ON f.codigo_int = ot.funcionario "
            "WHERE ot.os = %s "
            "ORDER BY ot.data, ot.hora_inicio",
            (codigo,),
        )
        items = []
        for r in cur.fetchall():
            hi = (r.get("hora_inicio") or "").strip()
            hf = (r.get("hora_fim") or "").strip()
            items.append({
                "codigo": int(r["codigo"]),
                "codigo_interno": (r.get("codigo_interno") or "").strip(),
                "item_descricao": (r.get("item_descricao") or "").strip(),
                "funcionario": int(r["funcionario"]) if r.get("funcionario") else None,
                "funcionario_nome": (r.get("funcionario_nome") or "").strip(),
                "data": r["data"].isoformat() if r.get("data") else None,
                "hora_inicio": hi,
                "hora_fim": hf or None,
                "obs": (r.get("obs") or "").strip(),
                "tempo_gasto_min": _tempo_gasto_min(hi, hf),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "situacao": sit}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_tempo(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_list_tempo_sync, servidor, banco, codigo)


def _save_tempo_sync(req: OSTempoSaveRequest, codigo: int, tempo_codigo: Optional[int]) -> dict:
    if not (req.codigo_interno or "").strip():
        return {"success": False, "message": "Selecione o Serviço."}
    if not req.funcionario:
        return {"success": False, "message": "Selecione o Técnico."}
    if not (req.data or "").strip():
        return {"success": False, "message": "Informe a Data."}
    if not (req.hora_inicio or "").strip():
        return {"success": False, "message": "Informe a Hora Inicial."}
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
            label = SITUACAO_LABEL.get(sit, sit)
            return {"success": False, "message": f"OS '{label}' não permite lançar Tempo Gasto — só com a OS Aberta."}

        sizes = _get_col_sizes(conn, req.banco, "os_tempo")
        codigo_interno = _trunc((req.codigo_interno or "").strip(), sizes, "codigo_interno", 20)
        obs = _trunc(req.obs or "", sizes, "obs", 200)
        hora_inicio = (req.hora_inicio or "").strip()
        hora_fim = (req.hora_fim or "").strip() or None

        if tempo_codigo is None:
            cur.execute(
                "INSERT INTO os_tempo (os, codigo_interno, funcionario, data, hora_inicio, hora_fim, obs) "
                "OUTPUT INSERTED.codigo "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (codigo, codigo_interno, req.funcionario, req.data, hora_inicio, hora_fim, obs),
            )
            row = cur.fetchone()
            novo = int(row["codigo"] if isinstance(row, dict) else row[0])
            conn.commit()
            cur.close()
            conn.close()
            return {"success": True, "codigo": novo}

        cur.execute("SELECT TOP 1 1 AS ok FROM os_tempo WHERE codigo=%s AND os=%s", (tempo_codigo, codigo))
        if not cur.fetchone():
            conn.close()
            return {"success": False, "message": "Lançamento de Tempo Gasto não encontrado."}
        cur.execute(
            "UPDATE os_tempo SET codigo_interno=%s, funcionario=%s, data=%s, "
            "hora_inicio=%s, hora_fim=%s, obs=%s WHERE codigo=%s AND os=%s",
            (codigo_interno, req.funcionario, req.data, hora_inicio, hora_fim, obs, tempo_codigo, codigo),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": tempo_codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar tempo gasto: {e}"}


async def save_tempo(req: OSTempoSaveRequest, codigo: int, tempo_codigo: Optional[int] = None) -> dict:
    return await asyncio.to_thread(_save_tempo_sync, req, codigo, tempo_codigo)


def _delete_tempo_sync(servidor: str, banco: str, codigo: int, tempo_codigo: int) -> dict:
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
            label = SITUACAO_LABEL.get(sit, sit)
            return {"success": False, "message": f"OS '{label}' não permite excluir Tempo Gasto — só com a OS Aberta."}
        cur.execute("DELETE FROM os_tempo WHERE codigo=%s AND os=%s", (tempo_codigo, codigo))
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"success": False, "message": "Lançamento de Tempo Gasto não encontrado."}
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
        return {"success": False, "message": f"Erro ao excluir: {e}"}


async def delete_tempo(servidor: str, banco: str, codigo: int, tempo_codigo: int) -> dict:
    return await asyncio.to_thread(_delete_tempo_sync, servidor, banco, codigo, tempo_codigo)
