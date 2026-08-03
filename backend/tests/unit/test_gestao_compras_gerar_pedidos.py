"""Testes UNITÁRIOS de "Gerar Pedido de Compra" a partir da seleção na tela
de Ressuprimento (`gestao_compras_service.gerar_pedidos_ressuprimento`) —
reaproveita `pedido_compra_service.gravar_cabecalho`/`incluir_item` (não
duplica a lógica de criação de Pedido de Compra), só orquestra o
agrupamento por fornecedor preferencial e o custo sugerido."""
import asyncio

import services.gestao_compras_service as svc
from models.pedido_compra import GerarPedidosRessuprimentoItem, GerarPedidosRessuprimentoRequest


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

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _req(**over):
    base = dict(
        servidor="srv", banco="bd",
        itens=[GerarPedidosRessuprimentoItem(codigo_int="P001", qtd=10)],
        usuario_alteracao=1, classe=1, plataforma="web",
    )
    base.update(over)
    return GerarPedidosRessuprimentoRequest(**base)


MODULO_ON = {"Curva_abc": 1}
MODULO_OFF = {"Curva_abc": 0}


class TestResolverFornecedoresECustos:
    def test_mapeia_custo_e_fornecedor_preferencial(self):
        cur = FakeCursor(
            many=[[{"codigo_int": "P001", "custo_reposicao": 12.5}]],
            one=[{"fornecedor": 7}],
        )
        fornecedores, custos = svc._resolver_fornecedores_e_custos_sync(cur, ["P001"])
        assert fornecedores == {"P001": 7}
        assert custos == {"P001": 12.5}

    def test_produto_sem_fornecedor_fica_de_fora_do_dict(self):
        cur = FakeCursor(many=[[{"codigo_int": "P002", "custo_reposicao": 5.0}]], one=[None])
        fornecedores, custos = svc._resolver_fornecedores_e_custos_sync(cur, ["P002"])
        assert fornecedores == {}
        assert custos == {"P002": 5.0}

    def test_lista_vazia_retorna_vazio_sem_querys(self):
        cur = FakeCursor()
        fornecedores, custos = svc._resolver_fornecedores_e_custos_sync(cur, [])
        assert fornecedores == {} and custos == {}
        assert cur.queries == []


class TestGerarPedidosRessuprimento:
    def test_sem_itens_validos_bloqueia(self):
        r = asyncio.run(svc.gerar_pedidos_ressuprimento(_req(itens=[])))
        assert r["success"] is False

    def test_qtd_zero_ou_negativa_e_filtrada(self):
        r = asyncio.run(svc.gerar_pedidos_ressuprimento(
            _req(itens=[GerarPedidosRessuprimentoItem(codigo_int="P001", qtd=0)])
        ))
        assert r["success"] is False

    def test_modulo_desativado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        _patch(monkeypatch, cur)
        r = asyncio.run(svc.gerar_pedidos_ressuprimento(_req()))
        assert r["success"] is False
        assert "desativado" in r["message"].lower()

    def test_agrupa_por_fornecedor_e_chama_funcoes_compartilhadas(self, monkeypatch):
        # 2 produtos do MESMO fornecedor (7) -> 1 pedido, 2 itens.
        cur = FakeCursor(
            one=[MODULO_ON, {"fornecedor": 7}, {"fornecedor": 7}],
            many=[[
                {"codigo_int": "P001", "custo_reposicao": 10.0},
                {"codigo_int": "P002", "custo_reposicao": 20.0},
            ]],
        )
        _patch(monkeypatch, cur)

        chamadas_cabecalho = []
        chamadas_item = []

        async def fake_gravar_cabecalho(servidor, banco, codigo, data, fornecedor, *resto):
            chamadas_cabecalho.append((fornecedor, data))
            return {"success": True, "codigo": 555}

        async def fake_incluir_item(servidor, banco, codigo_pedido, produto, qtd, p_unit, extras):
            chamadas_item.append((codigo_pedido, produto, qtd, p_unit))
            return {"success": True, "seq": 1}

        monkeypatch.setattr(svc.pedido_compra_service, "gravar_cabecalho", fake_gravar_cabecalho)
        monkeypatch.setattr(svc.pedido_compra_service, "incluir_item", fake_incluir_item)

        req = _req(itens=[
            GerarPedidosRessuprimentoItem(codigo_int="P001", qtd=10),
            GerarPedidosRessuprimentoItem(codigo_int="P002", qtd=5),
        ])
        r = asyncio.run(svc.gerar_pedidos_ressuprimento(req))

        assert r["success"] is True
        assert len(chamadas_cabecalho) == 1  # 1 fornecedor -> 1 pedido só
        assert chamadas_cabecalho[0][0] == 7
        assert len(chamadas_item) == 2
        assert (555, "P001", 10, 10.0) in chamadas_item
        assert (555, "P002", 5, 20.0) in chamadas_item
        assert r["pedidos_criados"] == [{"codigo": 555, "fornecedor": 7, "itens": 2, "itens_total": 2}]
        assert r["sem_fornecedor"] == []

    def test_produto_sem_fornecedor_reportado_e_nao_gera_pedido(self, monkeypatch):
        cur = FakeCursor(
            one=[MODULO_ON, None],
            many=[[{"codigo_int": "P003", "custo_reposicao": 1.0}]],
        )
        _patch(monkeypatch, cur)

        async def fake_gravar_cabecalho(*a, **k):
            raise AssertionError("não deveria criar pedido sem fornecedor resolvido")

        monkeypatch.setattr(svc.pedido_compra_service, "gravar_cabecalho", fake_gravar_cabecalho)

        req = _req(itens=[GerarPedidosRessuprimentoItem(codigo_int="P003", qtd=3)])
        r = asyncio.run(svc.gerar_pedidos_ressuprimento(req))

        assert r["success"] is True
        assert r["pedidos_criados"] == []
        assert r["sem_fornecedor"] == ["P003"]
