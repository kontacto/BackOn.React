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
    # Toda lista `one=[...]` ganhou um `None` a mais na frente — achado
    # real da reauditoria 2026-08-21 (`Valida_Data`, `FrmManRec.frm:9162-
    # 9174`): nova checagem de fechamento de Livro/Contabilidade consome
    # a 1ª posição da fila antes do restante da função rodar. `None`
    # aqui = "sem data de fechamento configurada" (não bloqueia).

    def test_tipo_mov_nao_cadastrado(self, monkeypatch):
        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, DADOS_MIN)
        assert r["success"] is False and "Movimentação não cadastrado" in r["message"]

    def test_duplicidade_bloqueia_nova_nota(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": "S01"}, {"codigo": 77}])
        _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, DADOS_MIN)
        assert r["success"] is False and "Já existe uma Nota Fiscal" in r["message"]

    def test_cria_nova_nota_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": "S01"}, None, {"codigo": 42}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, DADOS_MIN)
        assert r["success"] is True and r["codigo"] == 42
        assert conn.committed is True
        assert any("INSERT INTO n_fiscal" in q for q, _ in cur.queries)

    def test_edita_nota_existente_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": "S01"}, None, {"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", 10, DADOS_MIN)
        assert r["success"] is True and r["codigo"] == 10
        assert conn.committed is True
        assert any("UPDATE n_fiscal" in q for q, _ in cur.queries)

    def test_bloqueia_edicao_de_nota_cancelada(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": "S01"}, None, {"situacao": "C"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", 10, DADOS_MIN)
        assert r["success"] is False and "canceladas" in r["message"]
        assert conn.committed is False

    def test_bloqueia_data_anterior_ao_fechamento_do_livro(self, monkeypatch):
        cur = FakeCursor(one=[{"data_fecha_livro": "2026-07-31", "data_fecha_cont": None}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, {**DADOS_MIN, "data_mov": "2026-07-13"})
        assert r["success"] is False
        assert "fechamento" in r["message"].lower()
        assert conn.committed is False

    def test_bloqueia_data_anterior_ao_fechamento_contabil(self, monkeypatch):
        cur = FakeCursor(one=[{"data_fecha_livro": None, "data_fecha_cont": "2026-07-31"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_cabecalho_sync("srv", "bd", None, {**DADOS_MIN, "data_mov": "2026-07-13"})
        assert r["success"] is False
        assert "fechamento" in r["message"].lower()
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

    def test_cancela_reverte_baixa_de_pedido_de_compra(self, monkeypatch):
        """Achado real da reauditoria 2026-08-21 (`FrmManRec.frm:5461-
        5474`, "'refaz pedidos de compra"): cancelar uma NF que veio de
        um Recebimento com baixa de Pedido de Compra reverte
        `qtd_recebida`, reabre o pedido, e — se `controle_aux.
        baixa_pedido_compra` estiver ligado — apaga o vínculo de
        rastreio (`nf_recebimento_pedido`)."""
        cur = FakeCursor(
            one=[
                {"situacao": "A", "mov": "S01"},
                {"baixa_pedido_compra": True},
            ],
            many=[
                [],  # consignacao vazia
                [],  # movimentacao vazia
                [{"pedido": 900, "item": "P001", "quant": 3.0, "recebimento": 55}],  # baixas
            ],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert conn.committed is True
        upd_item = next((q, p) for q, p in cur.queries if q.startswith("UPDATE pedido_itens"))
        assert upd_item[1] == (3.0, 900, "P001")
        upd_pedido = next((q, p) for q, p in cur.queries if q.startswith("UPDATE pedido SET situacao"))
        assert upd_pedido[1] == (900,)
        assert any(q.startswith("DELETE nfrp FROM nf_recebimento_pedido") for q, _ in cur.queries)

    def test_cancela_sem_baixa_de_pedido_nao_mexe_em_pedido(self, monkeypatch):
        cur = FakeCursor(
            one=[{"situacao": "A", "mov": "S01"}],
            many=[[], [], []],  # consignacao, movimentacao, baixas (nenhuma)
        )
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_sync("srv", "bd", 10)
        assert r["success"] is True
        assert conn.committed is True
        assert not any(q.startswith("UPDATE pedido_itens") for q, _ in cur.queries)


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


class TestGetDanfeSync:
    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_danfe_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_sem_xml_bloqueia_com_mensagem_clara(self, monkeypatch):
        cur = FakeCursor(one=[{"xml": None, "protocolo_sefaz": None, "chave_acesso": None, "dhRecbto": None, "situacao": "D"}])
        _patch(monkeypatch, cur)
        r = svc._get_danfe_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "ainda não foi emitida" in r["message"].lower()

    def test_xml_invalido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"xml": "<not-xml", "protocolo_sefaz": "123", "chave_acesso": "3" * 44, "dhRecbto": None, "situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._get_danfe_sync("srv", "bd", 1)
        assert r["success"] is False
        assert "não foi possível ler" in r["message"].lower()

    def test_sucesso_colunas_do_cabecalho_sobrepoe_o_xml(self, monkeypatch):
        # O XML assinado nunca é reescrito com o protocolo pós-autorização
        # (mesmo princípio de parse_nfce_xml_para_exibicao) — as colunas de
        # n_fiscal são sempre a fonte de verdade sobre protocolo/chave/
        # situação, mesmo que o parser devolva algo diferente.
        monkeypatch.setattr(
            svc.nfe_emissao_service, "parse_nfe_xml_para_exibicao",
            lambda xml: {"chave_acesso": "0" * 44, "protocolo_sefaz": None, "valor_total": 20.0},
        )
        cur = FakeCursor(one=[
            {"xml": "<NFe/>", "protocolo_sefaz": "135000000000001", "chave_acesso": "3" * 44,
             "dhRecbto": "2026-08-20T10:00:00", "situacao": "A"},
            {"modelo_danfe": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._get_danfe_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["detalhe"]["protocolo_sefaz"] == "135000000000001"
        assert r["detalhe"]["chave_acesso"] == "3" * 44
        assert r["detalhe"]["situacao"] == "A"
        assert r["modelo_danfe"] == 1

    def test_sem_controle_aux_nao_quebra(self, monkeypatch):
        monkeypatch.setattr(
            svc.nfe_emissao_service, "parse_nfe_xml_para_exibicao",
            lambda xml: {"chave_acesso": "3" * 44, "valor_total": 20.0},
        )
        cur = FakeCursor(one=[
            {"xml": "<NFe/>", "protocolo_sefaz": "1", "chave_acesso": "3" * 44, "dhRecbto": None, "situacao": "A"},
            None,
        ])
        _patch(monkeypatch, cur)
        r = svc._get_danfe_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["modelo_danfe"] is None


class TestCartaCorrecaoSync:
    """Carta de Correção Eletrônica (CC-e) — `_carta_correcao_sync`.
    `nfe_correcao_service.emitir_carta_correcao_sync` (a peça que fala com
    o SEFAZ de verdade) é sempre mockada aqui — ver
    `test_nfe_correcao_service.py` pra cobertura da emissão em si."""

    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._carta_correcao_sync("srv", "bd", 1, "Motivo válido com bastante texto", "user")
        assert r["success"] is False
        assert "não encontrada" in r["message"].lower()

    def test_sem_protocolo_sefaz_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"protocolo_sefaz": "", "chave_acesso": "1" * 44}])
        _patch(monkeypatch, cur)
        r = svc._carta_correcao_sync("srv", "bd", 1, "Motivo válido com bastante texto", "user")
        assert r["success"] is False
        assert "protocolo" in r["message"].lower()

    def test_situacao_nfe_zero_nao_bloqueia_mais_com_protocolo_real(self, monkeypatch):
        # Achado ao vivo 2026-08-23: `situacao_nfe` nunca é gravado pelos
        # 3 caminhos de emissão modernos (nfe_agrupada_service.py/
        # nfe_avulsa_service.py/comanda_service.py) — ficava sempre no
        # DEFAULT 0 do schema mesmo com a nota genuinamente autorizada,
        # bloqueando incondicionalmente. `protocolo_sefaz` (o sinal real
        # de autorização nesta migração) é o único gate que resta.
        cur = FakeCursor(one=[
            {"situacao_nfe": 0, "protocolo_sefaz": "135000000000001", "chave_acesso": "1" * 44},
            {"qtd": 0},
            {"cgc": "12345678000199", "uf": "RJ"},
        ])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "2")
        monkeypatch.setattr(
            svc.nfe_correcao_service, "emitir_carta_correcao_sync",
            lambda cur, **kw: {
                "success": True, "message": "ok", "protocolo": "135260000012345", "cstat": "135",
                "xmotivo": "Evento registrado e vinculado a NF-e",
                "data_hora_registro": "2026-08-22T10:00:00-03:00", "xml_evento": "<evento/>",
            },
        )
        r = svc._carta_correcao_sync("srv", "bd", 1, "Motivo válido com bastante texto", "user")
        assert r["success"] is True
        assert conn.committed is True

    def test_ja_atingiu_20_cartas_bloqueia_a_21a(self, monkeypatch):
        cur = FakeCursor(one=[
            {"protocolo_sefaz": "135000000000001", "chave_acesso": "1" * 44},
            {"qtd": 20},
        ])
        _patch(monkeypatch, cur)
        r = svc._carta_correcao_sync("srv", "bd", 1, "Motivo válido com bastante texto", "user")
        assert r["success"] is False
        assert "20" in r["message"]

    def test_sucesso_grava_linha_e_faz_commit(self, monkeypatch):
        cur = FakeCursor(one=[
            {"protocolo_sefaz": "135000000000001", "chave_acesso": "1" * 44},
            {"qtd": 0},
            {"cgc": "12345678000199", "uf": "RJ"},
        ])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "2",
        )
        monkeypatch.setattr(
            svc.nfe_correcao_service, "emitir_carta_correcao_sync",
            lambda cur, **kw: {
                "success": True, "message": "Carta de Correção autorizada pelo SEFAZ — protocolo 135260000012345.",
                "protocolo": "135260000012345", "cstat": "135", "xmotivo": "Evento registrado e vinculado a NF-e",
                "data_hora_registro": "2026-08-22T10:00:00-03:00", "xml_evento": "<evento/>",
            },
        )
        r = svc._carta_correcao_sync("srv", "bd", 1, "Motivo válido com bastante texto", "user")
        assert r["success"] is True
        assert r["n_seq_evento"] == 1
        assert r["protocolo"] == "135260000012345"
        assert conn.committed is True
        insert_q = next(q for q, _ in cur.queries if "INSERT INTO n_fiscal_carta_correcao" in q)
        assert insert_q  # confere que o INSERT realmente foi emitido

    def test_falha_do_sefaz_nao_grava_linha(self, monkeypatch):
        cur = FakeCursor(one=[
            {"protocolo_sefaz": "135000000000001", "chave_acesso": "1" * 44},
            {"qtd": 0},
            {"cgc": "12345678000199", "uf": "RJ"},
        ])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "2")
        monkeypatch.setattr(
            svc.nfe_correcao_service, "emitir_carta_correcao_sync",
            lambda cur, **kw: {"success": False, "message": "SEFAZ recusou a Carta de Correção (status 573): Duplicidade."},
        )
        r = svc._carta_correcao_sync("srv", "bd", 1, "Motivo válido com bastante texto", "user")
        assert r["success"] is False
        assert not any("INSERT INTO n_fiscal_carta_correcao" in q for q, _ in cur.queries)
        assert conn.committed is False


class TestListCartasCorrecaoSync:
    def test_lista_cartas_ja_emitidas(self, monkeypatch):
        cartas = [
            {"codigo": 1, "n_seq_evento": 1, "motivo": "Motivo 1", "protocolo": "135000000000001",
             "cstat": "135", "xmotivo": "ok", "data_registro": "2026-08-22T10:00:00", "criado_em": "2026-08-22T10:00:00"},
        ]
        cur = FakeCursor(many=[cartas])
        _patch(monkeypatch, cur)
        r = svc._list_cartas_correcao_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["cartas"] == cartas
