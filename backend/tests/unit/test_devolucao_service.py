"""Testes unitários do Gestor de Devolução (migração de FrmManDev.frm,
Fase 1 enxuta — busca de itens de venda paga, registrar devolução + Vale
de Devolução opcional, consulta, cancelar)."""
import services.devolucao_service as svc
from models.schemas import (
    DevolucaoBuscarItensRequest, DevolucaoItemRegistrar, DevolucaoRegistrarRequest,
    DevolucaoConsultaRequest, DevolucaoCancelarRequest,
)


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


def _buscar_req(**over):
    base = dict(servidor="srv", banco="bd")
    base.update(over)
    return DevolucaoBuscarItensRequest(**base)


def _registrar_req(itens, **over):
    base = dict(
        servidor="srv", banco="bd", itens=itens, emitir_vale=False, cliente=None,
        master=True, usuario_alteracao=1, classe=None, plataforma="web",
    )
    base.update(over)
    return DevolucaoRegistrarRequest(**base)


def _consulta_req(**over):
    base = dict(servidor="srv", banco="bd")
    base.update(over)
    return DevolucaoConsultaRequest(**base)


def _cancelar_req(**over):
    base = dict(servidor="srv", banco="bd", master=True, usuario_alteracao=1, classe=None, plataforma="web")
    base.update(over)
    return DevolucaoCancelarRequest(**base)


class TestListMotivos:
    def test_lista_motivos(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 1, "descricao": "Devolução Normal"}, {"codigo": 2, "descricao": "Devolução por Defeito"}]])
        _patch(monkeypatch, cur)
        result = svc._list_motivos_sync("srv", "bd")
        assert result["success"] is True
        assert len(result["items"]) == 2


class TestListItensVenda:
    def test_lista_itens_com_saldo_disponivel(self, monkeypatch):
        cur = FakeCursor(
            one=[{"devolucao": 1}],
            many=[[
                {"id_mov": 10, "comanda": 500, "data": "2026-08-01", "cliente": 1, "cliente_nome": "MARIA",
                 "codigo_int": "P001", "descricao_p": "Produto X", "descricao_s": None,
                 "qtd": 5.0, "p_unit": 20.0, "qtd_ja_devolvida": 2.0},
                {"id_mov": 11, "comanda": 500, "data": "2026-08-01", "cliente": 1, "cliente_nome": "MARIA",
                 "codigo_int": "P002", "descricao_p": "Produto Y", "descricao_s": None,
                 "qtd": 3.0, "p_unit": 10.0, "qtd_ja_devolvida": 3.0},
            ]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_itens_venda_sync(_buscar_req())
        assert result["success"] is True
        # Item 11 já foi 100% devolvido (qtd_ja_devolvida == qtd) — excluído.
        assert len(result["items"]) == 1
        assert result["items"][0]["id_mov"] == 10
        assert result["items"][0]["qtd_disponivel"] == 3.0

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 0}])
        _patch(monkeypatch, cur)
        result = svc._list_itens_venda_sync(_buscar_req())
        assert result["success"] is False
        assert result["items"] == []


class TestRegistrarDevolucao:
    def test_registra_sem_vale(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"devolucao": 1},
                {"id_mov": 10, "qtd": 5.0, "p_unit": 20.0, "situacao": "PG", "estornado": 0},
                {"qtd": 0},
                {"id_devolucao": 900},
            ],
        )
        conn = _patch(monkeypatch, cur)
        req = _registrar_req([DevolucaoItemRegistrar(id_mov=10, qtd_devolvida=2, motivo=1)])
        result = svc._registrar_devolucao_sync(req)
        assert result == {"success": True, "ids_devolucao": [900], "valor_total": 40.0, "vale_devolucao": None}
        assert conn.committed is True
        assert not any("INSERT INTO vale_devolucao" in q for q, _ in cur.queries)

    def test_registra_com_vale(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"devolucao": 1},
                {"id_mov": 10, "qtd": 5.0, "p_unit": 20.0, "situacao": "PG", "estornado": 0},
                {"qtd": 0},
                {"id_devolucao": 900},
                {"codvale": 55},
            ],
        )
        conn = _patch(monkeypatch, cur)
        req = _registrar_req(
            [DevolucaoItemRegistrar(id_mov=10, qtd_devolvida=2, motivo=1)],
            emitir_vale=True, cliente=123,
        )
        result = svc._registrar_devolucao_sync(req)
        assert result == {"success": True, "ids_devolucao": [900], "valor_total": 40.0, "vale_devolucao": 55}
        assert conn.committed is True
        assert any("INSERT INTO vale_devolucao" in q for q, _ in cur.queries)
        assert any("UPDATE devolucao_itens SET vale_devolucao" in q for q, _ in cur.queries)

    def test_bloqueia_vale_sem_cliente(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 1}])
        conn = _patch(monkeypatch, cur)
        req = _registrar_req([DevolucaoItemRegistrar(id_mov=10, qtd_devolvida=2, motivo=1)], emitir_vale=True, cliente=None)
        result = svc._registrar_devolucao_sync(req)
        assert result["success"] is False
        assert "cliente" in result["message"].lower()
        assert conn.committed is False

    def test_bloqueia_quantidade_maior_que_disponivel(self, monkeypatch):
        cur = FakeCursor(
            one=[
                {"devolucao": 1},
                {"id_mov": 10, "qtd": 5.0, "p_unit": 20.0, "situacao": "PG", "estornado": 0},
                {"qtd": 4.0},  # já devolvido 4 de 5 -> disponível 1
            ],
        )
        conn = _patch(monkeypatch, cur)
        req = _registrar_req([DevolucaoItemRegistrar(id_mov=10, qtd_devolvida=2, motivo=1)])
        result = svc._registrar_devolucao_sync(req)
        assert result["success"] is False
        assert "inválida" in result["message"].lower()
        assert conn.rolled is True

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 0}])
        _patch(monkeypatch, cur)
        req = _registrar_req([DevolucaoItemRegistrar(id_mov=10, qtd_devolvida=2, motivo=1)])
        result = svc._registrar_devolucao_sync(req)
        assert result["success"] is False

    def test_bloqueia_sem_itens(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 1}])
        _patch(monkeypatch, cur)
        result = svc._registrar_devolucao_sync(_registrar_req([]))
        assert result["success"] is False
        assert "item" in result["message"].lower()


class TestListDevolucoes:
    def test_lista_devolucoes_ja_registradas(self, monkeypatch):
        cur = FakeCursor(
            one=[{"devolucao": 1}],
            many=[[{
                "id_devolucao": 900, "CodMov": 10, "Data": "2026-08-01", "Qtd_Devolvida": 2.0,
                "vale_devolucao": 55, "Status": 1, "comanda": 500, "cliente_nome": "MARIA",
                "descricao_p": "Produto X", "descricao_s": None, "p_unit": 20.0,
                "motivo_descricao": "Devolução Normal", "vale_situacao": "A",
            }]],
        )
        _patch(monkeypatch, cur)
        result = svc._list_devolucoes_sync(_consulta_req())
        assert result["success"] is True
        assert result["items"][0]["valor"] == 40.0
        assert result["items"][0]["vale_devolucao"] == 55

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 0}])
        _patch(monkeypatch, cur)
        result = svc._list_devolucoes_sync(_consulta_req())
        assert result["success"] is False
        assert result["items"] == []


class TestCancelarDevolucao:
    def test_cancela_e_reverte_vale(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 1}, {"vale_devolucao": 55, "Nfe": 0}])
        conn = _patch(monkeypatch, cur)
        result = svc._cancelar_devolucao_sync(_cancelar_req(), id_devolucao=900)
        assert result == {"success": True}
        assert conn.committed is True
        assert any(q == ("UPDATE vale_devolucao SET situacao='C' WHERE codvale=%s", (55,)) for q in cur.queries)
        assert any(q == ("DELETE FROM devolucao_itens WHERE id_devolucao=%s", (900,)) for q in cur.queries)

    def test_bloqueia_se_ja_tem_nf(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 1}, {"vale_devolucao": 0, "Nfe": 123}])
        _patch(monkeypatch, cur)
        result = svc._cancelar_devolucao_sync(_cancelar_req(), id_devolucao=900)
        assert result["success"] is False
        assert "NF" in result["message"]

    def test_bloqueia_modulo_desativado(self, monkeypatch):
        cur = FakeCursor(one=[{"devolucao": 0}])
        _patch(monkeypatch, cur)
        result = svc._cancelar_devolucao_sync(_cancelar_req(), id_devolucao=900)
        assert result["success"] is False
