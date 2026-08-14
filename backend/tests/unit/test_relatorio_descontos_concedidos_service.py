"""Testes unitários de Descontos (Concedidos) — réplica de `FrmRelDes.frm`,
generalizado pra Pedido/OS. Cobre montagem de query por tipo, e a
agregação por documento (Pedido traz tipo/concedido_por via
descontos_concedidos; OS não tem essa auditoria nesta migração)."""
import services.relatorio_descontos_concedidos_service as svc


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class TestValidacao:
    def test_periodo_obrigatorio(self):
        r = svc._descontos_concedidos_sync("srv", "bd", "", "2026-08-07", None, None)
        assert r["success"] is False and "período" in r["message"].lower()

    def test_tipo_invalido(self):
        r = svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", "invalido", None)
        assert r["success"] is False and "inválido" in r["message"].lower()


class TestQuery:
    def test_padrao_cobre_pedido_e_os(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert r["success"] is True
        query, _ = cur.queries[-1]
        assert "pedido_venda_prod" in query and "os_produto" in query
        assert "descontos_concedidos" in query

    def test_tipo_pedido_nao_consulta_os(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", "pedido", None)
        query, _ = cur.queries[-1]
        assert "pedido_venda_prod" in query and "os_produto" not in query

    def test_tipo_os_nao_consulta_pedido(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", "os", None)
        query, _ = cur.queries[-1]
        assert "os_produto" in query and "pedido_venda_prod" not in query

    def test_filtro_cliente_aplicado_nome_e_fantasia(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, "acme")
        query, params = cur.queries[-1]
        assert "c.nome LIKE %s" in query and "c.fantasia LIKE %s" in query
        assert "%acme%" in params


class TestAgregacaoPorDocumento:
    def test_agrupa_itens_do_pedido_com_tipo_e_concedido_por(self, monkeypatch):
        cur = FakeCursor(rows=[
            {
                "doc_tipo": "PEDIDO", "doc_numero": 100, "doc_data": "2026-01-05",
                "cliente_nome": "Cliente A", "vendedor_nome": "Zé",
                "item_cod": 1, "item_descricao": "Produto X", "qtd": 2.0, "p_normal": 50.0,
                "desconto_unit": 5.0, "tipo_desconto": "I", "percentual": 10.0, "concedido_por": "Maria",
            },
            {
                "doc_tipo": "PEDIDO", "doc_numero": 100, "doc_data": "2026-01-05",
                "cliente_nome": "Cliente A", "vendedor_nome": "Zé",
                "item_cod": 2, "item_descricao": "Serviço Y", "qtd": 1.0, "p_normal": 200.0,
                "desconto_unit": 20.0, "tipo_desconto": "G", "percentual": 0.0, "concedido_por": "João",
            },
        ])
        _patch(monkeypatch, cur)
        r = svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert r["success"] is True
        assert len(r["documentos"]) == 1
        doc = r["documentos"][0]
        assert doc["tipo"] == "PEDIDO" and doc["numero"] == 100
        assert doc["cliente_nome"] == "Cliente A"
        assert len(doc["itens"]) == 2
        i1, i2 = doc["itens"]
        assert i1["valor_bruto"] == 100.0 and i1["valor_desconto"] == 10.0 and i1["valor_liquido"] == 90.0
        assert i1["tipo_desconto_label"] == "Item" and i1["concedido_por"] == "Maria"
        assert i2["tipo_desconto_label"] == "Geral" and i2["concedido_por"] == "João"
        assert i2["percentual"] == 10.0  # calculado (20/200*100), já que veio 0 do banco
        assert doc["total_bruto"] == 300.0 and doc["total_desconto"] == 30.0 and doc["total_liquido"] == 270.0
        assert r["totais"]["bruto"] == 300.0

    def test_item_os_sem_auditoria_fica_com_campos_none(self, monkeypatch):
        cur = FakeCursor(rows=[{
            "doc_tipo": "OS", "doc_numero": 55, "doc_data": "2026-01-10",
            "cliente_nome": "Cliente B", "vendedor_nome": "Ana",
            "item_cod": 1, "item_descricao": "Peça Z", "qtd": 1.0, "p_normal": 80.0,
            "desconto_unit": 8.0, "tipo_desconto": None, "percentual": None, "concedido_por": None,
        }])
        _patch(monkeypatch, cur)
        r = svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", "os", None)
        item = r["documentos"][0]["itens"][0]
        assert item["tipo_desconto_label"] is None
        assert item["concedido_por"] is None

    def test_documentos_diferentes_nao_se_misturam(self, monkeypatch):
        cur = FakeCursor(rows=[
            {"doc_tipo": "PEDIDO", "doc_numero": 1, "doc_data": "2026-01-01", "cliente_nome": "A", "vendedor_nome": "V",
             "item_cod": 1, "item_descricao": "X", "qtd": 1.0, "p_normal": 10.0, "desconto_unit": 1.0,
             "tipo_desconto": "I", "percentual": 10.0, "concedido_por": "F"},
            {"doc_tipo": "OS", "doc_numero": 1, "doc_data": "2026-01-01", "cliente_nome": "B", "vendedor_nome": "W",
             "item_cod": 1, "item_descricao": "Y", "qtd": 1.0, "p_normal": 20.0, "desconto_unit": 2.0,
             "tipo_desconto": None, "percentual": None, "concedido_por": None},
        ])
        _patch(monkeypatch, cur)
        r = svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert len(r["documentos"]) == 2  # mesmo número (1), tipos diferentes -> documentos distintos

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._descontos_concedidos_sync("srv", "bd", "2026-01-01", "2026-01-31", None, None)
        assert r["success"] is True
        assert r["documentos"] == []
        assert r["totais"]["desconto_pct"] == 0.0
