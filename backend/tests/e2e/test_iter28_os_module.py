"""Iter28 — Validação BACKEND do módulo Ordem de Serviço (OS).

Endpoints sob teste (todos via EXPO_BACKEND_URL pública):
  POST   /api/os              -> lista com filtros (search/situacao/data_ini/data_fim)
  POST   /api/os/create       -> cria nova OS (codigo MAX+1, situacao 'A')
  GET    /api/os/{codigo}     -> leitura cabeçalho
  PUT    /api/os/{codigo}     -> update cabeçalho (somente situacao='A')
  GET    /api/os/{c}/itens
  POST   /api/os/{c}/itens    -> add item (vendedor/executor POR ITEM)
  PUT    /api/os/{c}/itens/{cod_os_prod}
  DELETE /api/os/{c}/itens/{cod_os_prod}
Valida-se também o recálculo de os.valor = SUM(quant*p_venda) dos itens não cancelados.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
TIMEOUT = 60  # Azure SQL serverless pode demorar a "acordar"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def conn_payload():
    return {"servidor": SERVIDOR, "banco": BANCO}


# ---------- Helpers ----------
def _wake_db(api, conn_payload):
    """Acorda o Azure SQL serverless: faz 1 chamada e ignora 1 erro 40613."""
    for _ in range(3):
        r = api.post(f"{BASE_URL}/api/os", json={**conn_payload, "page": 1, "size": 1}, timeout=TIMEOUT)
        if r.status_code == 200 and r.json().get("success"):
            return
    pytest.skip("Azure SQL indisponível para os testes.")


@pytest.fixture(scope="session", autouse=True)
def warmup(api, conn_payload):
    _wake_db(api, conn_payload)


# ---------- listagem ----------
class TestOSList:
    def test_list_os_basic(self, api, conn_payload):
        r = api.post(f"{BASE_URL}/api/os", json={**conn_payload, "page": 1, "size": 20}, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["success"] is True, j
        assert isinstance(j["items"], list)
        assert "total" in j
        assert j["total"] >= 1  # OS #1 já existe

    def test_list_filtra_aberta(self, api, conn_payload):
        r = api.post(f"{BASE_URL}/api/os", json={**conn_payload, "situacao": "A", "page": 1, "size": 50}, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        assert all(it["situacao"] == "A" for it in j["items"]), [it["situacao"] for it in j["items"]]

    def test_list_search_por_codigo(self, api, conn_payload):
        r = api.post(f"{BASE_URL}/api/os", json={**conn_payload, "search": "1", "page": 1, "size": 20}, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        # ao menos um item deve conter '1' no codigo/cgc/nome
        assert any("1" in str(it["codigo"]) or "1" in (it["cliente_nome"] or "") for it in j["items"])

    def test_list_search_cliente(self, api, conn_payload):
        r = api.post(f"{BASE_URL}/api/os", json={**conn_payload, "search": "TESTE", "page": 1, "size": 20}, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        assert all("TESTE" in (it["cliente_nome"] or "").upper() or "TESTE" in str(it["codigo"]) for it in j["items"])

    def test_list_situacao_inexistente(self, api, conn_payload):
        # 'Z' não é uma situação válida -> resultado vazio mas success=True
        r = api.post(f"{BASE_URL}/api/os", json={**conn_payload, "situacao": "Z"}, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        assert j["items"] == []


# ---------- get ----------
class TestOSGet:
    def test_get_existente(self, api, conn_payload):
        r = api.get(f"{BASE_URL}/api/os/1", params=conn_payload, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["success"] is True
        assert j["os"]["codigo"] == 1
        # contém campos esperados
        for k in ("cliente", "cliente_nome", "data", "situacao", "situacao_label", "total"):
            assert k in j["os"], k

    def test_get_inexistente(self, api, conn_payload):
        r = api.get(f"{BASE_URL}/api/os/999999", params=conn_payload, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is False
        assert "não encontrada" in j.get("message", "").lower()


# ---------- ciclo completo: cria OS, add itens, atualiza, deleta ----------
class TestOSLifecycle:
    @pytest.fixture(scope="class")
    def created(self, api, conn_payload):
        # cria OS — cliente 1 já existe (TESTE CLIENTE 9DIG)
        body = {**conn_payload, "cliente": 1, "area_atuacao": None,
                "descricao_cliente": "TEST_iter28 relato cliente",
                "obs": "TEST_iter28 obs"}
        r = api.post(f"{BASE_URL}/api/os/create", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j
        assert isinstance(j["codigo"], int) and j["codigo"] > 0
        yield j["codigo"]
        # cleanup: cancela OS marcando situacao -> não temos endpoint p/ cancel ainda;
        # deleta itens existentes para zerar total (cleanup best-effort)
        try:
            r2 = api.get(f"{BASE_URL}/api/os/{j['codigo']}/itens", params=conn_payload, timeout=TIMEOUT)
            for it in (r2.json() or {}).get("items", []):
                api.delete(f"{BASE_URL}/api/os/{j['codigo']}/itens/{it['cod_os_prod']}", params=conn_payload, timeout=TIMEOUT)
        except Exception:
            pass

    def test_01_create_persistido_via_get(self, api, conn_payload, created):
        r = api.get(f"{BASE_URL}/api/os/{created}", params=conn_payload, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        assert j["os"]["situacao"] == "A"
        assert j["os"]["cliente"] == 1
        assert "TEST_iter28" in (j["os"].get("descricao_cliente") or "")
        assert float(j["os"]["total"]) == 0.0

    def test_02_update_header(self, api, conn_payload, created):
        body = {**conn_payload, "cliente": 1, "area_atuacao": None,
                "descricao_cliente": "TEST_iter28 ATUALIZADO", "obs": "obs2"}
        r = api.put(f"{BASE_URL}/api/os/{created}", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        # verifica via GET
        g = api.get(f"{BASE_URL}/api/os/{created}", params=conn_payload, timeout=TIMEOUT).json()
        assert "ATUALIZADO" in g["os"]["descricao_cliente"]

    def test_03_add_item_produto_P001(self, api, conn_payload, created):
        body = {**conn_payload, "produto": "P001", "qtd": 2, "valor_unitario": 8.50,
                "desconto": 0, "acrescimo": 0, "complemento": "TEST_iter28 P001",
                "vendedor": 3, "executor": 3}
        r = api.post(f"{BASE_URL}/api/os/{created}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        assert j["cod_os_prod"] > 0
        # total = 2 * 8.50 = 17.00
        assert abs(float(j["total"]) - 17.0) < 0.01, j["total"]

    def test_04_add_item_servico_S01(self, api, conn_payload, created):
        body = {**conn_payload, "produto": "S01", "qtd": 1, "valor_unitario": 150.0,
                "desconto": 0, "acrescimo": 0, "complemento": "TEST_iter28 S01",
                "vendedor": 3, "executor": 3}
        r = api.post(f"{BASE_URL}/api/os/{created}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        # total acumulado = 17 + 150 = 167
        assert abs(float(j["total"]) - 167.0) < 0.01, j["total"]

    def test_05_list_itens_e_subtotal(self, api, conn_payload, created):
        r = api.get(f"{BASE_URL}/api/os/{created}/itens", params=conn_payload, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        assert j["editavel"] is True
        assert len(j["items"]) >= 2
        assert abs(float(j["subtotal"]) - 167.0) < 0.01
        # cada item tem vendedor/executor
        for it in j["items"]:
            assert it["vendedor"] == 3
            assert it["executor"] == 3
            assert it["tipo"] in ("P", "S")

    def test_06_update_item_recalcula_total(self, api, conn_payload, created):
        # pega 1o item (P001) e altera qtd para 3
        ritens = api.get(f"{BASE_URL}/api/os/{created}/itens", params=conn_payload, timeout=TIMEOUT).json()
        item_p = next(it for it in ritens["items"] if it["produto"].strip() == "P001")
        body = {**conn_payload, "produto": "P001", "qtd": 3, "valor_unitario": 8.50,
                "desconto": 0, "acrescimo": 0, "complemento": "TEST_iter28 P001 v2",
                "vendedor": 3, "executor": 3}
        r = api.put(f"{BASE_URL}/api/os/{created}/itens/{item_p['cod_os_prod']}", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        # novo total = 3*8.50 + 150 = 25.50 + 150 = 175.50
        assert abs(float(j["total"]) - 175.50) < 0.01, j["total"]

    def test_07_delete_item(self, api, conn_payload, created):
        ritens = api.get(f"{BASE_URL}/api/os/{created}/itens", params=conn_payload, timeout=TIMEOUT).json()
        item_s = next(it for it in ritens["items"] if it["produto"].strip() == "S01")
        r = api.delete(f"{BASE_URL}/api/os/{created}/itens/{item_s['cod_os_prod']}", params=conn_payload, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True
        # restaram apenas 3*8.50 = 25.50
        assert abs(float(j["total"]) - 25.50) < 0.01, j["total"]
        # confirma via GET
        ritens2 = api.get(f"{BASE_URL}/api/os/{created}/itens", params=conn_payload, timeout=TIMEOUT).json()
        assert all(it["produto"].strip() != "S01" for it in ritens2["items"])

    def test_08_add_item_qtd_zero_falha(self, api, conn_payload, created):
        body = {**conn_payload, "produto": "P001", "qtd": 0, "valor_unitario": 8.50,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "vendedor": 3, "executor": 3}
        r = api.post(f"{BASE_URL}/api/os/{created}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is False
        assert "quantidade" in (j.get("message") or "").lower()

    def test_09_add_item_produto_inexistente_falha(self, api, conn_payload, created):
        body = {**conn_payload, "produto": "ZZZNOPE", "qtd": 1, "valor_unitario": 1.0,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "vendedor": 3, "executor": 3}
        r = api.post(f"{BASE_URL}/api/os/{created}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is False
        assert "não encontrado" in (j.get("message") or "").lower()

    def test_10_update_item_inexistente_falha(self, api, conn_payload, created):
        body = {**conn_payload, "produto": "P001", "qtd": 1, "valor_unitario": 8.5,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "vendedor": 3, "executor": 3}
        r = api.put(f"{BASE_URL}/api/os/{created}/itens/9999999", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is False


class TestOSValidations:
    def test_get_itens_os_inexistente(self, api, conn_payload):
        r = api.get(f"{BASE_URL}/api/os/999999/itens", params=conn_payload, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is False

    def test_update_os_inexistente_404_like(self, api, conn_payload):
        body = {**conn_payload, "cliente": 1, "area_atuacao": None,
                "descricao_cliente": "x", "obs": ""}
        r = api.put(f"{BASE_URL}/api/os/999999", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is False
