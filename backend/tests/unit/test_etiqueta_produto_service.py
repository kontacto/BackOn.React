"""Testes unitários de Etiquetas de Produto — réplica de
`Geral\\FrmEtqProd.frm` (ver docstring do service pro raciocínio completo:
tabela nova `modelo_etiqueta`, busca por NF de entrada, busca manual com
fallback código interno→fábrica→barras, matriz de Grade Cor×Tamanho)."""
import services.etiqueta_produto_service as svc


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

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestListarModelos:
    def test_tabela_ja_existe_com_dados_nao_semeia_de_novo(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 0, "nome": "IDENTIFICAÇÃO (4 POR LINHA)"}]])
        # _ensure_modelo_etiqueta_table faz um SELECT COUNT antes do SELECT * final
        cur._one = [{"n": 8}]
        _patch(monkeypatch, cur)
        r = svc._listar_modelos_sync("srv", "bd")
        assert r["success"] is True
        insert_calls = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO modelo_etiqueta")]
        assert insert_calls == []

    def test_tabela_vazia_semeia_8_modelos(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        cur._one = [{"n": 0}]
        _patch(monkeypatch, cur)
        r = svc._listar_modelos_sync("srv", "bd")
        assert r["success"] is True
        insert_calls = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO modelo_etiqueta")]
        assert len(insert_calls) == 8


class TestGravarMargem:
    def test_modelo_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"n": 8}, None])
        _patch(monkeypatch, cur)
        r = svc._gravar_margem_sync("srv", "bd", 99, 1.0, 1.0)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_bloqueia_modelo_nao_laser(self, monkeypatch):
        cur = FakeCursor(one=[{"n": 8}, {"formato": "gondola"}])
        _patch(monkeypatch, cur)
        r = svc._gravar_margem_sync("srv", "bd", 2, 1.0, 1.0)
        assert r["success"] is False
        assert "margem" in r["message"].lower()

    def test_grava_modelo_laser(self, monkeypatch):
        cur = FakeCursor(one=[{"n": 8}, {"formato": "grade_laser"}])
        conn = _patch(monkeypatch, cur)
        r = svc._gravar_margem_sync("srv", "bd", 0, 0.9, 1.0)
        assert r["success"] is True
        assert conn.committed is True
        update_q, params = cur.queries[-1]
        assert "UPDATE modelo_etiqueta" in update_q
        assert 0.9 in params and 1.0 in params


class TestBuscarNf:
    def test_campos_obrigatorios(self):
        r = svc._buscar_nf_sync("srv", "bd", "", "1", 5)
        assert r["success"] is False and "informe" in r["message"].lower()

    def test_nf_nao_cadastrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._buscar_nf_sync("srv", "bd", "100", "1", 5)
        assert r["success"] is False
        assert "não cadastrada" in r["message"].lower()

    def test_calcula_quant_por_unidade_de_compra(self, monkeypatch):
        cur = FakeCursor(
            one=[{"codigo": 55, "data_mov": "2026-08-01"}],
            many=[[{
                "codigo_int": "P001", "codigo_fab": "FAB1", "descricao": "Parafuso",
                "codigo_bar": "7891234500000", "p_venda": 12.5, "qtd_un_compra": 10, "qtd": 3,
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._buscar_nf_sync("srv", "bd", "100", "1", 5)
        assert r["success"] is True
        assert r["itens"][0]["quant"] == 30


class TestBuscarProduto:
    def test_termo_vazio(self):
        r = svc._buscar_produto_sync("srv", "bd", "  ")
        assert r["success"] is False

    def test_resolve_por_codigo_interno_primeiro(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo_int": "P001", "codigo_fab": "FAB1", "descricao": "Parafuso", "descricao_pdv": "", "codigo_bar": "789", "p_venda": 5.0},
            {"n": 0},
        ])
        _patch(monkeypatch, cur)
        r = svc._buscar_produto_sync("srv", "bd", "P001")
        assert r["success"] is True
        assert r["produto"]["codigo_int"] == "P001"
        assert r["produto"]["tem_grade"] is False
        # só 1 tentativa de lookup em pecas (achou de cara por codigo_int)
        pecas_lookups = [q for q, _ in cur.queries if "FROM pecas WHERE" in q]
        assert len(pecas_lookups) == 1

    def test_fallback_codigo_fab_depois_barra(self, monkeypatch):
        cur = FakeCursor(one=[
            None,  # codigo_int não achou
            None,  # codigo_fab não achou
            {"codigo_int": "P002", "codigo_fab": "FAB2", "descricao": "Porca", "descricao_pdv": "", "codigo_bar": "999", "p_venda": 2.0},
            {"n": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._buscar_produto_sync("srv", "bd", "999")
        assert r["success"] is True
        assert r["produto"]["codigo_int"] == "P002"
        assert r["produto"]["tem_grade"] is True

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None])
        _patch(monkeypatch, cur)
        r = svc._buscar_produto_sync("srv", "bd", "XXX")
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestListarGrade:
    def test_codigo_vazio(self):
        r = svc._listar_grade_sync("srv", "bd", "")
        assert r["success"] is False

    def test_monta_matriz(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"cor": 1, "cor_descricao": "Azul", "tamanho": "P", "codigo_int": "P001-AZ-P", "codigo_fab": "F1", "descricao": "Camisa Azul P", "codigo_bar": "111", "p_venda": 30.0},
            {"cor": 1, "cor_descricao": "Azul", "tamanho": "M", "codigo_int": "P001-AZ-M", "codigo_fab": "F2", "descricao": "Camisa Azul M", "codigo_bar": "112", "p_venda": 30.0},
        ]])
        _patch(monkeypatch, cur)
        r = svc._listar_grade_sync("srv", "bd", "P001")
        assert r["success"] is True
        assert len(r["grade"]) == 2
        assert r["grade"][0]["cor_descricao"] == "Azul"
        assert r["grade"][1]["tamanho"] == "M"
