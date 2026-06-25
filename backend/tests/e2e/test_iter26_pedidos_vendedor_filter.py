"""Iter26 — Backend: filtro 'vendedor' no POST /api/pedidos (movido da Principal).

Valida:
  - vendedor='all' → retorna pedidos de todos os vendedores
  - vendedor=<numérico> existente → filtra apenas daquele vendedor
  - vendedor='-1' (não existe) → total=0
  - vendedor omitido → comporta-se como 'all'

Conexão (Azure SQL serverless, pode demorar ao acordar - erro 40613).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"


def _post_pedidos(payload: dict, retries: int = 3) -> dict:
    """POST /api/pedidos com retry para acordar Azure serverless (40613)."""
    last = None
    for i in range(retries):
        r = requests.post(f"{BASE_URL}/api/pedidos", json=payload, timeout=60)
        last = r
        try:
            j = r.json()
        except Exception:
            j = {"success": False, "message": r.text}
        if j.get("success") or "40613" not in str(j.get("message", "")):
            return j
        time.sleep(5 * (i + 1))
    return last.json() if last else {"success": False}


@pytest.fixture(scope="module")
def base_payload():
    return {
        "servidor": SERVIDOR,
        "banco": BANCO,
        "search": "",
        "situacao": "",
        "page": 1,
        "size": 20,
    }


# ---------- POST /api/pedidos vendedor filter ----------
class TestPedidosVendedorFilter:
    def test_vendedor_all_retorna_todos(self, base_payload):
        j = _post_pedidos({**base_payload, "vendedor": "all"})
        assert j.get("success") is True, f"resp={j}"
        assert isinstance(j.get("items"), list)
        assert isinstance(j.get("total"), int)
        # Esperado: pelo menos 1 pedido seedado (#1) existe no BDREACTAPP
        assert j["total"] >= 1, f"esperava >=1 pedido com vendedor=all, total={j['total']}"

    def test_vendedor_omitido_equivale_a_all(self, base_payload):
        # Schema PedidosListRequest: vendedor None => não aplica filtro
        j_all = _post_pedidos({**base_payload, "vendedor": "all"})
        j_none = _post_pedidos({**base_payload})  # sem 'vendedor'
        assert j_all.get("success") and j_none.get("success")
        assert j_all["total"] == j_none["total"], (
            f"all={j_all['total']} vs omit={j_none['total']}"
        )

    def test_vendedor_inexistente_retorna_zero(self, base_payload):
        j = _post_pedidos({**base_payload, "vendedor": "-1"})
        assert j.get("success") is True, f"resp={j}"
        assert j.get("total") == 0
        assert j.get("items") == []

    def test_vendedor_numerico_filtra(self, base_payload):
        # Pega total geral
        j_all = _post_pedidos({**base_payload, "vendedor": "all"})
        assert j_all.get("success") is True
        if not j_all["items"]:
            pytest.skip("Sem pedidos para testar filtro numérico")
        # Pega um vendedor existente em algum pedido
        vendedor_id = None
        for it in j_all["items"]:
            if it.get("vendedor"):
                vendedor_id = it["vendedor"]
                break
        if vendedor_id is None:
            pytest.skip("Nenhum pedido com vendedor preenchido nos primeiros 20")
        j_v = _post_pedidos({**base_payload, "vendedor": str(vendedor_id)})
        assert j_v.get("success") is True
        # total filtrado <= total geral
        assert j_v["total"] <= j_all["total"]
        # todos os items devem ter exatamente esse vendedor
        for it in j_v["items"]:
            assert it.get("vendedor") == vendedor_id, f"item com vendedor diferente: {it}"


# ---------- GET /api/funcionarios (usado pelo Pedidos para popular select) ----------
class TestFuncionariosListaParaFiltro:
    def test_get_funcionarios_retorna_lista(self):
        params = {"servidor": SERVIDOR, "banco": BANCO}
        r = requests.get(f"{BASE_URL}/api/funcionarios", params=params, timeout=60)
        j = r.json()
        assert j.get("success") is True, f"resp={j}"
        assert isinstance(j.get("items"), list)
        assert len(j["items"]) >= 1
        # Schema esperado por pedidos.tsx
        f0 = j["items"][0]
        assert "codigo" in f0
        assert "nome" in f0
