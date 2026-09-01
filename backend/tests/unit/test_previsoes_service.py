"""Testes unitários de Previsões (Financeiro > Fluxo de Caixa, migração de
`Tesouraria\\FrmManPrev.frm` — ver services/previsoes_service.py pro
rastreio completo da fonte, inclusive a correção sobre `cod_transf_caixa`
e a relação real com transferencia_caixa_service.py)."""
from datetime import date

import services.previsoes_service as svc


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


class TestAvancarDataFrequencia:
    def test_diario(self):
        assert svc.avancar_data_frequencia(date(2026, 1, 15), 0) == date(2026, 1, 16)

    def test_semanal(self):
        assert svc.avancar_data_frequencia(date(2026, 1, 1), 1) == date(2026, 1, 8)

    def test_mensal_dia_nao_existe_no_mes_seguinte(self):
        assert svc.avancar_data_frequencia(date(2026, 1, 31), 4) == date(2026, 2, 28)

    def test_mensal_dia_31_para_abril(self):
        assert svc.avancar_data_frequencia(date(2026, 3, 31), 4) == date(2026, 4, 30)

    def test_anual(self):
        assert svc.avancar_data_frequencia(date(2026, 1, 15), 9) == date(2027, 1, 15)

    def test_unica_vez_retorna_none(self):
        assert svc.avancar_data_frequencia(date(2026, 1, 15), 10) is None

    def test_virada_de_ano_no_avanco_mensal(self):
        assert svc.avancar_data_frequencia(date(2026, 12, 15), 4) == date(2027, 1, 15)


class TestUpsertHelpers:
    def test_favorecido_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 5}])
        _patch(monkeypatch, cur)
        assert svc._upsert_favorecido_sync(cur, "CLIENTE X") == 5
        assert "SELECT" in cur.queries[0][0]

    def test_favorecido_nao_encontrado_cria(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 9}])
        _patch(monkeypatch, cur)
        assert svc._upsert_favorecido_sync(cur, "NOVO") == 9
        assert "INSERT" in cur.queries[-1][0]

    def test_favorecido_vazio_retorna_zero_sem_query(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        assert svc._upsert_favorecido_sync(cur, "") == 0
        assert cur.queries == []

    def test_classe_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 3}])
        _patch(monkeypatch, cur)
        assert svc._upsert_classe_sync(cur, "ALUGUEL") == 3

    def test_sub_classe_sem_classe_pai_retorna_zero(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        assert svc._upsert_sub_classe_sync(cur, 0, "AGUA") == 0
        assert cur.queries == []


class TestListarSync:
    def test_lista_todas_e_marca_bloqueada_por_flag(self, monkeypatch):
        # Correção 2026-08-31, user-directed: a lista não esconde mais
        # previsões de outra tela — mostra todas, e o item vem marcado
        # `bloqueada`/`bloqueio_motivo` (ver `_bloqueio_transf_caixa`).
        rows = [
            {**PREV_PAGAR, "codigo": 10, "cod_transf_caixa": 0},
            {**PREV_PAGAR, "codigo": 11, "cod_transf_caixa": 5, "flag_transf_caixa": "P"},
            {**PREV_PAGAR, "codigo": 12, "cod_transf_caixa": 5, "flag_transf_caixa": "R"},
            {**PREV_PAGAR, "codigo": 13, "cod_transf_caixa": 5, "flag_transf_caixa": "C"},
            {**PREV_PAGAR, "codigo": 14, "cod_transf_caixa": 5, "flag_transf_caixa": "X"},
        ]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {})
        assert r["success"] is True
        assert "ISNULL(drv.situacao_duplicata,0) <> 1" in cur.queries[0][0]  # só o filtro de Jurídico continua
        por_codigo = {it["codigo"]: it for it in r["items"]}
        assert por_codigo[10]["bloqueada"] is False
        assert por_codigo[10]["bloqueio_motivo"] is None
        assert por_codigo[11]["bloqueada"] is True
        assert "Contas a Pagar" in por_codigo[11]["bloqueio_motivo"]
        assert por_codigo[12]["bloqueada"] is True
        assert "Contas a Receber" in por_codigo[12]["bloqueio_motivo"]
        assert por_codigo[13]["bloqueada"] is False  # 'C' (Comanda) — permitido
        assert por_codigo[14]["bloqueada"] is True
        assert "origem" in por_codigo[14]["bloqueio_motivo"]

    def test_filtro_atraso(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {"filtro_data": "atraso"})
        assert r["success"] is True
        assert "p.data_vencimento < %s" in cur.queries[0][0]

    def test_filtro_mes_navegavel(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {"filtro_data": "mes", "mes_ref": "2026-02"})
        assert r["success"] is True
        assert "p.data_vencimento BETWEEN %s AND %s" in cur.queries[0][0]
        assert cur.queries[0][1][-2:] == ["2026-02-01", "2026-02-28"]

    def test_filtro_mes_sem_mes_ref_usa_mes_atual(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {"filtro_data": "mes"})
        assert r["success"] is True
        hoje = date.today()
        assert cur.queries[0][1][-2] == date(hoje.year, hoje.month, 1).isoformat()

    def test_filtro_tipo_e_conta(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {"tipo": 1, "conta": 8})
        assert r["success"] is True
        params = cur.queries[0][1]
        assert 8 in params and 1 in params

    def test_monta_itens(self, monkeypatch):
        cur = FakeCursor(many=[[{
            "codigo": 1, "conta": 8, "conta_descricao": "INTER", "classe": 3, "classe_descricao": "ALUGUEL",
            "sub_classe": None, "documento": None, "data_documento": date(2026, 1, 1),
            "data_vencimento": date(2026, 1, 10), "favorecido": 5, "favorecido_nome": "IMOBILIARIA",
            "valor": 1200.0, "tipo": 0, "memorando": "Aluguel", "frequencia": 4,
        }]])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {})
        assert r["success"] is True
        assert len(r["items"]) == 1
        assert r["items"][0]["favorecido_nome"] == "IMOBILIARIA"


class TestGetSync:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_sync("srv", "bd", 1)
        assert r["success"] is False

    def test_encontrada_com_rateio(self, monkeypatch):
        row = {
            "codigo": 1, "conta": 8, "conta_descricao": None, "classe": 3, "sub_classe": None,
            "documento": None, "data_documento": date(2026, 1, 1), "data_vencimento": date(2026, 1, 10),
            "favorecido": 5, "favorecido_nome": "IMOBILIARIA", "classe_nome": "ALUGUEL", "sub_classe_nome": None,
            "valor": 1200.0, "tipo": 0, "memorando": "Aluguel", "frequencia": 4, "cod_transf_caixa": 0,
        }
        cur = FakeCursor(one=[row], many=[[{
            "codigo": 10, "centro_custo": 1, "classe": 3, "sub_classe": None, "valor": 1200.0,
            "memorando": "", "credito_debito": "D", "repete_lancamento": True,
        }]])
        _patch(monkeypatch, cur)
        r = svc._get_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["bloqueada"] is False
        assert len(r["rateio"]) == 1

    def test_bloqueada_quando_cod_transf_caixa(self, monkeypatch):
        row = {
            "codigo": 1, "conta": 8, "classe": 3, "sub_classe": None, "documento": None,
            "data_documento": date(2026, 1, 1), "data_vencimento": date(2026, 1, 10), "favorecido": 5,
            "favorecido_nome": "X", "classe_nome": "Y", "sub_classe_nome": None, "valor": 100.0, "tipo": 1,
            "memorando": "", "frequencia": 10, "cod_transf_caixa": 900,
        }
        cur = FakeCursor(one=[row], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._get_sync("srv", "bd", 1)
        assert r["bloqueada"] is True


class TestSaveSync:
    def test_tipo_invalido(self, monkeypatch):
        r = svc._save_sync("srv", "bd", {"tipo": 9, "conta": 1, "valor": 10, "data_vencimento": "2026-01-01"})
        assert r["success"] is False

    def test_sem_conta(self, monkeypatch):
        r = svc._save_sync("srv", "bd", {"tipo": 0, "valor": 10, "data_vencimento": "2026-01-01"})
        assert r["success"] is False
        assert "Conta" in r["message"]

    def test_valor_zero(self, monkeypatch):
        r = svc._save_sync("srv", "bd", {"tipo": 0, "conta": 1, "valor": 0, "data_vencimento": "2026-01-01"})
        assert r["success"] is False

    def test_sem_data_vencimento(self, monkeypatch):
        r = svc._save_sync("srv", "bd", {"tipo": 0, "conta": 1, "valor": 10})
        assert r["success"] is False

    def test_rateio_nao_bate_bloqueia(self, monkeypatch):
        r = svc._save_sync("srv", "bd", {
            "tipo": 0, "conta": 1, "valor": 100, "data_vencimento": "2026-01-01",
            "rateio": [{"centro_custo": 1, "valor": 40}],
        })
        assert r["success"] is False
        assert "rateio" in r["message"].lower()

    def test_cria_pagar_simples(self, monkeypatch):
        # Classe/Sub-Classe são código real do Plano de Contas (combobox
        # no frontend), não texto livre — sem query de resolução, o
        # código já vem pronto no payload.
        cur = FakeCursor(one=[
            None,               # favorecido select (não achado)
            {"codigo": 50},     # favorecido insert output
            {"codigo": 900},    # previsoes insert output
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {
            "tipo": 0, "conta": 1, "valor": 100.0, "data_vencimento": "2026-01-10",
            "favorecido_nome": "IMOBILIARIA", "classe": 3, "frequencia": 4,
        })
        assert r["success"] is True
        assert r["codigo"] == 900
        assert conn.committed is True
        insert_q, insert_p = [q for q in cur.queries if q[0].startswith("INSERT INTO previsoes")][0]
        assert insert_p[6] == 3  # classe = código direto, sem upsert

    def test_edicao_bloqueada_se_pertence_a_outra_tela(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_transf_caixa": 777}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {
            "codigo": 1, "tipo": 1, "conta": 1, "valor": 10, "data_vencimento": "2026-01-01",
        })
        assert r["success"] is False
        assert "outra tela" in r["message"]

    def test_transferencia_exige_conta_destino(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 1}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {
            "tipo": 2, "conta": 1, "valor": 10, "data_vencimento": "2026-01-01",
        })
        assert r["success"] is False
        assert "destino" in r["message"].lower()

    def test_transferencia_origem_igual_destino_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[None, {"codigo": 1}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {
            "tipo": 2, "conta": 1, "conta_destino": 1, "valor": 10, "data_vencimento": "2026-01-01",
        })
        assert r["success"] is False

    def test_transferencia_grava_classe_como_conta_destino(self, monkeypatch):
        # Sem favorecido_nome no payload -> _upsert_favorecido_sync não
        # dispara query nenhuma (nome vazio, retorna 0 direto) -- só a
        # fila do INSERT de previsoes é consumida.
        cur = FakeCursor(one=[{"codigo": 950}])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {
            "tipo": 2, "conta": 1, "conta_destino": 2, "valor": 10, "data_vencimento": "2026-01-01",
        })
        assert r["success"] is True
        insert_q, insert_p = [q for q in cur.queries if q[0].startswith("INSERT INTO previsoes")][0]
        assert insert_p[6] == 2  # classe = conta_destino

    def test_parcelas_cria_varias_previsoes_mensais(self, monkeypatch):
        cur = FakeCursor(one=[
            None, {"codigo": 1},      # favorecido
            {"codigo": 100},           # previsao parcela 1
            {"codigo": 101},           # previsao parcela 2
            {"codigo": 102},           # previsao parcela 3
        ])
        _patch(monkeypatch, cur)
        r = svc._save_sync("srv", "bd", {
            "tipo": 0, "conta": 1, "valor": 100.0, "data_vencimento": "2026-01-10",
            "favorecido_nome": "X", "classe": 3, "parcelas": 3,
        })
        assert r["success"] is True
        assert r["codigos"] == [100, 101, 102]
        datas = [p[3] for q, p in cur.queries if q.startswith("INSERT INTO previsoes")]
        assert datas == ["2026-01-10", "2026-02-10", "2026-03-10"]


class TestDeleteSync:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1, False)
        assert r["success"] is False

    def test_bloqueada_por_outra_tela(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_transf_caixa": 5}])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1, False)
        assert r["success"] is False
        assert "outra tela" in r["message"]

    def test_exige_autorizacao_quando_senha_gerente_ligada(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_transf_caixa": 0}, {"senha_gerente_cx": True}])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1, False)
        assert r["success"] is False
        assert r["exige_autorizacao"] is True

    def test_autorizado_exclui(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_transf_caixa": 0}, {"senha_gerente_cx": True}])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1, True)
        assert r["success"] is True
        assert conn.committed is True

    def test_sem_senha_gerente_exclui_direto(self, monkeypatch):
        cur = FakeCursor(one=[{"cod_transf_caixa": 0}, {"senha_gerente_cx": False}])
        _patch(monkeypatch, cur)
        r = svc._delete_sync("srv", "bd", 1, False)
        assert r["success"] is True


PREV_PAGAR = {
    "codigo": 1, "conta": 1, "classe": 3, "sub_classe": None, "documento": None,
    "data_documento": date(2026, 1, 1), "data_vencimento": date(2026, 1, 10),
    "favorecido": 5, "valor": 100.0, "tipo": 0, "memorando": "Aluguel", "frequencia": 4,
    "cod_transf_caixa": 0,
}
PREV_RECEBER = {**PREV_PAGAR, "tipo": 1, "frequencia": 10}
PREV_TRANSF = {**PREV_PAGAR, "tipo": 2, "classe": 2, "frequencia": 10}
GRUPOS_DOC = (1, 2, 3)


class TestEfetivarUm:
    def test_bloqueia_de_outra_tela(self, monkeypatch):
        cur = FakeCursor(one=[{**PREV_PAGAR, "cod_transf_caixa": 900}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert r["success"] is False

    def test_pagar_debita_conta(self, monkeypatch):
        cur = FakeCursor(one=[PREV_PAGAR, {"codigo": 700}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert r["success"] is True
        saldo_q = [q for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        assert len(saldo_q) == 1

    def test_receber_credita_conta(self, monkeypatch):
        cur = FakeCursor(one=[PREV_RECEBER, {"codigo": 701}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert r["success"] is True
        saldo_q = [q for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        assert len(saldo_q) == 1

    def test_transferencia_debita_origem_credita_destino(self, monkeypatch):
        cur = FakeCursor(one=[PREV_TRANSF, {"codigo": 702}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert r["success"] is True
        debitos = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        creditos = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        assert debitos[0][1] == 1   # conta origem
        assert creditos[0][1] == 2  # conta destino

    def test_unica_vez_exclui_previsao(self, monkeypatch):
        cur = FakeCursor(one=[PREV_RECEBER, {"codigo": 703}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert r["success"] is True
        assert any(q.startswith("DELETE FROM previsoes WHERE codigo") for q, p in cur.queries)

    def test_recorrente_avanca_data(self, monkeypatch):
        cur = FakeCursor(one=[PREV_PAGAR, {"codigo": 704}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert r["success"] is True
        updates = [p for q, p in cur.queries if q.startswith("UPDATE previsoes SET data_vencimento")]
        assert len(updates) == 1
        assert updates[0][0] == "2026-02-10"

    def test_copia_rateio_para_movimentacoes_centro_custo(self, monkeypatch):
        cur = FakeCursor(one=[PREV_PAGAR, {"codigo": 705}])
        _patch(monkeypatch, cur)
        svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC)
        assert any(q.startswith("INSERT INTO movimentacoes_centro_custo") and "SELECT" in q for q, p in cur.queries)

    def test_conta_override_lanca_na_conta_informada(self, monkeypatch):
        # "Transferência Para Movimentação" (FrmManPrev.frm:2095-2105) —
        # campo Conta do modal manda a movimentação pra outra conta, não a
        # gravada na previsão (conta=1). Achado do usuário 2026-08-31.
        cur = FakeCursor(one=[PREV_PAGAR, {"codigo": 706}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC, conta_override=9)
        assert r["success"] is True
        insert = [p for q, p in cur.queries if q.startswith("INSERT INTO movimentacoes")][0]
        assert insert[0] == 9  # conta na INSERT é a override, não a 1 da previsão
        saldo = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")][0]
        assert saldo[1] == 9

    def test_conta_override_transferencia_so_troca_origem(self, monkeypatch):
        cur = FakeCursor(one=[PREV_TRANSF, {"codigo": 707}])
        _patch(monkeypatch, cur)
        r = svc._efetivar_um_sync(cur, 1, None, GRUPOS_DOC, conta_override=9)
        assert r["success"] is True
        debitos = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual -")]
        creditos = [p for q, p in cur.queries if q.startswith("UPDATE contas SET saldo_atual = CAST(saldo_atual +")]
        assert debitos[0][1] == 9   # origem = override, não a 1 da previsão
        assert creditos[0][1] == 2  # destino (classe) nunca muda


class TestEfetivarSync:
    def test_isola_falha_por_item(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": None},  # grupo financeiro not found path simplified below
        ])
        # Simplifica: monkeypatch direto na função de resolução de grupos
        monkeypatch.setattr(svc, "_resolver_grupos_gestor_documentos_sync", lambda cur_: (1, 2, 3))

        def _fake_item(cur_, codigo, data_liq, grupos, conta_override=None):
            if codigo == 1:
                return {"success": True}
            return {"success": False, "message": "erro"}

        monkeypatch.setattr(svc, "_efetivar_um_sync", _fake_item)
        conn = _patch(monkeypatch, FakeCursor())
        r = svc._efetivar_sync("srv", "bd", [1, 2])
        assert r["success"] is False
        assert r["efetivados"] == [1]
        assert r["falhas"][0]["codigo"] == 2
        assert conn.committed is True
