"""Testes unitários de `controle_sistema_service.py` — guarda defensiva
contra `dados` vazio/ausente em `_save_controle_sistema_sync`/
`_save_grupo_sync`. Achado ao vivo 2026-08-17 (BD_PAJE/CASCADURA
AUTOCENTER): `routes/controle_sistema.py`'s `SalvarControleRequest.dados`
tinha `= {}` como default — uma chamada malformada (sem o campo `dados`)
passava silenciosamente, e o UPDATE às cegas gravava NULL/0 em TODOS os
campos de `controle`/`controle_aux`, apagando a configuração real da
empresa. Corrigido em duas camadas: `dados: dict` sem default no request
(rejeita com 422), e esta guarda no service (rejeita mesmo se `dados={}`
for explicitamente enviado). Ver PENDENCIAS.md > "O.S. Oficina — Ciclo de
Teste ao Vivo"."""
import services.controle_sistema_service as svc


class FakeCursor:
    def __init__(self):
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

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


class TestSalvarControleSistemaGuardaDadosVazio:
    def test_dados_vazio_rejeita_sem_tocar_banco(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._save_controle_sistema_sync("srv", "bd", {})
        assert r["success"] is False
        assert "nenhum dado" in r["message"].lower()
        assert cur.queries == []
        assert conn.committed is False

    def test_dados_com_ao_menos_um_campo_grava_normalmente(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._save_controle_sistema_sync("srv", "bd", {"fantasia": "Loja Teste"})
        assert r["success"] is True
        assert conn.committed is True
        assert len(cur.queries) == 2  # UPDATE controle + UPDATE controle_aux


class TestSalvarGrupoGuardaDadosVazio:
    def test_dados_vazio_rejeita_sem_tocar_banco(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._save_grupo_sync("srv", "bd", "controle", "empresa", ["numero_nf"], set(), {})
        assert r["success"] is False
        assert "nenhum dado" in r["message"].lower()
        assert cur.queries == []
        assert conn.committed is False

    def test_dados_com_campo_grava_normalmente(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._save_grupo_sync("srv", "bd", "controle", "empresa", ["numero_nf"], set(), {"numero_nf": 100})
        assert r["success"] is True
        assert conn.committed is True
