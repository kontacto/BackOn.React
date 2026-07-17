"""Testes UNITÁRIOS de Cilindro/Nº Série (Fase 2 do módulo Cilindros)."""
import services.cilindro_serie_service as svc


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


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _dados(**over):
    base = dict(numero_de_serie="NDS-001", cilindro=10, destino=0, tipo_destino="C",
                situacao="A", carga="CHEIO")
    base.update(over)
    return base


class TestProximaRevisao:
    def test_sem_revisao(self):
        assert svc._proxima_revisao(None, 3) is None

    def test_sem_prazo(self):
        assert svc._proxima_revisao("2024-01-10", None) is None

    def test_calcula(self):
        assert svc._proxima_revisao("2024-01-10", 3) == "2027-01-10"


class TestValidacoesSemBanco:
    def test_sem_numero_serie(self):
        r = svc._save_serie_sync("srv", "bd", None, _dados(numero_de_serie=""))
        assert r["success"] is False and "número de série" in r["message"].lower()

    def test_sem_cilindro(self):
        r = svc._save_serie_sync("srv", "bd", None, _dados(cilindro=0))
        assert r["success"] is False and "cilindro" in r["message"].lower()


class TestSaveSerie:
    def test_cilindro_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_serie_sync("srv", "bd", None, _dados())
        assert r["success"] is False and "cilindro" in r["message"].lower()

    def test_destino_cliente_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 10}, None])
        _patch(monkeypatch, cur)
        r = svc._save_serie_sync("srv", "bd", None, _dados(destino=5))
        assert r["success"] is False and "cliente" in r["message"].lower()

    def test_destino_fornecedor_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 10}, None])
        _patch(monkeypatch, cur)
        r = svc._save_serie_sync("srv", "bd", None, _dados(destino=5, tipo_destino="F"))
        assert r["success"] is False and "fornecedor" in r["message"].lower()

    def test_situacao_invalida(self, monkeypatch):
        cur = FakeCursor(one=[{"cod": 10}, None])
        _patch(monkeypatch, cur)
        r = svc._save_serie_sync("srv", "bd", None, _dados())
        assert r["success"] is False and "situação" in r["message"].lower()

    def test_cria_novo(self, monkeypatch):
        cur = FakeCursor(one=[
            {"cod": 10},              # cilindro existe
            {"descricao": "Ativo"},   # situacao ok
            {"codigo": 77},           # SELECT codigo apos INSERT
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_serie_sync("srv", "bd", None, _dados())
        assert r["success"] is True
        assert r["codigo"] == 77
        assert conn.committed is True

    def test_atualiza_existente(self, monkeypatch):
        cur = FakeCursor(one=[
            {"cod": 10},
            {"descricao": "Ativo"},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_serie_sync("srv", "bd", 77, _dados())
        assert r["success"] is True
        assert r["codigo"] == 77
        assert any("UPDATE" in (q or "") for q, _ in cur.queries)
        assert conn.committed is True


class TestDeleteSerie:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_serie_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_bloqueia_com_viagem(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}, {1: 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_serie_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "viagens" in r["message"].lower()
        assert conn.committed is False

    def test_exclui_sem_dependencia(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_serie_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
