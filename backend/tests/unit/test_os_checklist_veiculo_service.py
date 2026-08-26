"""Testes unitários de os_checklist_veiculo_service — Checklist de Entrada
de Veículo (O.S. Oficina), pedido explícito do usuário 2026-08-26, sem
precedente no legado. Cobre a migração de schema (tabela nova de
marcações + tabela nova de conclusão), CRUD de marcação (add/list) e o
cancelamento (soft, `situacao='C'`), além do botão "Concluir Checklist"
(`_concluir_sync`) — obrigatoriedade em si (bloquear incluir item/fechar/
faturar) é testada em `test_pedido_common.py`/`test_os_itens_service.py`/
`test_os_service.py`, não aqui (função vive em `pedido_common.py`)."""
from datetime import date

import services.os_checklist_veiculo_service as svc
from models.schemas import FecharRequest, OSChecklistVeiculoSaveRequest


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
        servidor="srv", banco="bd", tipo_avaria="AMASSADO",
        pos_x=0.42, pos_y=0.31, descricao="Porta dianteira esquerda",
        usuario_alteracao=-2, classe=1, plataforma="web",
    )
    base.update(over)
    return OSChecklistVeiculoSaveRequest(**base)


class TestEnsureTable:
    def test_cria_tabela_e_indice(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_os_checklist_veiculo_table(Cur())
        assert len(queries) == 2
        assert "CREATE TABLE os_checklist_veiculo" in queries[0]
        assert "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'os_checklist_veiculo')" in queries[0]
        assert "CREATE INDEX IX_os_checklist_veiculo_os ON os_checklist_veiculo(os)" in queries[1]

    def test_idempotente_no_registro_central(self):
        """Ver CLAUDE.md > 'Cada app precisa se auto-atualizar no banco' —
        toda migração nova precisa estar registrada em schema_ensure.py,
        não só existir como _ensure_* solto."""
        from services.schema_ensure import _MIGRACOES
        assert svc._ensure_os_checklist_veiculo_table in _MIGRACOES


class TestEnsureChecklistTable:
    """Tabela de CONCLUSÃO (`os_checklist`), distinta de
    `os_checklist_veiculo` (marcações) — ver docstring do módulo."""

    def test_cria_tabela_e_indice(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_os_checklist_table(Cur())
        assert len(queries) == 2
        assert "CREATE TABLE os_checklist (" in queries[0]
        assert "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'os_checklist')" in queries[0]
        assert "sem_avaria BIT NOT NULL DEFAULT 0" in queries[0]
        assert "CREATE INDEX IX_os_checklist_os ON os_checklist(os)" in queries[1]

    def test_idempotente_no_registro_central(self):
        from services.schema_ensure import _MIGRACOES
        assert svc._ensure_os_checklist_table in _MIGRACOES


class TestListChecklist:
    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._list_checklist_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_lista_vazia_sem_marcacao(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_checklist_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["items"] == []
        assert r["editavel"] is True

    def test_mapeia_marcacoes_corretamente(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "F"}],
            many=[[{
                "codigo": 1, "tipo_avaria": "ARRANHAO", "pos_x": 0.5, "pos_y": 0.6,
                "descricao": "Lateral direita",
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_checklist_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["editavel"] is False  # OS fechada, checklist só leitura
        item = r["items"][0]
        assert item["codigo"] == 1
        assert item["tipo_avaria"] == "ARRANHAO"
        assert item["pos_x"] == 0.5
        assert item["descricao"] == "Lateral direita"

    def test_sem_conclusao_ainda(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_checklist_sync("srv", "bd", 1)
        assert r["concluido"] is False
        assert r["sem_avaria"] is False
        assert r["concluido_por"] == ""

    def test_com_conclusao_sem_avaria(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"sem_avaria": True, "data": date(2026, 8, 26), "hora": "09:15", "usuario_nome": "JOAO"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_checklist_sync("srv", "bd", 1)
        assert r["concluido"] is True
        assert r["sem_avaria"] is True
        assert r["concluido_por"] == "JOAO"
        assert r["concluido_data"] == "2026-08-26"
        assert r["concluido_hora"] == "09:15"

    def test_com_conclusao_com_avaria(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A"}, {"sem_avaria": False, "data": date(2026, 8, 26), "hora": "10:00", "usuario_nome": "MARIA"}],
            many=[[{"codigo": 1, "tipo_avaria": "AMASSADO", "pos_x": 0.2, "pos_y": 0.3, "descricao": ""}]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_checklist_sync("srv", "bd", 1)
        assert r["concluido"] is True
        assert r["sem_avaria"] is False
        assert len(r["items"]) == 1


class TestAddItem:
    def test_tipo_avaria_invalido(self, monkeypatch):
        r = svc._add_item_sync(_req(tipo_avaria="RISCO"), 1)
        assert r["success"] is False
        assert "Tipo de avaria inválido" in r["message"]

    def test_posicao_fora_do_diagrama(self, monkeypatch):
        r = svc._add_item_sync(_req(pos_x=1.5), 1)
        assert r["success"] is False
        assert "fora do diagrama" in r["message"]

    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_req(), 1)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"]

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._add_item_sync(_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_grava_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"codigo": 77}], many=[[]])
        conn = _patch(monkeypatch, cur)
        r = svc._add_item_sync(_req(tipo_avaria="quebrado"), 1)
        assert r["success"] is True
        assert r["codigo"] == 77
        assert conn.committed is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_checklist_veiculo"))
        assert insert_p[0] == 1            # os
        assert insert_p[1] == "QUEBRADO"   # tipo_avaria normalizado maiúsculo
        assert insert_p[2] == 0.42         # pos_x
        assert insert_p[3] == 0.31         # pos_y


class TestCancelarItem:
    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_item_sync("srv", "bd", 1, 77)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"]

    def test_nao_encontrado_ou_ja_cancelado(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=0)
        _patch(monkeypatch, cur)
        r = svc._cancelar_item_sync("srv", "bd", 1, 77)
        assert r["success"] is False
        assert "já cancelada" in r["message"]

    def test_cancela_com_sucesso_soft_nao_deleta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_item_sync("srv", "bd", 1, 77)
        assert r["success"] is True
        assert conn.committed is True
        upd_q, upd_p = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE os_checklist_veiculo SET situacao='C'"))
        assert upd_p == (77, 1)
        assert not any(q.strip().startswith("DELETE FROM os_checklist_veiculo") for q, p in cur.queries)


def _concluir_req(**over):
    base = dict(servidor="srv", banco="bd", usuario_alteracao=-2, classe=1, plataforma="web")
    base.update(over)
    return FecharRequest(**base)


class TestConcluir:
    """Botão "Concluir Checklist" (`_concluir_sync`) — pedido explícito do
    usuário: "marcar o atendente que marcou sem avaria com os dados do
    veículo, atendente data e hora" + "acho que tem que ser criado uma
    tabela de OS_Checklist". `sem_avaria` é CALCULADO (não escolhido pelo
    usuário) a partir de `os_checklist_veiculo` no momento da conclusão."""

    def test_os_nao_aberta_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "F"}])
        _patch(monkeypatch, cur)
        r = svc._concluir_sync(_concluir_req(), 1)
        assert r["success"] is False
        assert "não pode ser alterada" in r["message"]

    def test_os_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._concluir_sync(_concluir_req(), 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_conclui_sem_avaria_quando_nao_ha_marcacao_ativa(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._concluir_sync(_concluir_req(usuario_alteracao=7), 1)
        assert r["success"] is True
        assert r["sem_avaria"] is True
        assert conn.committed is True
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_checklist"))
        assert insert_p[0] == 1   # os
        assert insert_p[1] == 1   # sem_avaria = True
        assert insert_p[2] == 7   # usuario

    def test_conclui_com_avaria_quando_ha_marcacao_ativa(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, {"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._concluir_sync(_concluir_req(), 1)
        assert r["success"] is True
        assert r["sem_avaria"] is False
        insert_q, insert_p = next((q, p) for q, p in cur.queries if q.strip().startswith("INSERT INTO os_checklist"))
        assert insert_p[1] == 0   # sem_avaria = False

    def test_idempotente_cancela_conclusao_anterior_antes_de_inserir(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}, None])
        _patch(monkeypatch, cur)
        r = svc._concluir_sync(_concluir_req(), 1)
        assert r["success"] is True
        idx_update = next(i for i, (q, p) in enumerate(cur.queries) if q.strip().startswith("UPDATE os_checklist SET situacao='C'"))
        idx_insert = next(i for i, (q, p) in enumerate(cur.queries) if q.strip().startswith("INSERT INTO os_checklist"))
        assert idx_update < idx_insert
        upd_q, upd_p = cur.queries[idx_update]
        assert upd_p == (1,)
