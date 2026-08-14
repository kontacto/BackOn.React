"""Testes unitários de Listagem de Clientes — réplica de
`Geral\\FrmRelClie.frm` (ver docstring do service pro raciocínio
completo: 6 modos de filtro, PF/PJ por tamanho de cgc_cpf, "Tipo"
generalizado pra cliente.cliente_forn)."""
import services.relatorio_listagem_clientes_service as svc


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

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestValidacao:
    def test_modo_invalido(self):
        r = svc._listar_clientes_sync("srv", "bd", "invalido", "x", None, None, True, True, "asc")
        assert r["success"] is False

    def test_ambos_pf_pj_desmarcados_retorna_vazio_sem_bater_no_banco(self):
        r = svc._listar_clientes_sync("srv", "bd", "nome", "Zé", None, None, False, False, "asc")
        assert r == {"success": True, "clientes": []}

    def test_sem_termo_e_sem_filtro_retorna_vazio(self):
        r = svc._listar_clientes_sync("srv", "bd", "nome", "", None, None, True, True, "asc")
        assert r == {"success": True, "clientes": []}


class TestModos:
    def test_modo_nome_usa_prefixo(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_clientes_sync("srv", "bd", "nome", "Ze", None, None, True, True, "asc")
        query, params = cur.queries[-1]
        assert "LEFT(c.nome, %s) = %s" in query
        assert params == (2, "Ze")

    def test_modo_tipo_usa_cliente_forn(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_clientes_sync("srv", "bd", "tipo", "3", None, None, True, True, "asc")
        query, params = cur.queries[-1]
        assert "c.cliente_forn = %s" in query
        assert "cliente.tipo" not in query

    def test_modo_data_cadastro(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_clientes_sync("srv", "bd", "data_cadastro", None, "2026-01-01", "2026-01-31", True, True, "asc")
        query, params = cur.queries[-1]
        assert "c.data AS DATE) BETWEEN" in query

    def test_pessoa_fisica_filtra_por_tamanho(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_clientes_sync("srv", "bd", "nome", "Ze", None, None, True, False, "asc")
        query, _ = cur.queries[-1]
        assert "LEN(ISNULL(c.cgc_cpf,'')) <= 11" in query

    def test_ordem_desc(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_clientes_sync("srv", "bd", "nome", "Ze", None, None, True, True, "desc")
        query, _ = cur.queries[-1]
        assert "ORDER BY c.nome DESC" in query


class TestResultado:
    def test_monta_lista(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"codigo": 1, "cgc_cpf": "12345678900", "nome": "Zé", "e_mail": "ze@x.com",
             "data_cad": "01/01/2026", "data_nasc": None, "tipo": 1, "situacao": "A"},
        ]])
        _patch(monkeypatch, cur)
        r = svc._listar_clientes_sync("srv", "bd", "nome", "Ze", None, None, True, True, "asc")
        assert r["success"] is True
        assert r["clientes"][0]["nome"] == "Zé"


class TestDetalheContatoEndereco:
    def test_monta_telefones_e_enderecos(self, monkeypatch):
        cur = FakeCursor(many=[
            [{"ddd": "21", "tel": "99999-0000"}],
            [{"endereco": "Rua X", "numero": None, "bairro": "Centro", "cep": "20000-000"}],
        ])
        _patch(monkeypatch, cur)
        r = svc._detalhe_contato_endereco_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["telefones"] == ["(21) 99999-0000"]
        assert "S/Num" in r["enderecos"][0]
