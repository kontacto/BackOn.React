"""Testes de integração — Módulos e Recursos (controle_configuracao) — Iteração 24.

Cobre:
- GET /api/controle-config/campos (38 campos)
- GET /api/controle-config (valores)
- POST /api/controle-config/salvar (desliga/religa Pedido_venda)
- Sobreposição em /api/permissoes/catalogo (PEDIDO some quando Pedido_venda=false)

CRÍTICO: ao final do módulo, garantir Pedido_venda=true e Clientes=true.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
QS = {"servidor": SERVIDOR, "banco": BANCO}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _retry_get(api, url, params=None, retries=3, sleep=4):
    """Azure SQL serverless pode dar 40613 na 1ª conexão — retry simples."""
    last = None
    for _ in range(retries):
        r = api.get(url, params=params, timeout=60)
        last = r
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code == 200 and data.get("success", True):
            return r, data
        time.sleep(sleep)
    return last, (last.json() if last is not None else {})


# ---------- Campos ----------
class TestCampos:
    def test_campos_retorna_38(self, api):
        r = api.get(f"{BASE_URL}/api/controle-config/campos", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["success"] is True
        campos = data["campos"]
        assert isinstance(campos, list)
        assert len(campos) == 38, f"esperava 38 campos, veio {len(campos)}"
        # Pedido_venda e Clientes presentes com label
        nomes = {c["campo"]: c["label"] for c in campos}
        assert "Pedido_venda" in nomes and nomes["Pedido_venda"]
        assert "Clientes" in nomes and nomes["Clientes"]
        # Todos têm label não vazio
        for c in campos:
            assert c.get("campo") and c.get("label")


# ---------- Read ----------
class TestRead:
    def test_get_valores_38_booleans(self, api):
        r, data = _retry_get(api, f"{BASE_URL}/api/controle-config", params=QS)
        assert r.status_code == 200, r.text
        assert data.get("success") is True, data
        valores = data["valores"]
        assert isinstance(valores, dict)
        assert len(valores) == 38, f"esperava 38 valores, veio {len(valores)}"
        # Booleans
        for k, v in valores.items():
            assert isinstance(v, bool), f"{k} não é bool: {v!r}"
        # Estado de produção esperado
        assert valores["Pedido_venda"] is True, "Pedido_venda deveria estar LIGADO no estado base"
        assert valores["Clientes"] is True, "Clientes deveria estar LIGADO no estado base"


# ---------- Save toggle + Override (Pedido_venda) ----------
class TestSalvarESobreposicao:

    def _set_pedido_venda(self, api, valor: bool):
        payload = {"servidor": SERVIDOR, "banco": BANCO, "valores": {"Pedido_venda": valor}}
        r = api.post(f"{BASE_URL}/api/controle-config/salvar", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True, data
        return data

    def _get_valores(self, api):
        _, data = _retry_get(api, f"{BASE_URL}/api/controle-config", params=QS)
        return data["valores"]

    def _has_pedido_no_catalogo(self, api):
        r, data = _retry_get(api, f"{BASE_URL}/api/permissoes/catalogo", params=QS)
        assert r.status_code == 200, r.text
        assert data.get("success") is True, data
        # Procura menu MOVIMENTO -> tela PEDIDO
        for menu in data["catalogo"]:
            if menu.get("tela") == "MOVIMENTO":
                for t in menu["children"]:
                    if t.get("tela") == "PEDIDO":
                        return True
        return False

    def test_desliga_pedido_venda_e_sobrepoe(self, api):
        # baseline: liga (idempotente)
        self._set_pedido_venda(api, True)
        assert self._get_valores(api)["Pedido_venda"] is True
        assert self._has_pedido_no_catalogo(api) is True

        # desliga
        self._set_pedido_venda(api, False)
        valores = self._get_valores(api)
        assert valores["Pedido_venda"] is False, "Pedido_venda deveria refletir FALSE após salvar"

        # catalog não deve conter PEDIDO
        assert self._has_pedido_no_catalogo(api) is False, "PEDIDO deveria sumir do catálogo quando módulo desligado"

    def test_religa_e_restaura_estado(self, api):
        # CRITICAL: garantir Pedido_venda=true e Clientes=true
        payload = {
            "servidor": SERVIDOR,
            "banco": BANCO,
            "valores": {"Pedido_venda": True, "Clientes": True},
        }
        r = api.post(f"{BASE_URL}/api/controle-config/salvar", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True
        valores = self._get_valores(api)
        assert valores["Pedido_venda"] is True, "DEVE estar TRUE ao final (estado de produção)"
        assert valores["Clientes"] is True, "DEVE estar TRUE ao final (estado de produção)"
        # E PEDIDO volta ao catálogo
        assert self._has_pedido_no_catalogo(api) is True


# ---------- Sanity: catalog sem servidor/banco usa CATALOGO completo ----------
class TestCatalogoSemFiltro:
    def test_catalogo_sem_filtro_inclui_pedido(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/catalogo", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["success"] is True
        # Esperado conter MOVIMENTO > PEDIDO (sem filtro)
        has = False
        for menu in data["catalogo"]:
            if menu.get("tela") == "MOVIMENTO":
                for t in menu["children"]:
                    if t.get("tela") == "PEDIDO":
                        has = True
        assert has, "Catálogo completo (sem filtro) deveria conter PEDIDO"
