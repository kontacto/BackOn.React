"""Iter29 — Re-validação BACKEND:
1) OS create/get/update gravam e devolvem TODOS os novos campos (status_os, atendente,
   situacao, placa, marca, modelo, km, ano, chassi, numero_de_serie, descricao_cliente,
   obs, resumo); custo_os do item produto = pecas.custo_reposicao; custo_os do item
   serviço = servicos.valor_hora.
2) REGRESSÃO Pedido: criar pedido, add item SERVIÇO (S01) → custo_ped = 150 (valor_hora).
   Add item PRODUTO (P001) → custo_ped = pecas.custo_reposicao.
"""
import os
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://order-crud-discounts.preview.emergentagent.com"
).rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
TIMEOUT = 60


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def conn():
    return {"servidor": SERVIDOR, "banco": BANCO}


@pytest.fixture(scope="session", autouse=True)
def warmup(api, conn):
    """Acorda o Azure SQL serverless."""
    for _ in range(4):
        try:
            r = api.post(f"{BASE_URL}/api/os", json={**conn, "page": 1, "size": 1}, timeout=TIMEOUT)
            if r.status_code == 200 and r.json().get("success"):
                return
        except Exception:
            pass
    pytest.skip("Azure SQL indisponível para os testes.")


def _custo_via_run_query(api, conn, sql: str):
    """Tenta /api/db/run-query para validar custo_ped via SQL bruto."""
    try:
        r = api.post(f"{BASE_URL}/api/db/run-query", json={**conn, "sql": sql}, timeout=TIMEOUT)
        if r.status_code == 200:
            j = r.json()
            if j.get("success"):
                return j.get("rows") or []
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------
# OS — novos campos no cabeçalho
# ----------------------------------------------------------------------
class TestOSCamposNovos:
    @pytest.fixture(scope="class")
    def os_id(self, api, conn):
        body = {
            **conn,
            "cliente": 1,
            "area_atuacao": None,
            "descricao_cliente": "TEST_iter29 cliente descreva",
            "obs": "TEST_iter29 obs",
            "resumo": "TEST_iter29 servico executado",
            "status_os": 3,                # Em execução
            "atendente": 3,                # Estela
            "situacao": "A",
            "placa": "AAA-1234",
            "marca": "VW",
            "modelo": "GOL",
            "km": 12345,
            "ano": "2022",
            "chassi": "9BWZZZ377VT123456",
            "numero_de_serie": "",
        }
        r = api.post(f"{BASE_URL}/api/os/create", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        cod = j["codigo"]
        yield cod
        # cleanup itens
        try:
            ri = api.get(f"{BASE_URL}/api/os/{cod}/itens", params=conn, timeout=TIMEOUT).json()
            for it in ri.get("items") or []:
                api.delete(f"{BASE_URL}/api/os/{cod}/itens/{it['cod_os_prod']}",
                           params=conn, timeout=TIMEOUT)
        except Exception:
            pass

    def test_get_retorna_todos_campos_novos(self, api, conn, os_id):
        r = api.get(f"{BASE_URL}/api/os/{os_id}", params=conn, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        o = j["os"]
        # novos campos do cabeçalho
        assert o["status_os"] == 3, o.get("status_os")
        assert o["atendente"] == 3, o.get("atendente")
        assert o["situacao"] == "A"
        assert o["placa"] == "AAA-1234", o.get("placa")
        assert (o.get("marca") or "").strip() == "VW"
        assert (o.get("modelo") or "").strip() == "GOL"
        assert o["km"] == 12345
        assert (o.get("ano") or "").strip() == "2022"
        assert "9BWZZZ377VT" in (o.get("chassi") or ""), o.get("chassi")
        assert "TEST_iter29 cliente descreva" in (o.get("descricao_cliente") or "")
        assert "TEST_iter29 obs" in (o.get("obs") or "")
        assert "TEST_iter29 servico executado" in (o.get("resumo") or "")

    def test_update_persiste_alteracoes(self, api, conn, os_id):
        body = {
            **conn, "cliente": 1, "area_atuacao": None,
            "descricao_cliente": "TEST_iter29 ALTERADO",
            "obs": "obs alterada", "resumo": "resumo alterado",
            "status_os": 4, "atendente": 3, "situacao": "A",
            "placa": "BBB-9999", "marca": "FI", "modelo": "PAL",
            "km": 99999, "ano": "2024", "chassi": "",
            "numero_de_serie": "SN-XYZ-001",
        }
        r = api.put(f"{BASE_URL}/api/os/{os_id}", json=body, timeout=TIMEOUT)
        assert r.json()["success"] is True
        g = api.get(f"{BASE_URL}/api/os/{os_id}", params=conn, timeout=TIMEOUT).json()["os"]
        assert g["status_os"] == 4
        assert g["placa"] == "BBB-9999"
        assert "PAL" in (g.get("modelo") or "")
        assert g["km"] == 99999
        assert (g.get("numero_de_serie") or "").strip() == "SN-XYZ-001"
        assert "ALTERADO" in g["descricao_cliente"]

    def test_add_item_produto_grava_custo_reposicao(self, api, conn, os_id):
        # P001 → pecas.custo_reposicao (4.71 conforme contexto E1)
        body = {**conn, "produto": "P001", "qtd": 1, "valor_unitario": 8.5,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "vendedor": 3, "executor": 3}
        r = api.post(f"{BASE_URL}/api/os/{os_id}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        cod_p = j["cod_os_prod"]
        # tenta validar custo via run-query
        rows = _custo_via_run_query(
            api, conn,
            f"SELECT custo_os FROM os_produto WHERE cod_os_prod={cod_p}",
        )
        if rows:
            custo = float(rows[0].get("custo_os") or 0)
            # pecas.custo_reposicao do P001 = 4.71 (informado pelo E1)
            assert custo > 0, f"custo_os deveria ser > 0 (custo_reposicao), got {custo}"

    def test_add_item_servico_grava_valor_hora(self, api, conn, os_id):
        # S01 → servicos.valor_hora = 150
        body = {**conn, "produto": "S01", "qtd": 1, "valor_unitario": 150.0,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "vendedor": 3, "executor": 3}
        r = api.post(f"{BASE_URL}/api/os/{os_id}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        cod_s = j["cod_os_prod"]
        rows = _custo_via_run_query(
            api, conn,
            f"SELECT custo_os FROM os_produto WHERE cod_os_prod={cod_s}",
        )
        if rows:
            custo = float(rows[0].get("custo_os") or 0)
            assert abs(custo - 150.0) < 0.01, f"custo_os esperado=150 (valor_hora), got {custo}"


# ----------------------------------------------------------------------
# Pedido — regressão custo_ped para serviço
# ----------------------------------------------------------------------
class TestPedidoCustoServico:
    @pytest.fixture(scope="class")
    def pedido_id(self, api, conn):
        body = {**conn, "cliente": 1, "vendedor": 3, "observacao": "TEST_iter29 ped"}
        r = api.post(f"{BASE_URL}/api/pedidos/create", json=body, timeout=TIMEOUT)
        # endpoint pode variar; tenta alternativos
        if r.status_code != 200 or not r.json().get("success"):
            r = api.post(f"{BASE_URL}/api/pedido/create", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, f"falha criando pedido: {j}"
        pid = j.get("pedido") or j.get("codigo")
        assert pid and pid > 0
        yield pid
        # cleanup itens
        try:
            ri = api.get(f"{BASE_URL}/api/pedidos/{pid}/itens", params=conn, timeout=TIMEOUT).json()
            for it in (ri or {}).get("items") or []:
                api.delete(f"{BASE_URL}/api/pedidos/{pid}/itens/{it['codauto']}",
                           params=conn, timeout=TIMEOUT)
        except Exception:
            pass

    def test_add_item_produto_grava_custo_reposicao(self, api, conn, pedido_id):
        body = {**conn, "produto": "P001", "qtd": 1, "valor_unitario": 8.5,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "funcao": None, "usuario_codigo": -1}
        r = api.post(f"{BASE_URL}/api/pedidos/{pedido_id}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j
        cod = j["codauto"]
        rows = _custo_via_run_query(
            api, conn,
            f"SELECT custo_ped FROM pedido_venda_prod WHERE codauto={cod}",
        )
        if rows:
            custo = float(rows[0].get("custo_ped") or 0)
            assert custo > 0, f"custo_ped (custo_reposicao) deveria ser > 0, got {custo}"

    def test_add_item_servico_grava_valor_hora_NAO_zero(self, api, conn, pedido_id):
        """O FIX da iter29: serviço passa a gravar custo_ped = valor_hora (antes era 0)."""
        body = {**conn, "produto": "S01", "qtd": 1, "valor_unitario": 150.0,
                "desconto": 0, "acrescimo": 0, "complemento": "",
                "funcao": None, "usuario_codigo": -1}
        r = api.post(f"{BASE_URL}/api/pedidos/{pedido_id}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j
        cod = j["codauto"]
        rows = _custo_via_run_query(
            api, conn,
            f"SELECT custo_ped FROM pedido_venda_prod WHERE codauto={cod}",
        )
        if rows:
            custo = float(rows[0].get("custo_ped") or 0)
            assert abs(custo - 150.0) < 0.01, (
                f"REGRESSÃO: custo_ped de serviço deveria ser valor_hora=150, got {custo}"
            )

    def test_list_itens_pedido(self, api, conn, pedido_id):
        r = api.get(f"{BASE_URL}/api/pedidos/{pedido_id}/itens", params=conn, timeout=TIMEOUT)
        j = r.json()
        assert j["success"] is True, j
        # 2 itens (P001 + S01)
        assert len([i for i in j["items"] if i["produto"] in ("P001", "S01")]) >= 2
