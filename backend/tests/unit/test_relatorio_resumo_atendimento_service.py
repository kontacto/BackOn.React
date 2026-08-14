"""Testes unitários de Resumo Atendimento — réplica de
`Kontacto\\frmrelos.frm` (VB_Name="FrmRelOSs"). Cobre filtros e a
inclusão/zeragem de coluna por destino (Cliente Pg./Contrato/Garantia)."""
import services.relatorio_resumo_atendimento_service as svc


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _row(**over):
    base = {
        "codigo": 1, "data_termino": "2026-01-10", "resumo": "Troca de óleo",
        "tipo_desc": "Revisão", "hora_inicio": "08:00", "hora_fim": "09:00",
        "tecnico_nome": "Zé", "tot_horas": 1.0, "tot_servicos": 100.0, "tot_pecas": 50.0,
        "tot_cliente_pg": 150.0, "tot_contrato": 0.0, "tot_garantia": 0.0,
    }
    base.update(over)
    return base


class TestQuery:
    def test_sem_filtros_nao_usa_where(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, True, True, True
        )
        query, params = cur.queries[-1]
        assert "t.codigo = o.tipo  ORDER BY" in query  # sem WHERE entre o JOIN e o ORDER BY
        assert params == ()

    def test_filtro_tipo_usa_os_tipo(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, 3, None, None, None, True, True, True
        )
        query, params = cur.queries[-1]
        assert "o.tipo = %s" in query
        assert "posicao_os" not in query
        assert 3 in params

    def test_filtro_tecnico_usa_subquery_max_executor(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, 7, None, None, True, True, True
        )
        query, params = cur.queries[-1]
        assert "MAX(executor)" in query
        assert 7 in params

    def test_situacao_csv(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        svc._resumo_atendimento_sync(
            "srv", "bd", None, None, "F,PG", None, None, None, None, True, True, True
        )
        query, params = cur.queries[-1]
        assert "o.situacao IN (%s,%s)" in query
        assert "F" in params and "PG" in params


class TestInclusaoEZeragem:
    def test_todos_incluidos_por_padrao(self, monkeypatch):
        cur = FakeCursor(rows=[_row()])
        _patch(monkeypatch, cur)
        r = svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, True, True, True
        )
        assert len(r["itens"]) == 1
        assert r["itens"][0]["tot_cliente_pg"] == 150.0

    def test_excluir_cliente_pg_zera_coluna_e_remove_se_so_tinha_isso(self, monkeypatch):
        cur = FakeCursor(rows=[_row()])
        _patch(monkeypatch, cur)
        r = svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, False, True, True
        )
        # única fonte de valor era cliente_pg; desmarcado -> OS não aparece
        assert r["itens"] == []

    def test_excluir_cliente_pg_mas_os_tem_contrato_continua_aparecendo(self, monkeypatch):
        cur = FakeCursor(rows=[_row(tot_contrato=200.0)])
        _patch(monkeypatch, cur)
        r = svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, False, True, True
        )
        assert len(r["itens"]) == 1
        assert r["itens"][0]["tot_cliente_pg"] == 0.0
        assert r["itens"][0]["tot_contrato"] == 200.0

    def test_totais_gerais_somam_apenas_itens_incluidos(self, monkeypatch):
        cur = FakeCursor(rows=[_row(codigo=1, tot_cliente_pg=100.0), _row(codigo=2, tot_cliente_pg=50.0)])
        _patch(monkeypatch, cur)
        r = svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, True, True, True
        )
        assert r["totais"]["cliente_pg"] == 150.0

    def test_resumo_remove_quebras_de_linha(self, monkeypatch):
        cur = FakeCursor(rows=[_row(resumo="Linha1\r\nLinha2")])
        _patch(monkeypatch, cur)
        r = svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, True, True, True
        )
        assert "\n" not in r["itens"][0]["resumo"] and "\r" not in r["itens"][0]["resumo"]

    def test_sem_resultados(self, monkeypatch):
        cur = FakeCursor(rows=[])
        _patch(monkeypatch, cur)
        r = svc._resumo_atendimento_sync(
            "srv", "bd", None, None, None, None, None, None, None, True, True, True
        )
        assert r["success"] is True
        assert r["itens"] == []
        assert r["totais"]["cliente_pg"] == 0.0
