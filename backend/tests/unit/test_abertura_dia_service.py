"""Testes unitários de Abertura do Dia — migração de `MdiPrincipal`
(`Ger_Abr_Click`) + `Revenda\\frmAbreDia.frm`. Ver PENDENCIAS.md > "MDI
Principal (VB6)". Reconciliação de estoque do legado CONFIRMADA em desuso
pela equipe VB6 (2026-08-16) — não portada, nem testada aqui de propósito.

Gate de rollout (`fantasia == "Kontacto"`, pedido explícito do usuário
2026-08-16) coberto em `TestDisponibilidade` — os demais testes usam
`FANTASIA_OK` no mock pra não precisar repetir a checagem em todo teste
que não é sobre esse gate especificamente."""
from datetime import date, timedelta

import services.abertura_dia_service as svc


class FakeCursor:
    def __init__(self, one=None, rowcount=1):
        self._one = list(one or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

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


HOJE = date.today().isoformat()
ONTEM = (date.today() - timedelta(days=1)).isoformat()
AMANHA = (date.today() + timedelta(days=1)).isoformat()
FANTASIA_OK = {"fantasia": "Kontacto"}


class TestDisponibilidade:
    def test_recurso_disponivel_case_insensitive_e_trim(self):
        assert svc._recurso_disponivel("  kontacto  ") is True
        assert svc._recurso_disponivel("KONTACTO") is True
        assert svc._recurso_disponivel("Kontacto") is True

    def test_recurso_indisponivel_outra_empresa(self):
        assert svc._recurso_disponivel("Cliente Real Ltda") is False
        assert svc._recurso_disponivel(None) is False
        assert svc._recurso_disponivel("") is False

    def test_status_reporta_disponivel_false_pra_outra_empresa(self, monkeypatch):
        cur = FakeCursor(one=[
            {"Data_Movimento": ONTEM, "fantasia": "Cliente Real Ltda"},
            {"CONTROLA_ABERTURA_DIA": False},
        ])
        _patch(monkeypatch, cur)
        r = svc._status_sync("srv", "bd")
        assert r["success"] is True
        assert r["disponivel"] is False

    def test_abrir_dia_bloqueia_fora_da_kontacto(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": ONTEM, "fantasia": "Cliente Real Ltda"}])
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 1, True, False)
        assert r["success"] is False
        assert "Kontacto" in r["message"]

    def test_abrir_dia_libera_para_kontacto(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": ONTEM, **FANTASIA_OK}])
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 1, True, False)
        assert r["success"] is True


class TestStatus:
    def test_retorna_data_flag_e_disponivel(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": ONTEM, **FANTASIA_OK}, {"CONTROLA_ABERTURA_DIA": True}])
        _patch(monkeypatch, cur)
        r = svc._status_sync("srv", "bd")
        assert r["success"] is True
        assert r["data_movimento"] == ONTEM
        assert r["controla_abertura_dia"] is True
        assert r["disponivel"] is True

    def test_falha_conexao(self, monkeypatch):
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        r = svc._status_sync("srv", "bd")
        assert r["success"] is False


class TestAbrirDiaValidacao:
    def test_data_invalida(self, monkeypatch):
        r = svc._abrir_dia_sync("srv", "bd", "não-é-data", 1, True, False)
        assert r["success"] is False and "inválida" in r["message"].lower()

    def test_data_futura_bloqueia(self, monkeypatch):
        r = svc._abrir_dia_sync("srv", "bd", AMANHA, 1, True, False)
        assert r["success"] is False and "superior" in r["message"].lower()


class TestAbrirDiaPermissao:
    def test_master_bypassa_permissao(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": ONTEM, **FANTASIA_OK}])
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 3, True, False)
        assert r["success"] is True

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[])  # tem_permissao's SELECT retorna None (fetchone vazio)
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 3, False, False)
        assert r["success"] is False and "permissão" in r["message"].lower()

    def test_com_permissao_libera(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"Data_Movimento": ONTEM, **FANTASIA_OK}])
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 3, False, False)
        assert r["success"] is True


class TestAbrirDiaRetrocesso:
    def test_retroceder_sem_confirmar_pede_confirmacao(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": HOJE, **FANTASIA_OK}])
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", ONTEM, 1, True, False)
        assert r["success"] is False
        assert r["requer_confirmacao"] is True

    def test_retroceder_confirmado_grava(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": HOJE, **FANTASIA_OK}])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", ONTEM, 1, True, True)
        assert r["success"] is True
        assert conn.committed is True
        _, params = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE controle"))
        assert ONTEM in params


class TestAbrirDiaSucesso:
    def test_avanca_data_normalmente(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": ONTEM, **FANTASIA_OK}])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 1, True, False)
        assert r["success"] is True
        assert r["data_movimento"] == HOJE
        assert r["data_anterior"] == ONTEM
        assert conn.committed is True

    def test_sem_data_atual_gravada_ainda_funciona(self, monkeypatch):
        cur = FakeCursor(one=[{"Data_Movimento": None, **FANTASIA_OK}])
        _patch(monkeypatch, cur)
        r = svc._abrir_dia_sync("srv", "bd", HOJE, 1, True, False)
        assert r["success"] is True
