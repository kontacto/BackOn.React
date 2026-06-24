"""Controle (tabela única) — limites de desconto por função e dados da empresa."""
import asyncio

from db.connection import _open_conn


def _get_limites_sync(servidor: str, banco: str) -> dict:
    """Lê os limites de desconto por função na tabela controle (registro único)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 desconto_pdv_gerente, desconto_pdv_supervisor, desconto_pdv_vendedor "
            "FROM controle"
        )
        r = cur.fetchone()
        cur.close(); conn.close()
        if not r:
            # sem registro de configuração → sem restrição
            return {"success": True, "gerente": 100.0, "supervisor": 100.0, "vendedor": 100.0, "configurado": False}
        return {
            "success": True,
            "gerente": float(r.get("desconto_pdv_gerente") or 0),
            "supervisor": float(r.get("desconto_pdv_supervisor") or 0),
            "vendedor": float(r.get("desconto_pdv_vendedor") or 0),
            "configurado": True,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _get_empresa_sync(servidor: str, banco: str) -> dict:
    """Dados da empresa (tabela controle, registro único): fantasia/razão social."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 empresa, fantasia, rz_social FROM controle")
        r = cur.fetchone() or {}
        cur.close(); conn.close()
        return {
            "success": True,
            "empresa": (r.get("empresa") or "").strip() or None,
            "fantasia": (r.get("fantasia") or "").strip() or None,
            "rz_social": (r.get("rz_social") or "").strip() or None,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


async def get_limites(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_limites_sync, servidor, banco)


async def get_empresa(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_empresa_sync, servidor, banco)
