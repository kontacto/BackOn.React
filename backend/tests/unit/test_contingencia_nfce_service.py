"""Testes unitários de `contingencia_nfce_service.py` — infraestrutura
mínima de Contingência NFCe (migração de `Geral\\FrmConNFC.frm`, só
abrir/fechar/consultar estado atual, não a grade histórica completa) —
ver PENDENCIAS.md > "Gestor NFCe" pro racional completo."""
import services.contingencia_nfce_service as svc


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
    def test_sem_linha_aberta_devolve_none(self):
        cur = FakeCursor(one=[None])
        assert svc.contingencia_aberta_sync(cur) is None

    def test_com_linha_aberta_devolve_a_linha(self):
        linha = {"id": 1, "data_inicio": "2026-08-19", "hora_inicio": "10:00:00", "motivo": "x" * 20, "tipo_contingencia": 9}
        cur = FakeCursor(one=[linha])
        assert svc.contingencia_aberta_sync(cur) == linha

    def test_query_usa_data_fim_is_null_nao_isnull_string(self):
        # Divergência deliberada do SQL literal do legado — ver docstring
        # do módulo: `data_fim` é DATE de verdade nesta tabela nova, não
        # aceitaria `ISNULL(data_fim,'')=''`.
        cur = FakeCursor(one=[None])
        svc.contingencia_aberta_sync(cur)
        query = cur.queries[-1][0]
        assert "data_fim IS NULL" in query


class TestAbrirContingenciaSync:
    def test_bloqueia_motivo_curto(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="curto", master=True)
        assert r["success"] is False
        assert "15 e 256" in r["message"]

    def test_bloqueia_motivo_longo(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 300, master=True)
        assert r["success"] is False

    def test_bloqueia_dupla_abertura(self, monkeypatch):
        cur = FakeCursor(one=[{"id": 1, "data_inicio": "2026-08-19", "hora_inicio": "10:00:00", "motivo": "x" * 20, "tipo_contingencia": 9}])
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="Falha de conexão com o SEFAZ", master=True)
        assert r["success"] is False
        assert "já existe" in r["message"].lower()

    def test_sucesso_grava_tipo_9(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="Falha de conexão com o SEFAZ agora", master=True)
        assert r["success"] is True
        assert conn.committed is True
        insert_q, insert_p = cur.queries[-1]
        assert "INSERT INTO contingencia_nfce" in insert_q
        assert insert_p[-1] == 9 or "9" in insert_q  # tipo_contingencia fixo em 9

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[])
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="Falha de conexão com o SEFAZ agora", master=False, classe=2)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()


class TestFecharContingenciaSync:
    def test_bloqueia_sem_contingencia_aberta(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._fechar_contingencia_sync("srv", "bd", master=True)
        assert r["success"] is False
        assert "não há contingência" in r["message"].lower()

    def test_sucesso_grava_data_fim(self, monkeypatch):
        cur = FakeCursor(one=[{"id": 5, "data_inicio": "2026-08-19", "hora_inicio": "10:00:00", "motivo": "x" * 20, "tipo_contingencia": 9}])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_contingencia_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE contingencia_nfce SET data_fim" in q[0] for q in cur.queries)


class TestStatusContingenciaSync:
    def test_sem_contingencia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._status_contingencia_sync("srv", "bd")
        assert r == {"success": True, "aberta": False}

    def test_com_contingencia(self, monkeypatch):
        cur = FakeCursor(one=[{"id": 1, "data_inicio": "2026-08-19", "hora_inicio": "10:00:00", "motivo": "x" * 20, "tipo_contingencia": 9}])
        _patch(monkeypatch, cur)
        r = svc._status_contingencia_sync("srv", "bd")
        assert r["success"] is True
        assert r["aberta"] is True
        assert r["tipo_contingencia"] == 9

    def test_falha_conexao(self, monkeypatch):
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        r = svc._status_contingencia_sync("srv", "bd")
        assert r["success"] is False
