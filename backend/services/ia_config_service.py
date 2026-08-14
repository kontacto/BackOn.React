"""IA Key — chave de API da Anthropic (Claude) usada pelo Motor de
Formulário Dinâmico ("Importar Formulário" — ver `layout_service.py`).
Gravada em `controle.ANTHROPIC_API_KEY` (coluna nova, sem precedente no
legado — ver `_ensure_anthropic_api_key_col`), mesmo padrão mono-empresa já
usado em `controle_sistema_service.py` (linha única, `UPDATE` às cegas sem
WHERE). Tela dedicada "IA Key" em Configurações > Administração — acesso
master-only no FRONTEND (mesmo gate de "Módulos e Recursos"/"WhatsApp",
que também não têm checagem de papel no backend nem entrada no catálogo de
permissões — este serviço segue o mesmo precedente, pedido explícito do
usuário 2026-08-12: "Acessado somente pelo Master").

**A chave nunca é devolvida em texto puro pra tela** — só um indicador
`configurada` (bool) + os últimos 4 caracteres, pro usuário confirmar qual
chave está salva sem expor o valor inteiro de volta pro navegador."""
import asyncio
import logging

from db.connection import _open_conn

_log = logging.getLogger(__name__)


def _ensure_anthropic_api_key_col(cur) -> None:
    """Migração idempotente: coluna `ANTHROPIC_API_KEY` em `controle` —
    campo genuinamente novo (sem precedente no legado VB6), usado pelo
    Importar Formulário. Mesmo padrão de
    `pedido_common._ensure_qtd_pessoas_col`."""
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.columns "
        "WHERE Name='ANTHROPIC_API_KEY' AND Object_ID=Object_ID('controle')) "
        "ALTER TABLE controle ADD ANTHROPIC_API_KEY NVARCHAR(200) NULL"
    )


def _friendly(acao: str, e: Exception) -> str:
    _log.warning("Falha ao %s (IA Key): %s", acao, e, exc_info=True)
    return f"Não foi possível {acao} agora. Tente novamente ou contate o suporte."


def _get_status_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 ANTHROPIC_API_KEY FROM controle")
        row = cur.fetchone()
        cur.close()
        conn.close()
        valor = ((row.get("ANTHROPIC_API_KEY") if row else None) or "").strip()
        return {
            "success": True,
            "configurada": bool(valor),
            "final": valor[-4:] if len(valor) >= 4 else None,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": _friendly("consultar a chave", e)}


def _save_sync(servidor: str, banco: str, api_key: str) -> dict:
    valor = (api_key or "").strip()
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("UPDATE controle SET ANTHROPIC_API_KEY=%s", (valor or None,))
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
        return {"success": False, "message": _friendly("gravar a chave", e)}


async def get_status(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_get_status_sync, servidor, banco)


async def save(servidor: str, banco: str, api_key: str) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, api_key)
