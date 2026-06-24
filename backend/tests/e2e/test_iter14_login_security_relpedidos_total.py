"""Iteration 14 tests:
1) BUG SECURITY (login invalid): POST /api/login com credencial inválida NÃO deve expor
   dados de conexão (empresa, server, database, sql_user, query, attempted, error_step).
   Apenas message='Usuário ou senha inválidos.' + success=false.
2) FEATURE (Relatório de Pedidos): /api/relatorios/pedidos retorna totais.produtos e
   totais.servicos para o front somar em 'Total Prod/Serv'.
3) Login VÁLIDO (KONTACTO / $KONT2011) continua funcionando.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
CONN = {
    "empresa": "BARESTEL",
    "servidor": "gibanweb.database.windows.net",
    "banco": "BDREACTAPP",
}


@pytest.fixture
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ----------------------- BUG SECURITY: login inválido -----------------------
class TestLoginInvalidNoLeak:
    def test_invalid_login_returns_generic_message_only(self, api_client):
        payload = {**CONN, "usuario": "naoexiste", "senha": "errada123"}
        # Múltiplas tentativas para acordar Azure SQL serverless
        last = None
        for _ in range(7):
            r = api_client.post(f"{BASE_URL}/api/login", json=payload, timeout=30)
            assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
            data = r.json()
            last = data
            if data.get("message") == "Usuário ou senha inválidos.":
                break
            import time as _t
            _t.sleep(3)
        assert last is not None
        # Mensagem genérica
        assert last.get("success") is False, f"success={last.get('success')} data={last}"
        assert last.get("message") == "Usuário ou senha inválidos.", f"message={last.get('message')}"
        # NÃO pode vazar nada de conexão / diagnóstico
        leaks = ["server", "database", "empresa", "attempted", "error_step",
                 "error_line", "error_code_line", "error_query", "usuario", "funcionario"]
        for k in leaks:
            assert last.get(k) is None, f"campo '{k}' deveria ser null/None mas veio: {last.get(k)!r}"


# ----------------------- Login MASTER válido -----------------------
class TestLoginMasterOK:
    def test_master_login_success(self, api_client):
        payload = {**CONN, "usuario": "KONTACTO", "senha": "$KONT2011"}
        r = api_client.post(f"{BASE_URL}/api/login", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("success") is True, data
        assert "sucesso" in (data.get("message") or "").lower()
        assert (data.get("usuario") or {}).get("usuario") == "KONTACTO"
        assert (data.get("usuario") or {}).get("master") is True


# ----------------------- FEATURE Relatório totais.produtos+servicos -----------------------
class TestRelatorioPedidosTotalProdServ:
    def test_relatorio_returns_produtos_servicos(self, api_client):
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data_ini": "2000-01-01",
            "data_fim": "2100-12-31",
        }
        # Retry para Azure wake-up
        data = None
        for _ in range(6):
            r = api_client.get(f"{BASE_URL}/api/relatorios/pedidos", params=params, timeout=45)
            assert r.status_code == 200, r.text[:300]
            data = r.json()
            if data.get("success"):
                break
            import time as _t
            _t.sleep(3)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        assert "produtos" in totais, f"chave 'produtos' ausente em totais: {totais}"
        assert "servicos" in totais, f"chave 'servicos' ausente em totais: {totais}"
        # Validar valores esperados (pedido #1: produtos 54.50, servicos 0.00)
        assert abs(float(totais.get("produtos") or 0) - 54.50) < 0.01, totais
        assert abs(float(totais.get("servicos") or 0) - 0.00) < 0.01, totais
        # Soma = 54.50 (o "Total Prod/Serv" do front)
        soma = float(totais["produtos"] or 0) + float(totais["servicos"] or 0)
        assert abs(soma - 54.50) < 0.01
        # Outros campos esperados pela revisão
        assert int(totais.get("qtd_pedidos") or 0) == 1, totais
        assert abs(float(totais.get("margem") or 0) - 24.39) < 0.05, totais
        assert abs(float(totais.get("margem_pct") or 0) - 44.75) < 0.1, totais
        assert abs(float(totais.get("desconto") or 0) - 2.40) < 0.01, totais
