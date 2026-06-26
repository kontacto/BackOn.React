"""DTOs do módulo de envio por WhatsApp."""
from typing import Optional

from pydantic import BaseModel


class WhatsappConfigRequest(BaseModel):
    servidor: str
    banco: str
    provider: Optional[str] = ""           # twilio | meta | evolution
    from_number: Optional[str] = ""
    twilio_sid: Optional[str] = ""
    twilio_token: Optional[str] = ""
    meta_phone_id: Optional[str] = ""
    meta_token: Optional[str] = ""
    evolution_url: Optional[str] = ""
    evolution_instance: Optional[str] = ""
    evolution_apikey: Optional[str] = ""
    signature: Optional[str] = ""
    message_template: Optional[str] = ""
    enabled: bool = False


class WhatsappSendRequest(BaseModel):
    servidor: str
    banco: str
    document_type: str                     # PED | OS
    document_id: int
    phone: Optional[str] = None            # sobrescreve o telefone do cliente
    message: Optional[str] = None          # sobrescreve a mensagem montada
    user_id: Optional[int] = None
    company_id: Optional[str] = None
