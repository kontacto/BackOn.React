"""Iteração 21 — FASE 2 do módulo Permissões (sistema=50).

Verifica:
  • Catálogo expõe o nó GERENCIAL com comandos TOTAIS, MARGEM, DESCONTOS, TODOS_VEND.
  • POST /api/permissoes/salvar grava apenas o(s) item(ns) marcados (delete+insert por classe/sistema).
  • GET /api/permissoes?classe=4 retorna apenas o que foi salvo (modo estrito).
  • Classe sem nada (ex.: ADMIN sem itens) volta lista vazia.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
SERVIDOR = "gibanweb.database.windows.net"
BANCO = "BDREACTAPP"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- catálogo ----------
class TestCatalogo:
    def test_catalogo_contains_gerencial(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/catalogo?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True
        assert j.get("sistema") == 50
        cat = j.get("catalogo") or []
        # localizar nó GERENCIAL
        gerencial = next((m for m in cat if m.get("tela") == "GERENCIAL" and m.get("tipo") == "MENU"), None)
        assert gerencial is not None, "Menu GERENCIAL não encontrado no catálogo"
        # painel gerencial (TELA) com 4 botões
        painel = next((t for t in gerencial["children"] if t.get("tipo") == "TELA"), None)
        assert painel is not None, "TELA Painel Gerencial não encontrada"
        comandos = sorted(b.get("comando") for b in painel.get("children", []))
        assert comandos == sorted(["TOTAIS", "MARGEM", "DESCONTOS", "TODOS_VEND"]), comandos


# ---------- enforcement / persistência ----------
class TestPermissoesEnforcement:
    @classmethod
    def teardown_class(cls):
        # limpa permissões de classe=4 e classe=1 ao final para não afetar UI manual
        for classe in (4, 1):
            requests.post(
                f"{BASE_URL}/api/permissoes/salvar",
                json={"servidor": SERVIDOR, "banco": BANCO, "classe": classe, "itens": []},
                timeout=30,
            )

    def test_classes_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/permissoes/classes?servidor={SERVIDOR}&banco={BANCO}", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j.get("success") is True
        assert isinstance(j.get("items"), list) and len(j["items"]) >= 1

    def test_salvar_apenas_cliente_abrir_para_vendedor(self, api):
        """Salva SOMENTE CLIENTE.ABRIR para classe 4 e verifica que é o único retornado."""
        payload = {
            "servidor": SERVIDOR,
            "banco": BANCO,
            "classe": 4,
            "itens": [
                {"tipo": "BOTAO", "tela": "CLIENTE", "comando": "ABRIR", "nome": "Abrir Tela", "formulario": "CLIENTE"},
            ],
        }
        r = api.post(f"{BASE_URL}/api/permissoes/salvar", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("success") is True, j

        # GET para verificar persistência
        g = api.get(
            f"{BASE_URL}/api/permissoes?servidor={SERVIDOR}&banco={BANCO}&classe=4",
            timeout=30,
        )
        assert g.status_code == 200
        gj = g.json()
        assert gj.get("success") is True
        itens = gj.get("items") or []
        assert len(itens) == 1, f"esperado 1 item, veio {len(itens)}: {itens}"
        it = itens[0]
        assert it.get("tela") == "CLIENTE" and it.get("comando") == "ABRIR" and it.get("tipo") == "BOTAO"

    def test_classe_sem_permissao_volta_vazia(self, api):
        # zera a classe ADMIN(1)
        requests.post(
            f"{BASE_URL}/api/permissoes/salvar",
            json={"servidor": SERVIDOR, "banco": BANCO, "classe": 1, "itens": []},
            timeout=30,
        )
        g = api.get(
            f"{BASE_URL}/api/permissoes?servidor={SERVIDOR}&banco={BANCO}&classe=1",
            timeout=30,
        )
        assert g.status_code == 200
        gj = g.json()
        assert gj.get("success") is True
        assert gj.get("items") == []

    def test_gerencial_pode_ser_salvo(self, api):
        """Garante que comandos GERENCIAL.* aceitam ser gravados (são reconhecidos pelo catálogo)."""
        itens = [
            {"tipo": "BOTAO", "tela": "GERENCIAL", "comando": "TOTAIS", "nome": "Ver totais do dia", "formulario": "GERENCIAL"},
            {"tipo": "BOTAO", "tela": "GERENCIAL", "comando": "MARGEM", "nome": "Ver margem média", "formulario": "GERENCIAL"},
        ]
        r = api.post(
            f"{BASE_URL}/api/permissoes/salvar",
            json={"servidor": SERVIDOR, "banco": BANCO, "classe": 4, "itens": itens},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json().get("success") is True
        g = api.get(f"{BASE_URL}/api/permissoes?servidor={SERVIDOR}&banco={BANCO}&classe=4", timeout=30).json()
        keys = sorted(f"{i['tela']}.{i['comando']}" for i in g.get("items", []))
        assert keys == sorted(["GERENCIAL.TOTAIS", "GERENCIAL.MARGEM"]), keys
