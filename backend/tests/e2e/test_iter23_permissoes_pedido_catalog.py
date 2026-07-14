"""Iteração 23 — Catálogo de Permissões: nó MOVIMENTO > PEDIDO deve refletir TODOS
os botões reais da tela de Pedido (incluindo os sensíveis de gerência).

Regras validadas:
  • Catálogo do PEDIDO contém EXATAMENTE: ABRIR, GRAVAR, ADD_ITEM, EDIT_ITEM,
    DEL_ITEM, DESC_ITEM, DESC_GERAL, VER_DESCONTOS, ANALISE, SITUACAO.
  • NÃO contém EXCLUIR (pedido não é excluível — apenas muda de situação).
  • Persistência (salvar/ler) para classe=4 (VENDEDOR) de um subconjunto.
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

EXPECTED_PEDIDO_CMDS = [
    "ABRIR", "GRAVAR", "ADD_ITEM", "EDIT_ITEM", "DEL_ITEM",
    "DESC_ITEM", "DESC_GERAL", "VER_DESCONTOS", "ANALISE", "SITUACAO",
]

EXPECTED_PEDIDO_LABELS = {
    "ABRIR": "Abrir tela",
    "GRAVAR": "Gravar pedido",
    "ADD_ITEM": "Adicionar item",
    "EDIT_ITEM": "Editar item",
    "DEL_ITEM": "Excluir item",
    "DESC_ITEM": "Desconto no item",
    "DESC_GERAL": "Desconto geral",
    "VER_DESCONTOS": "Ver descontos",
    "ANALISE": "Analisar margem",
    "SITUACAO": "Alterar situação",
}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _find_pedido_node(catalog):
    transacoes = next(
        (m for m in catalog if m.get("tela") == "TRANSACOES" and m.get("tipo") == "MENU"),
        None,
    )
    assert transacoes is not None, "Menu TRANSACOES não encontrado no catálogo"
    pedido = next(
        (t for t in transacoes.get("children", []) if t.get("tela") == "PEDIDO" and t.get("tipo") == "TELA"),
        None,
    )
    assert pedido is not None, "TELA PEDIDO não encontrada dentro de TRANSACOES"
    return pedido


# ---------- catálogo ----------
class TestCatalogoPedido:
    def test_pedido_node_exists(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/catalogo?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        assert j.get("sistema") == 50
        cat = j.get("catalogo") or []
        pedido = _find_pedido_node(cat)
        assert pedido.get("nome") == "Pedidos Mobile"

    def test_pedido_has_exact_commands(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/catalogo?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        j = r.json()
        cat = j.get("catalogo") or []
        pedido = _find_pedido_node(cat)
        cmds = [b.get("comando") for b in pedido.get("children", []) if b.get("tipo") == "BOTAO"]
        # Conjunto exato (não importa a ordem)
        assert sorted(cmds) == sorted(EXPECTED_PEDIDO_CMDS), (
            f"Comandos do PEDIDO inesperados: vieram {sorted(cmds)}, esperado {sorted(EXPECTED_PEDIDO_CMDS)}"
        )

    def test_pedido_does_NOT_contain_excluir(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/catalogo?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        j = r.json()
        pedido = _find_pedido_node(j.get("catalogo") or [])
        cmds = [b.get("comando") for b in pedido.get("children", [])]
        assert "EXCLUIR" not in cmds, "Pedido NÃO deve conter ação EXCLUIR (apenas SITUACAO)"

    def test_pedido_labels_match_real_buttons(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/catalogo?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        j = r.json()
        pedido = _find_pedido_node(j.get("catalogo") or [])
        labels = {b["comando"]: b["nome"] for b in pedido.get("children", []) if b.get("tipo") == "BOTAO"}
        for cmd, expected_label in EXPECTED_PEDIDO_LABELS.items():
            assert labels.get(cmd) == expected_label, (
                f"Label do {cmd} deve ser '{expected_label}', veio '{labels.get(cmd)}'"
            )


# ---------- persistência ----------
class TestPersistenciaSubsetVendedor:
    SUBSET = [
        {"tipo": "BOTAO", "tela": "PEDIDO", "comando": "ABRIR", "nome": "Abrir tela", "formulario": "PEDIDO"},
        {"tipo": "BOTAO", "tela": "PEDIDO", "comando": "GRAVAR", "nome": "Gravar pedido", "formulario": "PEDIDO"},
        {"tipo": "BOTAO", "tela": "PEDIDO", "comando": "ADD_ITEM", "nome": "Adicionar item", "formulario": "PEDIDO"},
        {"tipo": "BOTAO", "tela": "PEDIDO", "comando": "EDIT_ITEM", "nome": "Editar item", "formulario": "PEDIDO"},
        {"tipo": "BOTAO", "tela": "PEDIDO", "comando": "DEL_ITEM", "nome": "Excluir item", "formulario": "PEDIDO"},
    ]

    @classmethod
    def teardown_class(cls):
        # Limpa classe=4 (VENDEDOR) ao final para não impactar UI manual
        requests.post(
            f"{BASE_URL}/api/permissoes/salvar",
            json={"servidor": SERVIDOR, "banco": BANCO, "classe": 4, "itens": []},
            timeout=30,
        )

    def test_salvar_subset_para_vendedor(self, api):
        r = api.post(
            f"{BASE_URL}/api/permissoes/salvar",
            json={"servidor": SERVIDOR, "banco": BANCO, "classe": 4, "itens": self.SUBSET},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j
        assert j.get("total") == len(self.SUBSET)

    def test_ler_e_validar_subset(self, api):
        g = api.get(
            f"{BASE_URL}/api/permissoes?servidor={SERVIDOR}&banco={BANCO}&classe=4",
            timeout=30,
        )
        assert g.status_code == 200
        gj = g.json()
        assert gj.get("success") is True
        keys = sorted(f"{i['tela']}.{i['comando']}" for i in gj.get("items", []))
        expected = sorted(f"PEDIDO.{c}" for c in ["ABRIR", "GRAVAR", "ADD_ITEM", "EDIT_ITEM", "DEL_ITEM"])
        assert keys == expected, f"Persistido != enviado. veio={keys}, esperado={expected}"

    def test_sensíveis_não_persistidos_para_vendedor(self, api):
        """DESC_GERAL/ANALISE/SITUACAO NÃO foram salvos no subset → não devem aparecer."""
        g = api.get(
            f"{BASE_URL}/api/permissoes?servidor={SERVIDOR}&banco={BANCO}&classe=4",
            timeout=30,
        ).json()
        cmds = {i["comando"] for i in g.get("items", []) if i.get("tela") == "PEDIDO"}
        for sens in ("DESC_GERAL", "ANALISE", "SITUACAO", "VER_DESCONTOS", "DESC_ITEM"):
            assert sens not in cmds, f"Sensível {sens} não deveria estar persistido para VENDEDOR"
