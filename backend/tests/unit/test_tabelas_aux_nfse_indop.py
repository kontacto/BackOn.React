"""Testes de `NFSE_INDOP` (Indicador de Operação, leiaute IBS/CBS art. 11) —
tabela criada por esta migração, 2026-08-06, pedido explícito do usuário
("nome da tabela: NFSE_INDOP" + "ainda não existe, crie e popule"). Escopo
enxuto (só as funções novas) — `tabelas_aux_service.py` inteiro (~5000
linhas) não tem suíte de testes própria ainda."""
import services.tabelas_aux_service as svc


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

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _patch(monkeypatch, cur):
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestSeedNfseIndop:
    def test_seed_tem_26_codigos_unicos_e_sem_campo_vazio(self):
        assert len(svc._NFSE_INDOP_SEED) == 26
        codigos = [c for c, _, _ in svc._NFSE_INDOP_SEED]
        assert len(set(codigos)) == 26
        for codigo, descricao, local in svc._NFSE_INDOP_SEED:
            assert codigo and descricao and local


class TestListNfseIndop:
    def test_cria_e_popula_quando_tabela_vazia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"c": 0}],
            many=[[{"codigo": "020101", "descricao": "x", "local_fornecimento": "y"}]],
        )
        conn = _patch(monkeypatch, cur)
        result = svc._list_nfse_indop_sync("srv", "bd")
        assert result["success"] is True
        assert conn.committed is True
        assert any(q[0].startswith("IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'NFSE_INDOP')") for q in cur.queries)
        insert_qs = [q for q, _ in cur.queries if q.startswith("INSERT INTO NFSE_INDOP")]
        assert len(insert_qs) == 26

    def test_nao_repopula_quando_ja_tem_dados(self, monkeypatch):
        cur = FakeCursor(
            one=[{"c": 26}],
            many=[[{"codigo": "020101", "descricao": "x", "local_fornecimento": "y"}]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_nfse_indop_sync("srv", "bd")
        assert result["success"] is True
        assert not any(q.startswith("INSERT INTO NFSE_INDOP") for q, _ in cur.queries)

    def test_retorna_itens_com_local_fornecimento(self, monkeypatch):
        cur = FakeCursor(
            one=[{"c": 26}],
            many=[[{"codigo": "030101", "descricao": "Serviço prestado fisicamente sobre a pessoa",
                    "local_fornecimento": "Estabelecimento do fornecedor"}]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_nfse_indop_sync("srv", "bd")
        assert result["items"][0]["codigo"] == "030101"
        assert result["items"][0]["local_fornecimento"] == "Estabelecimento do fornecedor"
