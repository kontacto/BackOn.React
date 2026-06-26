"""Rotas do módulo de envio por WhatsApp (Pedidos, OS e futuros documentos)."""
from fastapi import APIRouter

from models.whatsapp_schemas import WhatsappConfigRequest, WhatsappSendRequest
from services.whatsapp import service as wa

router = APIRouter()


def _mask(cfg: dict) -> dict:
    """Não expõe segredos: devolve só se estão preenchidos."""
    return {
        "provider": cfg.get("provider") or "",
        "from_number": cfg.get("from_number") or "",
        "signature": cfg.get("signature") or "",
        "enabled": bool(cfg.get("enabled")),
        "configured": bool(cfg.get("configured")),
        "twilio_sid_set": bool(cfg.get("twilio_sid")),
        "twilio_token_set": bool(cfg.get("twilio_token")),
        "meta_phone_id_set": bool(cfg.get("meta_phone_id")),
        "meta_token_set": bool(cfg.get("meta_token")),
        "evolution_url": cfg.get("evolution_url") or "",
        "evolution_instance": cfg.get("evolution_instance") or "",
        "evolution_apikey_set": bool(cfg.get("evolution_apikey")),
    }


@router.get("/whatsapp/config")
async def get_config(servidor: str, banco: str):
    cfg = await wa.get_config(servidor, banco)
    return {"success": True, "config": _mask(cfg)}


@router.post("/whatsapp/config")
async def save_config(req: WhatsappConfigRequest):
    # Mantém segredos antigos quando o usuário deixa o campo vazio (não sobrescreve com vazio).
    current = await wa.get_config(req.servidor, req.banco)
    values = req.dict()
    for secret in ("twilio_sid", "twilio_token", "meta_phone_id", "meta_token", "evolution_apikey"):
        if not (values.get(secret) or "").strip():
            values[secret] = current.get(secret) or ""
    await wa.save_config(req.servidor, req.banco, values)
    cfg = await wa.get_config(req.servidor, req.banco)
    return {"success": True, "config": _mask(cfg)}


@router.get("/whatsapp/preview")
async def preview(servidor: str, banco: str, document_type: str, document_id: int):
    return await wa.preview(servidor, banco, document_type.upper(), document_id)


@router.post("/whatsapp/send")
async def send(req: WhatsappSendRequest):
    return await wa.send(
        req.servidor, req.banco, req.document_type.upper(), req.document_id,
        req.user_id, req.company_id, req.phone, req.message,
    )


@router.get("/whatsapp/logs")
async def logs(servidor: str, banco: str, document_type: str, document_id: int):
    items = await wa.list_logs(servidor, banco, document_type.upper(), document_id)
    return {"success": True, "items": items}
