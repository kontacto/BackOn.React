"""Testes unitários de forma_pagamento_service.py — camada de CRUD por
trás do modal "Forma de Pagamento" (FrmForPag.frm). A validação de total
(Fecha_FPAG_Dav) tem seus próprios testes em
test_pedido_common_forma_pagamento.py; aqui cobrimos permissão, validação
de tipo/valor e o roteamento DI (manual) vs. DU (parcelada)."""
import services.forma_pagamento_service as svc
from models.schemas import FormaPagamentoAddRequest, FormaPagamentoUpdateRequest, FormaPagamentoDeleteRequest


class FakeCursor:
    def __init__(self, one=None, rowcount=1):
        self._one = list(one or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return []

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


def _add_req(**over):
    base = dict(
        servidor="srv", banco="bd", tipo_dav="PED", tipo="DI", forma_pag="001", valor=100.0,
        classe=1, master=True, usuario_alteracao=1, plataforma="web",
    )
    base.update(over)
    return FormaPagamentoAddRequest(**base)


class TestAddFormaPagamento:
    def test_lanca_dinheiro_com_sucesso(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(), 77)
        assert r["success"] is True
        assert conn.committed is True
        insert_q, params = cur.queries[-1]
        assert insert_q.startswith("INSERT INTO pedido_venda_dinheiro")
        assert params == (77, "001", 100.0)

    def test_tipo_invalido_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(tipo="XX"), 77)
        assert r["success"] is False
        assert "tipo" in r["message"].lower()

    def test_sem_forma_pag_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(forma_pag=""), 77)
        assert r["success"] is False

    def test_valor_zero_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(valor=0), 77)
        assert r["success"] is False
        assert "valor" in r["message"].lower()

    def test_duplicata_roteia_para_parcelamento(self, monkeypatch):
        """Tipo DU não usa o INSERT genérico — delega pra
        `_insere_duplicata_parcelada` (testada isoladamente em
        test_pedido_common_forma_pagamento.py)."""
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(tipo="DU", forma_pag="002"), 77)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.startswith("INSERT INTO pedido_venda_duplicata") for q, _ in cur.queries)

    def test_usa_tabela_os_quando_tipo_dav_os(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(tipo_dav="OS"), 9)
        assert r["success"] is True
        insert_q, params = cur.queries[-1]
        assert insert_q.startswith("INSERT INTO os_dinheiro")
        assert params == (9, "001", 100.0)

    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._add_forma_pagamento_sync(_add_req(master=False, classe=4), 77)
        assert r["success"] is False
        assert "permiss" in r["message"].lower()


class TestUpdateFormaPagamento:
    def test_atualiza_com_sucesso(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        req = FormaPagamentoUpdateRequest(
            servidor="srv", banco="bd", tipo_dav="PED", tipo="DI", forma_pag="001", valor=80.0,
            sequencia=5, classe=1, master=True, usuario_alteracao=1, plataforma="web",
        )
        r = svc._update_forma_pagamento_sync(req, 77)
        assert r["success"] is True
        assert conn.committed is True
        update_q, params = cur.queries[-1]
        assert update_q == "UPDATE pedido_venda_dinheiro SET forma_pag=%s,valor_pago=%s WHERE sequencia=%s"
        assert params == ("001", 80.0, 5)

    def test_nao_encontrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        req = FormaPagamentoUpdateRequest(
            servidor="srv", banco="bd", tipo_dav="PED", tipo="DI", forma_pag="001", valor=80.0,
            sequencia=999, classe=1, master=True, usuario_alteracao=1, plataforma="web",
        )
        r = svc._update_forma_pagamento_sync(req, 77)
        assert r["success"] is False
        assert conn.rolled is True


class TestDeleteFormaPagamento:
    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(rowcount=1)
        conn = _patch(monkeypatch, cur)
        req = FormaPagamentoDeleteRequest(
            servidor="srv", banco="bd", tipo_dav="PED", tipo="CH", sequencia=3,
            classe=1, master=True, usuario_alteracao=1, plataforma="web",
        )
        r = svc._delete_forma_pagamento_sync(req, 77)
        assert r["success"] is True
        assert conn.committed is True
        delete_q, params = cur.queries[-1]
        assert delete_q == "DELETE FROM pedido_venda_cheque WHERE sequencia=%s AND pedido_venda=%s"
        assert params == (3, 77)

    def test_nao_encontrado_bloqueia(self, monkeypatch):
        cur = FakeCursor(rowcount=0)
        conn = _patch(monkeypatch, cur)
        req = FormaPagamentoDeleteRequest(
            servidor="srv", banco="bd", tipo_dav="PED", tipo="CH", sequencia=999,
            classe=1, master=True, usuario_alteracao=1, plataforma="web",
        )
        r = svc._delete_forma_pagamento_sync(req, 77)
        assert r["success"] is False
        assert conn.rolled is True
