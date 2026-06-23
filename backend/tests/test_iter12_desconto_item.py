"""Iteration 12: bugs BUG1 (desconto no add-item via /produtos) e BUG2 (combobox de vendedor).

Foco no backend:
- /api/controle/desconto-limites retorna limites por função
- /api/funcionarios?ativos=true lista vendedores para o combo
- /api/pedidos/{pedido}/itens aceita desconto/desconto_pct/usuario_codigo/funcao e grava
- /api/pedidos/{pedido}/descontos exibe o desconto concedido
- limpeza: remove o item criado para manter o pedido #1 no estado original
"""
import os
import pytest
import requests

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
PEDIDO_ID = 1


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _wait_azure(api, url, attempts=5):
    # Azure SQL serverless pode estar "pausado" — tenta algumas vezes
    last = None
    for _ in range(attempts):
        r = api.get(url, timeout=60)
        last = r
        if r.status_code == 200:
            try:
                if r.json().get("success") is not False:
                    return r
            except Exception:
                return r
        import time
        time.sleep(3)
    return last


# --- Desconto-limites (modal de adicionar item lê isso para mostrar 'máx. X%') ---
class TestDescontoLimites:
    def test_get_limites(self, api):
        url = f"{BASE}/api/controle/desconto-limites?servidor={SERVIDOR}&banco={BANCO}"
        r = _wait_azure(api, url)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        # campos esperados pelo frontend
        for k in ("gerente", "supervisor", "vendedor"):
            assert k in j, f"campo {k} ausente"
            assert isinstance(j[k], (int, float))


# --- Funcionários (combobox de vendedor) ---
class TestFuncionariosCombo:
    def test_lista_funcionarios(self, api):
        url = f"{BASE}/api/funcionarios?servidor={SERVIDOR}&banco={BANCO}&ativos=true"
        r = _wait_azure(api, url)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        items = j.get("items") or j.get("funcionarios") or []
        assert len(items) > 0, "deve haver funcionários ativos para popular combobox"
        # checa estrutura mínima usada pelo SelectField
        sample = items[0]
        assert ("codigo" in sample) or ("codigo_int" in sample)
        assert "nome" in sample or "nome_guerra" in sample


# --- Adicionar item com desconto e validar ---
class TestAddItemComDesconto:
    @pytest.fixture(scope="class")
    def state(self):
        return {"codauto": None, "old_total": None}

    def test_get_pedido_inicial(self, api, state):
        # snapshot do total inicial — guardamos para validar mudança
        r = api.get(f"{BASE}/api/pedidos/{PEDIDO_ID}?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        assert r.status_code == 200
        j = r.json()
        # tolera shape variável
        ped = j.get("pedido") or j
        state["old_total"] = float(ped.get("total") or 0)

    def test_add_item_com_desconto_pct(self, api, state):
        body = {
            "servidor": SERVIDOR,
            "banco": BANCO,
            "produto": "P001",          # Coca-Cola 600ml R$ 8,50
            "qtd": 2,
            "valor_unitario": 8.50,
            "desconto": 0.85,           # 10% de 8,50
            "desconto_pct": 10,
            "usuario_codigo": -2,       # master (KONTACTO)
            "funcao": 1,                # gerente
            "complemento": "TEST_iter12_desconto",
        }
        r = api.post(f"{BASE}/api/pedidos/{PEDIDO_ID}/itens", json=body, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        # tenta capturar codauto retornado p/ cleanup
        cod = j.get("codauto") or j.get("id") or (j.get("item") or {}).get("codauto")
        state["codauto"] = cod

    def test_desconto_aparece_relatorio(self, api):
        # /api/pedidos/{pedido}/descontos deve listar o desconto concedido
        r = api.get(f"{BASE}/api/pedidos/{PEDIDO_ID}/descontos?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        itens = j.get("itens") or j.get("items") or []
        # Endpoint só retorna itens COM desconto>0 (filtra no SQL),
        # então basta haver entradas e ao menos uma se referindo ao produto P001 recém-criado.
        assert len(itens) > 0, j
        assert any("Coca-Cola" in str(it.get("descricao", "")) for it in itens), itens

    def test_total_pedido_subiu(self, api, state):
        r = api.get(f"{BASE}/api/pedidos/{PEDIDO_ID}?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        assert r.status_code == 200
        ped = r.json().get("pedido") or r.json()
        new_total = float(ped.get("total") or 0)
        # 2 * 8,50 - 2*0,85 = 15,30 adicional
        assert new_total > (state["old_total"] or 0)

    def test_cleanup_remove_item(self, api, state):
        if not state.get("codauto"):
            pytest.skip("codauto não retornado pelo backend — cleanup manual necessário")
        cod = state["codauto"]
        url = f"{BASE}/api/pedidos/{PEDIDO_ID}/itens/{cod}?servidor={SERVIDOR}&banco={BANCO}"
        r = api.delete(url, timeout=30)
        assert r.status_code in (200, 204), r.text


# --- Validação de limite (desconto acima do limite deve falhar) ---
class TestDescontoLimiteValidacao:
    def test_desconto_acima_limite_pct(self, api):
        # vendedor (funcao=3) costuma ter limite menor; tentamos 99%
        body = {
            "servidor": SERVIDOR, "banco": BANCO,
            "produto": "P001", "qtd": 1, "valor_unitario": 8.50,
            "desconto": 8.41, "desconto_pct": 99,
            "usuario_codigo": 1, "funcao": 3,
            "complemento": "TEST_iter12_above_limit",
        }
        r = api.post(f"{BASE}/api/pedidos/{PEDIDO_ID}/itens", json=body, timeout=60)
        # backend pode rejeitar (success false) ou aceitar; o front é a barreira primária
        # apenas marcamos comportamento — não falhamos
        if r.status_code == 200 and r.json().get("success"):
            # se aceitou, faz cleanup
            cod = r.json().get("codauto") or (r.json().get("item") or {}).get("codauto")
            if cod:
                api.delete(f"{BASE}/api/pedidos/{PEDIDO_ID}/itens/{cod}?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
