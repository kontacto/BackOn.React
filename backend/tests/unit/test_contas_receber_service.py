"""Testes unitários de Financeiro > Contas a Receber (ver
services/contas_receber_service.py pro rastreio completo da fonte —
`Geral/frmTraNFRec.frm` + `Revenda/FrmManDur.frm`)."""
from datetime import date

import services.contas_receber_service as svc


class FakeCursor:
    """Mesmo padrão de test_transferencia_contas_service.py — fila de
    resultados na ordem de chamada."""
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


FLAGS_ROW = {"agrupa_nf_receber": 0, "geranumerodup": 0, "numero_dup": None, "desmembramento_dup": "", "fantasia": ""}


class TestSplitParcelas:
    def test_parcela_unica(self):
        r = svc._split_parcelas(150.0, 1, date(2026, 8, 28))
        assert r == [(date(2026, 8, 28), 150.0)]

    def test_split_com_arredondamento_na_ultima(self):
        # 100 / 3 = 33.33... — última parcela absorve o resto do arredondamento.
        r = svc._split_parcelas(100.0, 3, date(2026, 1, 31))
        valores = [v for _, v in r]
        assert valores[0] == 33.33
        assert valores[1] == 33.33
        assert valores[2] == 33.34
        assert round(sum(valores), 2) == 100.0

    def test_vencimento_avanca_1_mes_mesmo_dia(self):
        r = svc._split_parcelas(30.0, 3, date(2026, 1, 15))
        datas = [d for d, _ in r]
        assert datas == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]

    def test_vencimento_dia_31_cai_pro_ultimo_dia_valido_do_mes(self):
        # Réplica do loop `repete:` de frmTraNFRec.frm's Command7 — dia 31
        # não existe em fevereiro, decrementa até achar data válida.
        r = svc._split_parcelas(20.0, 2, date(2026, 1, 31))
        datas = [d for d, _ in r]
        assert datas[0] == date(2026, 1, 31)
        assert datas[1] == date(2026, 2, 28)  # 2026 não é bissexto


class TestListar:
    def test_lista_com_fallback_fantasia(self, monkeypatch):
        rows = [{
            "codigo": 1, "cliente": 10, "cliente_nome": "RAZAO SOCIAL LTDA", "cliente_fantasia": "APELIDO",
            "duplicata": 999, "desmembramento": "1", "dt_emissao": date(2026, 8, 1), "valor": 150.0,
            "situacao": "A", "num_parcelas": 1, "parcelas_pagas": 0,
            "proximo_vencimento": date(2020, 1, 1), "valor_em_aberto": 150.0,
        }]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {})
        assert r["success"] is True
        assert r["items"][0]["cliente_nome"] == "APELIDO"
        assert r["items"][0]["vencido"] is True  # vencimento em 2020, situacao ainda 'A'

    def test_filtro_busca_inclui_nome_e_fantasia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_sync("srv", "bd", {"busca": "acme"})
        sql = cur.queries[0][0]
        assert "c.nome LIKE" in sql and "c.fantasia LIKE" in sql

    def test_filtros_extras_frmcondur(self, monkeypatch):
        # Rastreado de FRMCONDUr.frm ("Consulta de Duplicatas à Receber"),
        # achado do usuário 2026-08-31 — integrado na listagem já existente.
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_sync("srv", "bd", {
            "duplicata_num": 1994, "valor": 150.5, "numero_boleto": 777,
            "situacao_duplicata": 1, "recebido_ini": "2026-08-01", "recebido_fim": "2026-08-31",
        })
        sql, params = cur.queries[0]
        assert "dr.duplicata = %s" in sql
        assert "v.valor + ISNULL(v.tarifa_banco,0) + ISNULL(v.outros_acres_pag,0)" in sql
        assert "v.numero_boleto = %s" in sql
        assert "ISNULL(v.situacao_duplicata,0) = %s" in sql
        assert "v.data_pag BETWEEN %s AND %s" in sql
        assert params == (1994, 150.5, 777, 1, "2026-08-01", "2026-08-31")

    def test_situacao_duplicata_zero_nao_e_ignorado(self, monkeypatch):
        # 0 = Normal — precisa passar no filtro mesmo sendo falsy em Python.
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_sync("srv", "bd", {"situacao_duplicata": 0})
        assert "ISNULL(v.situacao_duplicata,0) = %s" in cur.queries[0][0]


class TestCriarAvulsa:
    def _req(self, **over):
        base = {
            "cliente": 10, "numero": 555, "serie": "1", "tipo_mov": "S01",
            "dt_emissao": "2026-08-28", "valor": 100.0, "parcelas": 1,
            "dt_primeiro_vencimento": "2026-09-28", "observacao": "teste",
        }
        base.update(over)
        return base

    def test_sucesso_grava_receber_codigo_no_link_nf(self, monkeypatch):
        cur = FakeCursor(one=[
            {"nome": "Cliente Teste"},           # SELECT Cliente
            None,                                 # duplicidade: não existe
            {"codigo": 700},                      # INSERT Receber OUTPUT -> receber_codigo
            dict(FLAGS_ROW),                      # _controle_flags_sync
            {"codigo": 900},                      # INSERT Duplicata_Receber OUTPUT -> dup_codigo
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req())
        assert r["success"] is True
        assert r["codigo"] == 900
        assert conn.committed is True
        # Mesmo achado corrigido em transferencia_contas_service.py: o link
        # tem que gravar o codigo de Receber (700), nunca outro valor.
        insert_link = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Nf")][0]
        assert insert_link == (900, 700)
        insert_receber = [q for q, p in cur.queries if q.startswith("INSERT INTO Receber")][0]
        assert "'DU'" in insert_receber

    def test_cliente_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req())
        assert r["success"] is False
        assert "Cliente não encontrado" in r["message"]

    def test_bloqueia_duplicidade(self, monkeypatch):
        cur = FakeCursor(one=[{"nome": "Cliente Teste"}, {"codigo": 5}])
        _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req())
        assert r["success"] is False
        assert "Já existe um lançamento" in r["message"]

    def test_split_em_3_parcelas_grava_3_vencimentos(self, monkeypatch):
        cur = FakeCursor(one=[
            {"nome": "Cliente Teste"}, None, {"codigo": 700}, dict(FLAGS_ROW), {"codigo": 900},
        ])
        _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req(parcelas=3, valor=100.0))
        assert r["success"] is True
        inserts_venc = [q for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Venc")]
        assert len(inserts_venc) == 3


class TestBaixarParcela:
    def _req(self, **over):
        base = {"codigo_venc": 1, "data_pag": "2026-08-28", "valor_pag": 50.0,
                "desconto_pag": 0, "juros_pag": 0, "conta": 3, "forma_pag": "DIN"}
        base.update(over)
        return base

    def _parcela(self, **over):
        base = {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 50.0, "dt_vencimento": date(2026, 8, 28)}
        base.update(over)
        return base

    def test_sucesso_parcial_mantem_situacao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[
            self._parcela(),                                     # SELECT parcela (valor=50, sem residual)
            {"data_fecha_cx": None},                             # caixa nunca fechado
            {"total": 3, "pagas": 1},                            # contagem pós-UPDATE
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is True
        assert conn.committed is True
        update_dr = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Receber")][0]
        assert update_dr == (1, "A", 900)

    def test_sucesso_todas_pagas_marca_duplicata_pg(self, monkeypatch):
        cur = FakeCursor(one=[
            self._parcela(),
            {"data_fecha_cx": None},
            {"total": 1, "pagas": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is True
        update_dr = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Receber")][0]
        assert update_dr == (1, "PG", 900)

    def test_grava_campos_novos_da_baixa(self, monkeypatch):
        """Achado 2026-08-28 (screenshot do menu real): a baixa real do
        legado (`FrmManPar.frm`) grava banco/agência/tarifa/boleto/outros
        desc./outros acresc./observação — não só data/valor/desconto/
        juros/conta/forma. Confirma que os campos novos chegam no UPDATE."""
        cur = FakeCursor(one=[self._parcela(), {"data_fecha_cx": None}, {"total": 1, "pagas": 1}])
        _patch(monkeypatch, cur)
        req = self._req(
            outros_desc_pag=2, outros_acres_pag=3, tarifa_banco=1.5,
            banco_cedente=341, agencia_cedente=1234, numero_boleto=98765,
            observacao="pago via PIX",
        )
        r = svc._baixar_parcela_sync("srv", "bd", req)
        assert r["success"] is True
        update_venc = [q for q, p in cur.queries if q.startswith("UPDATE Duplicata_Rec_Venc")][0]
        assert "outros_desc_pag" in update_venc and "tarifa_banco" in update_venc
        assert "banco_cedente" in update_venc and "agencia_cedente" in update_venc
        assert "numero_boleto" in update_venc and "obs_vencimento" in update_venc
        # num_doc_pag é exclusivo do lado Pagar — não pode aparecer aqui.
        assert "num_doc_pag" not in update_venc

    def test_bloqueia_parcela_ja_paga(self, monkeypatch):
        cur = FakeCursor(one=[self._parcela(situacao="PG")])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is False
        assert "já está paga" in r["message"]

    def test_parcela_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_bloqueia_caixa_ja_fechado(self, monkeypatch):
        """Achado real, confirmado com Leandro 2026-08-28 ("deve usar os
        mesmos critérios de bloqueio que existem hoje, incluíndo bloqueio
        por caixa já fechado") — réplica de `Command2_Click`
        (`CDate(Campo(5)) <= CDate(Data_Fecha_Cx)`)."""
        cur = FakeCursor(one=[self._parcela(), {"data_fecha_cx": date(2026, 8, 28)}])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req(data_pag="2026-08-28"))
        assert r["success"] is False
        assert "Caixa já fechado" in r["message"]

    def test_permite_baixa_apos_data_de_fechamento(self, monkeypatch):
        cur = FakeCursor(one=[self._parcela(), {"data_fecha_cx": date(2026, 8, 20)}, {"total": 1, "pagas": 1}])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req(data_pag="2026-08-28"))
        assert r["success"] is True

    def test_bloqueia_sem_forma_pagamento(self, monkeypatch):
        cur = FakeCursor(one=[self._parcela(), {"data_fecha_cx": None}])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req(forma_pag=None))
        assert r["success"] is False
        assert "Forma de Pagamento" in r["message"]

    def test_bloqueia_sem_conta(self, monkeypatch):
        cur = FakeCursor(one=[self._parcela(), {"data_fecha_cx": None}])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req(conta=None))
        assert r["success"] is False
        assert "Conta" in r["message"]

    def test_bloqueia_valor_pago_maior_que_parcela(self, monkeypatch):
        """Achado real (só lado Receber): "O valor não pode ser superior
        ao do vencimento. Use os campos Juros/Outros Acréscimo." —
        `FrmManPar.frm` tem essa trava, `FrmManPap.frm` (Pagar) não."""
        cur = FakeCursor(one=[self._parcela(valor=50.0), {"data_fecha_cx": None}])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req(valor_pag=60.0))
        assert r["success"] is False
        assert "não pode ser superior" in r["message"]


class TestBaixaComResidual:
    """Pagamento parcial gera vencimento residual (achado real, os dois
    lados) — `TestBaixarParcela` acima sempre usa valor_pag == valor da
    parcela pra não disparar esse caminho; aqui testamos ele isolado."""

    def test_valor_pago_menor_gera_residual_e_incrementa_num_parcelas(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 100.0, "dt_vencimento": date(2026, 8, 28)},
            {"data_fecha_cx": None},               # caixa nunca fechado
            {"m": 2},                              # MAX(desmembramento) já existente = 2
            {"total": 3, "pagas": 1},               # rollup pós-baixa+residual
        ])
        conn = _patch(monkeypatch, cur)
        req = {"codigo_venc": 1, "data_pag": "2026-08-28", "valor_pag": 40.0,
               "desconto_pag": 0, "juros_pag": 0, "conta": 3, "forma_pag": "DIN"}
        r = svc._baixar_parcela_sync("srv", "bd", req)
        assert r["success"] is True
        assert conn.committed is True
        insert_residual = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Venc")][0]
        # (duplicata=900, próximo desmembramento=3, mesma dt_vencimento, saldo=60.0)
        assert insert_residual == (900, 3, date(2026, 8, 28), 60.0)
        update_num_parcelas = [q for q, p in cur.queries if "num_parcelas = num_parcelas + 1" in q]
        assert len(update_num_parcelas) == 1

    def test_valor_pago_igual_nao_gera_residual(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 100.0, "dt_vencimento": date(2026, 8, 28)},
            {"data_fecha_cx": None},
            {"total": 1, "pagas": 1},
        ])
        _patch(monkeypatch, cur)
        req = {"codigo_venc": 1, "data_pag": "2026-08-28", "valor_pag": 100.0,
               "desconto_pag": 0, "juros_pag": 0, "conta": 3, "forma_pag": "DIN"}
        r = svc._baixar_parcela_sync("srv", "bd", req)
        assert r["success"] is True
        assert not any(q.startswith("INSERT INTO Duplicata_Rec_Venc") for q, p in cur.queries)


class TestCancelarBaixa:
    def test_cancela_parcela_paga(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 0},  # guarda 1: agrupamento de comandas
            {"qtd": 0},  # guarda 2: cheque pré-datado
            {"total": 3, "pagas": 0},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1})
        assert r["success"] is True
        assert conn.committed is True
        update_venc = [q for q, p in cur.queries if q.startswith("UPDATE Duplicata_Rec_Venc")][0]
        assert "situacao = 'A'" in update_venc and "data_pag = NULL" in update_venc
        update_dr = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Receber")][0]
        assert update_dr == (0, "A", 900)

    def test_bloqueia_parcela_ainda_nao_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1, "duplicata": 900, "situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1})
        assert r["success"] is False
        assert "não está paga" in r["message"]

    def test_parcela_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 999})
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_bloqueia_se_agrupado_em_comanda_no_caixa(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 1},  # guarda 1: existe agrupamento
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1})
        assert r["success"] is False
        assert "agrupamento de comandas" in r["message"]
        assert conn.committed is False
        assert not any(q.startswith("UPDATE") for q, p in cur.queries)

    def test_pede_confirmacao_quando_tem_cheque_vinculado(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 0},  # guarda 1: sem agrupamento
            {"qtd": 2},  # guarda 2: 2 cheques vinculados
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1})
        assert r["success"] is False
        assert r["exige_confirmacao_cheque"] is True
        assert r["qtd_cheques"] == 2
        assert conn.committed is False
        assert not any(q.startswith("UPDATE") for q, p in cur.queries)

    def test_confirma_exclusao_de_cheque_e_cancela(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 0},
            {"qtd": 2},
            {"total": 3, "pagas": 0},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1, "excluir_cheques": True})
        assert r["success"] is True
        assert conn.committed is True
        delete_cheque = [q for q, p in cur.queries if q.startswith("DELETE FROM cheque")]
        assert len(delete_cheque) == 1

    def test_recusa_exclusao_de_cheque_mas_cancela_mesmo_assim(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 0},
            {"qtd": 2},
            {"total": 3, "pagas": 0},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1, "excluir_cheques": False})
        assert r["success"] is True
        assert conn.committed is True
        assert not any(q.startswith("DELETE FROM cheque") for q, p in cur.queries)

    def test_lado_pagar_nao_roda_as_2_guardas(self, monkeypatch):
        """Pagar não tem essas guardas no legado — origem_cheque=None
        (padrão) faz `_cancelar_baixa_core` pular direto pro UPDATE."""
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"total": 3, "pagas": 0},
        ])
        r = svc._cancelar_baixa_core(cur, "Duplicata_Pag_Venc", "Duplicata_Pagar", 1)
        assert r["success"] is True
        assert not any(
            "movimentacoes_agrupadas" in q or "FROM cheque" in q for q, p in cur.queries
        )


class TestProcessarLote:
    def test_baixa_em_lote_isola_falha_de_1_item(self, monkeypatch):
        """1 vencimento inexistente no meio do lote não aborta os outros
        — mesmo princípio de isolamento já usado em `ensure_all_schema`."""
        cur = FakeCursor(one=[
            {"valor": 50.0},                                                        # item 1: SELECT valor
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 50.0, "dt_vencimento": date(2026, 8, 28)},
            {"data_fecha_cx": None},                                                # caixa nunca fechado
            {"total": 1, "pagas": 1},                                               # rollup item 1
            None,                                                                    # item 2: SELECT valor -> não encontrado
        ])
        conn = _patch(monkeypatch, cur)
        req = {"modo": "baixar", "vencimentos": [1, 2], "data_pag": "2026-08-28", "conta": 3, "forma_pag": "DIN"}
        r = svc._processar_lote_sync("srv", "bd", req)
        assert r["success"] is True
        assert conn.committed is True
        assert r["processados"] == 1
        assert len(r["falhas"]) == 1
        assert r["falhas"][0]["codigo_venc"] == 2

    def test_cancelamento_em_lote(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 0},  # guarda 1
            {"qtd": 0},  # guarda 2
            {"total": 1, "pagas": 0},
        ])
        _patch(monkeypatch, cur)
        req = {"modo": "cancelar", "vencimentos": [1]}
        r = svc._processar_lote_sync("srv", "bd", req)
        assert r["success"] is True
        assert r["processados"] == 1
        assert r["falhas"] == []

    def test_cancelamento_em_lote_isola_item_com_cheque_vinculado(self, monkeypatch):
        """Lote não pode perguntar 'excluir cheque?' — item com cheque
        vinculado vira falha isolada, resto do lote segue normalmente."""
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"qtd": 0},  # guarda 1, item 1
            {"qtd": 1},  # guarda 2, item 1: tem cheque -> falha
            {"codigo": 2, "duplicata": 901, "situacao": "PG"},
            {"qtd": 0},  # guarda 1, item 2
            {"qtd": 0},  # guarda 2, item 2
            {"total": 1, "pagas": 0},
        ])
        conn = _patch(monkeypatch, cur)
        req = {"modo": "cancelar", "vencimentos": [1, 2]}
        r = svc._processar_lote_sync("srv", "bd", req)
        assert r["success"] is True
        assert conn.committed is True
        assert r["processados"] == 1
        assert len(r["falhas"]) == 1
        assert r["falhas"][0]["codigo_venc"] == 1
        assert "cheque" in r["falhas"][0]["message"]


class TestBaixarMontante:
    def test_distribui_sequencialmente_ate_esgotar(self, monkeypatch):
        """Montante de 80 sobre 2 parcelas de 50 cada — quita a 1ª
        inteira (50), aplica os 30 restantes na 2ª (residual de 20)."""
        cur = FakeCursor(one=[
            {"codigo": 1, "situacao": "A", "valor": 50.0},                          # parcela 1 (pré-check)
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 50.0, "dt_vencimento": date(2026, 8, 28)},
            {"data_fecha_cx": None},                                                # caixa nunca fechado (parcela 1)
            {"total": 1, "pagas": 1},                                               # rollup parcela 1
            {"codigo": 2, "situacao": "A", "valor": 50.0},                          # parcela 2 (pré-check)
            {"codigo": 2, "duplicata": 901, "situacao": "A", "valor": 50.0, "dt_vencimento": date(2026, 9, 1)},
            {"data_fecha_cx": None},                                                # caixa nunca fechado (parcela 2)
            {"m": 1},                                                                # MAX(desmembramento) residual
            {"total": 2, "pagas": 1},                                               # rollup parcela 2 (com residual)
        ])
        conn = _patch(monkeypatch, cur)
        req = {"vencimentos": [1, 2], "montante": 80.0, "data_pag": "2026-08-28", "conta": 3, "forma_pag": "DIN"}
        r = svc._baixar_montante_sync("srv", "bd", req)
        assert r["success"] is True
        assert conn.committed is True
        assert r["tocados"] == [1, 2]
        assert r["saldo_nao_utilizado"] == 0.0
        insert_residual = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Venc")][0]
        assert insert_residual == (901, 2, date(2026, 9, 1), 20.0)

    def test_para_quando_saldo_esgota(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "situacao": "A", "valor": 50.0},
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 50.0, "dt_vencimento": date(2026, 8, 28)},
            {"data_fecha_cx": None},
            {"total": 1, "pagas": 1},
        ])
        conn = _patch(monkeypatch, cur)
        req = {"vencimentos": [1, 2], "montante": 50.0, "data_pag": "2026-08-28", "conta": 3, "forma_pag": "DIN"}
        r = svc._baixar_montante_sync("srv", "bd", req)
        assert r["success"] is True
        assert r["tocados"] == [1]
        assert r["saldo_nao_utilizado"] == 0.0
        # vencimento 2 nunca foi tocado — saldo zerou antes de chegar nele.
        assert not any("codigo = 2" in str(p) for q, p in cur.queries if "SELECT" in q)


class TestEditarParcela:
    def test_bloqueia_parcela_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "PG"}])
        _patch(monkeypatch, cur)
        r = svc._editar_parcela_sync("srv", "bd", {"codigo_venc": 1, "dt_vencimento": "2026-09-01", "valor": 10.0})
        assert r["success"] is False
        assert "Alterações não permitidas" in r["message"]

    def test_edita_parcela_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._editar_parcela_sync("srv", "bd", {"codigo_venc": 1, "dt_vencimento": "2026-09-01", "valor": 10.0})
        assert r["success"] is True
        assert conn.committed is True


class TestAlterarSituacaoVencimento:
    # "Cadastro de Vencimentos" (FrmManDur.frm) — 0=Normal, 1=Jurídico,
    # 2=Protestado. Achado do usuário 2026-08-31.
    def test_vencimento_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._alterar_situacao_vencimento_sync("srv", "bd", 999, 1)
        assert r["success"] is False
        assert "não encontrado" in r["message"]

    def test_altera_situacao_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_situacao_vencimento_sync("srv", "bd", 1, 2)
        assert r["success"] is True
        assert conn.committed is True
        update = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Rec_Venc SET situacao_duplicata")][0]
        assert update == (2, 1)


class TestAlterarSituacaoVencimentoLote:
    def test_isola_falha_por_item(self, monkeypatch):
        # codigo 1 existe (achado), codigo 2 não (fetchone -> None)
        cur = FakeCursor(one=[{"codigo": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_situacao_vencimento_lote_sync("srv", "bd", [1, 2], 0)
        assert r["success"] is False
        assert r["alterados"] == [1]
        assert r["falhas"][0]["codigo"] == 2
        assert conn.committed is True

    def test_altera_todos_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}, {"codigo": 2}])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_situacao_vencimento_lote_sync("srv", "bd", [1, 2], 1)
        assert r["success"] is True
        assert r["alterados"] == [1, 2]
        assert conn.committed is True


class TestExcluir:
    def test_bloqueia_se_tem_parcela_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 900}, {"qtd": 1}])
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 900)
        assert r["success"] is False
        assert "já pagas" in r["message"]

    def test_exclui_e_apaga_receber_avulso(self, monkeypatch):
        cur = FakeCursor(
            one=[{"codigo": 900}, {"qtd": 0}, {"cod_n_fiscal": None}],
            many=[[{"nf_fiscal": 700}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 900)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.startswith("DELETE FROM Receber") for q, p in cur.queries)

    def test_exclui_limpa_previsoes_orfas_de_transferencia(self, monkeypatch):
        # Bug real corrigido 2026-08-31 (#017/#030) — excluir uma duplicata
        # já transferida pro Fluxo de Caixa não podia deixar a previsão
        # órfã (cod_transf_caixa apontando pra um vencimento apagado).
        cur = FakeCursor(
            one=[{"codigo": 900}, {"qtd": 0}, {"cod_n_fiscal": None}],
            many=[[{"nf_fiscal": 700}]],
        )
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 900)
        assert r["success"] is True
        idx_delete_prev = next(i for i, (q, p) in enumerate(cur.queries) if q.startswith("DELETE p FROM Previsoes"))
        idx_delete_venc = next(i for i, (q, p) in enumerate(cur.queries) if q.startswith("DELETE FROM Duplicata_Rec_Venc"))
        assert "flag_transf_caixa = 'R'" in cur.queries[idx_delete_prev][0]
        assert cur.queries[idx_delete_prev][1] == (900,)
        assert idx_delete_prev < idx_delete_venc  # previsão limpa ANTES do vencimento sumir (senão o JOIN não casa mais)

    def test_exclui_e_reabre_receber_de_nf_real(self, monkeypatch):
        cur = FakeCursor(
            one=[{"codigo": 900}, {"qtd": 0}, {"cod_n_fiscal": 123}],
            many=[[{"nf_fiscal": 700}]],
        )
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 900)
        assert r["success"] is True
        update_receber = [p for q, p in cur.queries if q.startswith("UPDATE Receber SET situacao")][0]
        assert update_receber == (700,)

    def test_duplicata_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]


class TestAlterarNumero:
    # "Alterar Número da Duplicata" (FrmManDur.frm::Command15_Click).
    # Achado do usuário 2026-08-31.
    def test_duplicata_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._alterar_numero_sync("srv", "bd", 999, 1994)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_bloqueia_numero_ja_usado(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 900}, {"codigo": 901}])
        _patch(monkeypatch, cur)
        r = svc._alterar_numero_sync("srv", "bd", 900, 1994)
        assert r["success"] is False
        assert "já existe" in r["message"].lower()

    def test_altera_numero_apaga_previsoes_e_reseta_transf(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 900}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._alterar_numero_sync("srv", "bd", 900, 1994)
        assert r["success"] is True
        assert r["duplicata"] == 1994
        assert conn.committed is True
        update = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Receber SET duplicata")][0]
        assert update == (1994, 900)
        delete_prev = [q for q, p in cur.queries if q.startswith("DELETE p FROM Previsoes")]
        assert len(delete_prev) == 1
        assert "flag_transf_caixa = 'R'" in delete_prev[0]
        reset_transf = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Rec_Venc SET transf_previsao")][0]
        assert reset_transf == (900,)


class TestNotasDisponiveis:
    # "Notas Fiscais" (FrmManDur.frm::Command5_Click) — achado do usuário
    # 2026-08-31.
    def test_duplicata_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._notas_disponiveis_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_busca_por_raiz_cgc_cpf(self, monkeypatch):
        cur = FakeCursor(
            one=[{"cliente": 10}, {"cgc_cpf": "12345678000199"}],
            many=[[{"codigo": 700, "codigo_cliente": 11, "nome": "FILIAL LTDA", "nota_fiscal": 55, "serie": "1", "valor": 200.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._notas_disponiveis_sync("srv", "bd", 900)
        assert r["success"] is True
        assert r["items"][0]["cliente_nome"] == "FILIAL LTDA"
        sql, params = cur.queries[-1]
        assert "LEFT(c.cgc_cpf,8) = %s" in sql
        assert params == ("12345678",)


class TestVincularNf:
    def test_duplicata_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._vincular_nf_sync("srv", "bd", 999, 700)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_bloqueia_ja_vinculada(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 900}, {"codigo": 1}])
        _patch(monkeypatch, cur)
        r = svc._vincular_nf_sync("srv", "bd", 900, 700)
        assert r["success"] is False
        assert "já vinculada" in r["message"].lower()

    def test_checagem_de_vinculo_usa_coluna_real(self, monkeypatch):
        # Regressão achada ao vivo (ARGEN TESTE, 2026-08-31, testando o
        # mirror do lado Pagar): `Duplicata_Rec_Nf` só tem as colunas
        # `(duplicata, nf_fiscal)` — `SELECT codigo FROM Duplicata_Rec_Nf`
        # quebra em produção ("Invalid column name 'codigo'"), invisível
        # no FakeCursor. Nunca reintroduzir `codigo` nessa checagem.
        cur = FakeCursor(one=[{"codigo": 900}, None, {"situacao": "A"}])
        _patch(monkeypatch, cur)
        svc._vincular_nf_sync("srv", "bd", 900, 700)
        check_query = [q for q, p in cur.queries if "Duplicata_Rec_Nf WHERE duplicata" in q][0]
        assert "SELECT codigo FROM Duplicata_Rec_Nf" not in check_query
        assert "SELECT duplicata FROM Duplicata_Rec_Nf" in check_query

    def test_bloqueia_nf_nao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 900}, None, {"situacao": "DU"}])
        _patch(monkeypatch, cur)
        r = svc._vincular_nf_sync("srv", "bd", 900, 700)
        assert r["success"] is False
        assert "não está mais em aberto" in r["message"]

    def test_vincula_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 900}, None, {"situacao": "A"}])
        conn = _patch(monkeypatch, cur)
        r = svc._vincular_nf_sync("srv", "bd", 900, 700)
        assert r["success"] is True
        assert conn.committed is True
        insert = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Nf")][0]
        assert insert == (900, 700)
        update = [p for q, p in cur.queries if q.startswith("UPDATE Receber SET situacao = 'DU'")][0]
        assert update == (700,)


class TestDesvincularNf:
    def test_bloqueia_se_ja_pago(self, monkeypatch):
        cur = FakeCursor(one=[{"qtd": 1}])
        _patch(monkeypatch, cur)
        r = svc._desvincular_nf_sync("srv", "bd", 900, 700)
        assert r["success"] is False
        assert "já pagos" in r["message"] or "pagos" in r["message"]

    def test_bloqueia_nao_vinculada(self, monkeypatch):
        cur = FakeCursor(one=[{"qtd": 0}, None])
        _patch(monkeypatch, cur)
        r = svc._desvincular_nf_sync("srv", "bd", 900, 700)
        assert r["success"] is False
        assert "não está vinculada" in r["message"]

    def test_desvincula_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[{"qtd": 0}, {"codigo": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._desvincular_nf_sync("srv", "bd", 900, 700)
        assert r["success"] is True
        assert conn.committed is True
        delete = [p for q, p in cur.queries if q.startswith("DELETE FROM Duplicata_Rec_Nf")][0]
        assert delete == (900, 700)
        update = [p for q, p in cur.queries if q.startswith("UPDATE Receber SET situacao = 'A'")][0]
        assert update == (700,)


class TestEmitirRecibo:
    """"Emitir Recibo" — achado 2026-08-31: botão real na tela de Baixa
    (`FrmManPar.frm::Command13`), Click comentado/morto na fonte;
    completa a intenção documentada no comentário morto. Numeração via
    núcleo compartilhado `recibo_service._gravar_recibo_numerado_sync`
    (mesmo já usado por Faturar Contratos)."""

    def test_rejeita_sem_recebemos(self, monkeypatch):
        r = svc._emitir_recibo_sync("srv", "bd", recebemos="", valor=100.0, referente="teste")
        assert r["success"] is False
        assert "pagando" in r["message"]

    def test_rejeita_valor_invalido(self, monkeypatch):
        r = svc._emitir_recibo_sync("srv", "bd", recebemos="Cliente X", valor=0, referente="teste")
        assert r["success"] is False
        assert "valor" in r["message"].lower()

    def test_rejeita_sem_referente(self, monkeypatch):
        r = svc._emitir_recibo_sync("srv", "bd", recebemos="Cliente X", valor=100.0, referente="")
        assert r["success"] is False
        assert "refere" in r["message"].lower()

    def test_emite_com_sucesso_numeracao_sequencial(self, monkeypatch):
        cur = FakeCursor(one=[{"rz_social": "MINHA EMPRESA LTDA", "seq_recibo": 41, "ano_recibo": 2026}])
        conn = _patch(monkeypatch, cur)
        r = svc._emitir_recibo_sync(
            "srv", "bd", recebemos="Cliente X", valor=1234.56, referente="Duplicata Nº 100/0",
            data_recibo="2026-08-31",
        )
        assert r["success"] is True
        assert r["numero"] == "042/2026"
        assert r["recebemos"] == "Cliente X"
        assert r["valor"] == 1234.56
        assert r["assinatura"] == "MINHA EMPRESA LTDA"
        assert "e" in r["valor_extenso"].lower()  # valor por extenso presente
        assert conn.committed is True
        insert = [p for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO RECIBOS")][0]
        assert insert[0] == 42 and insert[1] == 2026
        update = [p for q, p in cur.queries if q.strip().upper().startswith("UPDATE CONTROLE")][0]
        assert update == (42,)

    def test_assinatura_customizada_sobrescreve_rz_social(self, monkeypatch):
        cur = FakeCursor(one=[{"rz_social": "MINHA EMPRESA LTDA", "seq_recibo": 0, "ano_recibo": 2026}])
        _patch(monkeypatch, cur)
        r = svc._emitir_recibo_sync(
            "srv", "bd", recebemos="Cliente X", valor=50.0, referente="teste", assinatura="Fulano de Tal",
        )
        assert r["assinatura"] == "Fulano de Tal"

    def test_falha_conexao_nao_propaga(self, monkeypatch):
        def _falha(*a, **k):
            raise ConnectionError("boom")
        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._emitir_recibo_sync("srv", "bd", recebemos="Cliente X", valor=100.0, referente="teste")
        assert r["success"] is False
        assert "Falha conexão" in r["message"]


class TestAjustarDiaUtil:
    """Réplica da rolagem de `Gestor_Cartoes.bas::AtualizadrvCartao`
    (sábado +2, domingo +1, depois loop de feriado) — achado do usuário
    2026-08-31."""

    def test_dia_util_normal_nao_rola(self):
        cur = FakeCursor(one=[None])  # sem feriado
        seg = date(2026, 8, 31)  # segunda-feira real
        assert svc._ajustar_dia_util_sync(cur, seg) == seg

    def test_sabado_rola_2_dias_pra_segunda(self):
        cur = FakeCursor(one=[None])
        sab = date(2026, 9, 5)  # sábado
        r = svc._ajustar_dia_util_sync(cur, sab)
        assert r == date(2026, 9, 7) and r.weekday() == 0

    def test_domingo_rola_1_dia_pra_segunda(self):
        cur = FakeCursor(one=[None])
        dom = date(2026, 9, 6)  # domingo
        r = svc._ajustar_dia_util_sync(cur, dom)
        assert r == date(2026, 9, 7) and r.weekday() == 0

    def test_feriado_empurra_1_dia_e_reavalia_fim_de_semana(self):
        # sexta é feriado -> empurra pra sábado -> sábado rola +2 -> segunda
        cur = FakeCursor(one=[{"1": 1}, None])  # 1a checagem: feriado; 2a: livre
        sex = date(2026, 9, 4)  # sexta-feira real
        r = svc._ajustar_dia_util_sync(cur, sex)
        assert r == date(2026, 9, 7) and r.weekday() == 0

    def test_select_feriados_usa_coluna_nomeada(self):
        # Regressão achada ao vivo (GERDELL/BARESTELA, 2026-08-31):
        # `SELECT 1 FROM feriados` (sem alias) quebra em produção com
        # `pymssql.ColumnsWithoutNamesError` quando o cursor é as_dict=True
        # — o FakeCursor dos testes não reproduz essa restrição, então só
        # apareceu contra o banco real. Nunca reintroduzir um `SELECT`
        # de topo sem toda coluna nomeada nesta função.
        cur = FakeCursor(one=[None])
        svc._ajustar_dia_util_sync(cur, date(2026, 8, 31))
        query, _ = cur.queries[0]
        assert "select 1 from feriados" not in query.lower()
        assert " as " in query.lower()


class TestAtualizarCartao:
    """`_atualizar_cartao_sync` — réplica de `AtualizadrvCartao`. RECEBER-
    only, achado do usuário 2026-08-31."""

    def test_gera_parcelas_de_credito_corretamente(self, monkeypatch):
        cur = FakeCursor(
            many=[[{"codigo": 501}]],  # vencimentos da duplicata
            one=[
                {"valor_pag": 300.0, "data_pag": date(2026, 8, 31), "prazo": 0, "prazo_rec": 1, "parcela_max": 3},  # match CC
                None,  # feriado check parcela 1
                None,  # feriado check parcela 2
                None,  # feriado check parcela 3
                None,  # sem match CD
            ],
        )
        svc._atualizar_cartao_sync(cur, duplicata=900, codigo_venc=0)
        deletes = [q for q, p in cur.queries if q.startswith("DELETE FROM duplicata_rec_venc_cartao")]
        assert deletes == ["DELETE FROM duplicata_rec_venc_cartao WHERE sequencia_drv = %s"]
        inserts = [(q, p) for q, p in cur.queries if q.strip().upper().startswith("INSERT INTO DUPLICATA_REC_VENC_CARTAO")]
        assert len(inserts) == 3
        for _, p in inserts:
            assert p[0] == 501 and p[1] == 100.0  # 300/3 parcelas

    def test_sem_pagamento_por_cartao_nao_insere_nada(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 501}]], one=[None, None])  # nem CC nem CD
        svc._atualizar_cartao_sync(cur, duplicata=900, codigo_venc=501)
        inserts = [q for q, p in cur.queries if q.strip().upper().startswith("INSERT")]
        assert inserts == []

    def test_erro_nunca_propaga(self, monkeypatch):
        class CursorComFalha(FakeCursor):
            def execute(self, q, p=None):
                raise RuntimeError("boom")
        cur = CursorComFalha()
        svc._atualizar_cartao_sync(cur, duplicata=900, codigo_venc=1)  # não deve levantar


class TestGravarChequePre:
    """Réplica de `Geral/mdl_proc.bas::GravaChequePre` — cheque(s) pré-
    datado(s) recebido(s) como parte da própria baixa. Achado do usuário
    2026-08-31."""

    def test_insere_cheque_com_os_campos_corretos(self):
        cur = FakeCursor()
        svc._gravar_cheque_pre_sync(
            cur, 501, "2026-08-31",
            {"banco": 1, "agencia": "1234", "conta": "56789-0", "numero_ch": 777, "valor": 150.5,
             "bom_para": "2026-09-15", "nome_cheque": "Fulano", "telefone": "21999999999"},
        )
        q, p = cur.queries[0]
        assert q.strip().upper().startswith("INSERT INTO CHEQUE")
        assert p == (1, "1234", "56789-0", 777, 150.5, "2026-08-31", "2026-09-15", 501, "21999999999", "Fulano")

    def test_bom_para_ausente_usa_data_pag(self):
        cur = FakeCursor()
        svc._gravar_cheque_pre_sync(cur, 501, "2026-08-31", {"valor": 10.0})
        _, p = cur.queries[0]
        assert p[6] == "2026-08-31"  # bom_para = data_pag quando ausente


class TestBaixaComChequesEIntegracaoCartao:
    """Confirma que a baixa individual dispara `_gravar_cheque_pre_sync`
    (quando `cheques` vem no request) e sempre chama `_atualizar_cartao_
    sync` — achado do usuário 2026-08-31."""

    def test_baixa_com_cheque_grava_cheque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 100.0, "dt_vencimento": date(2026, 8, 1)},
            {"data_fecha_cx": None},
        ])
        monkeypatch.setattr(svc, "_rollup_cabecalho", lambda *a, **k: None)
        monkeypatch.setattr(svc, "_atualizar_cartao_sync", lambda *a, **k: None)
        _patch(monkeypatch, cur)
        req = {
            "codigo_venc": 1, "data_pag": "2026-08-31", "valor_pag": 100.0, "conta": 1, "forma_pag": "1",
            "cheques": [{"valor": 100.0, "banco": 1}],
        }
        r = svc._baixar_parcela_sync("srv", "bd", req)
        assert r["success"] is True
        assert any(q.strip().upper().startswith("INSERT INTO CHEQUE") for q, p in cur.queries)

    def test_baixa_sem_cheque_nao_grava_cheque(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 100.0, "dt_vencimento": date(2026, 8, 1)},
            {"data_fecha_cx": None},
        ])
        monkeypatch.setattr(svc, "_rollup_cabecalho", lambda *a, **k: None)
        monkeypatch.setattr(svc, "_atualizar_cartao_sync", lambda *a, **k: None)
        _patch(monkeypatch, cur)
        req = {"codigo_venc": 1, "data_pag": "2026-08-31", "valor_pag": 100.0, "conta": 1, "forma_pag": "1"}
        r = svc._baixar_parcela_sync("srv", "bd", req)
        assert r["success"] is True
        assert not any(q.strip().upper().startswith("INSERT INTO CHEQUE") for q, p in cur.queries)
