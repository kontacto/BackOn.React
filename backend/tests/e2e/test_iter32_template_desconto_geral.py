"""E2E tests for iter32:

1) WhatsApp message_template
   - POST /api/whatsapp/config persists `message_template`
   - GET /api/whatsapp/config returns it back (mask)
   - GET /api/whatsapp/preview uses the template (variables {primeiro_nome},{tipo},{numero},{valor},{assinatura})
   - Save empty template => falls back to default (multi-line message)
   - Unknown variables are stripped to empty

2) OS desconto-geral
   - POST /api/os/{codigo}/desconto-geral {valor=X} reduces total proportionally
   - valor=0 zera os descontos e total retorna ao cheio
"""
import os
import pytest
import requests

BASE = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
TIMEOUT = 90
OS_COD = 7


def _q():
    return {"servidor": SERVIDOR, "banco": BANCO}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def saved_state(api):
    """Save current whatsapp config + OS state, restore at end."""
    cfg = api.get(f"{BASE}/api/whatsapp/config", params=_q(), timeout=TIMEOUT).json().get("config", {})
    yield cfg
    # restore template/signature (won't overwrite secrets due to mask logic)
    restore = {
        "servidor": SERVIDOR, "banco": BANCO,
        "provider": cfg.get("provider") or "",
        "from_number": cfg.get("from_number") or "",
        "twilio_sid": "", "twilio_token": "",
        "meta_phone_id": "", "meta_token": "",
        "evolution_url": cfg.get("evolution_url") or "",
        "evolution_instance": cfg.get("evolution_instance") or "",
        "evolution_apikey": "",
        "signature": cfg.get("signature") or "",
        "message_template": cfg.get("message_template") or "",
        "enabled": bool(cfg.get("enabled")),
    }
    api.post(f"{BASE}/api/whatsapp/config", json=restore, timeout=TIMEOUT)
    # zera desconto da OS#7 no final
    api.post(f"{BASE}/api/os/{OS_COD}/desconto-geral",
             json={"servidor": SERVIDOR, "banco": BANCO, "valor": 0, "usuario_codigo": -2, "funcao": 1},
             timeout=TIMEOUT)


# ---------- WhatsApp message_template ----------
class TestWhatsappTemplate:
    def _save(self, api, template, signature="Equipe KONTACTO"):
        body = {
            "servidor": SERVIDOR, "banco": BANCO,
            "provider": "evolution",
            "from_number": "", "twilio_sid": "", "twilio_token": "",
            "meta_phone_id": "", "meta_token": "",
            "evolution_url": "https://invalid.example.com",
            "evolution_instance": "inst-test", "evolution_apikey": "",
            "signature": signature,
            "message_template": template,
            "enabled": False,
        }
        r = api.post(f"{BASE}/api/whatsapp/config", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        return r.json()["config"]

    def test_save_and_read_template(self, api, saved_state):
        tpl = "Olá {primeiro_nome}, {tipo} {numero} = {valor}. {assinatura}"
        cfg = self._save(api, tpl)
        assert cfg["message_template"] == tpl, f"template not persisted: {cfg.get('message_template')!r}"
        # confirm via GET
        r = api.get(f"{BASE}/api/whatsapp/config", params=_q(), timeout=TIMEOUT)
        assert r.status_code == 200
        got = r.json()["config"]
        assert got["message_template"] == tpl

    def test_preview_renders_template(self, api, saved_state):
        tpl = "Olá {primeiro_nome}, {tipo} {numero} = {valor}. {assinatura}"
        self._save(api, tpl, signature="Equipe KONTACTO")
        r = api.get(f"{BASE}/api/whatsapp/preview",
                    params={**_q(), "document_type": "OS", "document_id": OS_COD},
                    timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        msg = j["message"]
        assert "Olá" in msg
        assert "Ordem de Serviço" in msg  # {tipo}
        assert f"{OS_COD}" in msg          # {numero}
        assert "R$" in msg                 # {valor}
        assert "Equipe KONTACTO" in msg    # {assinatura}
        # template inline (sem múltiplas quebras de linha do default)
        assert "Segue seu(sua)" not in msg

    def test_preview_unknown_var_becomes_empty(self, api, saved_state):
        tpl = "X={cliente};Y={nao_existe};Z={primeiro_nome}"
        self._save(api, tpl)
        r = api.get(f"{BASE}/api/whatsapp/preview",
                    params={**_q(), "document_type": "OS", "document_id": OS_COD},
                    timeout=TIMEOUT)
        assert r.status_code == 200
        msg = r.json()["message"]
        # variável desconhecida deve sumir (sem deixar literal "{nao_existe}")
        assert "{nao_existe}" not in msg
        assert "{" not in msg and "}" not in msg, f"raw braces remain: {msg!r}"
        assert "Y=;" in msg or "Y=" in msg

    def test_empty_template_falls_back_to_default(self, api, saved_state):
        # save with explicit empty template
        cfg = self._save(api, "", signature="Equipe KONTACTO")
        assert (cfg["message_template"] or "") == ""
        r = api.get(f"{BASE}/api/whatsapp/preview",
                    params={**_q(), "document_type": "OS", "document_id": OS_COD},
                    timeout=TIMEOUT)
        assert r.status_code == 200
        msg = r.json()["message"]
        # default tem várias linhas e contém "Segue seu(sua)"
        assert "Segue seu(sua)" in msg
        assert "Ordem de Serviço" in msg
        assert msg.count("\n") >= 3


# ---------- OS desconto-geral ----------
class TestOSDescontoGeral:
    def _get_total(self, api):
        r = api.get(f"{BASE}/api/os/{OS_COD}", params=_q(), timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        # possíveis campos: total, valor
        data = j.get("os") or j
        total = data.get("valor", data.get("total"))
        return float(total or 0)

    def test_zera_desconto_primeiro(self, api, saved_state):
        # zera antes para baseline previsível
        r = api.post(f"{BASE}/api/os/{OS_COD}/desconto-geral",
                     json={"servidor": SERVIDOR, "banco": BANCO, "valor": 0, "usuario_codigo": -2, "funcao": 1},
                     timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        total_cheio = float(j.get("total") or 0)
        assert total_cheio > 0, f"OS#{OS_COD} sem itens? total={total_cheio}"

    def test_aplica_desconto_geral_reduz_total(self, api, saved_state):
        total_antes = self._get_total(api)
        valor = 10.0
        r = api.post(f"{BASE}/api/os/{OS_COD}/desconto-geral",
                     json={"servidor": SERVIDOR, "banco": BANCO, "valor": valor, "usuario_codigo": -2, "funcao": 1},
                     timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        total_depois = float(j.get("total") or 0)
        # com soma >= valor, o total novo deve ser ~ (total_antes - valor) (arredondamentos)
        assert abs(total_depois - (total_antes - valor)) < 0.5, (
            f"esperado ~{total_antes - valor}, recebido {total_depois}"
        )
        # percentual reportado deve ser > 0
        assert float(j.get("percentual") or 0) > 0

        # verifica via GET descontos
        r2 = api.get(f"{BASE}/api/os/{OS_COD}/descontos", params=_q(), timeout=TIMEOUT)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2.get("success") is True
        soma_descontos = sum(float(it.get("valor_total") or 0) for it in j2.get("items", []))
        assert abs(soma_descontos - valor) < 0.5, (
            f"soma descontos {soma_descontos} != {valor}"
        )

    def test_valor_zero_zera_descontos(self, api, saved_state):
        r = api.post(f"{BASE}/api/os/{OS_COD}/desconto-geral",
                     json={"servidor": SERVIDOR, "banco": BANCO, "valor": 0, "usuario_codigo": -2, "funcao": 1},
                     timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True, j
        # descontos endpoint deve retornar lista vazia
        r2 = api.get(f"{BASE}/api/os/{OS_COD}/descontos", params=_q(), timeout=TIMEOUT)
        assert r2.status_code == 200
        items = r2.json().get("items", [])
        assert items == [], f"esperado vazio, recebeu {items}"

    def test_analise_ok_apos_desconto(self, api, saved_state):
        # aplica desconto pequeno
        api.post(f"{BASE}/api/os/{OS_COD}/desconto-geral",
                 json={"servidor": SERVIDOR, "banco": BANCO, "valor": 5, "usuario_codigo": -2, "funcao": 1},
                 timeout=TIMEOUT)
        r = api.get(f"{BASE}/api/os/{OS_COD}/analise", params=_q(), timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True, j
        totais = j.get("totais", {})
        assert float(totais.get("desconto") or 0) >= 4.5
        assert float(totais.get("venda") or 0) > 0
        # zera no final
        api.post(f"{BASE}/api/os/{OS_COD}/desconto-geral",
                 json={"servidor": SERVIDOR, "banco": BANCO, "valor": 0, "usuario_codigo": -2, "funcao": 1},
                 timeout=TIMEOUT)
