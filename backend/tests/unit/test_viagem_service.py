"""Testes UNITÁRIOS de Manutenção de Viagens (Fase 3 do módulo Cilindros)."""
import services.viagem_service as svc


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


class TestDatasHelpers:
    def test_mes_dia_fmt(self):
        assert svc._mes("2026-03-05") == 3
        assert svc._dia("2026-03-05") == 5
        assert svc._fmt("2026-03-05") == "05/03/2026"


class TestSaveViagemHeader:
    def test_sem_tipo_viagem(self):
        r = svc._save_viagem_header_sync("srv", "bd", None, {"veiculo": 1})
        assert r["success"] is False and "tipo" in r["message"].lower()

    def test_novo_sem_veiculo(self):
        r = svc._save_viagem_header_sync("srv", "bd", None, {"veiculo": 0, "tipo_viagem": 0})
        assert r["success"] is False and "veículo" in r["message"].lower()

    def test_cria_nova(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_viagem_header_sync("srv", "bd", None, {"veiculo": 5, "tipo_viagem": 0})
        assert r["success"] is True
        assert r["codigo"] == 10
        assert conn.committed is True

    def test_viagem_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_viagem_header_sync("srv", "bd", 99, {"veiculo": 5, "tipo_viagem": 0})
        assert r["success"] is False and "não encontrada" in r["message"].lower()

    def test_atualiza_lado_saida_quando_nao_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"saida_fechada": False, "entrada_fechada": False, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_viagem_header_sync("srv", "bd", 10, {"veiculo": 5, "tipo_viagem": 0})
        assert r["success"] is True
        assert any("SET veiculo=" in (q or "") for q, _ in cur.queries)
        assert conn.committed is True

    def test_atualiza_lado_retorno_quando_saida_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"saida_fechada": True, "entrada_fechada": False, "situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._save_viagem_header_sync("srv", "bd", 10, {"veiculo": 5, "tipo_viagem": 0})
        assert r["success"] is True
        assert any("SET retorno=" in (q or "") for q, _ in cur.queries)


class TestAddItem:
    def _dados(self, **over):
        base = dict(cliente=1, cilindro=10, status_saida="AP")
        base.update(over)
        return base

    def test_sem_cliente(self):
        r = svc._add_item_sync("srv", "bd", 1, self._dados(cliente=0))
        assert r["success"] is False and "destinatário" in r["message"].lower()

    def test_sem_cilindro(self):
        r = svc._add_item_sync("srv", "bd", 1, self._dados(cilindro=0))
        assert r["success"] is False and "cilindro" in r["message"].lower()

    def test_status_invalido(self):
        r = svc._add_item_sync("srv", "bd", 1, self._dados(status_saida="XX"))
        assert r["success"] is False and "status" in r["message"].lower()

    def test_viagem_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync("srv", "bd", 1, self._dados())
        assert r["success"] is False and "viagem" in r["message"].lower()

    def test_bloqueia_saida_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"saida_fechada": True, "entrada_fechada": False, "situacao": "A", "tipo_viagem": 0}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync("srv", "bd", 1, self._dados())
        assert r["success"] is False and "saída já foi fechada" in r["message"].lower()

    def test_cilindro_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"saida_fechada": False, "entrada_fechada": False, "situacao": "A", "tipo_viagem": 0},
            None,
        ])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync("srv", "bd", 1, self._dados())
        assert r["success"] is False and "cilindro não cadastrado" in r["message"].lower()

    def test_cria_item_sem_numero_serie(self, monkeypatch):
        cur = FakeCursor(one=[
            {"saida_fechada": False, "entrada_fechada": False, "situacao": "A", "tipo_viagem": 0},  # viagem
            {"cod": 10},   # cilindro existe
            {"maior": 2},  # max ordem
            {"codigo": 77},  # @@IDENTITY do item
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._add_item_sync("srv", "bd", 1, self._dados())
        assert r["success"] is True
        assert r["codigo"] == 77
        assert conn.committed is True


class TestDeleteItem:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 1)
        assert r["success"] is False and "não encontrado" in r["message"].lower()

    def test_bloqueia_com_saida_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"viagem": 1, "saida_fechada": True, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 5)
        assert r["success"] is False
        assert conn.committed is False

    def test_exclui(self, monkeypatch):
        cur = FakeCursor(one=[{"viagem": 1, "saida_fechada": False, "situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_item_sync("srv", "bd", 5)
        assert r["success"] is True
        assert conn.committed is True


class TestFecharSaida:
    def test_viagem_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._fechar_saida_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_ja_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "saida_fechada": True}])
        _patch(monkeypatch, cur)
        r = svc._fechar_saida_sync("srv", "bd", 1)
        assert r["success"] is False and "já foi fechada" in r["message"].lower()

    def test_sem_data_saida(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "saida_fechada": False, "saida": None}])
        _patch(monkeypatch, cur)
        r = svc._fechar_saida_sync("srv", "bd", 1)
        assert r["success"] is False and "data de saída" in r["message"].lower()

    def test_sem_motorista(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "saida_fechada": False, "saida": "2026-01-01", "hora_saida": "08:00", "motorista": None}])
        _patch(monkeypatch, cur)
        r = svc._fechar_saida_sync("srv", "bd", 1)
        assert r["success"] is False and "motorista" in r["message"].lower()

    def test_fecha_com_sucesso_tipo_fabrica(self, monkeypatch):
        # tipo_viagem=1 (Fábrica) pula AtualizaTipoDocSaida (só roda p/ tipo Normal)
        cur = FakeCursor(one=[{
            "situacao": "A", "saida_fechada": False, "saida": "2026-01-01", "hora_saida": "08:00",
            "motorista": 3, "tipo_viagem": 1,
        }])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_saida_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True


class TestFecharEntrada:
    def _viagem_base(self, **over):
        base = dict(situacao="A", saida_fechada=True, entrada_fechada=False, retorno="2026-01-05",
                    hora_retorno="10:00", tipo_viagem=0)
        base.update(over)
        return base

    def test_bloqueia_sem_saida_fechada(self, monkeypatch):
        cur = FakeCursor(one=[self._viagem_base(saida_fechada=False)])
        _patch(monkeypatch, cur)
        r = svc._fechar_entrada_sync("srv", "bd", 1)
        assert r["success"] is False and "saída" in r["message"].lower()

    def test_critica_retorno_nao_confirmado(self, monkeypatch):
        cur = FakeCursor(
            one=[self._viagem_base()],
            many=[[{"codigo": 1, "ordem": 1, "cliente": 5, "status_saida": "AP", "status_retorno": "AP",
                    "cilindro_retorno": None, "cil_codigo": "P1", "cil_capacidade": 20, "cil_pressao": 150}]],
        )
        _patch(monkeypatch, cur)
        r = svc._fechar_entrada_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "criticas" in r
        assert "confirmado" in r["criticas"][0].lower()

    def test_fecha_item_cancelado_sem_reconciliacao(self, monkeypatch):
        cur = FakeCursor(
            one=[self._viagem_base()],
            many=[[{"codigo": 1, "ordem": 1, "cliente": 5, "status_saida": "CA", "status_retorno": "CA",
                    "cilindro_retorno": 99, "cil_codigo": "P1", "cil_capacidade": 20, "cil_pressao": 150}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_entrada_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        assert any("SET situacao='F'" in (q or "") for q, _ in cur.queries)


class TestCancelarViagem:
    def test_bloqueia_com_saida_fechada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "saida_fechada": True, "tipo_viagem": 0}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_viagem_sync("srv", "bd", 1)
        assert r["success"] is False
        assert conn.committed is False

    def test_cancela_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "saida_fechada": False, "tipo_viagem": 0}])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_viagem_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True


class TestReabrir:
    def test_reabre_apenas_saida(self, monkeypatch):
        cur = FakeCursor(one=[{"saida_fechada": True, "entrada_fechada": False}])
        conn = _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True

    def test_nada_a_reabrir(self, monkeypatch):
        cur = FakeCursor(one=[{"saida_fechada": False, "entrada_fechada": False}])
        _patch(monkeypatch, cur)
        r = svc._reabrir_sync("srv", "bd", 1)
        assert r["success"] is False
