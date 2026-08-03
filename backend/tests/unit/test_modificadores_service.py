"""Testes UNITÁRIOS de Modificadores (Cadastros > Tabelas Auxiliares) — Fase
1: cadastro (Categorias + Modificadores + associação com Produto/Serviço).
Ver PENDENCIAS.md > "Modificadores" pro desenho completo."""
import services.modificadores_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch(monkeypatch, cursor, modulo_bar_ativo=True):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    # Módulo Bar gateia todo o módulo Modificadores (2026-07-23, user-
    # directed) — mockado sempre ligado por padrão pros testes de regra de
    # negócio abaixo não precisarem empilhar uma linha extra em toda
    # chamada; `TestModuloBarGating` cobre o caso desligado separadamente.
    monkeypatch.setattr(svc, "_modulo_bar_ativo", lambda cur: modulo_bar_ativo)
    return conn


class TestModuloBarGating:
    """Módulo Modificadores só funciona com controle_configuracao.Bar
    ligado (2026-07-23, user-directed: "colocar o modificador ligado ao
    módulo de Pedido Bar") — cada função de entrada bloqueia com uma
    mensagem clara quando o módulo está desligado, mesmo padrão de
    `_modulo_contratos_ativo`/`_modulo_servicos_ativo`."""

    def test_list_categorias_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._list_categorias_sync("srv", "bd")
        assert r["success"] is False
        assert "Bar" in r["message"]
        assert r["items"] == []

    def test_get_categoria_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._get_categoria_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_save_categoria_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._save_categoria_sync("srv", "bd", {"nome": "Ponto da Carne"})
        assert r["success"] is False

    def test_delete_categoria_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._delete_categoria_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_list_por_item_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._list_categorias_por_item_sync("srv", "bd", "P", "P001")
        assert r["success"] is False
        assert r["items"] == []

    def test_completo_por_item_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._get_modificadores_completo_por_item_sync("srv", "bd", "P", "P001")
        assert r["success"] is False
        assert r["items"] == []

    def test_associar_bloqueia_com_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur, modulo_bar_ativo=False)
        r = svc._associar_item_categorias_sync("srv", "bd", "P", "P001", [1])
        assert r["success"] is False


class TestListCategorias:
    def test_lista_com_contadores(self, monkeypatch):
        linhas = [
            {"codigo": 1, "nome": "PONTO DA CARNE", "obrigatorio": True, "selecao_multipla": False,
             "qtd_modificadores": 3, "qtd_associados": 8},
        ]
        cur = FakeCursor(many=[linhas])
        _patch(monkeypatch, cur)
        r = svc._list_categorias_sync("srv", "bd")
        assert r["success"] is True
        assert r["items"][0]["qtd_modificadores"] == 3
        assert r["items"][0]["qtd_associados"] == 8

    def test_busca_filtra_por_nome(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_categorias_sync("srv", "bd", busca="carne")
        query, params = cur.queries[-1]
        assert "WHERE mc.nome LIKE %s" in query
        assert params == ("%carne%",)


class TestGetCategoria:
    def test_categoria_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_categoria_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_traz_modificadores_e_itens_associados(self, monkeypatch):
        categoria = {"codigo": 1, "nome": "PONTO DA CARNE", "obrigatorio": True, "selecao_multipla": False}
        modificadores = [
            {"codigo": 10, "nome": "Mal passado", "acrescimo": 0.0, "desconto": 0.0, "situacao": "A"},
        ]
        itens_brutos = [{"tipo": "P", "codigo": "P001"}]
        cur = FakeCursor(one=[categoria], many=[modificadores, itens_brutos])
        _patch(monkeypatch, cur)
        # a resolução de descrição do item associado faz mais 1 SELECT/fetchone
        cur._one.append({"descricao": "PICANHA"})
        r = svc._get_categoria_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["nome"] == "PONTO DA CARNE"
        assert len(r["modificadores"]) == 1
        assert r["modificadores"][0]["nome"] == "Mal passado"
        assert r["itens_associados"] == [{"tipo": "P", "codigo": "P001", "descricao": "PICANHA"}]


class TestSaveCategoria:
    def test_sem_nome_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_categoria_sync("srv", "bd", {"nome": "  "})
        assert r["success"] is False

    def test_modificador_sem_nome_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_categoria_sync("srv", "bd", {"nome": "Ponto da Carne", "modificadores": [{"nome": ""}]})
        assert r["success"] is False

    def test_cria_nova_categoria_com_modificadores_e_associacoes(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 5}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_categoria_sync("srv", "bd", {
            "nome": "Ponto da Carne",
            "obrigatorio": True,
            "selecao_multipla": False,
            "modificadores": [
                {"nome": "Mal passado", "acrescimo": 0, "desconto": 0, "situacao": "A"},
                {"nome": "Bem passado", "acrescimo": 0, "desconto": 0, "situacao": "A"},
            ],
            "itens_associados": [{"tipo": "P", "codigo": "P001"}],
        })
        assert r["success"] is True
        assert r["codigo"] == 5
        assert conn.committed is True
        insert_categoria = [q for q, _ in cur.queries if q.strip().upper().startswith("INSERT INTO MODIFICADOR_CATEGORIA (")]
        assert len(insert_categoria) == 1
        insert_modificadores = [q for q, _ in cur.queries if q.strip().upper().startswith("INSERT INTO MODIFICADOR ")]
        assert len(insert_modificadores) == 2
        insert_itens = [q for q, _ in cur.queries if "INSERT INTO modificador_categoria_item" in q]
        assert len(insert_itens) == 1

    def test_atualiza_categoria_existente_faz_replace_all(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_categoria_sync("srv", "bd", {
            "codigo": 7, "nome": "Ponto da Carne", "modificadores": [], "itens_associados": [],
        })
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.strip().upper().startswith("UPDATE MODIFICADOR_CATEGORIA") for q, _ in cur.queries)
        assert any(q.strip().upper().startswith("DELETE FROM MODIFICADOR WHERE") for q, _ in cur.queries)
        assert any("DELETE FROM modificador_categoria_item" in q for q, _ in cur.queries)

    def test_atualiza_categoria_inexistente_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_categoria_sync("srv", "bd", {"codigo": 999, "nome": "X"})
        assert r["success"] is False


class TestDeleteCategoria:
    def test_categoria_inexistente_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_categoria_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_exclui_em_cascata(self, monkeypatch):
        cur = FakeCursor(one=[{"nome": "Ponto da Carne"}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_categoria_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("DELETE FROM modificador_categoria_item" in q for q, _ in cur.queries)
        assert any(q.strip().upper().startswith("DELETE FROM MODIFICADOR WHERE") for q, _ in cur.queries)
        assert any(q.strip().upper().startswith("DELETE FROM MODIFICADOR_CATEGORIA WHERE") for q, _ in cur.queries)


class TestAssociacaoPorItem:
    def test_lista_categorias_de_um_produto(self, monkeypatch):
        linhas = [{"codigo": 1, "nome": "Ponto da Carne"}]
        cur = FakeCursor(many=[linhas])
        _patch(monkeypatch, cur)
        r = svc._list_categorias_por_item_sync("srv", "bd", "P", "P001")
        assert r["success"] is True
        assert r["items"] == [{"codigo": 1, "nome": "Ponto da Carne"}]
        query, params = cur.queries[-1]
        assert "i.tipo=%s AND i.codigo=%s" in query
        assert params == ("P", "P001")

    def test_associa_categorias_replace_all(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._associar_item_categorias_sync("srv", "bd", "S", "S010", [1, 2])
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.strip().upper().startswith("DELETE FROM MODIFICADOR_CATEGORIA_ITEM") for q, _ in cur.queries)
        inserts = [(q, p) for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO MODIFICADOR_CATEGORIA_ITEM")]
        assert len(inserts) == 2
        assert inserts[0][1] == (1, "S", "S010")
        assert inserts[1][1] == (2, "S", "S010")

    def test_completo_por_item_traz_modificadores_aninhados_so_ativos(self, monkeypatch):
        categorias = [
            {"codigo": 1, "nome": "Ponto da Carne", "obrigatorio": True, "selecao_multipla": False},
            {"codigo": 2, "nome": "Acompanhamentos", "obrigatorio": False, "selecao_multipla": True},
        ]
        mods_cat1 = [{"codigo": 10, "nome": "Mal passado", "acrescimo": 0.0, "desconto": 0.0}]
        mods_cat2 = [
            {"codigo": 20, "nome": "Batata Frita", "acrescimo": 8.0, "desconto": 0.0},
            {"codigo": 21, "nome": "Arroz", "acrescimo": 0.0, "desconto": 0.0},
        ]
        cur = FakeCursor(many=[categorias, mods_cat1, mods_cat2])
        _patch(monkeypatch, cur)
        r = svc._get_modificadores_completo_por_item_sync("srv", "bd", "P", "P001")
        assert r["success"] is True
        assert len(r["items"]) == 2
        assert r["items"][0]["obrigatorio"] is True
        assert r["items"][0]["modificadores"] == mods_cat1
        assert r["items"][1]["selecao_multipla"] is True
        assert r["items"][1]["modificadores"] == mods_cat2
        # cada busca de modificador filtra situacao='A'
        mod_queries = [q for q, _ in cur.queries if q.strip().upper().startswith("SELECT CODIGO, NOME, ACRESCIMO, DESCONTO FROM MODIFICADOR")]
        assert len(mod_queries) == 2
        assert all("situacao='A'" in q for q in mod_queries)
