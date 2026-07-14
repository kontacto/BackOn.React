"""Testes UNITÁRIOS de Notas Fiscais (Fase 1 — CRUD sem emissão fiscal).

Mesmo padrão de test_telemarketing_service.py / test_equipamentos_service.py:
cursor/conexão falsos (monkeypatch em _open_conn), sem banco real.
"""
import services.notas_fiscais_service as svc


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


DADOS_MIN = {
    "num_nf": 100, "serie_nf": "1", "fornecedor": 5, "mov": "S01",
    "data_nf": "2026-07-13",
}


class TestSaveCabecalhoValidacoes:
    def test_fornecedor_obrigatorio(self):
        r = svc._save_cabecalho_sync("srv", "bd", None, {**DADOS_MIN, "fornecedor": None})
        assert r["success"] is False and "Cliente/Fornecedor" in r["message"]

    def test_mov_obrigatorio(self):
        r = svc._save_cabecalho_sync("srv", "bd", None, {**DADOS_MIN, "mov": None})
        assert r["success"] is False and "Movimentação" in r["message"]

    def test_num_nf_obrigatorio(self):
        r = svc._save_cabecalho_sync("srv", "bd", None, {**DADOS_MIN, "num_nf": None})
        assert r["success"] is False and "Número da NF" in r["message"]

    def test_data_nf_obrigatoria(self):
        r = svc._save_cabecalho_sync("srv", "bd", None, {**DADOS_MIN, "data_nf": None})
        assert r["success"] is False and "Data de Emissão" in r["message"]


class TestSaveCabecalhoComMock:
    def test_tipo_mov_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, DADOS_MIN)
        assert r["success"] is False and "Movimentação não cadastrado" in r["message"]

    def test_duplicidade_bloqueia_nova_nota(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": "S01"}, {"codigo": 77}])
        _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, DADOS_MIN)
        assert r["success"] is False and "Já existe uma Nota Fiscal" in r["message"]

    def test_cria_nova_nota_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": "S01"}, None, {"codigo": 42}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, DADOS_MIN)
        assert r["success"] is True and r["codigo"] == 42
        assert conn.committed is True
        assert any("INSERT INTO n_fiscal" in q for q, _ in cur.queries)

    def test_edita_nota_existente_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": "S01"}, None, {"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", 10, DADOS_MIN)
        assert r["success"] is True and r["codigo"] == 10
        assert conn.committed is True
        assert any("UPDATE n_fiscal" in q for q, _ in cur.queries)

    def test_bloqueia_edicao_de_nota_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": "S01"}, None, {"situacao": "C"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", 10, DADOS_MIN)
        assert r["success"] is False and "canceladas" in r["message"]
        assert conn.committed is False


class TestSaveItens:
    def test_item_sem_codigo_int(self):
        r = svc._save_itens_sync("srv", "bd", 10, [{"codigo_int": "", "qtd": 1}])
        assert r["success"] is False and "Código de Produto" in r["message"]

    def test_item_sem_qtd(self):
        r = svc._save_itens_sync("srv", "bd", 10, [{"codigo_int": "P001", "qtd": 0}])
        assert r["success"] is False and "Quantidade" in r["message"]

    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._save_itens_sync("srv", "bd", 999, [{"codigo_int": "P001", "qtd": 1}])
        assert r["success"] is False and "não encontrada" in r["message"]

    def test_grava_itens_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 10}])
        conn = _patch(monkeypatch, cur)
        itens = [{"codigo_int": "P001", "qtd": 2, "p_unit": 10.0, "valor_total": 20.0}]
        r = svc._save_itens_sync("srv", "bd", 10, itens)
        assert r["success"] is True
        assert conn.committed is True
        assert any("DELETE FROM n_fiscal_itens" in q for q, _ in cur.queries)
        assert any("INSERT INTO n_fiscal_itens" in q for q, _ in cur.queries)


class TestSaveVencimentos:
    def test_venc_sem_data_ou_valor(self):
        r = svc._save_vencimentos_sync("srv", "bd", 10, [{"data_venc": "", "valor": 100}])
        assert r["success"] is False

    def test_grava_com_sucesso(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._save_vencimentos_sync("srv", "bd", 10, [{"data_venc": "2026-08-01", "valor": 100.0}])
        assert r["success"] is True
        assert conn.committed is True
        assert any("DELETE FROM nf_vencimento" in q for q, _ in cur.queries)
        assert any("INSERT INTO nf_vencimento" in q for q, _ in cur.queries)


class TestCriticar:
    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._criticar_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_valores_conferem_marca_ativa(self, monkeypatch):
        cur = FakeCursor(one=[{"valor_total": 100.0}, {"soma": 100.0}])
        conn = _patch(monkeypatch, cur)
        r = svc._criticar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert r["situacao"] == "A"
        assert r["divergencias"] == []
        assert conn.committed is True

    def test_valores_divergem_marca_erro(self, monkeypatch):
        cur = FakeCursor(one=[{"valor_total": 100.0}, {"soma": 80.0}])
        _patch(monkeypatch, cur)
        r = svc._criticar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert r["situacao"] == "E"
        assert len(r["divergencias"]) == 1


class TestCancelar:
    def test_ja_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C", "mov": "S01"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is False and "já foi cancelada" in r["message"]

    def test_consignacao_com_devolucao_bloqueia(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A", "mov": "S07"}],
            many=[[{"qtd_devolvida": 3, "qtd_faturada": 0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is False and "consignação" in r["message"]

    def test_cancela_com_sucesso_estorna_estoque(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A", "mov": "S01"}],
            many=[
                [],  # consignacao vazia
                [{"codigo_int": "P001", "qtd": 5, "tipo": "SAIDA"}],  # movimentacao
            ],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert conn.committed is True
        # Saída -> estorna somando de volta ao estoque
        upd = next(q for q, p in cur.queries if "UPDATE pecas" in q)
        assert "qtd + %s" in upd
        assert any("DELETE FROM movimentacao" in q for q, _ in cur.queries)
        assert any("DELETE FROM comanda_nf" in q for q, _ in cur.queries)
        assert any("situacao='C'" in q for q, _ in cur.queries)


class TestExcluir:
    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_bloqueia_se_nao_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 10)
        assert r["success"] is False and "cancelamento" in r["message"]

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "C"}])
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 10)
        assert r["success"] is True
        assert conn.committed is True
        assert any("DELETE FROM n_fiscal WHERE" in q for q, _ in cur.queries)


class TestListConsulta:
    def test_filtros_basicos_aplicados(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_consulta_sync("srv", "bd", {
            "num_nf": 100, "situacao": "A", "entrada": True, "saida": False,
        })
        assert r["success"] is True
        query, params = cur.queries[-1]
        assert "nf.num_nf=%s" in query
        assert "nf.situacao='A'" in query
        assert "LEFT(nf.mov,1)='E'" in query
        assert 100 in params

    def test_codigo_da_nf_filtra_exato(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_consulta_sync("srv", "bd", {"codigo": 5296})
        query, params = cur.queries[-1]
        assert "nf.codigo=%s" in query
        assert 5296 in params

    def test_termo_pessoa_restringe_por_origem_destino(self, monkeypatch):
        # Mesma regra do FrmConNF.frm real: o filtro de Cliente/Fornecedor
        # só é aplicado junto com a restrição tipo_mov.origem_destino, pra
        # não colidir cliente.codigo com fornecedor.codigo_int.
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_consulta_sync("srv", "bd", {
            "cliente_fornecedor_termo": "Fulano", "tipo_pessoa": "F",
        })
        query, params = cur.queries[-1]
        assert "tm.origem_destino=%s" in query
        assert "F" in params

    def test_uf_e_vencimento_nao_sao_filtros_reais(self, monkeypatch):
        # UF e faixa de Vencimento foram removidos por não existirem no
        # .frm real (FrmConNF.frm) — passar esses campos não deve gerar
        # erro nem afetar a query.
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._list_consulta_sync("srv", "bd", {"uf": "RJ", "vencimento_de": "2026-01-01"})
        assert r["success"] is True
        query, _ = cur.queries[-1]
        assert "nf.uf=%s" not in query


class TestBuscarProduto:
    def test_encontra_em_pecas(self, monkeypatch):
        cur = FakeCursor(one=[{"descricao": "Parafuso", "cod_fiscal": "1102"}])
        _patch(monkeypatch, cur)
        r = svc._buscar_produto_sync("srv", "bd", "P001")
        assert r["success"] is True and r["found"] is True
        assert r["descricao"] == "Parafuso"

    def test_nao_encontrado_em_nenhuma_tabela(self, monkeypatch):
        cur = FakeCursor(one=[None, None, None])
        _patch(monkeypatch, cur)
        r = svc._buscar_produto_sync("srv", "bd", "XXXX")
        assert r["success"] is True and r["found"] is False
