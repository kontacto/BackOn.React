"""Iter30 — Backend re-validation:
1) GET /api/os/7/analise → itens + totais (venda/desconto/custo/margem/margem_pct)
   custo_os: produto=custo_reposicao, serviço=valor_hora.
2) GET /api/os/7/descontos → itens com desconto > 0 (em OS #7, deve vir vazio).
3) Criar OS nova, adicionar item produto P001 com desconto unit. = 2.00, qtd=2
   e confirmar GET /api/os/{cod}/descontos retorna 1 item com valor_total = 4.00.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
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
    for _ in range(5):
        try:
            r = api.post(f"{BASE_URL}/api/os", json={**conn, "page": 1, "size": 1}, timeout=TIMEOUT)
            if r.status_code == 200 and r.json().get("success"):
                return
        except Exception:
            pass
    pytest.skip("Azure SQL indisponível.")


# ----------------------------------------------------------------------
# OS #7 — análise e descontos
# ----------------------------------------------------------------------
class TestOSAnaliseEDescontos7:
    def test_analise_os7_retorna_totais_e_itens(self, api, conn):
        r = api.get(f"{BASE_URL}/api/os/7/analise", params=conn, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        # totais
        t = j.get("totais") or {}
        for k in ("venda", "desconto", "custo", "margem", "margem_pct", "qtd_itens"):
            assert k in t, f"falta '{k}' em totais"
        # com itens P001+S01 na OS #7
        assert t["venda"] > 0, t
        assert t["custo"] > 0, t
        assert t["qtd_itens"] >= 2, t
        # margem = venda - custo
        assert abs(t["margem"] - round(t["venda"] - t["custo"], 2)) < 0.02, t
        # itens com campos esperados
        itens = j.get("itens") or []
        assert len(itens) >= 2
        for it in itens:
            for k in ("cod", "descricao", "qtd", "venda", "desconto", "custo", "margem", "margem_pct"):
                assert k in it, f"falta '{k}' em item {it}"

    def test_descontos_os7_estrutura(self, api, conn):
        r = api.get(f"{BASE_URL}/api/os/7/descontos", params=conn, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        assert "items" in j and "total" in j
        # Em OS #7 normalmente não há desconto (iter29 não criou desconto)
        # mas se algum teste anterior tiver criado, valida estrutura mesmo assim.
        for d in (j.get("items") or []):
            for k in ("cod", "descricao", "percentual", "valor_unitario", "qtd", "valor_total"):
                assert k in d, f"falta '{k}' em desconto {d}"


# ----------------------------------------------------------------------
# OS nova com desconto → verifica /descontos
# ----------------------------------------------------------------------
class TestOSCriarComDesconto:
    @pytest.fixture(scope="class")
    def os_id(self, api, conn):
        body = {
            **conn, "cliente": 1, "area_atuacao": None,
            "descricao_cliente": "TEST_iter30 desc",
            "obs": "TEST_iter30",
            "resumo": "TEST_iter30",
            "status_os": 3, "atendente": 3, "situacao": "A",
            "placa": "TST-3030", "marca": "VW", "modelo": "GOL",
            "km": 0, "ano": "2024", "chassi": "", "numero_de_serie": "",
        }
        r = api.post(f"{BASE_URL}/api/os/create", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j
        cod = j["codigo"]
        yield cod
        # cleanup itens
        try:
            ri = api.get(f"{BASE_URL}/api/os/{cod}/itens", params=conn, timeout=TIMEOUT).json()
            for it in ri.get("items") or []:
                api.delete(
                    f"{BASE_URL}/api/os/{cod}/itens/{it['cod_os_prod']}",
                    params=conn, timeout=TIMEOUT,
                )
        except Exception:
            pass

    def test_add_item_com_desconto(self, api, conn, os_id):
        body = {
            **conn, "produto": "P001", "qtd": 2,
            "valor_unitario": 8.5, "desconto": 2.0,
            "acrescimo": 0, "complemento": "",
            "vendedor": 3, "executor": 3,
        }
        r = api.post(f"{BASE_URL}/api/os/{os_id}/itens", json=body, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j

    def test_descontos_lista_item_e_total(self, api, conn, os_id):
        r = api.get(f"{BASE_URL}/api/os/{os_id}/descontos", params=conn, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j
        items = j.get("items") or []
        assert len(items) == 1, f"esperava 1 item com desconto, veio {items}"
        d = items[0]
        # qtd=2 × desconto unit=2 = 4
        assert abs(d["valor_unitario"] - 2.0) < 0.01, d
        assert abs(d["qtd"] - 2) < 0.01, d
        assert abs(d["valor_total"] - 4.0) < 0.01, d
        assert abs(j["total"] - 4.0) < 0.01, j
        # percentual = 2 / 8.5 * 100 ≈ 23.53
        assert d["percentual"] > 0, d

    def test_analise_reflete_desconto(self, api, conn, os_id):
        r = api.get(f"{BASE_URL}/api/os/{os_id}/analise", params=conn, timeout=TIMEOUT)
        j = r.json()
        assert j.get("success") is True, j
        t = j["totais"]
        # desconto total = qtd*desconto_unit = 4
        assert abs(t["desconto"] - 4.0) < 0.05, t
        # venda = qtd * p_venda = 2 * (8.5 - 2 + 0) = 13
        assert abs(t["venda"] - 13.0) < 0.05, t
        # custo = qtd * custo_reposicao (P001) ; deve ser > 0
        assert t["custo"] > 0, t
