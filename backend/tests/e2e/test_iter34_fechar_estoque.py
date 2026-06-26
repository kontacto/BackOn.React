"""Iter 34 — Regras de fechamento (Pedido / O.S.) e integridade de estoque.

Cenários validados:
  • POST /api/os/{codigo}/fechar (com/sem itens, OS não-aberta).
  • POST /api/pedidos/{pedido}/fechar (com/sem itens, Pedido não-aberto).
  • Estoque OS: incluir/remover item de peça em OS aberta movimenta pecas.qtd
    e pecas.reservado_os corretamente.
  • Estoque Pedido: incluir item em Pedido aberto NÃO movimenta estoque;
    somente após /fechar o estoque é movido (qtd-=q, reservado+=q).

Observação: o banco de teste tem pecas.qtd=0 em todos os produtos. Os
DELTAS (variação) são o que validamos, independente do sinal final.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"
PROD_P = "P001"  # peça existente — Coca-Cola 600ml
CONN = {"servidor": SERVIDOR, "banco": BANCO}
CONN_MASTER = {**CONN, "master": True}
CLIENTE_TEST = 1
VENDEDOR_TEST = 3  # ESTELA


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _get_estoque_p001(api) -> dict:
    r = api.get(f"{BASE_URL}/api/produtos-servicos", params={"servidor": SERVIDOR, "banco": BANCO,
                                                              "tipo": "P", "search": PROD_P,
                                                              "page": 1, "size": 50})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("success"), j
    for it in j.get("items", []):
        if str(it.get("codigo")).strip() == PROD_P:
            return {"qtd": float(it.get("qtd") or 0),
                    "reservado": float(it.get("reservado") or 0),
                    "reservado_os": float(it.get("reservado_os") or 0),
                    "estoque_total": float(it.get("estoque_total") or 0)}
    pytest.fail(f"Produto {PROD_P} não encontrado em /produtos-servicos")


# -------------------------------- OS estoque + fechar --------------------------------
class TestOSFecharEEstoque:

    def test_01_create_os_e_estoque_inclusao_remocao(self, api):
        """Cria OS, adiciona item peça (qtd=2): qtd -= 2 / reservado_os += 2; depois remove e estorna."""
        # estado inicial
        e0 = _get_estoque_p001(api)

        # cria OS
        r = api.post(f"{BASE_URL}/api/os/create", json={**CONN, "cliente": CLIENTE_TEST,
                                                         "atendente": VENDEDOR_TEST,
                                                         "obs": "TEST_iter34"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success"), j
        codigo = int(j["codigo"])
        pytest.os_codigo = codigo  # guarda p/ próximos testes

        # adiciona item de peça (qtd=2)
        r = api.post(f"{BASE_URL}/api/os/{codigo}/itens", json={**CONN, "produto": PROD_P,
                                                                 "qtd": 2, "valor_unitario": 10.0,
                                                                 "vendedor": VENDEDOR_TEST,
                                                                 "executor": VENDEDOR_TEST})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success"), j
        cod_os_prod = int(j["cod_os_prod"])
        pytest.os_cod_item = cod_os_prod

        # valida deltas após inclusão
        e1 = _get_estoque_p001(api)
        assert e1["qtd"] - e0["qtd"] == pytest.approx(-2.0), f"qtd delta {e1['qtd']-e0['qtd']} (esp -2)"
        assert e1["reservado_os"] - e0["reservado_os"] == pytest.approx(2.0), f"reservado_os delta (esp +2)"
        # estoque_total = qtd + reservado + reservado_os => não deve mudar
        assert e1["estoque_total"] == pytest.approx(e0["estoque_total"]), "estoque_total mudou após inclusão"

        # remove o item e valida estorno
        r = api.delete(f"{BASE_URL}/api/os/{codigo}/itens/{cod_os_prod}",
                       params={"servidor": SERVIDOR, "banco": BANCO})
        assert r.status_code == 200, r.text
        assert r.json().get("success"), r.text
        e2 = _get_estoque_p001(api)
        assert e2["qtd"] == pytest.approx(e0["qtd"]), f"qtd não estornou ({e2['qtd']} vs {e0['qtd']})"
        assert e2["reservado_os"] == pytest.approx(e0["reservado_os"]), "reservado_os não estornou"

    def test_02_fechar_os_sem_itens_retorna_erro(self, api):
        codigo = pytest.os_codigo
        r = api.post(f"{BASE_URL}/api/os/{codigo}/fechar", json=CONN_MASTER)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is False, j
        msg = (j.get("message") or "").lower()
        assert ("pelo menos um" in msg) or ("inclua" in msg), j

    def test_03_adiciona_item_e_fecha_os_ok(self, api):
        codigo = pytest.os_codigo
        e0 = _get_estoque_p001(api)
        r = api.post(f"{BASE_URL}/api/os/{codigo}/itens", json={**CONN, "produto": PROD_P,
                                                                 "qtd": 1, "valor_unitario": 5.0,
                                                                 "vendedor": VENDEDOR_TEST,
                                                                 "executor": VENDEDOR_TEST})
        assert r.status_code == 200, r.text
        assert r.json().get("success"), r.text
        # após inclusão na OS: qtd -=1, reservado_os +=1
        e1 = _get_estoque_p001(api)
        assert e1["qtd"] - e0["qtd"] == pytest.approx(-1.0)
        assert e1["reservado_os"] - e0["reservado_os"] == pytest.approx(1.0)

        # fechar a OS
        r = api.post(f"{BASE_URL}/api/os/{codigo}/fechar", json=CONN_MASTER)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        assert j.get("message") == "Pré-venda Fechada.", j
        assert j.get("situacao") == "F", j

        # após /fechar da OS, estoque NÃO deve mudar (já movido na inclusão)
        e2 = _get_estoque_p001(api)
        assert e2["qtd"] == pytest.approx(e1["qtd"]), "fechar OS não deve movimentar estoque novamente"
        assert e2["reservado_os"] == pytest.approx(e1["reservado_os"]), "reservado_os mudou ao fechar OS (erro)"

        # GET para confirmar persistência da situação 'F'
        r = api.get(f"{BASE_URL}/api/os/{codigo}", params={"servidor": SERVIDOR, "banco": BANCO})
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") and j["os"]["situacao"] == "F", j

    def test_04_fechar_os_ja_fechada_retorna_erro(self, api):
        codigo = pytest.os_codigo
        r = api.post(f"{BASE_URL}/api/os/{codigo}/fechar", json=CONN_MASTER)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is False, j
        assert "não pode ser fechada" in (j.get("message") or "").lower(), j


# -------------------------------- Pedido estoque + fechar --------------------------------
class TestPedidoFecharEEstoque:

    def test_05_pedido_aberto_inclusao_item_NAO_move_estoque(self, api):
        e0 = _get_estoque_p001(api)
        r = api.post(f"{BASE_URL}/api/pedidos/create", json={**CONN, "cliente": CLIENTE_TEST,
                                                              "vendedor": VENDEDOR_TEST,
                                                              "obs": "TEST_iter34"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success"), j
        pedido = int(j["pedido"])
        pytest.pedido_codigo = pedido

        # add item peça qtd=3
        r = api.post(f"{BASE_URL}/api/pedidos/{pedido}/itens", json={**CONN, "produto": PROD_P,
                                                                     "qtd": 3, "valor_unitario": 8.0})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success"), j
        pytest.pedido_codauto = int(j["codauto"])

        # estoque NÃO pode ter mudado (Pedido aberto)
        e1 = _get_estoque_p001(api)
        assert e1["qtd"] == pytest.approx(e0["qtd"]), f"Pedido aberto MOVEU estoque (qtd {e0['qtd']}→{e1['qtd']})"
        assert e1["reservado"] == pytest.approx(e0["reservado"]), "Pedido aberto MOVEU reservado"
        assert e1["reservado_os"] == pytest.approx(e0["reservado_os"]), "Pedido aberto mexeu em reservado_os"

    def test_06_fechar_pedido_baixa_estoque(self, api):
        pedido = pytest.pedido_codigo
        e0 = _get_estoque_p001(api)
        r = api.post(f"{BASE_URL}/api/pedidos/{pedido}/fechar", json=CONN_MASTER)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        assert j.get("message") == "Pré-venda Fechada.", j
        assert j.get("situacao") == "F", j

        # após /fechar: qtd -= 3, reservado += 3
        e1 = _get_estoque_p001(api)
        assert e1["qtd"] - e0["qtd"] == pytest.approx(-3.0), f"qtd delta {e1['qtd']-e0['qtd']} (esp -3)"
        assert e1["reservado"] - e0["reservado"] == pytest.approx(3.0), f"reservado delta (esp +3)"
        assert e1["reservado_os"] == pytest.approx(e0["reservado_os"]), "reservado_os não deveria mudar"

    def test_07_fechar_pedido_ja_fechado_retorna_erro(self, api):
        pedido = pytest.pedido_codigo
        r = api.post(f"{BASE_URL}/api/pedidos/{pedido}/fechar", json=CONN_MASTER)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is False, j
        assert "não pode ser fechado" in (j.get("message") or "").lower(), j

    def test_08_fechar_pedido_sem_itens_retorna_erro(self, api):
        # cria novo pedido sem itens
        r = api.post(f"{BASE_URL}/api/pedidos/create", json={**CONN, "cliente": CLIENTE_TEST,
                                                              "vendedor": VENDEDOR_TEST,
                                                              "obs": "TEST_iter34_empty"})
        assert r.status_code == 200, r.text
        pedido = int(r.json()["pedido"])
        r = api.post(f"{BASE_URL}/api/pedidos/{pedido}/fechar", json=CONN_MASTER)
        j = r.json()
        assert j.get("success") is False, j
        msg = (j.get("message") or "").lower()
        assert ("pelo menos um" in msg) or ("inclua" in msg), j


# -------------------------------- Produtos: campos novos --------------------------------
class TestProdutosCamposEstoque:

    def test_09_produtos_expor_qtd_reservado_reservado_os_total(self, api):
        r = api.get(f"{BASE_URL}/api/produtos-servicos", params={"servidor": SERVIDOR, "banco": BANCO,
                                                                  "tipo": "P", "page": 1, "size": 5})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success"), j
        assert len(j["items"]) > 0
        it = j["items"][0]
        for k in ("qtd", "reservado", "reservado_os", "estoque_total", "estoque"):
            assert k in it, f"campo {k} ausente em {it}"
        # estoque == qtd (disponível)
        assert it["estoque"] == it["qtd"]
        # estoque_total = qtd + reservado + reservado_os (tolerância 0.01)
        soma = round(float(it["qtd"]) + float(it["reservado"]) + float(it["reservado_os"]), 3)
        assert abs(soma - float(it["estoque_total"])) < 0.01
