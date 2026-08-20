"""Testes unitários de `contingencia_nfe_service.py` — infraestrutura
mínima de Contingência NFe (migração de `Geral\\FrmConNFe.frm`) — ver
PENDENCIAS.md > blueprint item 7 pro racional completo. Mesmo padrão de
`test_contingencia_nfce_service.py`, mas com uma diferença real: os DOIS
tipos (FS-IA=2/FS-DA=5) são igualmente selecionáveis ao abrir."""
import pytest

import services.contingencia_nfe_service as svc


@pytest.fixture(autouse=True)
def _modulo_nfe_ativo(monkeypatch):
    monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: True)


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
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


class TestContingenciaAbertaSync:
    def test_sem_contingencia_aberta(self):
        cur = FakeCursor(one=[None])
        assert svc.contingencia_aberta_sync(cur) is None

    def test_com_contingencia_aberta(self):
        linha = {"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 2}
        cur = FakeCursor(one=[linha])
        assert svc.contingencia_aberta_sync(cur) == linha


class TestAbrirContingenciaSync:
    def test_bloqueia_tipo_invalido(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=9, master=True)
        assert r["success"] is False
        assert "tipo de contingência" in r["message"].lower()

    def test_bloqueia_modulo_nfe_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: False)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, master=True)
        assert r["success"] is False
        assert "módulo nfe" in r["message"].lower()

    def test_bloqueia_motivo_curto(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="curto", tipo_contingencia=2, master=True)
        assert r["success"] is False
        assert "15 e 256" in r["message"]

    def test_bloqueia_dupla_abertura(self, monkeypatch):
        cur = FakeCursor(one=[{"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 5}])
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, master=True)
        assert r["success"] is False
        assert "já existe uma contingência aberta" in r["message"].lower()

    def test_sucesso_grava_tipo_fs_ia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, master=True)
        assert r["success"] is True
        assert conn.committed is True
        insert_q = [q for q in cur.queries if "INSERT INTO contingencia_nfe" in q[0]][0]
        assert insert_q[1][-1] == 2

    def test_sucesso_grava_tipo_fs_da(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=5, master=True)
        assert r["success"] is True
        assert conn.committed is True
        insert_q = [q for q in cur.queries if "INSERT INTO contingencia_nfe" in q[0]][0]
        assert insert_q[1][-1] == 5


class TestFecharContingenciaSync:
    def test_bloqueia_sem_contingencia_aberta(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._fechar_contingencia_sync("srv", "bd", master=True)
        assert r["success"] is False
        assert "não há contingência" in r["message"].lower()

    def test_sucesso_grava_data_fim(self, monkeypatch):
        cur = FakeCursor(one=[{"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 2}])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_contingencia_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE contingencia_nfe SET data_fim" in q[0] and "WHERE data_fim IS NULL" in q[0] for q in cur.queries)


class TestStatusContingenciaSync:
    def test_sem_contingencia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._status_contingencia_sync("srv", "bd")
        assert r == {"success": True, "aberta": False}

    def test_com_contingencia(self, monkeypatch):
        cur = FakeCursor(one=[{"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 5}])
        _patch(monkeypatch, cur)
        r = svc._status_contingencia_sync("srv", "bd")
        assert r["success"] is True
        assert r["aberta"] is True
        assert r["tipo_contingencia"] == 5


class TestSemPermissao:
    def test_bloqueia_abrir_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_fechar_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._fechar_contingencia_sync("srv", "bd", classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()
