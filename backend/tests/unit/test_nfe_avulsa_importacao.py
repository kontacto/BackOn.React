"""Testes das 6 sub-rotinas de importação automática de `nfe_avulsa_
service.py` ("Gerar NFe" — NF-e Avulsa) — ver PENDENCIAS.md > "6
sub-rotinas de importação automática" pro racional completo.

Todas as 6 funções são READ-ONLY (nunca escrevem em `nf_aux`) — os
testes cobrem só a resolução de dados: mapeamento de campos, resolução
de CFOP/tipo_mov por UF (Devolução/Requisição), FCP 2% (Complementar),
resolução de `tipo_pessoa` (Nota Fiscal), e os bloqueios de "documento
não encontrado"/"sem itens".

**Devolução não é testada aqui** — `_importar_devolucao_sync` mudou de
assinatura 2026-08-24 (aceita uma LISTA de `id_devolucao`, não mais 1;
achado real: `Command14_Click`/`FrmManDev.frm` sempre importa um array
`VetDevolucao`, consolidando 1+ devoluções do MESMO cliente numa única
NF-e). Cobertura completa (lista vazia, ids não encontrados, clientes
diferentes bloqueando, consolidação multi-devolução, sem config de UF)
está em `TestImportarDevolucaoSync`, `test_nfe_avulsa_service.py`."""
import services.nfe_avulsa_service as svc


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


_PRODUTO_ROW = {"descricao": "Produto Teste", "ncm": "", "unidade": "UN", "cod_icms": "0", "origem": 0}


class TestImportarPedido:
    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._importar_pedido_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não encontrado" in r["message"].lower()

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cliente": 5, "tipo": 0}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._importar_pedido_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não tem itens" in r["message"].lower()

    def test_sucesso_mapeia_tipo_5_pra_s09(self, monkeypatch):
        cur = FakeCursor(
            one=[{"cliente": 5, "tipo": 5}, _PRODUTO_ROW],
            many=[[{"produto": "P1", "qtd_pedida": 2.0, "p_venda": 10.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_pedido_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["header"] == {"fornecedor": 5, "tipo_pessoa": "C", "mov": "S09"}
        assert r["itens"][0]["codigo_int"] == "P1"
        assert r["itens"][0]["valor_total"] == 20.0

    def test_tipo_desconhecido_cai_pro_s01(self, monkeypatch):
        cur = FakeCursor(
            one=[{"cliente": 5, "tipo": 99}, _PRODUTO_ROW],
            many=[[{"produto": "P1", "qtd_pedida": 1.0, "p_venda": 1.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_pedido_sync("srv", "bd", 1)
        assert r["header"]["mov"] == "S01"


class TestImportarCompra:
    def test_pedido_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._importar_compra_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"fornecedor": 3}, {"desconto": 0}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._importar_compra_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não tem itens" in r["message"].lower()

    def test_sucesso_aplica_desconto_uniforme_do_fornecedor(self, monkeypatch):
        cur = FakeCursor(
            one=[{"fornecedor": 3}, {"desconto": 10.0}, _PRODUTO_ROW],
            many=[[{"codigo_int": "P2", "qtd": 5.0, "p_unit": 20.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_compra_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["header"] == {"fornecedor": 3, "tipo_pessoa": "F"}
        item = r["itens"][0]
        assert item["desconto_perc"] == 10.0
        assert item["desconto"] == 10.0
        assert item["valor_total"] == 90.0

    def test_sem_desconto_cadastrado_nao_aplica_nada(self, monkeypatch):
        cur = FakeCursor(
            one=[{"fornecedor": 3}, {"desconto": 0}, _PRODUTO_ROW],
            many=[[{"codigo_int": "P2", "qtd": 1.0, "p_unit": 50.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_compra_sync("srv", "bd", 1)
        item = r["itens"][0]
        assert item["desconto"] == 0
        assert item["valor_total"] == 50.0


class TestImportarRequisicao:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._importar_requisicao_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._importar_requisicao_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não tem itens" in r["message"].lower()

    def test_sucesso_sem_cabecalho_resolvido(self, monkeypatch):
        # Sem FK de cliente/fornecedor confirmada em `requisicao` — só os
        # itens vêm, cabeçalho fica vazio pro usuário completar.
        cur = FakeCursor(
            one=[{"codigo": 1}, _PRODUTO_ROW],
            many=[[{"prod": "P3", "qtd": 4.0, "p_unit": 2.5}]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_requisicao_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["header"] == {}
        assert r["itens"][0]["codigo_int"] == "P3"
        assert r["itens"][0]["valor_total"] == 10.0


class TestImportarNotaFiscal:
    def test_nota_de_origem_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._importar_nota_fiscal_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_sem_itens_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"fornecedor": 9, "mov": "E01", "cfop": "1102", "uf": "RJ"}, {"origem_destino": "F"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_nota_fiscal_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não tem itens" in r["message"].lower()

    def test_sucesso_copia_campos_e_resolve_tipo_pessoa_fornecedor(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"fornecedor": 9, "mov": "E01", "cfop": "1102", "uf": "RJ"},
                {"origem_destino": "F"},
                _PRODUTO_ROW,
            ],
            many=[[{
                "codigo_int": "P4", "cod_fiscal": None, "tributacao": None, "qtd": 3.0, "p_unit": 15.0,
                "desconto": 0, "valor_total": 45.0, "alqt_icms": 18.0, "reducao_base_icms": 0,
                "base_icms": 45.0, "valor_icms": 8.1, "base_ipi": 0, "alqt_ipi": 0, "valor_ipi": 0,
                "base_sub": 0, "valor_sub": 0, "base_iss": 0, "valor_iss": 0, "frete": 0, "seguro": 0, "despesas": 0,
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_nota_fiscal_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["header"] == {"fornecedor": 9, "tipo_pessoa": "F", "mov": "E01", "cfop": "1102"}
        assert r["itens"][0]["valor_icms"] == 8.1
        assert r["itens"][0]["descricao"] == "Produto Teste"

    def test_tipo_pessoa_cliente_quando_origem_destino_nao_e_f(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"fornecedor": 20, "mov": "S01", "cfop": "5102", "uf": "RJ"},
                {"origem_destino": "C"},
                _PRODUTO_ROW,
            ],
            many=[[{
                "codigo_int": "P5", "cod_fiscal": None, "tributacao": None, "qtd": 1.0, "p_unit": 1.0,
                "desconto": 0, "valor_total": 1.0, "alqt_icms": 0, "reducao_base_icms": 0,
                "base_icms": 0, "valor_icms": 0, "base_ipi": 0, "alqt_ipi": 0, "valor_ipi": 0,
                "base_sub": 0, "valor_sub": 0, "base_iss": 0, "valor_iss": 0, "frete": 0, "seguro": 0, "despesas": 0,
            }]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_nota_fiscal_sync("srv", "bd", 1)
        assert r["header"]["tipo_pessoa"] == "C"


class TestImportarComplementar:
    def test_comanda_sem_cliente_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._importar_complementar_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_sem_itens_cod_icms_6_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"cliente": 4}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._importar_complementar_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "icms código 6" in r["message"].lower()

    def test_sucesso_calcula_fcp_2_porcento_hardcoded(self, monkeypatch):
        # 2% confirmado hardcoded na fonte real (frmtranfe.frm:8999,
        # `precoFCP * 2 / 100`) — não é config, ver docstring da função.
        cur = FakeCursor(
            one=[{"cliente": 4}, _PRODUTO_ROW],
            many=[[{"produto": "P5", "qtd": 3.0, "p_unit": 2.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_complementar_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["header"]["fornecedor"] == 4
        assert r["header"]["tipo_pessoa"] == "C"
        assert r["header"]["mov"] == "S50"
        assert r["header"]["cfop"] == "5102"
        assert r["header"]["BASE_FCP"] == 6.0
        assert r["header"]["VALOR_FCP"] == 0.12
        item = r["itens"][0]
        assert item["qtd"] == 0
        assert item["p_unit"] == 0
        assert item["valor_total"] == 0

    def test_soma_multiplos_itens_na_base_fcp(self, monkeypatch):
        cur = FakeCursor(
            one=[{"cliente": 4}, _PRODUTO_ROW, _PRODUTO_ROW],
            many=[[
                {"produto": "P5", "qtd": 2.0, "p_unit": 2.0},
                {"produto": "P6", "qtd": 1.0, "p_unit": 10.0},
            ]],
        )
        _patch(monkeypatch, cur)
        r = svc._importar_complementar_sync("srv", "bd", 1)
        assert r["header"]["BASE_FCP"] == 14.0
        assert r["header"]["VALOR_FCP"] == 0.28
