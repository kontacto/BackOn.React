"""Iteration 15 — RECONCILIAÇÃO de totais (Dashboard + Relatório de Pedidos).

Bug original: cards 'Produtos' + 'Serviços' somavam itens (p_venda*qtd)
enquanto a lista 'Pedidos de Hoje' (e o relatório) somam pedido_venda.total.
Pedidos legados têm total diferente da soma dos itens => os cards NÃO batiam
com o 'Total' da lista.

Correção (server.py _ratear_totais_por_pedido): produtos/serviços são RATEADOS
pelo pedido_venda.total de cada pedido, com peso por p_venda dos itens.
Garantia: produtos + serviços == Σ pedido.total == 'Total' da lista.
Margem usa venda = Σ pedido.total − Σ custo.

Cenário no preview (pedido #1, data 2026-06-24, situação A, só produtos):
  - total = 54,50; produtos = 54,50; serviços = 0,00
  - margem = 24,39 (44,75%); descontos = 2,40
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
PEDIDO_DATA = "2026-06-24"  # data do pedido #1 (HOJE no preview)


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _get_with_retry(client: requests.Session, url: str, params: dict, retries: int = 7):
    """Azure SQL serverless pode estar pausado; faz wake-up com retry."""
    last = None
    for _ in range(retries):
        r = client.get(url, params=params, timeout=45)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        last = r.json()
        if last.get("success"):
            return last
        _t.sleep(3)
    return last  # retorna o último mesmo se não ok (caller decide)


# ============================================================================
# DASHBOARD — produtos + serviços == soma dos pedido.total (= total da lista)
# ============================================================================
class TestDashboardReconciliacao:
    def test_dashboard_situacao_todos(self, api_client):
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data": PEDIDO_DATA,
            # sem 'situacao' = todos
        }
        data = _get_with_retry(api_client, f"{BASE_URL}/api/dashboard/me", params)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        pedidos = data.get("pedidos") or []
        # Soma dos pedido.total exibida na lista 'Pedidos de Hoje'
        soma_lista = round(sum(float(p.get("valor") or 0) for p in pedidos), 2)
        # Cards Produtos + Serviços (já rateados)
        soma_cards = round(
            float(totais.get("produtos") or 0) + float(totais.get("servicos") or 0), 2
        )
        # *** RECONCILIAÇÃO ***
        assert abs(soma_cards - soma_lista) < 0.01, (
            f"Produtos+Serviços ({soma_cards}) != Total da lista ({soma_lista}); "
            f"totais={totais} pedidos={pedidos}"
        )
        # Valores esperados do preview (pedido #1)
        assert abs(soma_lista - 54.50) < 0.01, f"soma_lista={soma_lista} pedidos={pedidos}"
        assert abs(float(totais.get("produtos") or 0) - 54.50) < 0.01, totais
        assert abs(float(totais.get("servicos") or 0) - 0.00) < 0.01, totais
        assert int(totais.get("pedidos") or 0) == 1, totais
        # Margem = 54,50 − 30,11 = 24,39 (44,75%)
        assert abs(float(totais.get("margem") or 0) - 24.39) < 0.05, totais
        assert abs(float(totais.get("margem_pct") or 0) - 44.75) < 0.1, totais
        # Descontos
        assert abs(float(totais.get("descontos") or 0) - 2.40) < 0.01, totais

    def test_dashboard_situacao_aberto(self, api_client):
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data": PEDIDO_DATA,
            "situacao": "A",
        }
        data = _get_with_retry(api_client, f"{BASE_URL}/api/dashboard/me", params)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        pedidos = data.get("pedidos") or []
        soma_lista = round(sum(float(p.get("valor") or 0) for p in pedidos), 2)
        soma_cards = round(
            float(totais.get("produtos") or 0) + float(totais.get("servicos") or 0), 2
        )
        assert abs(soma_cards - soma_lista) < 0.01, (
            f"[Aberto] Produtos+Serviços ({soma_cards}) != Total da lista ({soma_lista})"
        )
        # pedido #1 é 'A' (Aberto) → mesmo valor
        assert int(totais.get("pedidos") or 0) == 1, totais
        assert abs(soma_lista - 54.50) < 0.01, soma_lista

    def test_dashboard_situacao_fechado_vazio(self, api_client):
        """Filtro 'Fechado' não deve retornar o pedido #1 (que é Aberto)."""
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data": PEDIDO_DATA,
            "situacao": "F",
        }
        data = _get_with_retry(api_client, f"{BASE_URL}/api/dashboard/me", params)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        pedidos = data.get("pedidos") or []
        assert len(pedidos) == 0, f"esperava 0 pedidos Fechados, veio {pedidos}"
        assert int(totais.get("pedidos") or 0) == 0
        assert abs(float(totais.get("produtos") or 0)) < 0.01
        assert abs(float(totais.get("servicos") or 0)) < 0.01


# ============================================================================
# RELATÓRIO DE PEDIDOS — produtos+servicos == Σ total da lista
# ============================================================================
class TestRelatorioPedidosReconciliacao:
    def test_periodo_amplo(self, api_client):
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data_ini": "2000-01-01",
            "data_fim": "2100-12-31",
        }
        data = _get_with_retry(api_client, f"{BASE_URL}/api/relatorios/pedidos", params)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        pedidos = data.get("pedidos") or []
        soma_lista = round(sum(float(p.get("total") or 0) for p in pedidos), 2)
        soma_cards = round(
            float(totais.get("produtos") or 0) + float(totais.get("servicos") or 0), 2
        )
        # *** RECONCILIAÇÃO: Produtos+Servicos == Σ pedido.total ***
        assert abs(soma_cards - soma_lista) < 0.01, (
            f"Produtos+Serviços ({soma_cards}) != soma da lista ({soma_lista}); "
            f"totais={totais}"
        )
        # 'Total Prod/Serv' (front: relpedidos-tot-total) = produtos+servicos
        # Já é igual a soma_cards (validado acima). Também checa que totais.venda
        # (Σ pedido.total) == soma_lista quando exposto.
        venda = totais.get("venda")
        if venda is not None:
            assert abs(float(venda) - soma_lista) < 0.01, (
                f"totais.venda ({venda}) != soma_lista ({soma_lista})"
            )
        # Valores esperados (pedido #1)
        assert int(totais.get("qtd_pedidos") or 0) == 1, totais
        assert abs(soma_lista - 54.50) < 0.01, soma_lista
        assert abs(float(totais.get("produtos") or 0) - 54.50) < 0.01, totais
        assert abs(float(totais.get("servicos") or 0) - 0.00) < 0.01, totais
        assert abs(float(totais.get("margem") or 0) - 24.39) < 0.05, totais
        assert abs(float(totais.get("margem_pct") or 0) - 44.75) < 0.1, totais
        assert abs(float(totais.get("desconto") or 0) - 2.40) < 0.01, totais

    def test_filtro_situacao_aberto(self, api_client):
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data_ini": "2000-01-01",
            "data_fim": "2100-12-31",
            "situacao": "A",
        }
        data = _get_with_retry(api_client, f"{BASE_URL}/api/relatorios/pedidos", params)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        pedidos = data.get("pedidos") or []
        soma_lista = round(sum(float(p.get("total") or 0) for p in pedidos), 2)
        soma_cards = round(
            float(totais.get("produtos") or 0) + float(totais.get("servicos") or 0), 2
        )
        assert abs(soma_cards - soma_lista) < 0.01
        assert int(totais.get("qtd_pedidos") or 0) == 1
        # todos os pedidos retornados devem ter situacao = A
        for p in pedidos:
            assert (p.get("situacao") or "").strip() == "A", p

    def test_filtro_situacao_fechado_vazio(self, api_client):
        params = {
            "servidor": CONN["servidor"],
            "banco": CONN["banco"],
            "data_ini": "2000-01-01",
            "data_fim": "2100-12-31",
            "situacao": "F",
        }
        data = _get_with_retry(api_client, f"{BASE_URL}/api/relatorios/pedidos", params)
        assert data and data.get("success") is True, data
        totais = data.get("totais") or {}
        pedidos = data.get("pedidos") or []
        assert len(pedidos) == 0
        assert int(totais.get("qtd_pedidos") or 0) == 0
        assert abs(float(totais.get("produtos") or 0)) < 0.01
        assert abs(float(totais.get("servicos") or 0)) < 0.01
