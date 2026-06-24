"""
Iter 13 — Validação backend:
 - /api/dashboard/me: totais inclui 'descontos' (= 2.40)
 - /api/relatorios/pedidos: retorna bloco 'totais' com qtd_pedidos, margem, margem_pct,
   desconto, produtos, servicos e respeita filtro de situacao (A vs F).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
COMMON = f"servidor={SERVIDOR}&banco={BANCO}"


@pytest.fixture
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# -------------------- Dashboard --------------------
class TestDashboardMe:
    def test_dashboard_returns_descontos_field(self, api):
        r = api.get(f"{BASE_URL}/api/dashboard/me?{COMMON}&vendedor=all")
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        tot = j.get("totais") or {}
        assert "descontos" in tot, "Campo totais.descontos ausente"
        assert round(float(tot["descontos"]), 2) == 2.40
        assert round(float(tot["margem"]), 2) == 24.39
        assert round(float(tot["margem_pct"]), 2) == 44.75
        assert int(tot.get("pedidos", 0)) == 1

    def test_dashboard_situacao_F_zera_descontos(self, api):
        r = api.get(f"{BASE_URL}/api/dashboard/me?{COMMON}&vendedor=all&situacao=F")
        assert r.status_code == 200
        j = r.json()
        tot = j.get("totais") or {}
        assert int(tot.get("pedidos", 0)) == 0
        assert float(tot.get("descontos", 0)) == 0.0


# -------------------- Relatório de Pedidos --------------------
class TestRelatorioPedidosTotais:
    def test_totais_block_present(self, api):
        url = f"{BASE_URL}/api/relatorios/pedidos?{COMMON}&data_ini=2000-01-01&data_fim=2100-12-31"
        r = api.get(url)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        assert "totais" in j, "Bloco totais ausente em /relatorios/pedidos"
        t = j["totais"]
        for k in ("qtd_pedidos", "venda", "desconto", "custo", "margem", "margem_pct", "produtos", "servicos"):
            assert k in t, f"chave {k} ausente em totais"

    def test_totais_values_match_pedido1(self, api):
        url = f"{BASE_URL}/api/relatorios/pedidos?{COMMON}&data_ini=2000-01-01&data_fim=2100-12-31"
        j = api.get(url).json()
        t = j["totais"]
        assert int(t["qtd_pedidos"]) == 1
        assert round(float(t["venda"]), 2) == 54.50
        assert round(float(t["desconto"]), 2) == 2.40
        assert round(float(t["margem"]), 2) == 24.39
        assert round(float(t["margem_pct"]), 2) == 44.75
        assert round(float(t["produtos"]), 2) == 54.50
        assert round(float(t["servicos"]), 2) == 0.00

    def test_totais_situacao_F_zerado(self, api):
        url = (f"{BASE_URL}/api/relatorios/pedidos?{COMMON}"
               f"&data_ini=2000-01-01&data_fim=2100-12-31&situacao=F")
        j = api.get(url).json()
        assert j.get("success") is True
        assert j.get("pedidos") == []
        t = j["totais"]
        assert int(t["qtd_pedidos"]) == 0
        assert float(t["venda"]) == 0.0
        assert float(t["desconto"]) == 0.0

    def test_totais_situacao_A_volta(self, api):
        url = (f"{BASE_URL}/api/relatorios/pedidos?{COMMON}"
               f"&data_ini=2000-01-01&data_fim=2100-12-31&situacao=A")
        j = api.get(url).json()
        assert int(j["totais"]["qtd_pedidos"]) == 1
        assert round(float(j["totais"]["desconto"]), 2) == 2.40
