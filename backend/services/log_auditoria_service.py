"""Log de Auditoria — grava e lista ações de escrita do sistema novo (tabela
`log_auditoria`). Não confundir com as tabelas legadas do VB6 `logs`/
`tipo_log`/`log_sistema` (login), que continuam em uso pelo sistema antigo e
não são tocadas por este módulo.

`tela`/`comando` usam o mesmo vocabulário já declarado em
`services/permissoes_service.CATALOGO` — não existe aqui um catálogo próprio
de "tipos de log" (esse era o problema do `tipo_log` legado: catálogo
duplicado, hardcoded, recriado a cada abertura de tela).

`registrar_log` é best-effort: qualquer falha ao gravar o log é só logada via
`logging.warning`, nunca propagada — uma falha no log não pode derrubar a
ação de negócio que está sendo registrada.
"""
import asyncio
import json
import logging
from typing import Optional

from db.connection import _open_conn
from services.permissoes_service import tem_permissao

logger = logging.getLogger(__name__)


def _registrar_log_sync(
    servidor: str, banco: str, *,
    tela: str, comando: str,
    usuario: Optional[int] = None,
    classe: Optional[int] = None,
    referencia: Optional[str] = None,
    descricao: Optional[str] = None,
    campos_alterados: Optional[list] = None,
    ip_origem: Optional[str] = None,
    plataforma: Optional[str] = None,
) -> None:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        logger.warning("log_auditoria: falha ao conectar — %s", e)
        return
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "INSERT INTO log_auditoria "
            "(tela, comando, referencia, descricao, campos_alterados, usuario, classe, ip_origem, plataforma) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                tela[:15], comando[:15], (referencia or None), descricao,
                json.dumps(campos_alterados, ensure_ascii=False) if campos_alterados else None,
                usuario, classe, ip_origem, plataforma,
            ),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        logger.warning("log_auditoria: falha ao gravar (tela=%s comando=%s) — %s", tela, comando, e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def _list_logs_sync(
    servidor: str, banco: str, *,
    tela: Optional[str] = None,
    comando: Optional[str] = None,
    usuario: Optional[int] = None,
    data_de: Optional[str] = None,
    data_ate: Optional[str] = None,
    referencia: Optional[str] = None,
    descricao_like: Optional[str] = None,
    page: int = 1,
    size: int = 40,
    classe: Optional[int] = None,
    master: bool = False,
) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not master and classe is not None and not tem_permissao(cur, classe, "LOG_AUDITORIA", "ABRIR"):
            return {"success": False, "message": "Sem permissão para consultar o log de auditoria.", "items": [], "total": 0}
        where = ["1=1"]
        params: list = []
        if tela:
            where.append("la.tela=%s")
            params.append(tela)
        if comando:
            where.append("la.comando=%s")
            params.append(comando)
        if usuario is not None:
            where.append("la.usuario=%s")
            params.append(usuario)
        if data_de:
            where.append("la.data_hora >= %s")
            params.append(data_de)
        if data_ate:
            where.append("la.data_hora < DATEADD(day, 1, %s)")
            params.append(data_ate)
        if referencia:
            where.append("la.referencia LIKE %s")
            params.append(f"%{referencia}%")
        if descricao_like:
            where.append("la.descricao LIKE %s")
            params.append(f"%{descricao_like}%")
        where_sql = " AND ".join(where)

        cur.execute(f"SELECT COUNT(*) AS n FROM log_auditoria la WHERE {where_sql}", tuple(params))
        total = int(cur.fetchone()["n"])

        offset = max(0, (page - 1) * size)
        cur.execute(
            f"SELECT la.id, la.data_hora, la.tela, la.comando, la.referencia, la.descricao, "
            f"la.campos_alterados, la.usuario, f.nome_guerra AS usuario_nome, la.classe, "
            f"la.ip_origem, la.plataforma "
            f"FROM log_auditoria la LEFT JOIN funcionarios f ON f.codigo_int = la.usuario "
            f"WHERE {where_sql} ORDER BY la.id DESC "
            f"OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            tuple(params) + (offset, size),
        )
        items = []
        for r in cur.fetchall():
            campos = None
            if r.get("campos_alterados"):
                try:
                    campos = json.loads(r["campos_alterados"])
                except Exception:
                    campos = None
            items.append({
                "id": r["id"],
                "data_hora": r["data_hora"].isoformat() if r.get("data_hora") else None,
                "tela": r.get("tela"),
                "comando": r.get("comando"),
                "referencia": r.get("referencia"),
                "descricao": r.get("descricao"),
                "campos_alterados": campos,
                "usuario": r.get("usuario"),
                "usuario_nome": (r.get("usuario_nome") or "").strip() or None,
                "classe": r.get("classe"),
                "ip_origem": r.get("ip_origem"),
                "plataforma": r.get("plataforma"),
            })
        cur.close()
        return {"success": True, "items": items, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}
    finally:
        conn.close()


async def registrar_log(servidor: str, banco: str, **kwargs) -> None:
    await asyncio.to_thread(_registrar_log_sync, servidor, banco, **kwargs)


async def list_logs(servidor: str, banco: str, **kwargs) -> dict:
    return await asyncio.to_thread(_list_logs_sync, servidor, banco, **kwargs)


# ---------------- Helpers de diff campo-a-campo ----------------
# Usados pelas rotas de Cadastros/Tabelas Auxiliares/Financeiro pra montar o
# "antes" de um registro (SELECT pelo PK antes de chamar o service, que faz o
# UPDATE/DELETE às cegas — nenhuma mudança nas ~50 funções de service
# existentes) e comparar contra os valores novos do request.

def _get_row_by_pk_sync(servidor: str, banco: str, tabela: str, pk_col: str, pk_val) -> Optional[dict]:
    if pk_val is None:
        return None
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        logger.warning("log_auditoria: falha ao buscar %s/%s=%s pra diff — %s", tabela, pk_col, pk_val, e)
        return None
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT * FROM {tabela} WHERE {pk_col}=%s", (pk_val,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.warning("log_auditoria: falha ao buscar %s/%s=%s pra diff — %s", tabela, pk_col, pk_val, e)
        return None
    finally:
        conn.close()


async def get_row_by_pk(servidor: str, banco: str, tabela: str, pk_col: str, pk_val) -> Optional[dict]:
    return await asyncio.to_thread(_get_row_by_pk_sync, servidor, banco, tabela, pk_col, pk_val)


def _norm_valor(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, float):
        return round(v, 6)
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return round(float(v), 6)
    except ImportError:
        pass
    return v


def diff_campos(antes: Optional[dict], depois: dict, campos: list) -> list:
    """Compara `campos` entre o dict `antes` (linha atual no banco, ou None se
    for um registro novo) e `depois` (valores novos do request) — devolve só
    os que realmente mudaram, como [{"campo","antes","depois"}]."""
    antes = antes or {}
    out = []
    for c in campos:
        a = _norm_valor(antes.get(c))
        d = _norm_valor(depois.get(c))
        if isinstance(a, int) and isinstance(d, bool):
            a = bool(a)
        elif isinstance(d, int) and isinstance(a, bool):
            d = bool(d)
        if a != d:
            out.append({
                "campo": c,
                "antes": "" if a is None else str(a),
                "depois": "" if d is None else str(d),
            })
    return out


def snapshot_campos(row: Optional[dict], campos: list) -> list:
    """Snapshot pra log de exclusão — só o "antes" (não há "depois")."""
    if not row:
        return []
    out = []
    for c in campos:
        v = _norm_valor(row.get(c))
        if v is not None and v != "":
            out.append({"campo": c, "antes": str(v)})
    return out


def diff_set_membership(antes_chaves: set, depois_chaves: set) -> list:
    """Diff pra tabelas "replace-all" (lista inteira apagada e regravada a cada
    save — ex. permissões de um grupo), onde não existe uma linha única com PK
    pra buscar "antes"/"depois" campo a campo. Cada item vira uma "chave"
    (string); o resultado é só quem entrou ou saiu, no mesmo formato
    campo/antes/depois usado por `diff_campos`."""
    out = []
    for chave in sorted(depois_chaves - antes_chaves):
        out.append({"campo": chave, "antes": "Não concedida", "depois": "Concedida"})
    for chave in sorted(antes_chaves - depois_chaves):
        out.append({"campo": chave, "antes": "Concedida", "depois": "Não concedida"})
    return out
