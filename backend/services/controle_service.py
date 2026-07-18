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
    """Dados da empresa (tabela controle, registro único): fantasia/razão
    social + endereço/documento/telefone (cabeçalho de recibo/impressão,
    ver `Cabec`/`Pedido_48_COL` no FrmManPedBar.frm) e `cod_rel` (decide se
    o recibo mostra código interno ou código de fábrica do item)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 empresa, fantasia, rz_social, uf, endereco, numero, complemento, "
            "       bairro, cidade, cep, ddd, telefone, CELULAR, cgc, inscr_est, cod_rel, "
            "       exige_cpf_cliente, aceita_duplicar_cnpj "
            "FROM controle"
        )
        r = cur.fetchone() or {}
        cur.close(); conn.close()
        return {
            "success": True,
            "empresa": (r.get("empresa") or "").strip() or None,
            "fantasia": (r.get("fantasia") or "").strip() or None,
            "rz_social": (r.get("rz_social") or "").strip() or None,
            "uf": (r.get("uf") or "").strip() or None,
            "endereco": (r.get("endereco") or "").strip(),
            "numero": r.get("numero"),
            "complemento": (r.get("complemento") or "").strip(),
            "bairro": (r.get("bairro") or "").strip(),
            "cidade": (r.get("cidade") or "").strip(),
            "cep": (r.get("cep") or "").strip(),
            "ddd": (r.get("ddd") or ""),
            "telefone": (r.get("telefone") or "").strip(),
            "celular": (r.get("CELULAR") or "").strip(),
            "cgc": (r.get("cgc") or "").strip(),
            "inscr_est": (r.get("inscr_est") or "").strip(),
            "cod_rel": (r.get("cod_rel") or "").strip(),
            "exige_cpf_cliente": bool(r.get("exige_cpf_cliente")),
            "aceita_duplicar_cnpj": bool(r.get("aceita_duplicar_cnpj")),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _get_mensagens_pdv_sync(servidor: str, banco: str) -> dict:
    """Mensagens configuráveis do rodapé do recibo/comanda (tabela
    `mensagenspdv`, até 5 linhas, centralizadas na impressão)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "linhas": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 linha1, linha2, linha3, linha4, linha5 FROM mensagenspdv")
        r = cur.fetchone() or {}
        cur.close(); conn.close()
        linhas = [
            (r.get(f"linha{i}") or "").strip()
            for i in range(1, 6)
        ]
        return {"success": True, "linhas": [l for l in linhas if l]}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "linhas": []}


async def get_limites(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_limites_sync, servidor, banco)


async def get_empresa(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_empresa_sync, servidor, banco)


async def get_mensagens_pdv(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_mensagens_pdv_sync, servidor, banco)
