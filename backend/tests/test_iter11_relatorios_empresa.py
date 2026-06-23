"""Tests for iteration 11 review_request:
- /api/controle/empresa  → fantasia "PISCINA BAR"
- /api/relatorios/pedidos with vendedor/situacao/period filters
- Per-pedido analysis endpoints used by expand (relatorios/descontos-margem + pedidos/{id}/descontos)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://cliente-crud.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
COMMON = {"servidor": SERVIDOR, "banco": BANCO}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- /api/controle/empresa ----------
class TestControleEmpresa:
    def test_empresa_returns_fantasia(self, api):
        r = api.get(f"{BASE_URL}/api/controle/empresa", params=COMMON, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        assert j.get("fantasia") == "PISCINA BAR", f"fantasia inesperada: {j.get('fantasia')}"


# ---------- /api/relatorios/pedidos ----------
class TestRelatorioPedidos:
    PERIODO = {"data_ini": "2000-01-01", "data_fim": "2100-12-31"}

    def test_sem_filtros_retorna_pedido_1(self, api):
        r = api.get(f"{BASE_URL}/api/relatorios/pedidos", params={**COMMON, **self.PERIODO}, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        peds = j.get("pedidos") or []
        assert len(peds) >= 1
        p1 = next((p for p in peds if p.get("pedido") == 1), None)
        assert p1 is not None, "Pedido #1 não retornado"
        assert p1.get("situacao") == "A"
        assert p1.get("situacao_label") == "Aberto"
        assert "TESTE CLIENTE" in (p1.get("cliente") or "").upper()
        assert "CARLOS" in (p1.get("vendedor_nome") or "").upper()
        assert p1.get("vendedor_cod") == 1
        assert p1.get("data"), "data ausente no pedido"
        assert abs(float(p1.get("total") or 0) - 54.50) < 0.01

    def test_filtro_situacao_fechado_vazio(self, api):
        r = api.get(f"{BASE_URL}/api/relatorios/pedidos",
                    params={**COMMON, **self.PERIODO, "situacao": "F"}, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        assert j.get("pedidos") == []

    def test_filtro_situacao_aberto_retorna_pedido(self, api):
        r = api.get(f"{BASE_URL}/api/relatorios/pedidos",
                    params={**COMMON, **self.PERIODO, "situacao": "A"}, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        peds = j.get("pedidos") or []
        assert any(p.get("pedido") == 1 for p in peds)

    def test_filtro_vendedor_carlos(self, api):
        r = api.get(f"{BASE_URL}/api/relatorios/pedidos",
                    params={**COMMON, **self.PERIODO, "vendedor": 1}, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        peds = j.get("pedidos") or []
        assert any(p.get("pedido") == 1 for p in peds)

    def test_filtro_vendedor_inexistente_vazio(self, api):
        r = api.get(f"{BASE_URL}/api/relatorios/pedidos",
                    params={**COMMON, **self.PERIODO, "vendedor": 99999}, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        assert j.get("pedidos") == []

    def test_periodo_no_passado_vazio(self, api):
        r = api.get(f"{BASE_URL}/api/relatorios/pedidos",
                    params={**COMMON, "data_ini": "1990-01-01", "data_fim": "1990-12-31"}, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        assert j.get("pedidos") == []


# ---------- Endpoints usados ao expandir uma linha ----------
class TestExpansaoPedido:
    def test_margem_pedido_1(self, api):
        r = api.get(
            f"{BASE_URL}/api/relatorios/descontos-margem",
            params={**COMMON, "data_ini": "2000-01-01", "data_fim": "2100-12-31", "pedido": 1},
            timeout=60,
        )
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        tot = j.get("totais") or {}
        # Esperado: Venda 54.50, Desconto 2.40, Custo 30.11, Margem 24.39, 44.75%
        assert abs(float(tot.get("venda") or 0) - 54.50) < 0.05
        assert abs(float(tot.get("desconto") or 0) - 2.40) < 0.05
        assert abs(float(tot.get("custo") or 0) - 30.11) < 0.05
        assert abs(float(tot.get("margem") or 0) - 24.39) < 0.05
        assert abs(float(tot.get("margem_pct") or 0) - 44.75) < 0.10

    def test_descontos_pedido_1(self, api):
        r = api.get(f"{BASE_URL}/api/pedidos/1/descontos", params=COMMON, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        items = j.get("items") or []
        assert len(items) >= 1, "Nenhum desconto retornado para pedido #1"
        heineken = next(
            (i for i in items if "HEINEKEN" in (i.get("descricao") or "").upper()),
            None,
        )
        assert heineken is not None, f"Heineken Long Neck não encontrado nos descontos: {items}"
        assert abs(float(heineken.get("percentual") or 0) - 10.0) < 0.5
        assert abs(float(heineken.get("valor_total") or 0) - 2.40) < 0.05
