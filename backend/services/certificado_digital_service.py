"""Certificado Digital (aba Fiscal de Controle do Sistema) — tabela
`certificado_digital`. Legado: grid "Certificado Digital" em `FrmGerCon.frm`, cujos
botões A1/A3 chamavam uma DLL (`Backon.Controllers/Certificado.vb`, ver
"Legacy VB6 Source Reference" no CLAUDE.md) que só faz parsing local de
`.pfx`/`.cer` via `X509Certificate2` — não é uma API de assinatura remota. Isso é
replicável em Python com a lib `cryptography` (PKCS#12), sem precisar da DLL.

A1 (arquivo `.pfx` com senha) é o único tipo suportado por ora — A3 depende de
hardware/token e não tem como ser lido a partir de um upload de arquivo.

O `.pfx` em si é armazenado (coluna `certificado_digital.certificado_digital`,
varbinary — a própria tabela legada já reserva esse campo pra isso) junto da senha
(`senha_certificado`) — mesmo desenho de dados já usado pelo sistema legado, não é
uma decisão nova de segurança introduzida aqui.
"""
import asyncio
from typing import Optional

from cryptography.hazmat.primitives.serialization import pkcs12

from db.connection import _open_conn, _to_json_safe


def _list_certificados_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT sequencia, data_inicio, data_fim, tipo_certificado, numero_serial, "
            "cnpj_certificado FROM certificado_digital ORDER BY sequencia DESC"
        )
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _extrair_cnpj(subject_rfc4514: str) -> Optional[str]:
    # Certificados e-CNPJ ICP-Brasil costumam trazer "CN=RAZAO SOCIAL:CNPJ" —
    # tentativa best-effort, sem falhar o upload se não encontrar.
    import re
    m = re.search(r":(\d{14})", subject_rfc4514 or "")
    return m.group(1) if m else None


def _upload_certificado_sync(servidor: str, banco: str, arquivo: bytes, senha: str, tipo_certificado: str) -> dict:
    senha_bytes = (senha or "").encode("utf-8") if senha else None
    try:
        _chave, cert, _cadeia = pkcs12.load_key_and_certificates(arquivo, senha_bytes)
    except Exception as e:
        return {"success": False, "message": f"Não foi possível ler o certificado (.pfx inválido ou senha incorreta): {e}"}
    if cert is None:
        return {"success": False, "message": "Arquivo não contém um certificado válido."}

    data_inicio = cert.not_valid_before_utc.date()
    data_fim = cert.not_valid_after_utc.date()
    numero_serial = format(cert.serial_number, "X")
    cnpj = _extrair_cnpj(cert.subject.rfc4514_string())

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "INSERT INTO certificado_digital "
            "(data_inicio, data_fim, certificado_digital, senha_certificado, tipo_certificado, numero_serial, cnpj_certificado) "
            "OUTPUT INSERTED.sequencia "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (data_inicio, data_fim, arquivo, (senha or "")[:20] or None, (tipo_certificado or "A1")[:2], numero_serial[:40], cnpj),
        )
        nova_sequencia = int(cur.fetchone()["sequencia"])
        conn.commit()
        cur.close()
        return {
            "success": True, "sequencia": nova_sequencia, "message": "Certificado cadastrado.",
            "data_inicio": data_inicio.isoformat(), "data_fim": data_fim.isoformat(),
            "numero_serial": numero_serial,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_certificado_sync(servidor: str, banco: str, sequencia: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM certificado_digital WHERE sequencia=%s", (sequencia,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Certificado não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Certificado excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_certificados(servidor, banco):
    return await asyncio.to_thread(_list_certificados_sync, servidor, banco)


async def upload_certificado(servidor, banco, arquivo, senha, tipo_certificado):
    return await asyncio.to_thread(_upload_certificado_sync, servidor, banco, arquivo, senha, tipo_certificado)


async def delete_certificado(servidor, banco, sequencia):
    return await asyncio.to_thread(_delete_certificado_sync, servidor, banco, sequencia)
