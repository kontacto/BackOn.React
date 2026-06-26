"""Camada de provedores de WhatsApp (Strategy Pattern).

Cada provedor implementa `IWhatsappProvider.send_text` e recebe sua própria
configuração (dict). A troca de provedor é feita em runtime pela factory
`build_provider`, lendo o campo `provider` da configuração do tenant.

Provedores suportados:
  - twilio     → Twilio WhatsApp API
  - meta       → Meta WhatsApp Cloud API (Graph API)
  - evolution  → Evolution API (self-hosted)

Fase 1: somente mensagem de texto (sem mídia).
HTTP via biblioteca padrão (urllib) — não requer dependências externas.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

GRAPH_VERSION = "v20.0"
HTTP_TIMEOUT = 30


def _digits(phone: str) -> str:
    """Remove tudo que não é dígito (E.164 sem '+')."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _http_post(url: str, *, form: Optional[dict] = None, json_body: Optional[dict] = None,
               headers: Optional[dict] = None, basic_auth: Optional[tuple] = None) -> tuple:
    """POST via urllib. Retorna (status_code, texto). status_code=0 em falha de comunicação."""
    headers = dict(headers or {})
    if form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    else:
        body = json.dumps(json_body or {}).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    if basic_auth:
        token = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, detail
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"comunicação: {e}"


class WhatsappResult:
    def __init__(self, success: bool, provider_message_id: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.provider_message_id = provider_message_id
        self.error = error


class IWhatsappProvider(ABC):
    """Contrato de um provedor de envio de WhatsApp."""

    name: str = "base"

    @abstractmethod
    def validate_config(self) -> Optional[str]:
        """Retorna None se a config está completa, ou uma mensagem de erro."""

    @abstractmethod
    def send_text(self, to_e164: str, message: str) -> WhatsappResult:
        """Envia uma mensagem de texto para o número (E.164)."""


class TwilioProvider(IWhatsappProvider):
    name = "twilio"

    def __init__(self, cfg: dict):
        self.sid = (cfg.get("twilio_sid") or "").strip()
        self.token = (cfg.get("twilio_token") or "").strip()
        self.from_number = (cfg.get("from_number") or "").strip()

    def validate_config(self) -> Optional[str]:
        if not self.sid or not self.token:
            return "Twilio: informe Account SID e Auth Token."
        if not self.from_number:
            return "Twilio: informe o número de origem (From)."
        return None

    def send_text(self, to_e164: str, message: str) -> WhatsappResult:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        from_fmt = self.from_number if self.from_number.startswith("whatsapp:") else f"whatsapp:+{_digits(self.from_number)}"
        form = {"From": from_fmt, "To": f"whatsapp:+{_digits(to_e164)}", "Body": message}
        status, text = _http_post(url, form=form, basic_auth=(self.sid, self.token))
        if status in (200, 201):
            sid = ""
            try:
                sid = json.loads(text).get("sid", "")
            except Exception:
                pass
            return WhatsappResult(True, provider_message_id=sid)
        if status == 0:
            return WhatsappResult(False, error=f"Twilio falha de {text}")
        return WhatsappResult(False, error=f"Twilio HTTP {status}: {text[:300]}")


class MetaProvider(IWhatsappProvider):
    name = "meta"

    def __init__(self, cfg: dict):
        self.phone_id = (cfg.get("meta_phone_id") or "").strip()
        self.token = (cfg.get("meta_token") or "").strip()

    def validate_config(self) -> Optional[str]:
        if not self.phone_id or not self.token:
            return "Meta Cloud API: informe Phone Number ID e Access Token."
        return None

    def send_text(self, to_e164: str, message: str) -> WhatsappResult:
        url = f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_id}/messages"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": _digits(to_e164),
            "type": "text",
            "text": {"preview_url": True, "body": message},
        }
        status, text = _http_post(url, json_body=payload, headers=headers)
        if status == 200:
            mid = ""
            try:
                mid = (json.loads(text).get("messages") or [{}])[0].get("id", "")
            except Exception:
                pass
            return WhatsappResult(True, provider_message_id=mid)
        if status == 0:
            return WhatsappResult(False, error=f"Meta falha de {text}")
        return WhatsappResult(False, error=f"Meta HTTP {status}: {text[:300]}")


class EvolutionProvider(IWhatsappProvider):
    name = "evolution"

    def __init__(self, cfg: dict):
        self.base = (cfg.get("evolution_url") or "").strip().rstrip("/")
        self.instance = (cfg.get("evolution_instance") or "").strip()
        self.apikey = (cfg.get("evolution_apikey") or "").strip()

    def validate_config(self) -> Optional[str]:
        if not self.base or not self.instance or not self.apikey:
            return "Evolution API: informe URL, instância e API Key."
        return None

    def send_text(self, to_e164: str, message: str) -> WhatsappResult:
        url = f"{self.base}/message/sendText/{self.instance}"
        headers = {"apikey": self.apikey}
        payload = {"number": _digits(to_e164), "text": message}
        status, text = _http_post(url, json_body=payload, headers=headers)
        if status in (200, 201):
            mid = ""
            try:
                j = json.loads(text)
                mid = (j.get("key") or {}).get("id", "") if isinstance(j, dict) else ""
            except Exception:
                pass
            return WhatsappResult(True, provider_message_id=mid)
        if status == 0:
            return WhatsappResult(False, error=f"Evolution falha de {text}")
        return WhatsappResult(False, error=f"Evolution HTTP {status}: {text[:300]}")


_PROVIDERS = {"twilio": TwilioProvider, "meta": MetaProvider, "evolution": EvolutionProvider}


def build_provider(cfg: dict) -> Optional[IWhatsappProvider]:
    """Factory: instancia o provedor conforme cfg['provider']."""
    klass = _PROVIDERS.get((cfg.get("provider") or "").strip().lower())
    return klass(cfg) if klass else None
