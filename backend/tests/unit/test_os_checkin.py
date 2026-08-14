"""Testes unitários de check-in/check-out por geolocalização (tela de
Atendimento de Campo — Assistência Técnica, ver AssistenciaTecnicaCampo.md
regra 2) + resolução de equipamento por número de série (regras 1/8) e o
histórico de OS por equipamento (regra 1)."""
import services.os_service as os_svc
import services.os_equipamento_service as equip_svc
import services.equipamentos_service as equipamentos_svc
from models.schemas import OSCheckinRequest, LimparLocalizacaoRequest


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


def _req(**over):
    base = dict(servidor="srv", banco="bd", latitude=-22.9, longitude=-43.2,
                usuario_alteracao=-2, classe=1, plataforma="android")
    base.update(over)
    return OSCheckinRequest(**base)


class TestCheckin:
    def test_checkin_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"checkin_em": None}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkin_os_sync(_req(), 123)

        assert r["success"] is True
        assert conn.committed is True
        upd_q, upd_p = cur.queries[-1]
        assert "UPDATE os SET checkin_em=GETDATE()" in upd_q
        assert upd_p == (-22.9, -43.2, -2, 123)

    def test_checkin_bloqueado_se_ja_registrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"checkin_em": "2026-08-14 10:00:00"}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkin_os_sync(_req(), 123)

        assert r["success"] is False
        assert "já registrado" in r["message"]
        assert conn.committed is False

    def test_checkin_bloqueado_se_os_nao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkin_os_sync(_req(), 123)

        assert r["success"] is False
        assert "não pode receber check-in" in r["message"]

    def test_checkin_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkin_os_sync(_req(), 999)

        assert r["success"] is False
        assert r["message"] == "OS não encontrada."


class TestCheckout:
    def test_checkout_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "checkin_em": "2026-08-14 09:00:00", "checkout_em": None}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkout_os_sync(_req(latitude=1.0, longitude=2.0), 123)

        assert r["success"] is True
        assert conn.committed is True
        upd_q, upd_p = cur.queries[-1]
        assert "UPDATE os SET checkout_em=GETDATE()" in upd_q
        assert upd_p == (1.0, 2.0, -2, 123)

    def test_checkout_bloqueado_sem_checkin_previo(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A", "checkin_em": None, "checkout_em": None}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkout_os_sync(_req(), 123)

        assert r["success"] is False
        assert "check-in antes do check-out" in r["message"]

    def test_checkout_bloqueado_se_ja_registrado(self, monkeypatch):
        cur = FakeCursor(one=[{
            "situacao": "A", "checkin_em": "2026-08-14 09:00:00", "checkout_em": "2026-08-14 11:00:00",
        }])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._checkout_os_sync(_req(), 123)

        assert r["success"] is False
        assert "já registrado" in r["message"]


class TestResolverPorEquipamento:
    def test_equipamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = FakeConn(cur)
        monkeypatch.setattr(equip_svc, "_open_conn", lambda *a, **k: conn)

        r = equip_svc._resolver_os_aberta_por_serie_sync("srv", "bd", "ABC123")

        assert r["success"] is False
        assert "Nenhum equipamento cadastrado" in r["message"]

    def test_equipamento_sem_os_aberta_vinculada(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, None])
        conn = FakeConn(cur)
        monkeypatch.setattr(equip_svc, "_open_conn", lambda *a, **k: conn)

        r = equip_svc._resolver_os_aberta_por_serie_sync("srv", "bd", "ABC123")

        assert r["success"] is False
        assert "vinculado a uma OS pela retaguarda" in r["message"]

    def test_resolve_os_aberta_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"codigo": 555}])
        conn = FakeConn(cur)
        monkeypatch.setattr(equip_svc, "_open_conn", lambda *a, **k: conn)

        r = equip_svc._resolver_os_aberta_por_serie_sync("srv", "bd", "ABC123")

        assert r["success"] is True
        assert r["os_codigo"] == 555

    def test_numero_de_serie_vazio(self, monkeypatch):
        r = equip_svc._resolver_os_aberta_por_serie_sync("srv", "bd", "  ")
        assert r["success"] is False


def _limpar_req(**over):
    base = dict(servidor="srv", banco="bd", classe=1, master=False, usuario_alteracao=-2, plataforma="web")
    base.update(over)
    return LimparLocalizacaoRequest(**base)


class TestLimparLocalizacao:
    """Ferramenta de conformidade LGPD — remove lat/lng de check-in/check-
    out, mantém os horários. Ver AssistenciaTecnicaCampo.md seção 7."""

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._limpar_localizacao_sync(_limpar_req(), 999)

        assert r["success"] is False
        assert r["message"] == "OS não encontrada."

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, None])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._limpar_localizacao_sync(_limpar_req(), 123)

        assert r["success"] is False
        assert "permissão" in r["message"].lower()
        assert conn.committed is False

    def test_com_permissao_limpa(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"ok": 1}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._limpar_localizacao_sync(_limpar_req(), 123)

        assert r["success"] is True
        assert conn.committed is True
        upd_q, upd_p = cur.queries[-1]
        assert "checkin_lat=NULL" in upd_q and "checkout_lat=NULL" in upd_q
        assert upd_p == (123,)

    def test_master_bypassa_permissao(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = FakeConn(cur)
        monkeypatch.setattr(os_svc, "_open_conn", lambda *a, **k: conn)

        r = os_svc._limpar_localizacao_sync(_limpar_req(master=True), 123)

        assert r["success"] is True
        assert conn.committed is True


class TestHistoricoOs:
    def test_lista_historico(self, monkeypatch):
        import datetime
        cur = FakeCursor(many=[[
            {"codigo": 20, "data_entrada": datetime.date(2026, 8, 1), "situacao": "PG", "resumo": "Troca de filtro"},
            {"codigo": 15, "data_entrada": None, "situacao": "A", "resumo": ""},
        ]])
        conn = FakeConn(cur)
        monkeypatch.setattr(equipamentos_svc, "_open_conn", lambda *a, **k: conn)

        r = equipamentos_svc._historico_os_sync("srv", "bd", 10)

        assert r["success"] is True
        assert len(r["items"]) == 2
        assert r["items"][0]["codigo"] == 20
        assert r["items"][0]["data"] == "2026-08-01"
        assert r["items"][1]["data"] is None
