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

    def test_sucesso_parcial_mantem_situacao_aberta(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "A"},   # SELECT parcela
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
            {"codigo": 1, "duplicata": 900, "situacao": "A"},
            {"total": 1, "pagas": 1},
        ])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is True
        update_dr = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Receber")][0]
        assert update_dr == (1, "PG", 900)

    def test_bloqueia_parcela_ja_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1, "duplicata": 900, "situacao": "PG"}])
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
