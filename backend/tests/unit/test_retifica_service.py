"""Testes unitários de retifica_service — Envio de Equipamentos para
Terceiros (migração de `FrmManRet.frm`)."""
import services.retifica_service as svc
from models.schemas import RetificaSaveRequest, RetificaRetornoRequest


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


def _save_req(**over):
    base = dict(
        servidor="srv", banco="bd", os=100, marca="001", modelo="001",
        cliente=10, fornecedor=76, numero_de_serie="NS123", entrada="2026-08-01",
        valor=100.0, obs="teste", usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return RetificaSaveRequest(**base)


def _retorno_req(**over):
    base = dict(servidor="srv", banco="bd", saida="2026-08-05", valor=150.0,
                usuario_alteracao=1, classe=1, plataforma="web")
    base.update(over)
    return RetificaRetornoRequest(**base)


class TestSaveRetifica:
    def test_os_inexistente_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_sync(_save_req())
        assert r["success"] is False
        assert "inexistente" in r["message"].lower()

    def test_numero_serie_vazio_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._save_sync(_save_req(numero_de_serie="  "))
        assert r["success"] is False
        assert "número de série" in r["message"].lower()

    def test_sucesso_cria_protocolo(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"num": 501}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(_save_req())
        assert r["success"] is True and r["num"] == 501
        assert conn.committed is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO retifica"))
        assert insert_p[3] == "10"   # cliente gravado como string
        assert insert_p[4] == "76"   # fornecedor gravado como string
        assert insert_p[6] == "2026-08-01"  # entrada


class TestUpdateRetifica:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._update_sync(_save_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._update_sync(_save_req(valor=200.0), 501)
        assert r["success"] is True
        assert conn.committed is True


class TestRetornoRetifica:
    def test_protocolo_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._retorno_sync(_retorno_req(), 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_sucesso_grava_saida_e_valor(self, monkeypatch):
        cur = FakeCursor(one=[{"valor": 100.0}])
        conn = _patch(monkeypatch, cur)
        r = svc._retorno_sync(_retorno_req(valor=150.0), 501)
        assert r["success"] is True
        assert conn.committed is True
        update_q, update_p = cur.queries[-1]
        assert "SET saida=%s, valor=%s" in update_q
        assert update_p == ("2026-08-05", 150.0, 501)

    def test_sem_valor_mantem_o_atual(self, monkeypatch):
        cur = FakeCursor(one=[{"valor": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._retorno_sync(_retorno_req(valor=None), 501)
        assert r["success"] is True
        update_p = cur.queries[-1][1]
        assert update_p[1] == 100.0  # mantém o valor já gravado


class TestDeleteRetifica:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_sucesso(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 501)
        assert r["success"] is True
        assert conn.committed is True


class TestListRetifica:
    def test_lista_marca_abertos(self, monkeypatch):
        cur = FakeCursor(many=[[
            {
                "num": 1, "os": 100, "marca": "001", "modelo": "001",
                "numero_de_serie": "NS1", "entrada": None, "saida": None,
                "valor": 100.0, "obs": "", "fornecedor_codigo": 76,
                "fornecedor_nome": "Fornecedor Teste", "cliente_codigo": 10,
                "cliente_nome": "Cliente Teste", "marca_descricao": "IBM",
                "modelo_descricao": "PC",
            },
        ]])
        _patch(monkeypatch, cur)
        r = svc._list_sync("srv", "bd", None, False)
        assert r["success"] is True
        assert r["items"][0]["aberto"] is True
        assert r["items"][0]["fornecedor_nome"] == "Fornecedor Teste"

    def test_filtro_somente_abertos_aplica_where(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_sync("srv", "bd", None, True)
        query = cur.queries[0][0]
        assert "r.saida IS NULL" in query
