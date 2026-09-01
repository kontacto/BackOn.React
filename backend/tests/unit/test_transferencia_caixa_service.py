"""Testes unitários de Transferência p/Fluxo de Caixa (migração de
`Geral\\FrmTransfCaixa.frm` — ver services/transferencia_caixa_service.py
pro rastreio completo da fonte, inclusive o que ficou de fora na Fase 1)."""
import services.transferencia_caixa_service as svc


class FakeCursor:
    """Fila de resultados na ordem de chamada — mesmo padrão já usado em
    test_transferencia_contas_service.py."""
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


CONTROLE_ROW = {
    "conta_transf_caixa": 5, "data_fecha_cx": "2026-08-01",
    "sai_tarifa_cl": 1, "sai_tarifa_sc": 1, "sai_juros_cl": 2, "sai_juros_sc": 2,
    "sai_desc_cl": 3, "sai_desc_sc": 3, "ent_tarifa_cl": 4, "ent_tarifa_sc": 4,
    "ent_juros_cl": 6, "ent_juros_sc": 6, "ent_desc_cl": 7, "ent_desc_sc": 7,
}


class TestSplitProporcional:
    def test_uma_linha_aplica_valor_total(self):
        rateio = [{"custo": 1, "porcusto": 100.0, "realdup": 100.0}]
        r = svc._split_proporcional(rateio, 250.0)
        assert r == [(1, None, None, 250.0)]

    def test_duas_linhas_corrige_arredondamento_na_ultima(self):
        rateio = [
            {"custo": 1, "porcusto": 33.33, "realdup": 100.0},
            {"custo": 2, "porcusto": 66.67, "realdup": 100.0},
        ]
        r = svc._split_proporcional(rateio, 10.0)
        total = round(sum(v for *_x, v in r), 2)
        assert total == 10.0

    def test_sem_linhas_retorna_vazio(self):
        assert svc._split_proporcional([], 100.0) == []


class TestUpsertFavorecido:
    def test_encontrado_atualiza_conta_contabil(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 9}])
        _patch(monkeypatch, cur)
        codigo = svc._upsert_favorecido_sync(cur, "CLIENTE X", 50)
        assert codigo == 9
        assert "UPDATE favorecidos" in cur.queries[-1][0]

    def test_nao_encontrado_cria_novo(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 20}])
        _patch(monkeypatch, cur)
        codigo = svc._upsert_favorecido_sync(cur, "CLIENTE NOVO", 0)
        assert codigo == 20
        assert "INSERT INTO favorecidos" in cur.queries[-1][0]


class TestListarPendentesSync:
    def test_sem_conta_transf_caixa_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{**CONTROLE_ROW, "conta_transf_caixa": 0}])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd", {"prev_receber": True})
        assert r["success"] is False
        assert "Conta de Transferência" in r["message"]

    def test_nenhum_checkbox_marcado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[CONTROLE_ROW])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd", {})
        assert r["success"] is False
        assert "Defina o que vai ser transferido" in r["message"]

    def test_periodo_sem_datas_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[CONTROLE_ROW])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd", {"periodo": True, "prev_receber": True})
        assert r["success"] is False
        assert "período" in r["message"].lower()

    def test_todos_aberto_movimentacao_usa_data_fecha_cx(self, monkeypatch):
        # 1º `[]` consumido por `_get_config_agrupamento_sync`
        # (`agrupa_comandas_fp`) — Fase 2 desativada nesta instalação de
        # teste (`agrupa_comandas` sem linha, ver CONTROLE_ROW).
        cur = FakeCursor(one=[CONTROLE_ROW], many=[[], []])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd", {"mov_receber": True})
        assert r["success"] is True
        query = cur.queries[-1][0]
        assert "data_pag >" in query
        assert "2026-08-01" in query

    def test_todos_aberto_previsao_nao_filtra_data(self, monkeypatch):
        cur = FakeCursor(one=[CONTROLE_ROW], many=[[], []])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd", {"prev_receber": True})
        assert r["success"] is True
        query = cur.queries[-1][0]
        assert "BETWEEN" not in query
        assert "data_pag" not in query

    def test_monta_itens_das_partes_marcadas(self, monkeypatch):
        cur = FakeCursor(
            one=[CONTROLE_ROW],
            many=[[], [{"seq": 10, "nome": "CLIENTE A", "num_controle": 100, "data_doc": None, "valor_total": 50.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd", {"entrada_caixa": True})
        assert r["success"] is True
        assert len(r["items"]) == 1
        assert r["agrupamento_ativo"] is False
        assert r["agrupadas"] == []
        assert r["items"][0]["flag"] == "EntradaCaixa"
        assert r["items"][0]["codigo"] == 10


CAB_RECEBER = {
    "dup_codigo": 100, "cliente": 1, "cliente_nome": "CLIENTE A", "conta_cliente": None,
    "classe_cliente": None, "subclasse_cliente": None, "conta_contabil_cliente": 0,
    "conta_venc": None, "realdup": 500.0, "valor_pag": 500.0, "num_parcelas": 1, "parcela": 1,
    "dt_emissao": "2026-08-01", "dt_vencimento": "2026-08-10", "data_pag": "2026-08-09",
    "obs_vencimento": "", "descontos": 0.0, "juros": 0.0, "tarifa_banco": 0.0,
}
LINHA_RECEBER = {"custo": 1, "porcusto": 500.0, "classe_rateio": 10, "sub_classe_rateio": 10}


class TestTransferirPrevisaoReceber:
    def test_ja_transferida_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"transf_previsao": "T"}])
        _patch(monkeypatch, cur)
        r = svc._transferir_previsao_receber_sync(cur, {}, 1)
        assert r["success"] is False
        assert "já foi transferida" in r["message"]

    def test_sucesso_grava_previsao_sem_mexer_saldo(self, monkeypatch):
        cur = FakeCursor(
            one=[{"transf_previsao": None}, CAB_RECEBER, {"codigo": 7}, {"codigo": 900}],
            many=[[LINHA_RECEBER]],
        )
        _patch(monkeypatch, cur)
        flags = {"conta_transf_caixa": 5}
        r = svc._transferir_previsao_receber_sync(cur, flags, 1)
        assert r["success"] is True
        queries = " ".join(q for q, _p in cur.queries)
        assert "INSERT INTO previsoes " in queries
        assert "INSERT INTO previsoes_centro_custo" in queries
        assert "UPDATE contas SET saldo_atual" not in queries
        assert "UPDATE duplicata_rec_venc SET transf_previsao = 'T'" in queries


class TestTransferirMovReceber:
    def test_ja_transferido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 55}])
        _patch(monkeypatch, cur)
        r = svc._transferir_mov_receber_sync(cur, {}, 1)
        assert r["success"] is False
        assert "já foi transferido" in r["message"]

    def test_sucesso_atualiza_saldo_da_conta(self, monkeypatch):
        cur = FakeCursor(
            one=[None, CAB_RECEBER, {"codigo": 7}, {"codigo": 900}],
            many=[[LINHA_RECEBER]],
        )
        _patch(monkeypatch, cur)
        flags = {
            "conta_transf_caixa": 5, "sai_juros": (2, 2), "sai_desconto": (3, 3), "sai_tarifa": (1, 1),
            "ent_juros": (6, 6), "ent_desconto": (7, 7),
        }
        r = svc._transferir_mov_receber_sync(cur, flags, 1)
        assert r["success"] is True
        update_saldo = [q for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        assert len(update_saldo) == 1
        assert "UPDATE duplicata_rec_venc SET transf_caixa = 'T'" in " ".join(q for q, _p in cur.queries)

    def test_juros_desconto_tarifa_ajustam_movimentacoes_centro_custo(self, monkeypatch):
        cab = {**CAB_RECEBER, "juros": 10.0, "descontos": 5.0, "tarifa_banco": 2.0}
        cur = FakeCursor(
            one=[None, cab, {"codigo": 7}, {"codigo": 900}],
            many=[[LINHA_RECEBER]],
        )
        _patch(monkeypatch, cur)
        flags = {
            "conta_transf_caixa": 5, "sai_juros": (2, 2), "sai_desconto": (3, 3), "sai_tarifa": (1, 1),
            "ent_juros": (6, 6), "ent_desconto": (7, 7),
        }
        r = svc._transferir_mov_receber_sync(cur, flags, 1)
        assert r["success"] is True
        cc_inserts = [p for q, p in cur.queries if q.startswith("INSERT INTO movimentacoes_centro_custo")]
        # juros + desconto + tarifa + rateio principal = 4 inserts
        assert len(cc_inserts) == 4


CAB_PAGAR = {
    "dup_codigo": 200, "fornecedor": 1, "fornecedor_nome": "FORNECEDOR A", "conta_fornecedor": None,
    "classe_fornecedor": None, "subclasse_fornecedor": None, "conta_contabil_fornecedor": 0,
    "conta_venc": None, "realdup": 300.0, "valor_pag": 300.0, "num_parcelas": 1, "parcela": 1,
    "dt_emissao": "2026-08-01", "dt_vencimento": "2026-08-10", "data_pag": "2026-08-09",
    "obs_vencimento": "", "descontos": 0.0, "juros": 0.0, "tarifa_banco": 0.0,
}
LINHA_PAGAR = {"custo": 1, "porcusto": 300.0, "classe_rateio": 20, "sub_classe_rateio": 20}


class TestTransferirMovPagar:
    def test_sucesso_diminui_saldo_da_conta(self, monkeypatch):
        cur = FakeCursor(
            one=[None, CAB_PAGAR, {"codigo": 8}, {"codigo": 901}],
            many=[[LINHA_PAGAR]],
        )
        _patch(monkeypatch, cur)
        flags = {
            "conta_transf_caixa": 5, "sai_juros": (2, 2), "sai_desconto": (3, 3), "sai_tarifa": (1, 1),
            "ent_juros": (6, 6), "ent_desconto": (7, 7),
        }
        r = svc._transferir_mov_pagar_sync(cur, flags, 1)
        assert r["success"] is True
        update_saldo = [q for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        assert len(update_saldo) == 1
        assert "UPDATE duplicata_pag_venc SET transf_caixa = 'T'" in " ".join(q for q, _p in cur.queries)


ENTRADA_ROW = {
    "codigo": 1, "data": "2026-08-10", "atendente": 1, "valor": 100.0, "descricao": "Aporte",
    "transf_caixa": None, "centro_custo": 1, "classe": 0, "sub_classe": 0, "favorecido": 9, "conta": 5,
}
SAIDA_ROW = {
    "codigo": 1, "data": "2026-08-10", "atendente": 1, "valor": 50.0, "descricao": "Retirada",
    "transf_caixa": None, "centro_custo": 1, "classe": 0, "sub_classe": 0, "favorecido": 9, "conta": 5,
    "transferencia": "0",
}


class TestTransferirEntradaSaidaCaixa:
    def test_entrada_ja_transferida_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{**ENTRADA_ROW, "transf_caixa": "T"}])
        _patch(monkeypatch, cur)
        r = svc._transferir_entrada_caixa_sync(cur, {"conta_transf_caixa": 5}, 1)
        assert r["success"] is False

    def test_entrada_sucesso_soma_saldo(self, monkeypatch):
        cur = FakeCursor(one=[ENTRADA_ROW, {"nome_guerra": "JOAO"}, {"codigo": 700}])
        _patch(monkeypatch, cur)
        r = svc._transferir_entrada_caixa_sync(cur, {"conta_transf_caixa": 5}, 1)
        assert r["success"] is True
        assert any(q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +") for q, p in cur.queries)
        assert any(q.startswith("UPDATE entrada_caixa SET cod_movimentacao") for q, p in cur.queries)

    def test_saida_sucesso_subtrai_saldo(self, monkeypatch):
        cur = FakeCursor(one=[SAIDA_ROW, {"nome_guerra": "JOAO"}, {"codigo": 701}])
        _patch(monkeypatch, cur)
        r = svc._transferir_saida_caixa_sync(cur, {"conta_transf_caixa": 5}, 1)
        assert r["success"] is True
        assert any(q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -") for q, p in cur.queries)

    def test_saida_transferencia_dupla_credita_conta_destino(self, monkeypatch):
        row = {**SAIDA_ROW, "transferencia": "2", "classe": 8}
        cur = FakeCursor(one=[row, {"nome_guerra": "JOAO"}, {"codigo": 702}])
        _patch(monkeypatch, cur)
        r = svc._transferir_saida_caixa_sync(cur, {"conta_transf_caixa": 5}, 1)
        assert r["success"] is True
        soma = [q for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +") and p[1] == 8]
        assert len(soma) == 1


class TestTransferirSync:
    def test_sem_conta_transf_caixa_bloqueia_tudo(self, monkeypatch):
        cur = FakeCursor(one=[{**CONTROLE_ROW, "conta_transf_caixa": 0}])
        _patch(monkeypatch, cur)
        r = svc._transferir_sync("srv", "bd", [{"codigo": 1, "flag": "EntradaCaixa"}])
        assert r["success"] is False

    def test_flag_desconhecida_vira_falha_isolada(self, monkeypatch):
        cur = FakeCursor(one=[CONTROLE_ROW])
        conn = _patch(monkeypatch, cur)
        r = svc._transferir_sync("srv", "bd", [{"codigo": 1, "flag": "XYZ"}])
        assert r["success"] is False
        assert r["falhas"][0]["message"].startswith("Tipo desconhecido")
        assert conn.committed is True

    def test_erro_em_um_item_nao_derruba_os_outros(self, monkeypatch):
        cur = FakeCursor(one=[CONTROLE_ROW])
        _patch(monkeypatch, cur)

        def _explode(cur_, flags_, codigo_):
            raise RuntimeError("boom")

        monkeypatch.setitem(svc._DISPATCH, "EntradaCaixa", _explode)
        r = svc._transferir_sync("srv", "bd", [
            {"codigo": 1, "flag": "EntradaCaixa"},
            {"codigo": 2, "flag": "XYZ"},
        ])
        assert r["success"] is False
        assert len(r["falhas"]) == 2


class TestTemPendencia:
    def test_conta_registros_pendentes(self, monkeypatch):
        cur = FakeCursor(one=[{"pendentes": 4}])
        _patch(monkeypatch, cur)
        r = svc._tem_pendencia_sync("srv", "bd")
        assert r["success"] is True
        assert r["pendentes"] == 4


# =============================================================================
# Fase 2 — Agrupamento de Comandas
# =============================================================================

CONFIG_ROW = {"clientes_diversos": True, "sem_documento": True, "cpf": True, "cnpj": True}


class TestGetConfigAgrupamento:
    def test_sem_linha_configurada_inativo(self, monkeypatch):
        cur = FakeCursor(one=[None], many=[[]])
        _patch(monkeypatch, cur)
        cfg = svc._get_config_agrupamento_sync(cur)
        assert cfg["ativo"] is False

    def test_sem_forma_marcada_inativo(self, monkeypatch):
        cur = FakeCursor(one=[CONFIG_ROW], many=[[]])
        _patch(monkeypatch, cur)
        cfg = svc._get_config_agrupamento_sync(cur)
        assert cfg["ativo"] is False

    def test_sem_nenhum_checkbox_de_cliente_inativo(self, monkeypatch):
        row = {"clientes_diversos": False, "sem_documento": False, "cpf": False, "cnpj": False}
        cur = FakeCursor(one=[row], many=[[{"codigo": "1"}]])
        _patch(monkeypatch, cur)
        cfg = svc._get_config_agrupamento_sync(cur)
        assert cfg["ativo"] is False

    def test_com_linha_e_forma_ativo(self, monkeypatch):
        cur = FakeCursor(one=[CONFIG_ROW], many=[[{"codigo": "1"}, {"codigo": "2"}]])
        _patch(monkeypatch, cur)
        cfg = svc._get_config_agrupamento_sync(cur)
        assert cfg["ativo"] is True
        assert cfg["formas"] == ["1", "2"]


class TestDiversosCodes:
    def test_junta_cod_cliente_orcamento_e_cliente_diversos(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_cliente_orcamento": 50}, {"codigo": 99}])
        _patch(monkeypatch, cur)
        codes = svc._diversos_codes_sync(cur)
        assert codes == {50, 99}

    def test_sem_nenhum_dos_dois(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_cliente_orcamento": None}, None])
        _patch(monkeypatch, cur)
        codes = svc._diversos_codes_sync(cur)
        assert codes == set()


class TestListarAgrupadasCandidatas:
    def test_config_inativa_nao_consulta_nada(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        candidatas = svc._listar_agrupadas_candidatas_sync(cur, {"ativo": False}, False, None, None)
        assert candidatas == []
        assert cur.queries == []

    def test_cpf_aceito_quando_checkbox_marcado(self, monkeypatch):
        config = {"ativo": True, "clientes_diversos": False, "sem_documento": False,
                  "cpf": True, "cnpj": False, "formas": ["1"]}
        cur = FakeCursor(
            one=[{"cod_cliente_orcamento": None}, None],
            many=[[{"seq": 1, "cli_codigo": 10, "nome": "FULANO", "cgc_cpf": "12345678901",
                    "forma_codigo": "1", "forma_descricao": "DINHEIRO", "data_doc": None, "valor_total": 100.0}]],
        )
        _patch(monkeypatch, cur)
        candidatas = svc._listar_agrupadas_candidatas_sync(cur, config, False, None, None)
        assert len(candidatas) == 1
        assert candidatas[0]["flag"] == "MovimentacaoReceberAgrupada"

    def test_cnpj_rejeitado_quando_checkbox_desmarcado(self, monkeypatch):
        config = {"ativo": True, "clientes_diversos": False, "sem_documento": False,
                  "cpf": False, "cnpj": False, "formas": ["1"]}
        cur = FakeCursor(
            one=[{"cod_cliente_orcamento": None}, None],
            many=[[{"seq": 1, "cli_codigo": 10, "nome": "EMPRESA LTDA", "cgc_cpf": "12345678000199",
                    "forma_codigo": "1", "forma_descricao": "DINHEIRO", "data_doc": None, "valor_total": 100.0}]],
        )
        _patch(monkeypatch, cur)
        candidatas = svc._listar_agrupadas_candidatas_sync(cur, config, False, None, None)
        assert candidatas == []

    def test_clientes_diversos_aceito_por_cod_cliente_orcamento(self, monkeypatch):
        config = {"ativo": True, "clientes_diversos": True, "sem_documento": False,
                  "cpf": False, "cnpj": False, "formas": ["1"]}
        cur = FakeCursor(
            one=[{"cod_cliente_orcamento": 10}, None],
            many=[[{"seq": 1, "cli_codigo": 10, "nome": "CONSUMIDOR", "cgc_cpf": "",
                    "forma_codigo": "1", "forma_descricao": "DINHEIRO", "data_doc": None, "valor_total": 50.0}]],
        )
        _patch(monkeypatch, cur)
        candidatas = svc._listar_agrupadas_candidatas_sync(cur, config, False, None, None)
        assert len(candidatas) == 1


class TestConsolidarCentroCusto:
    def test_soma_linhas_do_mesmo_centro_custo(self, monkeypatch):
        cur = FakeCursor(many=[[{"total": 300.0, "centro_custo": 1, "classe": 0, "sub_classe": 0}]])
        _patch(monkeypatch, cur)
        svc._consolidar_centro_custo_sync(cur, 700)
        inserts = [p for q, p in cur.queries if q.startswith("INSERT INTO movimentacoes_centro_custo")]
        assert len(inserts) == 1
        assert inserts[0][4] == 300.0


CAB_AGRUPADA = {**CAB_RECEBER, "cliente_nome": "MESA 5", "conta_venc": None, "conta_cliente": None}


class TestTransferirAgrupadas:
    def test_sem_conta_transf_caixa_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{**CONTROLE_ROW, "conta_transf_caixa": 0}])
        _patch(monkeypatch, cur)
        r = svc._transferir_agrupadas_sync("srv", "bd", [1])
        assert r["success"] is False

    def test_config_inativa_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[CONTROLE_ROW, None], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._transferir_agrupadas_sync("srv", "bd", [1])
        assert r["success"] is False
        assert "não está configurado" in r["message"]

    def test_dois_itens_do_mesmo_grupo_consolidam_em_1_movimentacao(self, monkeypatch):
        item_lookup = {"data_pag": "2026-08-20", "forma_descricao": "DINHEIRO"}
        cur = FakeCursor(
            one=[
                CONTROLE_ROW,                 # _controle_flags_sync
                CONFIG_ROW,                   # _get_config_agrupamento_sync (agrupa_comandas)
                item_lookup, item_lookup,      # data_pag/forma de cada item (101, 102)
                None, {"codigo": 900},         # _upsert_favorecido_sync (não achado -> cria)
                None, {"codigo": 700},         # cabeçalho do grupo (não achado -> cria) = cod_mov
                None, CAB_AGRUPADA,             # item 101: dedupe + rateio (cab)
                None, CAB_AGRUPADA,             # item 102: dedupe + rateio (cab)
            ],
            many=[
                [{"codigo": "1"}],             # formas marcadas
                [LINHA_RECEBER],               # item 101 rateio (linhas)
                [LINHA_RECEBER],               # item 102 rateio (linhas)
                [{"total": 1000.0, "centro_custo": 1, "classe": 0, "sub_classe": 0}],  # consolidação
            ],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._transferir_agrupadas_sync("srv", "bd", [101, 102])
        assert r["success"] is True
        assert r["transferidos"] == [101, 102]
        assert conn.committed is True

        acumula = [q for q, p in cur.queries if q.startswith("UPDATE movimentacoes SET valor = valor +")]
        assert len(acumula) == 2  # 1 por item, mesmo cod_mov (700) os dois
        assert all(p[1] == 700 for q, p in cur.queries if q.startswith("UPDATE movimentacoes SET valor"))

        marca_transferido = [q for q, p in cur.queries if q.startswith("UPDATE duplicata_rec_venc SET transf_caixa")]
        assert len(marca_transferido) == 2

    def test_item_ja_transferido_agrupado_vira_falha_isolada(self, monkeypatch):
        item_lookup = {"data_pag": "2026-08-20", "forma_descricao": "DINHEIRO"}
        cur = FakeCursor(
            one=[
                CONTROLE_ROW, CONFIG_ROW, item_lookup,
                None, {"codigo": 900},   # favorecido
                None, {"codigo": 700},   # cabeçalho do grupo
                {"codigo": 55},          # dedupe: JÁ existe em movimentacoes_agrupadas
            ],
            many=[[{"codigo": "1"}]],
        )
        _patch(monkeypatch, cur)
        r = svc._transferir_agrupadas_sync("srv", "bd", [101])
        assert r["success"] is False
        assert r["falhas"][0]["message"] == "Esta comanda já foi transferida (agrupada)."
