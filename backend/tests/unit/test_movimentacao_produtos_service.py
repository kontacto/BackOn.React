"""Testes UNITÁRIOS de Movimentação de Produtos (Transações > Movimentações)."""
from datetime import date

import services.movimentacao_produtos_service as svc


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


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _dados(**over):
    base = dict(data="2026-07-10", tipo="E01", codigo_int="P001", qtd=5, p_unit=10.0, num_nf=None)
    base.update(over)
    return base


class TestFindProduto:
    def test_termo_vazio_nao_bate_no_banco(self, monkeypatch):
        conn = _patch(monkeypatch, FakeCursor())
        r = svc._find_produto_sync("srv", "bd", "  ")
        assert r == {"success": True, "found": False}
        assert conn._c.queries == []

    def test_encontra_por_codigo_int(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo_int": "P001", "descricao": "Parafuso", "p_custo": 2.5, "qtd": 100.0}])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "P001")
        assert r["success"] and r["found"]
        assert r["descricao"] == "Parafuso"
        assert r["p_custo"] == 2.5

    def test_fallback_por_codigo_fab(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo_int": "P002", "descricao": "Porca", "p_custo": 1.0, "qtd": 5.0}])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "FAB-9")
        assert r["found"] and r["codigo_int"] == "P002"

    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)
        r = svc._find_produto_sync("srv", "bd", "XXX")
        assert r["success"] and not r["found"]


class TestIncluirValidacoesSemBanco:
    def test_sem_data(self):
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(data=""))
        assert not r["success"] and "data" in r["message"].lower()

    def test_sem_tipo(self):
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(tipo=""))
        assert not r["success"] and "tipo" in r["message"].lower()

    def test_sem_produto(self):
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(codigo_int=""))
        assert not r["success"] and "produto" in r["message"].lower()

    def test_qtd_invalida(self):
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(qtd=0))
        assert not r["success"] and "quantidade" in r["message"].lower()

    def test_preco_negativo(self):
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(p_unit=-1))
        assert not r["success"] and "preço" in r["message"].lower()


class TestIncluirComBanco:
    def test_data_maior_que_data_sistema_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"data_movimento": date(2026, 7, 1)}])
        _patch(monkeypatch, cur)
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(data="2026-07-10"))
        assert not r["success"] and "data" in r["message"].lower()

    def test_tipo_inexistente_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados())
        assert not r["success"] and "tipo" in r["message"].lower()

    def test_produto_nao_cadastrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None, {"ok": 1}, None])
        _patch(monkeypatch, cur)
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados())
        assert not r["success"] and "produto" in r["message"].lower()

    def test_entrada_soma_estoque_e_grava_data_ultima_compra(self, monkeypatch):
        cur = FakeCursor(one=[None, {"ok": 1}, {"qtd": 10.0}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(tipo="E01", qtd=5))
        assert r["success"] and r["estoque"] == 15.0
        assert conn.committed
        insert_q = cur.queries[-2][0].lower()
        update_q = cur.queries[-1][0]
        assert "insert into movimentacao" in insert_q
        assert "data_ultima_compra" in update_q

    def test_saida_subtrai_estoque_e_grava_data_ultima_venda(self, monkeypatch):
        cur = FakeCursor(one=[None, {"ok": 1}, {"qtd": 10.0}])
        conn = _patch(monkeypatch, cur)
        r = svc._incluir_movimentacao_sync("srv", "bd", _dados(tipo="S01", qtd=4))
        assert r["success"] and r["estoque"] == 6.0
        assert conn.committed
        update_q = cur.queries[-1][0]
        assert "data_ultima_venda" in update_q


class TestExcluirMovimentacao:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_movimentacao_sync("srv", "bd", 999)
        assert not r["success"]

    def test_excluir_entrada_subtrai_de_volta(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": "E01", "codigo_int": "P001", "qtd": 5.0}, {"qtd": 20.0}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_movimentacao_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        update_q, update_p = cur.queries[-2]
        assert "update pecas" in update_q.lower()
        assert update_p[0] == 15.0

    def test_excluir_saida_soma_de_volta(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": "S01", "codigo_int": "P001", "qtd": 5.0}, {"qtd": 20.0}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_movimentacao_sync("srv", "bd", 1)
        assert r["success"] and conn.committed
        update_q, update_p = cur.queries[-2]
        assert "update pecas" in update_q.lower()
        assert update_p[0] == 25.0

    def test_delete_so_atinge_serie_nf_mv(self, monkeypatch):
        cur = FakeCursor(one=[{"tipo": "E01", "codigo_int": "P001", "qtd": 5.0}, {"qtd": 20.0}])
        _patch(monkeypatch, cur)
        svc._excluir_movimentacao_sync("srv", "bd", 1)
        delete_q = cur.queries[-1][0]
        assert "serie_nf='mv'" in delete_q.lower()
