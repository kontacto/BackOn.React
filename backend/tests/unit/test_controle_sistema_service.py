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
        r = svc._save_grupo_sync("srv", "bd", "controle", ["numero_nf"], set(), {})
        assert r["success"] is False
        assert "nenhum dado" in r["message"].lower()
        assert cur.queries == []
        assert conn.committed is False

    def test_dados_com_campo_grava_normalmente(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._save_grupo_sync("srv", "bd", "controle", ["numero_nf"], set(), {"numero_nf": 100})
        assert r["success"] is True
        assert conn.committed is True


# ---------------------------------------------------------------------------
# Achado real 2026-08-28 (Adriana/suporte, instalação "KONTACTO APP"):
# `controle.empresa` NÃO é sempre 0 numa instalação real (nesse caso, vale
# "1") — um `WHERE empresa=0` hardcoded nunca batia com nenhuma linha real,
# fazendo a leitura de Controle do Sistema (e a gravação) silenciosamente
# não afetar nada. `controle`/`controle_aux` são mono-linha e devem ser
# lidas/gravadas SEM WHERE nenhum (mesmo padrão do resto do sistema);
# `controle_nota_fiscal` é multi-linha de verdade e precisa do valor
# GENUÍNO de `empresa`, resolvido via `_resolver_empresa_sync`.
# ---------------------------------------------------------------------------
class FakeCursorComFetch:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []
        self.rowcount = 1

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnComFetch:
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


def _patch_fetch(monkeypatch, cursor):
    conn = FakeConnComFetch(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestResolverEmpresaSync:
    def test_devolve_valor_real_da_controle(self):
        cur = FakeCursorComFetch(one=[{"empresa": 1}])
        assert svc._resolver_empresa_sync(cur) == 1

    def test_fallback_quando_controle_vazia(self):
        cur = FakeCursorComFetch(one=[None])
        assert svc._resolver_empresa_sync(cur) == svc.EMPRESA


class TestGetControleSistemaSyncSemWhereEmpresa:
    def test_select_controle_e_controle_aux_sem_where_empresa(self, monkeypatch):
        cur = FakeCursorComFetch(one=[{"fantasia": "Loja"}, {}])
        _patch_fetch(monkeypatch, cur)
        r = svc._get_controle_sistema_sync("srv", "bd")
        assert r["success"] is True
        assert r["dados"]["fantasia"] == "Loja"
        for q, p in cur.queries:
            assert "WHERE empresa" not in q
            assert p is None


class TestSeriesNfUsaEmpresaResolvida:
    def test_list_series_nf_usa_empresa_real(self, monkeypatch):
        cur = FakeCursorComFetch(one=[{"empresa": 1}])
        _patch_fetch(monkeypatch, cur)
        r = svc._list_series_nf_sync("srv", "bd")
        assert r["success"] is True
        select_series = next(q for q, p in cur.queries if "FROM controle_nota_fiscal" in q)
        params = next(p for q, p in cur.queries if "FROM controle_nota_fiscal" in q)
        assert params == (1,)

    def test_save_serie_nf_usa_empresa_real_no_insert(self, monkeypatch):
        cur = FakeCursorComFetch(one=[{"empresa": 1}, None])  # resolver + "existe?" (não existe)
        _patch_fetch(monkeypatch, cur)
        r = svc._save_serie_nf_sync("srv", "bd", "1", 100)
        assert r["success"] is True
        insert_q = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT"))
        assert insert_q[1] == (100, "1", 1)

    def test_delete_serie_nf_usa_empresa_real(self, monkeypatch):
        cur = FakeCursorComFetch(one=[{"empresa": 1}])
        _patch_fetch(monkeypatch, cur)
        r = svc._delete_serie_nf_sync("srv", "bd", "1")
        assert r["success"] is True
        delete_q = next((q, p) for q, p in cur.queries if q.strip().startswith("DELETE"))
        assert delete_q[1] == (1, "1")
