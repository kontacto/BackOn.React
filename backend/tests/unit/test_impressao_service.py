"""Testes unitários da fila de impressão (polling do agente local — ver
services/impressao_service.py e print-agent/agente_impressao.py)."""
import services.impressao_service as svc


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


class TestEnfileirar:
    def test_ok(self, monkeypatch):
        cur = FakeCursor(one=[{"id": 7}])
        conn = _patch(monkeypatch, cur)
        r = svc._enfileirar_sync("SRV", "BANCO", "PC-CAIXA1", "Epson TM-T20", "conteudo do cupom")
        assert r["success"] is True
        assert r["id"] == 7
        assert conn.committed is True
        insert_q = cur.queries[-1][0]
        assert "INSERT INTO impressao_fila" in insert_q

    def test_bloqueia_computador_vazio(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._enfileirar_sync("SRV", "BANCO", "  ", None, "conteudo")
        assert r["success"] is False
        assert "computador" in r["message"].lower()

    def test_bloqueia_conteudo_vazio(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._enfileirar_sync("SRV", "BANCO", "PC-CAIXA1", None, "")
        assert r["success"] is False
        assert "conteúdo" in r["message"].lower() or "conteudo" in r["message"].lower()

    def test_impressora_opcional(self, monkeypatch):
        cur = FakeCursor(one=[{"id": 1}])
        _patch(monkeypatch, cur)
        r = svc._enfileirar_sync("SRV", "BANCO", "PC-CAIXA1", None, "conteudo")
        assert r["success"] is True
        params = cur.queries[-1][1]
        assert params[1] is None


class TestListPendentes:
    def test_retorna_itens_e_marca_enviado(self, monkeypatch):
        itens = [
            {"id": 1, "impressora": "Epson", "tipo": "TEXTO", "conteudo": "cupom 1"},
            {"id": 2, "impressora": None, "tipo": "TEXTO", "conteudo": "cupom 2"},
        ]
        cur = FakeCursor(many=[itens])
        conn = _patch(monkeypatch, cur)
        r = svc._list_pendentes_sync("SRV", "BANCO", "PC-CAIXA1")
        assert r["success"] is True
        assert len(r["items"]) == 2
        assert conn.committed is True
        update_q = cur.queries[-1][0]
        assert "UPDATE impressao_fila SET status='ENVIADO'" in update_q
        assert cur.queries[-1][1] == (1, 2)

    def test_sem_itens_nao_executa_update(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_pendentes_sync("SRV", "BANCO", "PC-CAIXA1")
        assert r["success"] is True
        assert r["items"] == []
        assert not any("UPDATE impressao_fila" in q for q, _ in cur.queries)

    def test_bloqueia_computador_vazio(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._list_pendentes_sync("SRV", "BANCO", "")
        assert r["success"] is False
        assert r["items"] == []

    def test_query_inclui_recuperacao_de_enviado_travado(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_pendentes_sync("SRV", "BANCO", "PC-CAIXA1")
        select_q, params = cur.queries[-1]
        assert "status='ENVIADO'" in select_q
        assert svc.RECUPERACAO_ENVIADO_MINUTOS in params


class TestConfirmar:
    def test_sucesso_marca_impresso(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        r = svc._confirmar_sync("SRV", "BANCO", 7, True)
        assert r["success"] is True
        assert conn.committed is True
        update_q, params = cur.queries[-1]
        assert "status=%s" in update_q
        assert params[0] == "IMPRESSO"

    def test_falha_marca_erro_com_mensagem(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        _patch(monkeypatch, cur)
        r = svc._confirmar_sync("SRV", "BANCO", 7, False, "Impressora offline")
        assert r["success"] is True
        params = cur.queries[-1][1]
        assert params[0] == "ERRO"
        assert params[1] == "Impressora offline"

    def test_job_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        r = svc._confirmar_sync("SRV", "BANCO", 999, True)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()
        assert conn.rolled is True
