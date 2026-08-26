"""Cadastro/Consulta de NCM e CEST (tabela auxiliar fiscal).

Migração de `Geral\\FrmCesNCM.frm` ("NCM's e CEST's..."). Diferente das
demais Tabelas Auxiliares deste sistema, `ncm`/`ncm_cest` já chegam
POPULADAS com dado oficial (Nomenclatura Comum do Mercosul + Convênio
ICMS 142/2018 — confirmado ao vivo contra ARGEN TESTE: 10.343 linhas em
`ncm`, 1.285 em `ncm_cest`) — o uso real predominante é CONSULTA/BUSCA,
não digitação em massa; por isso as listagens abaixo são sempre
filtradas por busca (nunca "listar tudo"), diferente do padrão simples
de `tabelas_aux_service.py`.

- `ncm(ncm nvarchar(100) PK, descricao nvarchar(MAX))`.
- `ncm_cest(ncm nvarchar(8), cest nvarchar(8), descricao nvarchar(MAX))` —
  confirmado ao vivo: `NCM_CEST_PRIMARIA` é um índice ÚNICO **composto**
  `(ncm, cest)` — um NCM pode ter vários CEST vinculados (e um CEST pode
  se repetir em vários NCM, achado real: 148 CEST aparecem em mais de 1
  NCM, até 17 vezes) — a unicidade é do PAR, nunca do NCM sozinho.
  `ncm` pode ficar em branco (string vazia, a coluna não é NULLABLE) em
  poucos casos reais (4 de 1.285) — CEST de referência genérica, ainda
  sem um NCM específico vinculado.
- **`ncm_cest.ncm` é frequentemente um PREFIXO, não o código completo de 8
  dígitos** — achado ao vivo (508 das 1.281 linhas com `ncm` preenchido
  têm de 2 a 7 dígitos: capítulo/posição/subposição, exatamente a
  granularidade real do Convênio ICMS 142/2018; só 773 usam o código
  completo). Por isso `_get_ncm_sync` resolve os CEST de um NCM completo
  por PREFIXO (`LEFT(ncm_completo, LEN(ncm_cest.ncm)) = ncm_cest.ncm`),
  nunca por igualdade exata, e `_save_ncm_cest_sync` nunca exige que o
  NCM informado exista como linha própria em `ncm` — só que seja numérico
  e caiba nos 8 caracteres da coluna.

Duas correções conscientes em relação ao `.frm` original (ver CLAUDE.md
"Não replicar truques VB6"):

1. `Command2_Click` do legado checa duplicata só por `NCM` (ignora
   `CEST`) antes de inserir um vínculo novo — como a chave real é
   composta, isso bloquearia silenciosamente um 2º CEST válido pro
   mesmo NCM. Aqui a checagem é pelo PAR completo, com mensagem clara.
2. `Command3_Click` (excluir vínculo) tem uma checagem `RecordCount < 0`
   que nunca é verdadeira (bug morto) — "não encontrado" nunca aparecia
   de fato. Aqui a existência é checada de verdade antes do DELETE.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


# ---------------- NCM ----------------

def _list_ncm_sync(servidor: str, banco: str, search: str, limit: int = 50) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        termo = (search or "").strip()
        if not termo:
            return {"success": True, "items": []}
        like = f"%{termo}%"
        cur.execute(
            f"SELECT TOP {int(limit)} ncm, descricao FROM ncm "
            "WHERE ncm LIKE %s OR descricao LIKE %s ORDER BY ncm",
            (f"{termo}%", like),
        )
        rows = cur.fetchall() or []
        return {"success": True, "items": rows}
    except Exception as e:
        return {"success": False, "message": f"Falha ao buscar NCM: {e}"}
    finally:
        conn.close()


def _get_ncm_sync(servidor: str, banco: str, ncm: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT ncm, descricao FROM ncm WHERE ncm=%s", (ncm,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "NCM não encontrado."}
        # `ncm_cest.ncm` real: achado ao vivo contra ARGEN TESTE — 508 das
        # 1.281 linhas com ncm preenchido usam um PREFIXO (2 a 7 dígitos,
        # nível capítulo/posição/subposição do Convênio ICMS 142/2018), só
        # 773 usam o código completo de 8 dígitos. O CEST se aplica a toda
        # a faixa daquele prefixo — o match certo é "o NCM completo COMEÇA
        # com o prefixo salvo em ncm_cest.ncm", nunca igualdade exata.
        cur.execute(
            "SELECT ncm, cest, descricao FROM ncm_cest "
            "WHERE ncm<>'' AND LEFT(%s, LEN(ncm))=ncm ORDER BY LEN(ncm) DESC, cest",
            (ncm,),
        )
        cests = cur.fetchall() or []
        return {"success": True, "item": row, "cests": cests}
    except Exception as e:
        return {"success": False, "message": f"Falha ao consultar NCM: {e}"}
    finally:
        conn.close()


def _save_ncm_sync(servidor: str, banco: str, ncm: str, descricao: str) -> dict:
    ncm_v = (ncm or "").strip()
    desc_v = (descricao or "").strip()
    if not ncm_v:
        return {"success": False, "message": "Informe o código NCM."}
    if not desc_v:
        return {"success": False, "message": "Informe a descrição do NCM."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM ncm WHERE ncm=%s", (ncm_v,))
        existe = cur.fetchone() is not None
        if existe:
            cur.execute("UPDATE ncm SET descricao=%s WHERE ncm=%s", (desc_v, ncm_v))
        else:
            cur.execute("INSERT INTO ncm (ncm, descricao) VALUES (%s,%s)", (ncm_v, desc_v))
        conn.commit()
        return {"success": True, "message": "NCM gravado.", "ncm": ncm_v}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Falha ao gravar NCM: {e}"}
    finally:
        conn.close()


def _delete_ncm_sync(servidor: str, banco: str, ncm: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM ncm WHERE ncm=%s", (ncm,))
        if not cur.fetchone():
            return {"success": False, "message": "NCM não encontrado."}
        cur.execute("SELECT COUNT(*) AS n FROM ncm_cest WHERE ncm=%s", (ncm,))
        n_cest = (cur.fetchone() or {}).get("n") or 0
        if n_cest:
            return {
                "success": False,
                "message": f"Não é possível excluir: existem {n_cest} CEST vinculado(s) a este NCM. Exclua os vínculos primeiro.",
            }
        cur.execute("DELETE FROM ncm WHERE ncm=%s", (ncm,))
        conn.commit()
        return {"success": True, "message": "NCM excluído."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Falha ao excluir NCM: {e}"}
    finally:
        conn.close()


# ---------------- CEST (vínculo NCM_CEST) ----------------

def _search_cest_sync(servidor: str, banco: str, search: str, limit: int = 50) -> dict:
    """Busca livre em ncm_cest (independente de NCM) — cobre o caso real
    de CEST cadastrado sem NCM vinculado ainda, e a busca "por CEST" do
    2º ListView do legado."""
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        termo = (search or "").strip()
        if not termo:
            return {"success": True, "items": []}
        like = f"%{termo}%"
        cur.execute(
            f"SELECT TOP {int(limit)} ncm, cest, descricao FROM ncm_cest "
            "WHERE cest LIKE %s OR descricao LIKE %s ORDER BY cest, ncm",
            (f"{termo}%", like),
        )
        rows = cur.fetchall() or []
        return {"success": True, "items": rows}
    except Exception as e:
        return {"success": False, "message": f"Falha ao buscar CEST: {e}"}
    finally:
        conn.close()


def _save_ncm_cest_sync(servidor: str, banco: str, ncm: str, cest: str, descricao: str) -> dict:
    ncm_v = (ncm or "").strip()
    cest_v = (cest or "").strip()
    desc_v = (descricao or "").strip()
    if not cest_v:
        return {"success": False, "message": "Informe o código CEST."}
    if ncm_v and (len(ncm_v) > 8 or not ncm_v.isdigit()):
        return {"success": False, "message": "NCM deve ter até 8 dígitos numéricos (pode ser um prefixo — capítulo/posição/subposição)."}
    if len(cest_v) > 8:
        return {"success": False, "message": "CEST deve ter até 8 caracteres."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        # NCM aqui é intencionalmente livre pra ser um PREFIXO (2 a 8
        # dígitos — capítulo/posição/subposição, ver achado ao vivo acima
        # em `_get_ncm_sync`) — não exige bater com um NCM completo já
        # cadastrado em `ncm`, isso bloquearia a maioria dos vínculos reais.
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM ncm_cest WHERE ncm=%s AND cest=%s",
            (ncm_v, cest_v),
        )
        existe = cur.fetchone() is not None
        if existe:
            cur.execute(
                "UPDATE ncm_cest SET descricao=%s WHERE ncm=%s AND cest=%s",
                (desc_v, ncm_v, cest_v),
            )
        else:
            cur.execute(
                "INSERT INTO ncm_cest (ncm, cest, descricao) VALUES (%s,%s,%s)",
                (ncm_v, cest_v, desc_v),
            )
        conn.commit()
        return {"success": True, "message": "CEST vinculado.", "ncm": ncm_v, "cest": cest_v}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Falha ao gravar CEST: {e}"}
    finally:
        conn.close()


def _delete_ncm_cest_sync(servidor: str, banco: str, ncm: str, cest: str) -> dict:
    ncm_v = (ncm or "").strip()
    cest_v = (cest or "").strip()
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 1 AS ok FROM ncm_cest WHERE ncm=%s AND cest=%s",
            (ncm_v, cest_v),
        )
        if not cur.fetchone():
            return {"success": False, "message": "Vínculo NCM/CEST não encontrado."}
        cur.execute("DELETE FROM ncm_cest WHERE ncm=%s AND cest=%s", (ncm_v, cest_v))
        conn.commit()
        return {"success": True, "message": "Vínculo CEST excluído."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Falha ao excluir vínculo: {e}"}
    finally:
        conn.close()


# ---------------- Async wrappers ----------------

async def list_ncm(servidor, banco, search, limit=50):
    return await asyncio.to_thread(_list_ncm_sync, servidor, banco, search, limit)


async def get_ncm(servidor, banco, ncm):
    return await asyncio.to_thread(_get_ncm_sync, servidor, banco, ncm)


async def save_ncm(servidor, banco, ncm, descricao):
    return await asyncio.to_thread(_save_ncm_sync, servidor, banco, ncm, descricao)


async def delete_ncm(servidor, banco, ncm):
    return await asyncio.to_thread(_delete_ncm_sync, servidor, banco, ncm)


async def search_cest(servidor, banco, search, limit=50):
    return await asyncio.to_thread(_search_cest_sync, servidor, banco, search, limit)


async def save_ncm_cest(servidor, banco, ncm, cest, descricao):
    return await asyncio.to_thread(_save_ncm_cest_sync, servidor, banco, ncm, cest, descricao)


async def delete_ncm_cest(servidor, banco, ncm, cest):
    return await asyncio.to_thread(_delete_ncm_cest_sync, servidor, banco, ncm, cest)
