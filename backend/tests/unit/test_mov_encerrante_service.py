"""Testes UNITÁRIOS de Movimentação de Encerrantes (Posto de Combustível).

Sem Excluir (ver docstring do service — legado tinha bug real/reversão
sem rastreabilidade, não replicado).
"""
import services.mov_encerrante_service as svc


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
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


MODULO_ON = {"Posto": 1}
MODULO_OFF = {"Posto": 0}


def _args(**over):
    base = dict(
        servidor="srv", banco="bd", data="2026-07-13", turno=1, bomba=1, funcionario=1,
        contador_inicial=1000.0, contador_final=1100.0, afericao=0.0,
    )
    base.update(over)
    return base


class TestValidacoesSemBanco:
    def test_afericao_maior_que_final(self):
        r = svc._save_sync(**_args(afericao=2000))
        assert r["success"] is False and "aferição" in r["message"].lower()

    def test_final_menor_que_inicial(self):
        r = svc._save_sync(**_args(contador_final=900))
        assert r["success"] is False and "contador final" in r["message"].lower()

    def test_final_menor_que_inicial_mais_afericao(self):
        r = svc._save_sync(**_args(contador_inicial=1000, contador_final=1050, afericao=100))
        assert r["success"] is False and "aferição" in r["message"].lower()


class TestModuloDesativado:
    def test_save_bloqueado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_OFF])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(**_args())
        assert r["success"] is False and "desativado" in r["message"].lower()
        assert conn.committed is False


class TestSaveComMock:
    def test_data_futura_bloqueada(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"data_movimento": "2026-07-01"}])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(**_args(data="2026-07-13"))
        assert r["success"] is False and "data de movimento" in r["message"].lower()
        assert conn.committed is False

    def test_funcionario_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"data_movimento": "2026-12-31"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(**_args())
        assert r["success"] is False and "funcion" in r["message"].lower()
        assert conn.committed is False

    def test_bomba_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[MODULO_ON, {"data_movimento": "2026-12-31"}, {"ok": 1}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(**_args())
        assert r["success"] is False and "bomba" in r["message"].lower()
        assert conn.committed is False

    def test_insere_sem_volume_positivo(self, monkeypatch):
        # contador_final == contador_inicial -> volume 0, não mexe em estoque/custo
        cur = FakeCursor(one=[
            MODULO_ON, {"data_movimento": "2026-12-31"}, {"ok": 1},
            {"combustivel": 5, "contador_final": 500.0},  # bomba
            None,  # mov_bomba não existe -> insert
        ])
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(**_args(contador_inicial=1000, contador_final=1000, afericao=0))
        assert r["success"] is True
        assert conn.committed is True
        assert any("INSERT INTO mov_bomba" in q for q, _ in cur.queries)
        assert not any("Custo_Combustivel" in q for q, _ in cur.queries)

    def test_insere_com_volume_consome_lote_fifo(self, monkeypatch):
        cur = FakeCursor(
            one=[
                MODULO_ON, {"data_movimento": "2026-12-31"}, {"ok": 1},
                {"combustivel": 5, "contador_final": 0.0},  # bomba (contador atual baixo -> avança)
                None,  # mov_bomba não existe -> insert
                {"estoque": 1000.0, "venda": 5.0, "custo": 4.0},  # combustivel
                None,  # estoque (combustivel+data+turno) não existe -> insert
            ],
            many=[[{"cod_cus": 1, "entrada": 200.0, "saida": 0.0, "custo": 4.5}]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._save_sync(**_args(contador_inicial=1000, contador_final=1100, afericao=0))
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE bomba SET contador_final" in q for q, _ in cur.queries)
        assert any("UPDATE Custo_Combustivel SET saida" in q for q, _ in cur.queries)
        assert any("INSERT INTO Mov_Combustivel" in q for q, _ in cur.queries)
