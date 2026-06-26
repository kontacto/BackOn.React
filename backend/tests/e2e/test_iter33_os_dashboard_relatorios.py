# Iter 33: testa Painel (movimento OS+PED), endpoints /api/dashboard/me e os relatórios de OS.
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    # Read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")

SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"


@pytest.fixture
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ----- /api/dashboard/me -----
class TestDashboardMe:
    def test_dashboard_me_data_2026_06_25(self, s):
        r = s.get(f"{BASE_URL}/api/dashboard/me", params={
            "servidor": SERVIDOR, "banco": BANCO, "vendedor": "all", "data": "2026-06-25"
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        tot = j.get("totais") or {}
        # Chaves obrigatórias
        for k in ["pedidos", "os", "produtos", "servicos", "descontos", "margem", "margem_pct"]:
            assert k in tot, f"Faltou chave {k} em totais"
        assert tot["pedidos"] == 2
        assert tot["os"] == 3
        mov = j.get("movimento") or []
        assert isinstance(mov, list) and len(mov) >= 5
        tipos = {m.get("tipo") for m in mov}
        assert "PED" in tipos and "OS" in tipos
        # cada item tem doc, cliente, valor
        for m in mov:
            for k in ["tipo", "doc", "cliente", "valor"]:
                assert k in m

    def test_dashboard_me_today_no_error(self, s):
        # Hoje (sem param de data) — pode estar vazio, mas success=true
        r = s.get(f"{BASE_URL}/api/dashboard/me", params={
            "servidor": SERVIDOR, "banco": BANCO, "vendedor": "all"
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        assert "totais" in j and "movimento" in j


# ----- /api/relatorios/os -----
class TestRelatorioOS:
    def test_relatorio_os_periodo(self, s):
        r = s.get(f"{BASE_URL}/api/relatorios/os", params={
            "servidor": SERVIDOR, "banco": BANCO,
            "data_ini": "2026-06-01", "data_fim": "2026-06-30"
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        assert "os" in j and isinstance(j["os"], list)
        assert "totais" in j
        tot = j["totais"]
        for k in ["qtd_pedidos", "venda", "desconto", "custo", "margem", "margem_pct"]:
            assert k in tot
        # No período há 8 OS retornadas (algumas zero) e qtd_pedidos consolida apenas as com itens
        assert len(j["os"]) >= 3
        assert tot["venda"] == 342.5

    def test_relatorio_os_filtro_vendedor_reduz_total(self, s):
        r = s.get(f"{BASE_URL}/api/relatorios/os", params={
            "servidor": SERVIDOR, "banco": BANCO,
            "data_ini": "2026-06-01", "data_fim": "2026-06-30",
            "vendedor": 3,
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        tot = j["totais"]
        # Filtrar vendedor=3 reduz a venda total para 192.5
        assert tot["venda"] == 192.5


# ----- /api/relatorios/os/descontos-margem -----
class TestRelatorioOSDescontos:
    def test_descontos_margem_agrupado(self, s):
        r = s.get(f"{BASE_URL}/api/relatorios/os/descontos-margem", params={
            "servidor": SERVIDOR, "banco": BANCO,
            "data_ini": "2026-06-01", "data_fim": "2026-06-30",
        }, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        vends = j.get("vendedores") or []
        assert len(vends) >= 1
        # Cada grupo tem campos esperados
        g0 = vends[0]
        for k in ["vendedor", "vendedor_nome", "pedidos",
                  "sub_venda", "sub_desconto", "sub_custo", "sub_margem", "sub_margem_pct"]:
            assert k in g0
        tot = j.get("totais") or {}
        for k in ["venda", "desconto", "custo", "margem", "margem_pct", "qtd_pedidos"]:
            assert k in tot
