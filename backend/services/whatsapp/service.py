"""WhatsappService — orquestra validação, montagem da mensagem, envio (com retry)
e registro de log. Mantém regras de negócio fora dos controllers (rotas).
"""
import asyncio
import re
import time
from typing import Optional

from services.whatsapp import repository as repo
from services.whatsapp.providers import build_provider

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5  # segundos (multiplicado pela tentativa)


# ---------------- Validators / Sanitizers ----------------
def sanitize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    # remove caracteres de controle, preserva quebras de linha
    return "".join(ch for ch in s if ch == "\n" or ch == "\t" or ord(ch) >= 32).strip()


def normalize_phone(raw: Optional[str], default_ddi: str = "55") -> str:
    """Normaliza para E.164. Assume Brasil (55) quando vem só o número nacional."""
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    # já veio com DDI internacional? (12+ dígitos) -> usa como está
    if raw.strip().startswith("+"):
        return "+" + digits
    if len(digits) <= 11:  # número nacional BR (10 ou 11 dígitos)
        digits = default_ddi + digits
    return "+" + digits


def is_valid_e164(phone: str) -> bool:
    return bool(_E164_RE.match(phone or ""))


# ---------------- Message builder ----------------
def build_message(summary: dict, signature: str) -> str:
    nome = summary.get("cliente_nome") or "cliente"
    primeiro = nome.split(" ")[0] if nome else "cliente"
    data = summary.get("data")
    data_br = "—"
    if data:
        try:
            y, m, d = data.split("-")
            data_br = f"{d}/{m}/{y}"
        except Exception:
            data_br = data
    total = summary.get("total") or 0
    total_br = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    linhas = [
        f"Olá {primeiro},",
        "",
        f"Segue seu(sua) {summary.get('doc_label')}: Nº {summary.get('doc')}.",
        "",
        f"Data: {data_br}",
    ]
    if summary.get("doc_type") == "OS":
        if summary.get("veiculo"):
            linhas.append(f"Equipamento/Veículo: {summary['veiculo']}")
        if summary.get("serie"):
            linhas.append(f"Nº de Série/Chassi: {summary['serie']}")
        if summary.get("descricao_cliente"):
            linhas.append(f"Relato do cliente: {summary['descricao_cliente']}")
        if summary.get("resumo"):
            linhas.append(f"Serviço executado: {summary['resumo']}")
    if summary.get("obs"):
        linhas.append(f"Obs: {summary['obs']}")
    if summary.get("situacao_label"):
        linhas.append(f"Status: {summary['situacao_label']}")
    linhas.append(f"Valor: {total_br}")
    linhas.append("")
    linhas.append("Qualquer dúvida estamos à disposição.")
    linhas.append("")
    linhas.append(signature or "Equipe")
    return "\n".join(linhas)


# ---------------- Core ----------------
def _is_transient(error: Optional[str]) -> bool:
    if not error:
        return False
    e = error.lower()
    return ("comunicação" in e) or (" http 5" in e) or ("timeout" in e) or ("429" in e)


def _preview_sync(servidor: str, banco: str, doc_type: str, doc_id: int) -> dict:
    summary = repo.get_document_summary(servidor, banco, doc_type, doc_id)
    if not summary:
        return {"success": False, "message": "Documento não encontrado."}
    cfg = repo.get_config_raw(servidor, banco)
    phone = normalize_phone(summary.get("telefone"))
    message = build_message(summary, cfg.get("signature") or "")
    return {
        "success": True,
        "cliente_nome": summary.get("cliente_nome"),
        "phone": phone,
        "phone_raw": summary.get("telefone") or "",
        "phone_valid": is_valid_e164(phone),
        "message": message,
        "provider": cfg.get("provider"),
        "enabled": cfg.get("enabled"),
        "configured": cfg.get("configured"),
    }


def _send_sync(servidor: str, banco: str, doc_type: str, doc_id: int,
               user_id: Optional[int], company_id: Optional[str],
               override_phone: Optional[str], override_message: Optional[str]) -> dict:
    summary = repo.get_document_summary(servidor, banco, doc_type, doc_id)
    if not summary:
        return {"success": False, "message": "Documento não encontrado."}

    cfg = repo.get_config_raw(servidor, banco)
    if not cfg.get("enabled"):
        return {"success": False, "message": "Envio por WhatsApp está desativado. Ative em Configurações."}

    provider = build_provider(cfg)
    if not provider:
        return {"success": False, "message": "Provedor de WhatsApp não configurado."}
    cfg_err = provider.validate_config()
    if cfg_err:
        return {"success": False, "message": cfg_err}

    phone = normalize_phone(override_phone or summary.get("telefone"))
    if not is_valid_e164(phone):
        return {"success": False, "message": "Cliente sem celular válido (formato E.164)."}

    message = sanitize_text(override_message) or build_message(summary, cfg.get("signature") or "")

    # envio com retry em falhas transitórias + observabilidade (duração)
    started = time.time()
    result = None
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        result = provider.send_text(phone, message)
        if result.success:
            break
        last_error = result.error
        if not _is_transient(result.error) or attempt == MAX_RETRIES:
            break
        time.sleep(RETRY_BACKOFF * attempt)
    duration_ms = int((time.time() - started) * 1000)

    status = "SUCCESS" if (result and result.success) else "FAILED"
    log_id = repo.insert_log(servidor, banco, {
        "company_id": company_id,
        "document_type": doc_type,
        "document_id": doc_id,
        "customer_id": summary.get("cliente_id"),
        "phone_number": phone,
        "message": message,
        "status": status,
        "error_message": None if status == "SUCCESS" else (last_error or "Falha desconhecida"),
        "provider": cfg.get("provider"),
        "provider_message_id": result.provider_message_id if result else None,
        "duration_ms": duration_ms,
        "user_id": user_id,
    })

    if status == "SUCCESS":
        return {"success": True, "log_id": log_id, "phone": phone, "duration_ms": duration_ms}
    return {"success": False, "message": last_error or "Falha no envio.", "log_id": log_id}


# ---------------- async wrappers ----------------
async def preview(servidor: str, banco: str, doc_type: str, doc_id: int) -> dict:
    return await asyncio.to_thread(_preview_sync, servidor, banco, doc_type, doc_id)


async def send(servidor: str, banco: str, doc_type: str, doc_id: int,
               user_id, company_id, override_phone, override_message) -> dict:
    return await asyncio.to_thread(
        _send_sync, servidor, banco, doc_type, doc_id, user_id, company_id, override_phone, override_message
    )


async def get_config(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(repo.get_config_raw, servidor, banco)


async def save_config(servidor: str, banco: str, values: dict) -> None:
    return await asyncio.to_thread(repo.save_config, servidor, banco, values)


async def list_logs(servidor: str, banco: str, doc_type: str, doc_id: int) -> list:
    return await asyncio.to_thread(repo.list_logs, servidor, banco, doc_type, doc_id)
