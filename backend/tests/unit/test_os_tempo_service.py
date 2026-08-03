"""Testes unitários de os_tempo_service — Tempo Gasto por Serviço (migração
do frame "Tempo Gasto" em `Revenda\\FrmTraOsNew.frm`, tabela `os_tempo`).
Cobre listagem (com tempo_gasto_min derivado), inclusão/alteração (exige OS
Aberta) e exclusão (idem)."""
import services.os_tempo_service as svc
from models.schemas import OSTempoSaveRequest


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


def _req(**over):
    base = dict(
        servidor="srv", banco="bd", codigo_interno="S001", funcionario=30,
        data="2026-08-01", hora_inicio="08:00", hora_fim="09:30", obs="teste",
        usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return OSTempoSaveRequest(**base)


class TestTempoGastoMin:
    def test_calcula_diferenca_normal(self):
        assert svc._tempo_gasto_min("08:00", "09:30") == 90

    def test_atravessa_meia_noite(self):
        assert svc._tempo_gasto_min("23:30", "00:15") == 45

    def test_sem_hora_fim_retorna_none(self):
        assert svc._tempo_gasto_min("08:00", "") is None
        assert svc._tempo_gasto_min("08:00", None) is None


class TestListTempo:
    def test_lista_com_sucesso(self, monkeypatch):
        os_row = {"situacao": "A"}
        itens = [
            {
                "codigo": 1, "codigo_interno": "S001", "funcionario": 30,
                "data": None, "hora_inicio": "08:00", "hora_fim": "09:30",
                "obs": "  troca de óleo  ", "item_descricao": "Troca de óleo",
                "funcionario_nome": "João",
            },
        ]
        cur = FakeCursor(one=[os_row], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._list_tempo_sync("srv", "bd", 55)
        assert r["success"] is True
        assert r["situacao"] == "A"
        assert len(r["items"]) == 1
        item = r["items"][0]
        assert item["codigo"] == 1
        assert item["obs"] == "troca de óleo"
        assert item["tempo_gasto_min"] == 90

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._list_tempo_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()


class TestSaveTempo:
    def test_bloqueia_sem_servico(self, monkeypatch):
        r = svc._save_tempo_sync(_req(codigo_interno=""), 55, None)
        assert r["success"] is False
        assert "serviço" in r["message"].lower()

    def test_bloqueia_sem_tecnico(self, monkeypatch):
        r = svc._save_tempo_sync(_req(funcionario=None), 55, None)
        assert r["success"] is False
        assert "técnico" in r["message"].lower()

    def test_bloqueia_sem_data(self, monkeypatch):
        r = svc._save_tempo_sync(_req(data=""), 55, None)
        assert r["success"] is False
        assert "data" in r["message"].lower()

    def test_bloqueia_sem_hora_inicio(self, monkeypatch):
        r = svc._save_tempo_sync(_req(hora_inicio=""), 55, None)
        assert r["success"] is False
        assert "hora inicial" in r["message"].lower()

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_tempo_sync(_req(), 999, None)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_bloqueia_os_nao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._save_tempo_sync(_req(), 55, None)
        assert r["success"] is False
        assert "aberta" in r["message"].lower()

    def test_cria_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo": 501}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_tempo_sync(_req(), 55, None)
        assert r["success"] is True
        assert r["codigo"] == 501
        assert conn.committed is True
        insert_q, insert_p = next(
            (q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_tempo")
        )
        assert insert_p == (55, "S001", 30, "2026-08-01", "08:00", "09:30", "teste")

    def test_cria_sem_hora_fim(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo": 502}])
        _patch(monkeypatch, cur)
        r = svc._save_tempo_sync(_req(hora_fim=None), 55, None)
        assert r["success"] is True
        insert_p = next(p for q, p in cur.queries if q.strip().startswith("INSERT INTO os_tempo"))
        assert insert_p[5] is None  # hora_fim

    def test_atualiza_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_tempo_sync(_req(obs="atualizado"), 55, 501)
        assert r["success"] is True
        assert r["codigo"] == 501
        assert conn.committed is True
        update_q, update_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_tempo"))
        assert update_p[-2:] == (501, 55)

    def test_atualiza_bloqueia_lancamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._save_tempo_sync(_req(), 55, 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()


class TestDeleteTempo:
    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_tempo_sync("srv", "bd", 999, 501)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_bloqueia_os_nao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._delete_tempo_sync("srv", "bd", 55, 501)
        assert r["success"] is False
        assert "aberta" in r["message"].lower()

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_tempo_sync("srv", "bd", 55, 501)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.strip().startswith("DELETE FROM os_tempo") for q, _ in cur.queries)

    def test_bloqueia_lancamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._delete_tempo_sync("srv", "bd", 55, 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()
        assert conn.rolled is True
