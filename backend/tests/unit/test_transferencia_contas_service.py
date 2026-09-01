"""Testes unitários de Transferência p/Contas Pagar/Receber (migração de
`Geral\\FrmTransfContas.frm` — ver services/transferencia_contas_service.py
pro rastreio completo da fonte)."""
import services.transferencia_contas_service as svc


class FakeCursor:
    """Fila de resultados na ordem de chamada — cada `fetchone()`/`fetchall()`
    consome o próximo item da fila correspondente (mesmo padrão já usado em
    test_devolucao_service.py)."""
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


FLAGS_SIMPLES = {"agrupa_nf_receber": False, "geranumerodup": False, "numero_dup": None, "desmembramento_dup": ""}
FLAGS_AGRUPA = {"agrupa_nf_receber": True, "geranumerodup": False, "numero_dup": None, "desmembramento_dup": ""}
FLAGS_GERANUM = {"agrupa_nf_receber": False, "geranumerodup": True, "numero_dup": 500, "desmembramento_dup": "D"}

NF_ROW = {
    "codigo": 10, "fornecedor": 1, "num_nf": 999.0, "serie_nf": "1", "pagar": "S",
    "mov": "S01", "data_nf": "2026-08-01", "data_mov": "2026-08-01", "valor_total": 150.0,
}


class TestListarPendentesSync:
    # Achado real 2026-08-28 (Adriana/suporte, "KONTACTO REAL"): a listagem
    # mostrava Notas de Saída cuja comanda vinculada já estava baixada no
    # Contas a Receber — sempre falhavam ao transferir (mesmo bloqueio de
    # `_bloqueio_comanda_ja_transferida`). Réplica fiel do legado, mas o
    # usuário pediu explicitamente pra excluir da listagem em vez de deixar
    # o usuário descobrir só depois de tentar transferir.
    def test_exclui_nota_com_comanda_ja_baixada_da_query(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd")
        assert r["success"] is True
        query = cur.queries[0][0]
        assert "NOT EXISTS" in query
        assert "comanda_nf" in query
        assert "transf_caixa" in query


class TestNfRecebe:
    def test_sucesso_sem_agrupar_sem_gerar_numero(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(NF_ROW), None, None, {"codigo": 100}, {"codigo": 200}],
            many=[[], []],
        )
        r = svc._nf_recebe_sync(cur, 10, FLAGS_SIMPLES)
        assert r["success"] is True
        # Duplicata usa o próprio número da nota (999), não sequenciada.
        insert_dup = [q for q, p in cur.queries if "INSERT INTO Duplicata_Receber" in q][0]
        assert insert_dup  # achado — confirma que o INSERT rodou
        update_nf = [p for q, p in cur.queries if q.startswith("UPDATE N_fiscal")][0]
        assert update_nf == (10,)
        # Bug real corrigido 2026-08-28: Duplicata_Rec_Nf.nf_fiscal grava o
        # codigo de Receber (100), NUNCA o codigo de N_fiscal (10) — apesar
        # do nome da coluna, confirmado contra FRMCONNFREC.frm/frmTraNFRec.frm.
        insert_nf_link = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Nf")][0]
        assert insert_nf_link == (200, 100)

    def test_nota_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        r = svc._nf_recebe_sync(cur, 999, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_nota_ja_transferida(self, monkeypatch):
        nf = dict(NF_ROW, pagar="T")
        cur = FakeCursor(one=[nf])
        r = svc._nf_recebe_sync(cur, 10, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "já foi transferida" in r["message"]

    def test_bloqueia_duplicidade(self, monkeypatch):
        cur = FakeCursor(one=[dict(NF_ROW), {"codigo": 5}])
        r = svc._nf_recebe_sync(cur, 10, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "já existe tal Nota Fiscal em Contas a Receber" in r["message"]

    def test_bloqueia_comanda_ja_transferida(self, monkeypatch):
        cur = FakeCursor(one=[dict(NF_ROW), None, {"comanda": 55, "transf_caixa": "S"}])
        r = svc._nf_recebe_sync(cur, 10, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "já está baixada no Contas a Receber" in r["message"]

    def test_agrupa_soma_em_duplicata_existente(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(NF_ROW), None, None, {"codigo": 100}, {"codigo": 300}],
            many=[[], []],
        )
        r = svc._nf_recebe_sync(cur, 10, FLAGS_AGRUPA)
        assert r["success"] is True
        # Achou duplicata aberta (codigo 300) — UPDATE de soma, sem INSERT novo.
        assert any(q.startswith("UPDATE Duplicata_Receber SET valor = valor +") for q, p in cur.queries)
        assert not any("INSERT INTO Duplicata_Receber" in q for q, p in cur.queries)
        insert_nf_link = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Rec_Nf")][0]
        assert insert_nf_link == (300, 100)

    def test_geranumerodup_incrementa_controle(self, monkeypatch):
        cur = FakeCursor(
            one=[dict(NF_ROW), None, None, {"codigo": 100}, {"codigo": 400}],
            many=[[], []],
        )
        r = svc._nf_recebe_sync(cur, 10, FLAGS_GERANUM)
        assert r["success"] is True
        update_controle = [p for q, p in cur.queries if q.startswith("UPDATE controle SET numero_dup")][0]
        assert update_controle == (501,)


class TestNfPaga:
    def test_sucesso(self, monkeypatch):
        nf = dict(NF_ROW, mov="E01")
        cur = FakeCursor(
            one=[nf, None, {"codigo": 700}, {"codigo": 800}],
            many=[[], []],
        )
        r = svc._nf_paga_sync(cur, 10, FLAGS_SIMPLES)
        assert r["success"] is True
        assert any("INSERT INTO Pagar" in q for q, p in cur.queries)
        assert any("INSERT INTO Duplicata_Pagar" in q for q, p in cur.queries)
        assert any("INSERT INTO Duplicata_Pag_Venc" in q for q, p in cur.queries)
        # Bug real corrigido 2026-08-28 (mesmo padrão do lado Receber):
        # Duplicata_Pag_Nf.nf_fiscal grava o codigo de Pagar (700), não de
        # N_fiscal (10).
        insert_nf_link = [p for q, p in cur.queries if q.startswith("INSERT INTO Duplicata_Pag_Nf")][0]
        assert insert_nf_link == (800, 700)

    def test_bloqueia_duplicidade(self, monkeypatch):
        nf = dict(NF_ROW, mov="E01")
        cur = FakeCursor(one=[nf, {"codigo": 9}])
        r = svc._nf_paga_sync(cur, 10, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "já existe tal Nota Fiscal em Contas a Pagar" in r["message"]


class TestTransferirComanda:
    def test_sucesso(self, monkeypatch):
        comanda = {"comanda": 55, "cliente": 3, "valor_venda": 88.0, "transf_caixa": None, "situacao": "PG"}
        cur = FakeCursor(one=[comanda, {"codigo": 900}])
        r = svc._transferir_comanda_sync(cur, 55, FLAGS_SIMPLES)
        assert r["success"] is True
        assert any(q.startswith("UPDATE comanda SET transf_caixa") for q, p in cur.queries)

    def test_bloqueia_ja_transferida(self, monkeypatch):
        comanda = {"comanda": 55, "cliente": 3, "valor_venda": 88.0, "transf_caixa": "S", "situacao": "PG"}
        cur = FakeCursor(one=[comanda])
        r = svc._transferir_comanda_sync(cur, 55, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "já foi transferida" in r["message"]

    def test_bloqueia_nao_paga(self, monkeypatch):
        comanda = {"comanda": 55, "cliente": 3, "valor_venda": 88.0, "transf_caixa": None, "situacao": "A"}
        cur = FakeCursor(one=[comanda])
        r = svc._transferir_comanda_sync(cur, 55, FLAGS_SIMPLES)
        assert r["success"] is False
        assert "não está paga" in r["message"]


class TestTransferirSync:
    def test_isola_falha_de_item_sem_derrubar_os_outros(self, monkeypatch):
        # 1º item: NF inexistente (falha). 2º item: Comanda válida (sucesso).
        cur = FakeCursor(
            one=[
                {"agrupa_nf_receber": False, "geranumerodup": False, "numero_dup": None, "desmembramento_dup": ""},
                None,  # NF_RECEBE: nota não encontrada
                {"comanda": 55, "cliente": 3, "valor_venda": 88.0, "transf_caixa": None, "situacao": "PG"},
                {"codigo": 900},
            ],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._transferir_sync("srv", "bd", [
            {"codnota": 999, "flag": "Contas a Receber"},
            {"codnota": 55, "flag": "Comanda"},
        ])
        assert r["success"] is False  # tem falha
        assert r["transferidos"] == [55]
        assert len(r["falhas"]) == 1
        assert r["falhas"][0]["codnota"] == 999
        assert conn.committed is True  # o sucesso parcial ainda é commitado

    def test_flag_desconhecida(self, monkeypatch):
        cur = FakeCursor(one=[FLAGS_SIMPLES.copy()])
        _patch(monkeypatch, cur)
        r = svc._transferir_sync("srv", "bd", [{"codnota": 1, "flag": "???"}])
        assert r["success"] is False
        assert r["falhas"][0]["message"].startswith("Tipo desconhecido")
