"""Testes UNITÁRIOS de `_aplicar_desconto_geral_sync` (Desconto Geral sobre
o total do pedido) — em especial a exclusão de itens com
`pecas.aceita_desconto=False` do rateio, adicionada 2026-07-30 (mesma
proteção que já bloqueia desconto de item avulso nesse produto). Ver
PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado"."""
import services.descontos_service as svc
from models.schemas import DescontoGeralRequest


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


def _patch(monkeypatch, cursor, limites=None):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    # `_get_limites_sync` abre a PRÓPRIA conexão (servidor/banco), separada
    # do cursor `cur` — sempre mockado aqui pra não bater no banco de verdade.
    monkeypatch.setattr(svc, "_get_limites_sync", lambda *a, **k: limites or {})
    return conn


def _req(**over):
    base = dict(servidor="srv", banco="bd", valor=0, usuario_codigo=-2, funcao=1, classe=1, plataforma="web")
    base.update(over)
    return DescontoGeralRequest(**base)


class TestAplicarDescontoGeral:
    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._aplicar_desconto_geral_sync(_req(valor=10), 1)
        assert r["success"] is False and "sem itens" in r["message"].lower()

    def test_distribui_proporcional_entre_todos_quando_todos_aceitam(self, monkeypatch):
        itens = [
            {"codauto": 1, "p_normal": 60.0, "acrescimo": 0, "qtd_pedida": 1, "aceita_desconto": 1},
            {"codauto": 2, "p_normal": 40.0, "acrescimo": 0, "qtd_pedida": 1, "aceita_desconto": 1},
        ]
        cur = FakeCursor(one=[{"situacao": "A"}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._aplicar_desconto_geral_sync(_req(valor=20), 1)
        assert r["success"] is True
        updates = {p[2]: p for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod")}
        # base=100, item1 pesa 60% -> desconto 12; item2 pesa 40% -> desconto 8
        assert updates[1][0] == 12.0 and updates[2][0] == 8.0

    def test_item_sem_aceita_desconto_fica_de_fora_do_rateio(self, monkeypatch):
        """Item marcado `aceita_desconto=False` (ex.: produto com preço
        fixo/tabelado) não recebe nada do desconto geral, e o valor total
        pedido é rateado só entre quem aceita."""
        itens = [
            {"codauto": 1, "p_normal": 100.0, "acrescimo": 0, "qtd_pedida": 1, "aceita_desconto": 1},
            {"codauto": 2, "p_normal": 100.0, "acrescimo": 0, "qtd_pedida": 1, "aceita_desconto": 0},
        ]
        cur = FakeCursor(one=[{"situacao": "A"}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._aplicar_desconto_geral_sync(_req(valor=20), 1)
        assert r["success"] is True
        updates = {p[2]: p for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod")}
        # base considera só o item 1 (100) -> desconto inteiro (20) cai nele
        assert updates[1][0] == 20.0
        assert updates[2][0] == 0.0  # item 2 não participa

    def test_aceita_desconto_null_trata_como_aceita(self, monkeypatch):
        """Serviço (sem correspondência em `pecas`, LEFT JOIN -> NULL) ou
        peça sem o campo definido conta como aceitando — mesmo default já
        usado em `_linha_peca_completo`/inclusão de item."""
        itens = [{"codauto": 1, "p_normal": 50.0, "acrescimo": 0, "qtd_pedida": 1, "aceita_desconto": None}]
        cur = FakeCursor(one=[{"situacao": "A"}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._aplicar_desconto_geral_sync(_req(valor=10), 1)
        assert r["success"] is True
        update = next(p for q, p in cur.queries if q.strip().startswith("UPDATE pedido_venda_prod"))
        assert update[0] == 10.0

    def test_todos_recusam_desconto_bloqueia(self, monkeypatch):
        itens = [{"codauto": 1, "p_normal": 100.0, "acrescimo": 0, "qtd_pedida": 1, "aceita_desconto": 0}]
        cur = FakeCursor(one=[{"situacao": "A"}], many=[itens])
        _patch(monkeypatch, cur)
        r = svc._aplicar_desconto_geral_sync(_req(valor=10), 1)
        assert r["success"] is False and "sem valor" in r["message"].lower()
