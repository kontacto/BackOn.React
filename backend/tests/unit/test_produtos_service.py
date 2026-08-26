"""Testes UNITÁRIOS de produtos_service (busca de produto/serviço p/ Pedido)."""
import services.produtos_service as svc


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestListProdutosServicosBuscaPeca:
    """Busca de produto (pecas) — trazida 2026-07-20 pra aceitar Código de
    Fábrica, Aplicação/Observações (Descricao_Completa) e Níveis, além de
    Código Interno/Descrição já existentes. Pedido explícito do usuário:
    "a busca de produto do adicionar item do pedido geral tem que aceitar
    codigo interno..., código de fabrica, descriçao, aplicação e níveis"."""

    def test_busca_com_termo_inclui_todos_os_campos_no_where(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._list_produtos_servicos_sync("srv", "bd", "WR-245", 1, 40, "P")
        q, params = cur.queries[0]
        assert "p.codigo_int" in q
        assert "p.codigo_fab" in q
        assert "p.descricao" in q
        assert "p.Descricao_Completa" in q
        assert "p.nivel1" in q and "p.nivel2" in q and "p.nivel3" in q and "p.nivel4" in q and "p.nivel5" in q
        # 9 LIKEs no WHERE + 4 params extras do ORDER BY (2 exato + 2 prefixo)
        assert params.count("%WR-245%") == 9
        assert "WR-245" in params
        assert "WR-245%" in params

    def test_ordena_exato_codigo_interno_primeiro(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._list_produtos_servicos_sync("srv", "bd", "P245", 1, 40, "P")
        q, _ = cur.queries[0]
        assert "ORDER BY CASE" in q
        assert "UPPER(CAST(p.codigo_int AS NVARCHAR(20))) = UPPER(%s) THEN 0" in q
        assert "UPPER(p.codigo_fab) = UPPER(%s) THEN 1" in q

    def test_sem_termo_nao_filtra_e_ordena_por_descricao(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._list_produtos_servicos_sync("srv", "bd", "", 1, 40, "P")
        q, params = cur.queries[0]
        assert "WHERE" not in q
        assert "ORDER BY p.descricao" in q
        assert params == ()

    def test_mapeia_item_encontrado(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "tipo": "P", "codigo": "P6393", "descricao": "FILTRO DE AR",
            "valor": 45.0, "qtd": 10.0, "reservado": 1.0, "reservado_os": 0.0,
            "codigo_fab": "WR-245", "uni": "UN",
        }])
        _patch(monkeypatch, cur)
        r = svc._list_produtos_servicos_sync("srv", "bd", "245", 1, 40, "P")
        assert r["success"] is True
        assert len(r["items"]) == 1
        item = r["items"][0]
        assert item["codigo"] == "P6393" and item["cod_fab"] == "WR-245"
        # produto ainda sem foto migrada pra produto_imagem (ver "Fotos de
        # Produto") — imagem_codigo ausente na row não pode quebrar o mapeamento.
        assert item["imagem_codigo"] is None


class TestListProdutosServicosImagemPrincipal:
    """LEFT JOIN produto_imagem (foto principal) — ver PENDENCIAS.md >
    "Fotos de Produto". Devolve o `codigo` da foto principal por item pra
    `produtos.tsx` montar a URL da thumbnail sem precisar de uma chamada
    extra por produto na lista de busca."""

    def test_query_faz_left_join_produto_imagem_principal_ativa(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._list_produtos_servicos_sync("srv", "bd", "", 1, 40, "P")
        q, _ = cur.queries[0]
        assert "LEFT JOIN produto_imagem pi ON pi.codigo_int = p.codigo_int" in q
        assert "pi.principal = 1 AND pi.situacao = 'A'" in q
        assert "pi.codigo AS imagem_codigo" in q

    def test_mapeia_imagem_codigo_quando_produto_tem_foto_principal(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "tipo": "P", "codigo": "P6393", "descricao": "FILTRO DE AR",
            "valor": 45.0, "qtd": 10.0, "reservado": 0.0, "reservado_os": 0.0,
            "codigo_fab": "WR-245", "uni": "UN", "imagem_codigo": 77,
        }])
        _patch(monkeypatch, cur)
        r = svc._list_produtos_servicos_sync("srv", "bd", "245", 1, 40, "P")
        assert r["items"][0]["imagem_codigo"] == 77
