"""Testes UNITÁRIOS do Motor de Formulário Dinâmico (Cadastro de Layout +
Preenchimento). Ver PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B:
Clínica (Agendamento)"."""
import services.layout_service as svc


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


LAYOUT_ROW = {
    "codigo": 1, "descricao": "Ficha de Anamnese", "cliente": 0, "fornecedor": 0,
    "funcionario": 0, "produto": 0, "servico": 0, "pedido_venda": 0, "os": 0,
    "profissional": 0, "contrato": 0,
}
CAMPO_ROW = {
    "codigo": 5, "campo1": "Dados Gerais", "campo2": "Peso", "tipo": 3, "calculado": 0,
    "calc_campo1": None, "calc_campo2": None, "operador": "", "valor_minimo": None,
    "valor_maximo": None, "unidade_medida": "Kg", "decimais": 2, "tamanho": 0,
    "campo_agrupado": 0, "tipo_descricao": "Decimal",
}


class TestListLayouts:
    def test_lista(self, monkeypatch):
        cur = FakeCursor(many=[[dict(LAYOUT_ROW)]])
        _patch(monkeypatch, cur)
        r = svc._list_layouts_sync("srv", "bd")
        assert r["success"] is True
        assert r["items"][0]["descricao"] == "Ficha de Anamnese"


class TestSaveLayout:
    def test_cria_novo(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 7}])
        _patch(monkeypatch, cur)
        r = svc._save_layout_sync("srv", "bd", None, {"descricao": "Novo Layout", "cliente": True})
        assert r["success"] is True and r["codigo"] == 7
        insert_q = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO layout")]
        assert len(insert_q) == 1

    def test_atualiza_existente(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._save_layout_sync("srv", "bd", 1, {"descricao": "Atualizado"})
        assert r["success"] is True and r["codigo"] == 1
        update_q = [q for q, _ in cur.queries if q.strip().startswith("UPDATE layout SET")]
        assert len(update_q) == 1

    def test_sem_descricao_bloqueia(self, monkeypatch):
        r = svc._save_layout_sync("srv", "bd", None, {"descricao": ""})
        assert r["success"] is False


class TestDeleteLayout:
    def test_bloqueia_se_ja_tem_preenchimento(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._delete_layout_sync("srv", "bd", 1)
        assert r["success"] is False and "preenchimentos" in r["message"].lower()

    def test_exclui_com_sucesso(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._delete_layout_sync("srv", "bd", 1)
        assert r["success"] is True and conn.committed is True


class TestCamposLayout:
    def test_lista_campos(self, monkeypatch):
        cur = FakeCursor(many=[[dict(CAMPO_ROW)]])
        _patch(monkeypatch, cur)
        r = svc._list_campos_sync("srv", "bd", 1)
        assert r["success"] is True
        assert r["items"][0]["unidade_medida"] == "Kg"

    def test_cria_campo(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 9}])
        _patch(monkeypatch, cur)
        r = svc._save_campo_sync("srv", "bd", None, {"layout": 1, "campo1": "Peso", "tipo": 3})
        assert r["success"] is True and r["codigo"] == 9

    def test_sem_layout_ou_campo1_bloqueia(self, monkeypatch):
        r = svc._save_campo_sync("srv", "bd", None, {"layout": None, "campo1": ""})
        assert r["success"] is False

    def test_exclui_campo(self, monkeypatch):
        cur = FakeCursor()
        conn = _patch(monkeypatch, cur)
        r = svc._delete_campo_sync("srv", "bd", 9)
        assert r["success"] is True and conn.committed is True


class TestPossiveisEPreenchidos:
    def test_possiveis_generico_por_entidade(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 1, "descricao": "Layout Cliente"}]])
        _patch(monkeypatch, cur)
        r = svc._list_possiveis_sync("srv", "bd", 1, 999)  # entidade=1 (Cliente)
        assert r["success"] is True and r["items"][0]["descricao"] == "Layout Cliente"

    def test_possiveis_agenda_sem_agendamento(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._list_possiveis_sync("srv", "bd", svc.ENTIDADE_AGENDA, 900)
        assert r["success"] is True and r["items"] == []

    def test_possiveis_agenda_por_servico_profissional(self, monkeypatch):
        cur = FakeCursor(
            one=[{"servico": "S100", "funcionario": 10}],
            many=[[{"codigo": 2, "descricao": "Ficha de Anamnese"}]],
        )
        _patch(monkeypatch, cur)
        r = svc._list_possiveis_sync("srv", "bd", svc.ENTIDADE_AGENDA, 900)
        assert r["success"] is True and r["items"][0]["descricao"] == "Ficha de Anamnese"

    def test_preenchidos(self, monkeypatch):
        cur = FakeCursor(many=[[{"codigo": 3, "descricao": "Ficha", "data": "2026-08-01"}]])
        _patch(monkeypatch, cur)
        r = svc._list_preenchidos_sync("srv", "bd", svc.ENTIDADE_AGENDA, 900)
        assert r["success"] is True and r["items"][0]["codigo"] == 3


class TestGetPreenchimento:
    def test_nao_encontrado(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._get_preenchimento_sync("srv", "bd", 3)
        assert r["success"] is False

    def test_encontrado_com_respostas(self, monkeypatch):
        cur = FakeCursor(
            one=[{"codigo": 3, "codlayout": 1, "data": "2026-08-01", "obs": "", "obs_descricao": ""}],
            many=[
                [{"campo1": "Dados Gerais", "campo2": "Peso", "conteudo": "70", "codlayoutcampo": 5}],
                [dict(CAMPO_ROW)],
            ],
        )
        _patch(monkeypatch, cur)
        r = svc._get_preenchimento_sync("srv", "bd", 3)
        assert r["success"] is True
        assert r["campos"][0]["conteudo"] == "70"


class TestPreencher:
    def test_sem_dados_obrigatorios_bloqueia(self, monkeypatch):
        r = svc._preencher_sync("srv", "bd", {"entidade": None})
        assert r["success"] is False

    def test_cria_novo_preenchimento(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 30}, dict(CAMPO_ROW)])
        conn = _patch(monkeypatch, cur)
        r = svc._preencher_sync("srv", "bd", {
            "entidade": svc.ENTIDADE_AGENDA, "codentidade": 900, "codlayout": 1,
            "respostas": [{"codigo_campo": 5, "conteudo": "70"}],
        })
        assert r["success"] is True and r["codigo"] == 30
        assert conn.committed is True
        insert_resp = [q for q, _ in cur.queries if q.strip().startswith("INSERT INTO layout_preenchido")]
        assert len(insert_resp) == 1

    def test_atualiza_preenchimento_existente_substitui_respostas(self, monkeypatch):
        cur = FakeCursor(one=[dict(CAMPO_ROW)])
        _patch(monkeypatch, cur)
        r = svc._preencher_sync("srv", "bd", {
            "entidade": svc.ENTIDADE_AGENDA, "codentidade": 900, "codlayout": 1, "codigo": 30,
            "respostas": [{"codigo_campo": 5, "conteudo": "72"}],
        })
        assert r["success"] is True and r["codigo"] == 30
        delete_q = [q for q, _ in cur.queries if q.strip().startswith("DELETE FROM layout_preenchido")]
        assert len(delete_q) == 1
