"""Testes UNITÁRIOS do Cadastro de Produtos (completo) — tabela `pecas`."""
import services.produto_completo_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
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


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestValidacoesSemBanco:
    def test_sem_descricao(self):
        r = svc._save_produto_sync("srv", "bd", None, {"situacao": "A"})
        assert r["success"] is False and "descrição" in r["message"].lower()

    def test_sem_situacao(self):
        r = svc._save_produto_sync("srv", "bd", None, {"descricao": "Produto X"})
        assert r["success"] is False and "situação" in r["message"].lower()


class TestGerarCodigoInt:
    def test_incrementa_e_formata(self):
        cur = FakeCursor(one=[{"cod_peca": 781}])
        codigo = svc._gerar_codigo_int_sync(cur)
        assert codigo == "P781"
        assert cur.queries[0][0].startswith("UPDATE controle SET cod_peca")


class TestModulos:
    def test_grade_ativo(self, monkeypatch):
        cur = FakeCursor(one=[{"v": True}])
        assert svc._modulo_grade_ativo(cur) is True

    def test_grade_inativo(self, monkeypatch):
        cur = FakeCursor(one=[{"v": False}])
        assert svc._modulo_grade_ativo(cur) is False

    def test_grade_sem_linha(self, monkeypatch):
        cur = FakeCursor(one=[None])
        assert svc._modulo_grade_ativo(cur) is False

    def test_livraria_ativo(self, monkeypatch):
        cur = FakeCursor(one=[{"v": True}])
        assert svc._modulo_livraria_ativo(cur) is True


class TestDeleteProduto:
    def test_produto_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_produto_sync("srv", "bd", "P1")
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_bloqueia_com_estoque(self, monkeypatch):
        cur = FakeCursor(one=[{"qtd": 5, "reservado": 0, "reservado_os": 0}])
        _patch(monkeypatch, cur)
        r = svc._delete_produto_sync("srv", "bd", "P1")
        assert r["success"] is False and "estoque" in r["message"].lower()

    def test_bloqueia_com_dependencia(self, monkeypatch):
        # qtd/reservado zerados (passa na 1a checagem), depois a 1a
        # dependência (movimentação) encontra um registro.
        cur = FakeCursor(one=[
            {"qtd": 0, "reservado": 0, "reservado_os": 0},
            {1: 1},  # movimentacao encontrada
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_produto_sync("srv", "bd", "P1")
        assert r["success"] is False
        assert "movimentação" in r["message"].lower()
        assert conn.committed is False

    def test_exclui_sem_dependencias(self, monkeypatch):
        cur = FakeCursor(one=[
            {"qtd": 0, "reservado": 0, "reservado_os": 0},
            None, None, None, None, None,  # nenhuma dependência encontrada
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_produto_sync("srv", "bd", "P1")
        assert r["success"] is True
        assert conn.committed is True


class TestCriarItensGrade:
    def test_bloqueia_modulo_desligado(self, monkeypatch):
        cur = FakeCursor(one=[{"v": False}])
        _patch(monkeypatch, cur)
        r = svc._criar_itens_grade_sync("srv", "bd", "P1", [{"cor": "001", "tamanho": "M"}])
        assert r["success"] is False and "grade desativado" in r["message"].lower()

    def test_produto_principal_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"v": True}, None])
        _patch(monkeypatch, cur)
        r = svc._criar_itens_grade_sync("srv", "bd", "P1", [{"cor": "001", "tamanho": "M"}])
        assert r["success"] is False and "produto principal" in r["message"].lower()

    def test_gera_item_por_combinacao(self, monkeypatch):
        principal = {"codigo_int": "P1", "codigo_fab": "ABC", "AutoNumProdutos": 10, "qtd": 5}
        cur = FakeCursor(one=[
            {"v": True},       # módulo grade ativo
            principal,          # SELECT * FROM pecas (principal)
            {"cod_peca": 900},  # gerar novo codigo (1a combinação)
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._criar_itens_grade_sync("srv", "bd", "P1", [{"cor": "001", "tamanho": "M"}])
        assert r["success"] is True
        assert r["itens"] == [{"codigo_int": "P900", "cor": "001", "tamanho": "M"}]
        assert conn.committed is True


class TestListCoresGrade:
    def test_retorna_cores(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": "001", "descricao": "Preto"}]])
        _patch(monkeypatch, cur)
        r = svc._list_cores_grade_sync("srv", "bd", "P1")
        assert r["success"] is True
        assert r["items"] == [{"codigo": "001", "descricao": "Preto"}]
