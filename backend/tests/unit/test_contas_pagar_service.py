"""Testes unitários de Financeiro > Contas a Pagar (espelho de
test_contas_receber_service.py — ver services/contas_pagar_service.py pro
rastreio da fonte: `Geral/frmTraNFPag.frm` + `Revenda/frmmandup.frm`)."""
from datetime import date

import services.contas_pagar_service as svc


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


FLAGS_ROW = {"agrupa_nf_receber": 0, "geranumerodup": 0, "numero_dup": None, "desmembramento_dup": "", "fantasia": ""}


class TestListar:
    def test_lista_com_fallback_fantasia(self, monkeypatch):
        rows = [{
            "codigo": 1, "fornecedor": 10, "fornecedor_nome": "RAZAO SOCIAL LTDA", "fornecedor_fantasia": "APELIDO",
            "duplicata": 999, "desmembramento": "1", "dt_emissao": date(2026, 8, 1), "valor": 150.0,
            "situacao": "A", "num_parcelas": 1, "parcelas_pagas": 0,
            "proximo_vencimento": date(2020, 1, 1), "valor_em_aberto": 150.0,
        }]
        cur = FakeCursor(many=[rows])
        _patch(monkeypatch, cur)
        r = svc._listar_sync("srv", "bd", {})
        assert r["success"] is True
        assert r["items"][0]["fornecedor_nome"] == "APELIDO"
        assert r["items"][0]["vencido"] is True

    def test_filtro_busca_inclui_nome_e_fantasia(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._listar_sync("srv", "bd", {"busca": "acme"})
        sql = cur.queries[0][0]
        assert "f.nome LIKE" in sql and "f.fantasia LIKE" in sql


class TestCriarAvulsa:
    def _req(self, **over):
        base = {
            "fornecedor": 10, "numero": 555, "serie": "1", "tipo_mov": "E01",
            "dt_emissao": "2026-08-28", "valor": 100.0, "parcelas": 1,
            "dt_primeiro_vencimento": "2026-09-28", "observacao": "teste",
        }
        base.update(over)
        return base

    def test_sucesso_grava_pagar_codigo_no_link_nf(self, monkeypatch):
        cur = FakeCursor(one=[
            {"nome": "Fornecedor Teste"},          # SELECT Fornecedor
            None,                                    # duplicidade: não existe
            {"codigo": 700},                         # INSERT Pagar OUTPUT -> pagar_codigo
            dict(FLAGS_ROW),                         # _controle_flags_sync
            {"codigo": 900},                         # INSERT Duplicata_Pagar OUTPUT -> dup_codigo
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req())
        assert r["success"] is True
        assert r["codigo"] == 900
        assert conn.committed is True
        insert_link = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Pag_Nf")][0]
        assert insert_link == (900, 700)
        insert_pagar = [q for q, p in cur.queries if q.startswith("INSERT INTO Pagar")][0]
        assert "'DU'" in insert_pagar
        assert "NULL" in insert_pagar  # cod_n_fiscal explícito, nunca omitido (achado ao vivo do lado Receber)

    def test_fornecedor_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req())
        assert r["success"] is False
        assert "Fornecedor não encontrado" in r["message"]

    def test_bloqueia_duplicidade(self, monkeypatch):
        cur = FakeCursor(one=[{"nome": "Fornecedor Teste"}, {"codigo": 5}])
        _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req())
        assert r["success"] is False
        assert "Já existe um lançamento" in r["message"]

    def test_split_em_3_parcelas_grava_3_vencimentos(self, monkeypatch):
        cur = FakeCursor(one=[
            {"nome": "Fornecedor Teste"}, None, {"codigo": 700}, dict(FLAGS_ROW), {"codigo": 900},
        ])
        _patch(monkeypatch, cur)
        r = svc._criar_avulsa_sync("srv", "bd", self._req(parcelas=3, valor=100.0))
        assert r["success"] is True
        inserts_venc = [q for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Pag_Venc")]
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
        cur = FakeCursor(one=[self._parcela(), {"total": 3, "pagas": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is True
        assert conn.committed is True
        update_dp = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Pagar")][0]
        assert update_dp == (1, "A", 900)

    def test_sucesso_todas_pagas_marca_duplicata_pg(self, monkeypatch):
        cur = FakeCursor(one=[self._parcela(), {"total": 1, "pagas": 1}])
        _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req())
        assert r["success"] is True
        update_dp = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Pagar")][0]
        assert update_dp == (1, "PG", 900)

    def test_grava_campos_novos_inclusive_num_doc_pag(self, monkeypatch):
        """`num_doc_pag` é exclusivo do lado Pagar (não existe em
        `Duplicata_Rec_Venc`) — confirmado via INFORMATION_SCHEMA ao vivo,
        e é o único campo extra em relação ao lado Receber."""
        cur = FakeCursor(one=[self._parcela(), {"total": 1, "pagas": 1}])
        _patch(monkeypatch, cur)
        req = self._req(num_doc_pag="NF-12345", banco_cedente=341, agencia_cedente=1234)
        r = svc._baixar_parcela_sync("srv", "bd", req)
        assert r["success"] is True
        update_venc = [q for q, p in cur.queries if q.startswith("UPDATE Duplicata_Pag_Venc")][0]
        assert "num_doc_pag" in update_venc
        valores = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Pag_Venc")][0]
        assert "NF-12345" in valores

    def test_nao_bloqueia_valor_pago_maior_que_parcela(self, monkeypatch):
        """Diferente do lado Receber — o legado (`FrmManPap.frm`) NÃO tem
        essa trava (comentário de validação desativado no fonte real)."""
        cur = FakeCursor(one=[self._parcela(valor=50.0), {"total": 1, "pagas": 1}])
        conn = _patch(monkeypatch, cur)
        r = svc._baixar_parcela_sync("srv", "bd", self._req(valor_pag=999.0))
        assert r["success"] is True
        assert conn.committed is True

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


class TestCancelarBaixa:
    def test_cancela_parcela_paga(self, monkeypatch):
        cur = FakeCursor(one=[
            {"codigo": 1, "duplicata": 900, "situacao": "PG"},
            {"total": 2, "pagas": 0},
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1})
        assert r["success"] is True
        assert conn.committed is True
        update_dp = [p for q, p in cur.queries if q.startswith("UPDATE Duplicata_Pagar")][0]
        assert update_dp == (0, "A", 900)

    def test_bloqueia_parcela_ainda_nao_paga(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1, "duplicata": 900, "situacao": "A"}])
        _patch(monkeypatch, cur)
        r = svc._cancelar_baixa_sync("srv", "bd", {"codigo_venc": 1})
        assert r["success"] is False
        assert "não está paga" in r["message"]


class TestProcessarLote:
    def test_baixa_em_lote_isola_falha_de_1_item(self, monkeypatch):
        cur = FakeCursor(one=[
            {"valor": 50.0},
            {"codigo": 1, "duplicata": 900, "situacao": "A", "valor": 50.0, "dt_vencimento": date(2026, 8, 28)},
            {"total": 1, "pagas": 1},
            None,
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
            {"total": 1, "pagas": 0},
        ])
        _patch(monkeypatch, cur)
        req = {"modo": "cancelar", "vencimentos": [1]}
        r = svc._processar_lote_sync("srv", "bd", req)
        assert r["success"] is True
        assert r["processados"] == 1
        assert r["falhas"] == []


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

    def test_exclui_e_apaga_pagar_avulso(self, monkeypatch):
        cur = FakeCursor(
            one=[{"codigo": 900}, {"qtd": 0}, {"cod_n_fiscal": None}],
            many=[[{"nf_fiscal": 700}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 900)
        assert r["success"] is True
        assert conn.committed is True
        assert any(q.startswith("DELETE FROM Pagar") for q, p in cur.queries)

    def test_exclui_e_reabre_pagar_de_nf_real(self, monkeypatch):
        cur = FakeCursor(
            one=[{"codigo": 900}, {"qtd": 0}, {"cod_n_fiscal": 123}],
            many=[[{"nf_fiscal": 700}]],
        )
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 900)
        assert r["success"] is True
        update_pagar = [p for q, p in cur.queries if q.startswith("UPDATE Pagar SET situacao")][0]
        assert update_pagar == (700,)

    def test_duplicata_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._excluir_sync("srv", "bd", 999)
        assert r["success"] is False
        assert "não encontrada" in r["message"]
