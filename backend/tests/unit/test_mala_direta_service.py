"""Testes unitários de Mala Direta — migração de Geral\\FrmMalDir2.FRM,
redesenhada como seleção de destinatário pra envio em massa (WhatsApp/
E-mail) em vez de etiqueta impressa (ver docstring do service pro
raciocínio completo)."""
import services.mala_direta_service as svc


class FakeCursor:
    def __init__(self, many=None):
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._many.pop(0) if self._many else []

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


class TestValidacao:
    def test_nenhum_tipo_selecionado(self):
        r = svc._selecionar_destinatarios_sync("srv", "bd", False, False, "todos", None, None, None)
        assert r["success"] is False

    def test_sub_modo_invalido(self):
        r = svc._selecionar_destinatarios_sync("srv", "bd", True, False, "invalido", None, None, None)
        assert r["success"] is False


class TestModosCliente:
    def test_todos_sem_filtro_extra(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._selecionar_destinatarios_sync("srv", "bd", True, False, "todos", None, None, None)
        query, params = cur.queries[-1]
        assert "c.situacao = 'A'" in query
        assert "FORMAT" not in query

    def test_aniversario_usa_format_mm_dd(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._selecionar_destinatarios_sync("srv", "bd", True, False, "aniversario", None, "01-01", "01-31")
        query, params = cur.queries[-1]
        assert "FORMAT(c.data_nasc, 'MM-dd')" in query
        assert params == ("01-01", "01-31")

    def test_tipo_usa_cliente_forn(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._selecionar_destinatarios_sync("srv", "bd", True, False, "tipo", "3", None, None)
        query, params = cur.queries[-1]
        assert "c.cliente_forn = %s" in query
        assert params == ("3",)


class TestResultado:
    def test_clientes_e_fornecedores_juntos(self, monkeypatch):
        cur = FakeCursor(many=[
            [{"codigo": 1, "nome": "Cliente A", "email": "a@x.com", "tem_telefone": 1}],
            [{"codigo_int": 10, "nome": "Fornecedor B", "email": None}],
        ])
        _patch(monkeypatch, cur)
        r = svc._selecionar_destinatarios_sync("srv", "bd", True, True, "todos", None, None, None)
        assert r["success"] is True
        assert len(r["destinatarios"]) == 2
        assert r["destinatarios"][0]["tipo"] == "cliente"
        assert r["destinatarios"][0]["tem_telefone"] is True
        assert r["destinatarios"][1]["tipo"] == "fornecedor"
        assert r["destinatarios"][1]["email"] is None

    def test_so_fornecedores(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo_int": 10, "nome": "Fornecedor B", "email": "b@x.com"}]])
        _patch(monkeypatch, cur)
        r = svc._selecionar_destinatarios_sync("srv", "bd", False, True, "todos", None, None, None)
        assert len(r["destinatarios"]) == 1
        assert r["destinatarios"][0]["codigo"] == 10
