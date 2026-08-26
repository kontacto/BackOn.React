"""Testes de `ncm_cest_service.py` — Cadastro/Consulta de NCM e CEST.

Cobre as 2 correções conscientes em relação a `Geral\\FrmCesNCM.frm`:
(1) duplicata de vínculo checada pelo PAR ncm+cest (não só ncm — a real
`NCM_CEST_PRIMARIA` é um índice único composto, confirmado ao vivo contra
ARGEN TESTE); (2) "vínculo não encontrado" real no delete (o legado tem
uma checagem `RecordCount < 0` que nunca dispara — bug morto)."""
import services.ncm_cest_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
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


def _patch(monkeypatch, cur):
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


# ---------------- NCM ----------------

class TestListNcmSync:
    def test_busca_vazia_nao_consulta_banco(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._list_ncm_sync("s", "b", "")
        assert r["success"] is True
        assert r["items"] == []
        assert cur.queries == []

    def test_busca_retorna_itens(self, monkeypatch):
        cur = FakeCursor(many=[[{"ncm": "84713012", "descricao": "Máquinas automáticas..."}]])
        _patch(monkeypatch, cur)
        r = svc._list_ncm_sync("s", "b", "8471")
        assert r["success"] is True
        assert len(r["items"]) == 1


class TestSaveNcmSync:
    def test_ncm_vazio_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_ncm_sync("s", "b", "  ", "Descrição")
        assert r["success"] is False

    def test_descricao_vazia_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_ncm_sync("s", "b", "84713012", "  ")
        assert r["success"] is False

    def test_insere_quando_nao_existe(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_sync("s", "b", "84713012", "Descrição real")
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO ncm" in q for q, _ in cur.queries)

    def test_atualiza_quando_ja_existe(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_sync("s", "b", "84713012", "Nova descrição")
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.startswith("UPDATE ncm") for q, _ in cur.queries)


class TestDeleteNcmSync:
    def test_nao_encontrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_ncm_sync("s", "b", "00000000")
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_bloqueia_com_cest_vinculado(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"n": 3}])
        _patch(monkeypatch, cur)
        r = svc._delete_ncm_sync("s", "b", "84713012")
        assert r["success"] is False
        assert "3 cest" in r["message"].lower()

    def test_exclui_quando_sem_vinculo(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}, {"n": 0}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_ncm_sync("s", "b", "84713012")
        assert r["success"] is True
        assert conn.committed is True


# ---------------- CEST ----------------

class TestSaveNcmCestSync:
    def test_cest_vazio_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "84713012", "  ", "desc")
        assert r["success"] is False

    def test_ncm_nao_numerico_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "ABCD", "2806100", "desc")
        assert r["success"] is False
        assert cur.queries == []

    def test_ncm_com_mais_de_8_digitos_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "123456789", "2806100", "desc")
        assert r["success"] is False
        assert cur.queries == []

    def test_ncm_prefixo_parcial_e_aceito_sem_existir_em_ncm(self, monkeypatch):
        # Achado real: 508/1281 linhas de ncm_cest usam prefixo (2-7
        # dígitos, capítulo/posição/subposição) — nunca deve exigir que
        # esse prefixo exista como linha própria na tabela `ncm`.
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "42", "2806000", "Outros artigos de vestuário")
        assert r["success"] is True
        assert conn.committed is True

    def test_insere_novo_vinculo(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "84713012", "2806100", "desc")
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO ncm_cest" in q for q, _ in cur.queries)

    def test_atualiza_vinculo_existente_pelo_par(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "84713012", "2806100", "nova desc")
        assert r["success"] is True
        assert conn.committed is True
        # a checagem/gravação do vínculo sempre usa o PAR (ncm E cest), nunca só ncm
        vinculo_queries = [(q, p) for q, p in cur.queries if "ncm_cest" in q]
        assert any(p == ("84713012", "2806100") for _, p in vinculo_queries if p)

    def test_cest_sem_ncm_permitido(self, monkeypatch):
        # sem NCM informado: não valida existência de NCM, só checa vínculo (não existe)
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "", "2806100", "CEST genérico")
        assert r["success"] is True
        assert conn.committed is True

    def test_mesmo_cest_em_ncm_diferentes_nao_e_duplicata(self, monkeypatch):
        # Real: NCM_CEST_PRIMARIA é único por (ncm, cest) — o mesmo CEST em
        # outro NCM não deve ser bloqueado como duplicata.
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_ncm_cest_sync("s", "b", "84713099", "2806100", "desc")
        assert r["success"] is True
        assert conn.committed is True


class TestDeleteNcmCestSync:
    def test_nao_encontrado_bloqueia_com_mensagem_real(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_ncm_cest_sync("s", "b", "84713012", "9999999")
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_exclui_vinculo_existente(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_ncm_cest_sync("s", "b", "84713012", "2806100")
        assert r["success"] is True
        assert conn.committed is True


class TestSearchCestSync:
    def test_busca_vazia_nao_consulta_banco(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._search_cest_sync("s", "b", "")
        assert r["success"] is True
        assert r["items"] == []
        assert cur.queries == []

    def test_busca_retorna_itens_incluindo_sem_ncm(self, monkeypatch):
        cur = FakeCursor(many=[[
            {"ncm": "", "cest": "0199900", "descricao": "Outras peças..."},
            {"ncm": "0201", "cest": "1708400", "descricao": "Carne..."},
        ]])
        _patch(monkeypatch, cur)
        r = svc._search_cest_sync("s", "b", "0199900")
        assert r["success"] is True
        assert len(r["items"]) == 2
