"""Testes UNITÁRIOS de Cilindros (Cadastro/Consulta)."""
import services.cilindro_service as svc


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


def _dados(**over):
    base = dict(codigo="P123", capacidade=20, pressao=150, padrao="01", descricao="Cilindro Teste", situacao="A")
    base.update(over)
    return base


class TestGrupoGas:
    def test_extrai_ate_o_primeiro_ponto(self):
        assert svc._grupo_gas_de("ABC123.XYZ") == "ABC123"

    def test_sem_ponto_usa_tudo(self):
        assert svc._grupo_gas_de("ABC123") == "ABC123"

    def test_vazio(self):
        assert svc._grupo_gas_de("") == ""


class TestValidacoesSemBanco:
    def test_sem_codigo(self):
        r = svc._save_cilindro_sync("srv", "bd", None, _dados(codigo=""))
        assert r["success"] is False and "produto" in r["message"].lower()

    def test_sem_padrao(self):
        r = svc._save_cilindro_sync("srv", "bd", None, _dados(padrao=""))
        assert r["success"] is False and "padrão" in r["message"].lower()

    def test_sem_situacao(self):
        r = svc._save_cilindro_sync("srv", "bd", None, _dados(situacao=""))
        assert r["success"] is False and "situação" in r["message"].lower()


class TestSaveCilindro:
    def test_produto_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_cilindro_sync("srv", "bd", None, _dados())
        assert r["success"] is False and "produto" in r["message"].lower()

    def test_padrao_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"descricao": "Prod"}, None])
        _patch(monkeypatch, cur)
        r = svc._save_cilindro_sync("srv", "bd", None, _dados())
        assert r["success"] is False and "padrão" in r["message"].lower()

    def test_duplicidade(self, monkeypatch):
        cur = FakeCursor(one=[{"descricao": "Prod"}, {"descricao": "Padrao"}, {"cod": 55}])
        _patch(monkeypatch, cur)
        r = svc._save_cilindro_sync("srv", "bd", None, _dados())
        assert r["success"] is False and "55" in r["message"]

    def test_cria_novo(self, monkeypatch):
        cur = FakeCursor(one=[
            {"descricao": "Prod"},      # produto ok
            {"descricao": "Padrao"},    # padrao ok
            None,                        # sem duplicidade
            {"codigo": "P1"},             # _garantir_grupo_gas_sync: SELECT codigo FROM Cilindro_Grupo -> nao existe
            {"cod": 10},                  # SELECT cod apos INSERT
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cilindro_sync("srv", "bd", None, _dados())
        assert r["success"] is True
        assert r["cod"] == 10
        assert conn.committed is True


class TestFindProdutoPorCodigoFab:
    def test_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"descricao": "Produto X"}])
        _patch(monkeypatch, cur)
        r = svc._find_produto_por_codigo_fab_sync("srv", "bd", "ABC123")
        assert r["success"] is True and r["found"] is True and r["descricao"] == "Produto X"

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._find_produto_por_codigo_fab_sync("srv", "bd", "ZZZ")
        assert r["success"] is True and r["found"] is False


class TestDeleteCilindro:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_cilindro_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_bloqueia_com_dependencia(self, monkeypatch):
        cur = FakeCursor(one=[
            {"cod": 1},   # existe
            {1: 1},        # Cilindro_Cliente encontrado
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_cilindro_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "clientes" in r["message"].lower()
        assert conn.committed is False

    def test_exclui_sem_dependencias(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 1}, None, None, None, None])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_cilindro_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
