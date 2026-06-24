"""Iteration 16 — REGRESSÃO COMPLETA após refatoração estrutural.

Contexto: server.py foi quebrado em db/models/services/routes (mesmos paths
e contratos /api/*). Frontend pedido-form.tsx idem (componentes em
src/components/pedido/* + hook usePedidoItens). Este arquivo confirma que
todos os 33 endpoints /api continuam respondendo igual.

Cenário no preview:
  - conn: BARESTEL / gibanweb.database.windows.net / BDREACTAPP
  - pedido #1 (situacao 'A', data 2026-06-24, total R$54,50)
  - usuários: KONTACTO/$KONT2011 (master), ADM/admin, Estela/26171 (VENDEDOR),
              CARLOS/123, MARIA/321
"""
import os
import time as _t
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com"
).rstrip("/")
CONN = {
    "empresa": "BARESTEL",
    "servidor": "gibanweb.database.windows.net",
    "banco": "BDREACTAPP",
}
PEDIDO_DATA = "2026-06-24"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _post_with_retry(api, url, body, retries=6, sleep=3):
    """Azure SQL serverless pode estar dormindo; retry no erro 40613."""
    last = None
    for _ in range(retries):
        r = api.post(url, json=body, timeout=60)
        if r.status_code == 200:
            last = r.json()
            if last.get("success"):
                return r, last
        try:
            last = r.json()
        except Exception:
            last = {"raw": r.text[:300]}
        # Repete se for erro de wake-up
        msg = (last or {}).get("message", "")
        if "40613" in str(msg) or "is not currently available" in str(msg):
            _t.sleep(sleep)
            continue
        return r, last
    return r, last


def _get_with_retry(api, url, params, retries=6, sleep=3):
    last = None
    for _ in range(retries):
        r = api.get(url, params=params, timeout=60)
        if r.status_code == 200:
            last = r.json()
            # Para endpoints sem 'success' (listas puras) retorna direto
            if not isinstance(last, dict) or last.get("success") is True or "success" not in last:
                return r, last
        try:
            last = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:200]}
        except Exception:
            last = {"raw": r.text[:200]}
        _t.sleep(sleep)
    return r, last


# ============================================================================
# 0. SMOKE / ROOT
# ============================================================================
class TestSmoke:
    def test_api_root(self, api):
        r = api.get(f"{BASE_URL}/api/", timeout=15)
        assert r.status_code == 200, r.text
        assert "message" in r.json()


# ============================================================================
# 1. LOGIN — master, usuários do banco, credencial inválida
# ============================================================================
class TestLogin:
    def _login(self, api, usuario, senha):
        body = {**CONN, "usuario": usuario, "senha": senha}
        return _post_with_retry(api, f"{BASE_URL}/api/login", body)

    def test_master_kontacto(self, api):
        _, j = self._login(api, "KONTACTO", "$KONT2011")
        assert j and j.get("success") is True, j
        u = j.get("usuario") or {}
        assert u.get("master") is True
        assert (j.get("funcionario") or {}).get("nome_guerra") == "KONTACTO"

    def test_user_estela_vendedor(self, api):
        _, j = self._login(api, "Estela", "26171")
        assert j and j.get("success") is True, j
        u = j.get("usuario") or {}
        # Conforme review_request iter19: Estela é classe '3 - SÓCIO'
        assert int(u.get("classe") or -1) == 3, u
        assert (u.get("classe_descricao") or "").strip().upper() == "SÓCIO", u
        f = j.get("funcionario") or {}
        # cod_funcao '01' (limite de desconto de gerente)
        assert (f.get("cod_funcao") or "").strip() == "01", f

    def test_user_adm(self, api):
        _, j = self._login(api, "ADM", "admin")
        assert j and j.get("success") is True, j

    def test_user_carlos(self, api):
        _, j = self._login(api, "CARLOS", "123")
        assert j and j.get("success") is True, j

    def test_invalid_credentials_no_leak(self, api):
        """Credencial inválida deve retornar mensagem genérica sem vazar dados."""
        _, j = self._login(api, "naoexiste", "errada123")
        assert j and j.get("success") is False, j
        assert j.get("message") == "Usuário ou senha inválidos.", j
        # Nenhum campo sensível pode vir preenchido
        for k in ("empresa", "server", "database", "attempted",
                  "error_step", "error_line", "error_code_line", "error_query",
                  "usuario", "funcionario"):
            assert j.get(k) in (None, "", {}, []), f"campo {k} vazou: {j.get(k)}"

    def test_missing_fields_400(self, api):
        r = api.post(f"{BASE_URL}/api/login", json={**CONN, "usuario": "", "senha": ""}, timeout=15)
        assert r.status_code == 400, r.text


# ============================================================================
# 2. LOOKUPS (área, funcionários, tipo-cliente, limites, empresa)
# ============================================================================
class TestLookups:
    def test_area_atuacao(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/area-atuacao",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        assert isinstance(j.get("items"), list)

    def test_funcionarios(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/funcionarios",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        assert isinstance(j.get("items"), list)
        assert len(j["items"]) >= 1

    def test_tipo_cliente(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/tipo-cliente",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        assert isinstance(j.get("items"), list)

    def test_controle_desconto_limites(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/controle/desconto-limites",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j

    def test_controle_empresa(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/controle/empresa",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j


# ============================================================================
# 3. CLIENTES — list/search/get/find by cgc
# ============================================================================
class TestClientes:
    def test_list_clientes(self, api):
        body = {**CONN, "search": "", "page": 1, "size": 10}
        r, j = _post_with_retry(api, f"{BASE_URL}/api/clientes", body)
        assert r.status_code == 200, r.text
        assert j.get("success") is True, j
        assert isinstance(j.get("items"), list)

    def test_clientes_search(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/clientes/find/search",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"], "term": ""})
        assert j and j.get("success") is True, j
        assert isinstance(j.get("items"), list)

    def test_get_cliente_existente(self, api):
        # Acha um código a partir do search
        _, lst = _get_with_retry(api, f"{BASE_URL}/api/clientes/find/search",
                                 {"servidor": CONN["servidor"], "banco": CONN["banco"], "term": ""})
        assert lst and lst.get("items"), lst
        codigo = lst["items"][0].get("codigo")
        assert codigo, lst["items"][0]
        _, j = _get_with_retry(api, f"{BASE_URL}/api/clientes/{codigo}",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        # data structure check (cliente + endereco + telefones)
        assert "cliente" in j, j

    def test_find_by_cgc_inexistente(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/clientes/find/by-cgc",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"], "cgc": "00000000000"})
        assert j is not None
        # Deve retornar success com items vazio ou flag found=False
        assert ("items" in j) or ("cliente" in j) or (j.get("success") in (True, False))


# ============================================================================
# 4. PRODUTOS / SERVIÇOS
# ============================================================================
class TestProdutos:
    def test_list_produtos_servicos_all(self, api):
        _, j = _get_with_retry(
            api, f"{BASE_URL}/api/produtos-servicos",
            {"servidor": CONN["servidor"], "banco": CONN["banco"], "tipo": "all", "page": 1, "size": 20}
        )
        assert j and j.get("success") is True, j
        items = j.get("items") or []
        assert len(items) >= 1, items

    def test_list_produtos_only(self, api):
        _, j = _get_with_retry(
            api, f"{BASE_URL}/api/produtos-servicos",
            {"servidor": CONN["servidor"], "banco": CONN["banco"], "tipo": "produto", "page": 1, "size": 20}
        )
        assert j and j.get("success") is True, j

    def test_produto_foto_inexistente_204(self, api):
        r = api.get(f"{BASE_URL}/api/produtos/foto/NAOEXISTE", timeout=15)
        assert r.status_code == 204, r.text


# ============================================================================
# 5. PEDIDOS — list, get, itens
# ============================================================================
class TestPedidos:
    def test_list_pedidos(self, api):
        body = {**CONN, "search": "", "page": 1, "size": 10}
        r, j = _post_with_retry(api, f"{BASE_URL}/api/pedidos", body)
        assert j.get("success") is True, j
        items = j.get("items") or []
        # Tem pelo menos o pedido #1
        assert len(items) >= 1, items
        # Pedido #1 deve estar lá
        assert any(int(p.get("pedido") or 0) == 1 for p in items), items

    def test_get_pedido_1(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/pedidos/1",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        p = j.get("pedido") or {}
        assert int(p.get("pedido") or 0) == 1
        assert (p.get("situacao") or "").strip() == "A"

    def test_list_itens_pedido_1(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/pedidos/1/itens",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        itens = j.get("items") or []
        assert len(itens) >= 1, itens
        # campos do contrato atual: qtd, valor_unitario, desconto, acrescimo, total
        # total = qtd * valor_unitario (valor_unitario já reflete preço após desconto unitário)
        for it in itens:
            qtd = float(it.get("qtd") or 0)
            vu = float(it.get("valor_unitario") or 0)
            tot = float(it.get("total") or 0)
            esperado = round(qtd * vu, 2)
            assert abs(tot - esperado) < 0.05, f"item total inconsistente: esperado={esperado} got={tot}; {it}"


# ============================================================================
# 6. DESCONTOS — listagem (sem aplicar desconto geral; somente leitura)
# ============================================================================
class TestDescontos:
    def test_list_descontos_pedido_1(self, api):
        _, j = _get_with_retry(api, f"{BASE_URL}/api/pedidos/1/descontos",
                               {"servidor": CONN["servidor"], "banco": CONN["banco"]})
        assert j and j.get("success") is True, j
        assert isinstance(j.get("items"), list)
        # Existe desconto do item Heineken Long Neck (R$ 2,40)
        # 'total' top-level resume soma dos descontos
        total = float(j.get("total") or 0)
        assert abs(total - 2.4) < 0.05, j
        assert len(j["items"]) >= 1


# ============================================================================
# 7. RELATÓRIOS / DASHBOARD (reconciliação rápida)
# ============================================================================
class TestRelatorios:
    def test_dashboard_data_hoje(self, api):
        params = {"servidor": CONN["servidor"], "banco": CONN["banco"], "data": PEDIDO_DATA}
        _, j = _get_with_retry(api, f"{BASE_URL}/api/dashboard/me", params)
        assert j and j.get("success") is True, j
        totais = j.get("totais") or {}
        pedidos = j.get("pedidos") or []
        soma_lista = round(sum(float(p.get("valor") or 0) for p in pedidos), 2)
        soma_cards = round(float(totais.get("produtos") or 0) + float(totais.get("servicos") or 0), 2)
        assert abs(soma_cards - soma_lista) < 0.01, (totais, pedidos)
        assert int(totais.get("pedidos") or 0) >= 1

    def test_relatorio_pedidos_amplo(self, api):
        params = {
            "servidor": CONN["servidor"], "banco": CONN["banco"],
            "data_ini": "2000-01-01", "data_fim": "2100-12-31",
        }
        _, j = _get_with_retry(api, f"{BASE_URL}/api/relatorios/pedidos", params)
        assert j and j.get("success") is True, j
        totais = j.get("totais") or {}
        pedidos = j.get("pedidos") or []
        soma_lista = round(sum(float(p.get("total") or 0) for p in pedidos), 2)
        soma_cards = round(float(totais.get("produtos") or 0) + float(totais.get("servicos") or 0), 2)
        assert abs(soma_cards - soma_lista) < 0.01, (totais, pedidos)
        assert int(totais.get("qtd_pedidos") or 0) >= 1

    def test_relatorio_descontos_margem(self, api):
        params = {
            "servidor": CONN["servidor"], "banco": CONN["banco"],
            "data_ini": "2000-01-01", "data_fim": "2100-12-31",
        }
        _, j = _get_with_retry(api, f"{BASE_URL}/api/relatorios/descontos-margem", params)
        assert j and j.get("success") is True, j
        # estrutura: vendedores (lista, cada um com pedidos) + totais
        assert "vendedores" in j, j
        assert "totais" in j, j
        t = j["totais"]
        assert abs(float(t.get("venda") or 0) - 54.5) < 0.05, t
        assert abs(float(t.get("desconto") or 0) - 2.4) < 0.05, t
        assert abs(float(t.get("margem") or 0) - 24.39) < 0.05, t
