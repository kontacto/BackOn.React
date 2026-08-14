"""Testes unitários de os_equipamento_service — múltiplos equipamentos por
O.S. (Assistência Técnica, ver AssistenciaTecnicaCampo.md seção 5, regra
14). Cobre a migração de schema (tabela + backfill), CRUD de vínculo
equipamento<->OS e o cancelamento por equipamento (soft, `situacao='C'`)."""
import services.os_equipamento_service as svc
from models.schemas import OSEquipamentoSaveRequest


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
        servidor="srv", banco="bd", equipamento=10,
        defeito_reclamado="Não gela", servico_executado="", servico_a_executar="", diagnostico="",
        status_os=None, usuario_alteracao=-2, classe=1, plataforma="web",
    )
    base.update(over)
    return OSEquipamentoSaveRequest(**base)


class TestEnsureTable:
    def test_cria_tabela_e_faz_backfill(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_os_equipamento_table(Cur())
        assert len(queries) == 4
        assert "CREATE TABLE os_equipamento" in queries[0]
        assert "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'os_equipamento')" in queries[0]
        assert "INSERT INTO os_equipamento" in queries[1]
        assert "NOT EXISTS (SELECT 1 FROM os_equipamento oe WHERE oe.os = o.codigo)" in queries[1]
        assert "CREATE INDEX IX_os_equipamento_os ON os_equipamento(os)" in queries[2]
        assert "CREATE INDEX IX_os_equipamento_equipamento ON os_equipamento(equipamento)" in queries[3]

    def test_backfill_nao_faz_fan_out_com_numero_de_serie_duplicado(self):
        """Bug real encontrado ao vivo (KONTACTO TESTE, 2026-08-13): dado legado
        sujo tinha 15 equipamentos com o mesmo numero_de_serie='1' — um LEFT
        JOIN direto por numero_de_serie faria a OS virar 15 linhas de backfill
        em vez de 1. O JOIN precisa resolver no máximo 1 equipamento por OS
        (o de menor `codigo`, determinístico) via subquery correlacionada."""
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_os_equipamento_table(Cur())
        insert_sql = queries[1]
        assert "LEFT JOIN equipamentos e ON e.codigo = (" in insert_sql
        assert "SELECT MIN(e2.codigo) FROM equipamentos e2 WHERE e2.numero_de_serie = o.numero_de_serie" in insert_sql
        # nunca mais o JOIN ingênuo que causa fan-out
        assert "LEFT JOIN equipamentos e ON e.numero_de_serie = o.numero_de_serie" not in insert_sql


class TestListEquipamentos:
    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._list_equipamentos_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_mapeia_itens_corretamente(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}],
            many=[[{
                "codigo": 1, "equipamento": 10, "numero_de_serie": "SN-1", "principal": True, "situacao": "A",
                "defeito_reclamado": "Não gela", "servico_executado": "", "servico_a_executar": "",
                "diagnostico": "", "status_os": 3, "status_os_descricao": "Atendendo",
                "marca": "SAM", "marca_descricao": "Samsung", "modelo": "M01", "modelo_descricao": "Split 9000",
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_equipamentos_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["editavel"] is True
        item = r["items"][0]
        assert item["codigo"] == 1
        assert item["equipamento"] == 10
        assert item["principal"] is True
        assert item["status_os_descricao"] == "Atendendo"
        assert item["marca_descricao"] == "Samsung"


class TestAddEquipamento:
    def test_sem_equipamento_selecionado(self, monkeypatch):
        r = svc._add_equipamento_sync(_req(equipamento=None), 1)
        assert r["success"] is False
        assert "Selecione um equipamento" in r["message"]

    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._add_equipamento_sync(_req(), 1)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"]

    def test_equipamento_inexistente(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._add_equipamento_sync(_req(), 1)
        assert r["success"] is False
        assert "Equipamento não encontrado" in r["message"]

    def test_equipamento_ja_vinculado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"numero_de_serie": "SN-1"}, {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._add_equipamento_sync(_req(), 1)
        assert r["success"] is False
        assert "já está vinculado" in r["message"]

    def test_vincula_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"numero_de_serie": "SN-1"}, None, {"codigo": 55}])
        conn = _patch(monkeypatch, cur)
        r = svc._add_equipamento_sync(_req(defeito_reclamado="Não gela"), 1)
        assert r["success"] is True
        assert r["codigo"] == 55
        assert conn.committed is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_equipamento"))
        assert insert_p[0] == 1       # os
        assert insert_p[1] == 10      # equipamento
        assert insert_p[2] == "SN-1"  # numero_de_serie (resolvido do cadastro, não digitado)


class TestUpdateEquipamento:
    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        _patch(monkeypatch, cur)
        r = svc._update_equipamento_sync(_req(), 1, 55)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"]

    def test_equipamento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._update_equipamento_sync(_req(), 1, 999)
        assert r["success"] is False
        assert "não encontrado" in r["message"]
        assert conn.rolled is True

    def test_atualiza_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._update_equipamento_sync(_req(diagnostico="Gás baixo", status_os=3), 1, 55)
        assert r["success"] is True
        assert conn.committed is True
        upd_q, upd_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_equipamento SET defeito"))
        assert upd_p[-2] == 55  # codigo
        assert upd_p[-1] == 1   # os


class TestCancelarEquipamento:
    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_equipamento_sync("srv", "bd", 1, 55)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"]

    def test_nao_encontrado_ou_ja_cancelado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=0)
        _patch(monkeypatch, cur)
        r = svc._cancelar_equipamento_sync("srv", "bd", 1, 55)
        assert r["success"] is False
        assert "já cancelado" in r["message"]

    def test_cancela_com_sucesso_soft_nao_deleta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_equipamento_sync("srv", "bd", 1, 55)
        assert r["success"] is True
        assert conn.committed is True
        upd_q, upd_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_equipamento SET situacao='C'"))
        assert upd_p == (55, 1)
        assert not any(q.strip().startswith("DELETE FROM os_equipamento") for q, p in cur.queries)
