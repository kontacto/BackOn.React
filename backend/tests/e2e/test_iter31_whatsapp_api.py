"""E2E tests for WhatsApp module (iter 31).

Validates:
  - GET/POST /api/whatsapp/config (mask + secret preservation)
  - GET /api/whatsapp/preview (OS and PED, E.164 phone, message body)
  - POST /api/whatsapp/send disabled -> success=false
  - POST /api/whatsapp/send with active config + bogus evolution -> FAILED log
  - GET /api/whatsapp/logs lists history
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
TIMEOUT = 60


def _q():
    return {"servidor": SERVIDOR, "banco": BANCO}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- CONFIG ----------
class TestConfig:
    def test_get_config_masks_secrets(self, api):
        r = api.get(f"{BASE}/api/whatsapp/config", params=_q(), timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        cfg = j["config"]
        # Should never expose raw secrets
        forbidden = {"twilio_sid", "twilio_token", "meta_phone_id", "meta_token", "evolution_apikey"}
        assert forbidden.isdisjoint(cfg.keys())
        # *_set flags must be present (booleans)
        for k in ("twilio_sid_set", "twilio_token_set", "meta_phone_id_set", "meta_token_set", "evolution_apikey_set"):
            assert isinstance(cfg.get(k), bool), f"{k} missing/typed wrong"

    def test_save_config_preserves_secret_when_empty(self, api):
        # Step 1: save with an evolution_apikey
        body1 = {
            "servidor": SERVIDOR, "banco": BANCO, "provider": "evolution",
            "enabled": False, "signature": "Equipe TESTE", "from_number": "",
            "twilio_sid": "", "twilio_token": "", "meta_phone_id": "", "meta_token": "",
            "evolution_url": "https://invalid.example.com", "evolution_instance": "inst-test",
            "evolution_apikey": "TEST_APIKEY_123",
        }
        r1 = api.post(f"{BASE}/api/whatsapp/config", json=body1, timeout=TIMEOUT)
        assert r1.status_code == 200, r1.text
        c1 = r1.json()["config"]
        assert c1["provider"] == "evolution"
        assert c1["evolution_apikey_set"] is True
        assert c1["evolution_url"] == "https://invalid.example.com"

        # Step 2: save again with apikey empty -> backend must KEEP secret
        body2 = dict(body1)
        body2["evolution_apikey"] = ""
        r2 = api.post(f"{BASE}/api/whatsapp/config", json=body2, timeout=TIMEOUT)
        assert r2.status_code == 200, r2.text
        c2 = r2.json()["config"]
        assert c2["evolution_apikey_set"] is True, "secret must be preserved when empty"
        assert c2["evolution_instance"] == "inst-test"

    def test_enable_config_for_send_tests(self, api):
        """Enable so later send tests can hit the provider."""
        body = {
            "servidor": SERVIDOR, "banco": BANCO, "provider": "evolution",
            "enabled": True, "signature": "Equipe TESTE", "from_number": "",
            "twilio_sid": "", "twilio_token": "", "meta_phone_id": "", "meta_token": "",
            "evolution_url": "https://invalid.example.com", "evolution_instance": "inst-test",
            "evolution_apikey": "",  # preserved
        }
        r = api.post(f"{BASE}/api/whatsapp/config", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["config"]["enabled"] is True


# ---------- PREVIEW ----------
class TestPreview:
    def test_preview_os_7(self, api):
        params = {**_q(), "document_type": "OS", "document_id": 7}
        r = api.get(f"{BASE}/api/whatsapp/preview", params=params, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        if not j.get("success"):
            pytest.skip(f"OS #7 not found: {j.get('message')}")
        assert "phone" in j
        assert isinstance(j.get("phone_valid"), bool)
        assert isinstance(j.get("message"), str) and "Ordem" in j["message"] or "Nº 7" in j["message"]

    def test_preview_ped_1(self, api):
        params = {**_q(), "document_type": "PED", "document_id": 1}
        r = api.get(f"{BASE}/api/whatsapp/preview", params=params, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        if not j.get("success"):
            pytest.skip(f"PED #1 not found: {j.get('message')}")
        assert "Pedido" in j.get("message", "") or "Nº 1" in j.get("message", "")
        # phone must start with + when valid
        if j.get("phone_valid"):
            assert j["phone"].startswith("+")

    def test_preview_invalid_doc(self, api):
        params = {**_q(), "document_type": "OS", "document_id": 99999999}
        r = api.get(f"{BASE}/api/whatsapp/preview", params=params, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("success") is False


# ---------- SEND ----------
class TestSend:
    def test_send_disabled_returns_message(self, api):
        # Temporarily disable
        cfg = api.get(f"{BASE}/api/whatsapp/config", params=_q(), timeout=TIMEOUT).json()["config"]
        body_off = {
            "servidor": SERVIDOR, "banco": BANCO, "provider": cfg.get("provider") or "evolution",
            "enabled": False, "signature": cfg.get("signature", ""), "from_number": cfg.get("from_number", ""),
            "twilio_sid": "", "twilio_token": "", "meta_phone_id": "", "meta_token": "",
            "evolution_url": cfg.get("evolution_url", ""), "evolution_instance": cfg.get("evolution_instance", ""),
            "evolution_apikey": "",
        }
        api.post(f"{BASE}/api/whatsapp/config", json=body_off, timeout=TIMEOUT)
        try:
            send_body = {
                "servidor": SERVIDOR, "banco": BANCO,
                "document_type": "OS", "document_id": 7,
                "user_id": None, "company_id": None, "phone": None, "message": None,
            }
            r = api.post(f"{BASE}/api/whatsapp/send", json=send_body, timeout=TIMEOUT)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("success") is False
            assert "desativ" in (j.get("message") or "").lower()
        finally:
            # Re-enable
            body_off["enabled"] = True
            api.post(f"{BASE}/api/whatsapp/config", json=body_off, timeout=TIMEOUT)

    def test_send_enabled_invalid_provider_logs_failed(self, api):
        # Find a doc that has a valid phone (preview)
        doc_type, doc_id = "OS", 7
        params = {**_q(), "document_type": doc_type, "document_id": doc_id}
        pj = api.get(f"{BASE}/api/whatsapp/preview", params=params, timeout=TIMEOUT).json()
        if not pj.get("success"):
            pytest.skip("preview not available")
        phone = pj.get("phone") if pj.get("phone_valid") else "+5511999998888"

        send_body = {
            "servidor": SERVIDOR, "banco": BANCO,
            "document_type": doc_type, "document_id": doc_id,
            "user_id": 1, "company_id": None,
            "phone": phone, "message": pj.get("message") or "TEST_message",
        }
        r = api.post(f"{BASE}/api/whatsapp/send", json=send_body, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is False, f"expected failure, got: {j}"
        assert j.get("log_id"), "must persist a FAILED log entry"

        # Verify GET /logs returns the entry
        time.sleep(1)
        rl = api.get(f"{BASE}/api/whatsapp/logs", params=params, timeout=TIMEOUT)
        assert rl.status_code == 200
        items = rl.json().get("items", [])
        assert any(it.get("id") == j["log_id"] for it in items), "log entry not found in /logs"
        ours = next(it for it in items if it["id"] == j["log_id"])
        assert ours["status"] == "FAILED"
        assert ours["provider"] in ("evolution", "")
        assert ours["phone_number"].startswith("+")


# ---------- LOGS ----------
class TestLogs:
    def test_logs_endpoint_ok(self, api):
        params = {**_q(), "document_type": "OS", "document_id": 7}
        r = api.get(f"{BASE}/api/whatsapp/logs", params=params, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        assert isinstance(j.get("items"), list)
