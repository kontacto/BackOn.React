"""Testes unitários do Caixa Analítico — réplica de `FrmTotCaixa.frm`.

Cobre a construção dos períodos (`_build_buckets`, um por modo de
agrupamento) e a agregação por período (`_caixa_analitico_sync`), incluindo
a mesma correção de arquitetura do Fechamento de Caixa: soma
`pedido_venda_*`/`os_*` via COMANDA_PED/comanda_os, não `comanda_*`."""
from datetime import date

import services.caixa_analitico_service as svc


class SqlFakeCursor:
    """Casamento por substring MAIS ESPECÍFICA da última query — mesmo
    padrão de `test_fechamento_caixa_service.py` (a função sob teste dispara
    uma query por tabela de forma de pagamento, em loop)."""

    def __init__(self):
        self._last_q = ""
        self._many_rules: list[tuple[str, object]] = []

    def when_many(self, substr: str, value) -> "SqlFakeCursor":
        self._many_rules.append((substr, value))
        return self

    def execute(self, q, p=None):
        self._last_q = q

    def fetchall(self):
        matches = [(substr, val) for substr, val in self._many_rules if substr in self._last_q]
        if not matches:
            return []
        return max(matches, key=lambda m: len(m[0]))[1]

    def close(self):
        pass


class FakeConn:
    def __init__(self, cur: SqlFakeCursor):
        self._cur = cur

    def cursor(self, as_dict=True):
        return self._cur

    def close(self):
        pass


class TestDow0:
    def test_domingo_e_zero(self):
        assert svc._dow0(date(2026, 7, 12)) == 0  # domingo

    def test_sabado_e_seis(self):
        assert svc._dow0(date(2026, 7, 18)) == 6  # sábado

    def test_quinta_e_quatro(self):
        assert svc._dow0(date(2026, 7, 16)) == 4  # quinta-feira (data atual do projeto)


class TestBuildBuckets:
    def test_diario_uma_linha_por_dia_no_periodo(self):
        buckets, ini, fim = svc._build_buckets(date(2026, 7, 1), date(2026, 7, 3), "diario", {0, 1, 2, 3, 4, 5, 6})
        assert [b["label"] for b in buckets] == [
            "01/07 Quarta-feira", "02/07 Quinta-feira", "03/07 Sexta-feira",
        ]
        assert (ini, fim) == (date(2026, 7, 1), date(2026, 7, 3))

    def test_diario_pula_dia_da_semana_desmarcado(self):
        # 2026-07-01 é quarta; desmarcando quarta (índice 3) a linha some.
        buckets, _, _ = svc._build_buckets(date(2026, 7, 1), date(2026, 7, 3), "diario", {0, 1, 2, 4, 5, 6})
        assert [b["label"] for b in buckets] == ["02/07 Quinta-feira", "03/07 Sexta-feira"]

    def test_dia_semana_gera_7_linhas_com_intervalo_arredondado(self):
        buckets, ini, fim = svc._build_buckets(date(2026, 7, 1), date(2026, 7, 3), "dia_semana", set())
        assert len(buckets) == 7
        assert [b["label"] for b in buckets][:2] == ["Domingo", "Segunda-feira"]
        # 2026-07-01 (quarta) arredonda pra domingo anterior; 2026-07-03 (sexta) pra sábado seguinte.
        assert ini == date(2026, 6, 28)
        assert fim == date(2026, 7, 4)
        assert all(b["ini"] == ini and b["fim"] == fim for b in buckets)
        assert [b["dow_filter"] for b in buckets] == list(range(7))

    def test_semanal_blocos_de_7_dias(self):
        buckets, ini, fim = svc._build_buckets(date(2026, 7, 1), date(2026, 7, 3), "semanal", set())
        assert ini == date(2026, 6, 28) and fim == date(2026, 7, 4)
        assert len(buckets) == 1
        assert buckets[0]["label"] == "28/06 a 04/07"

    def test_mensal_comeca_em_janeiro_do_ano_inicial(self):
        buckets, ini, fim = svc._build_buckets(date(2026, 3, 15), date(2026, 5, 10), "mensal", set())
        assert ini == date(2026, 1, 1)
        assert fim == date(2026, 5, 31)
        assert [b["label"] for b in buckets] == ["Janeiro/2026", "Fevereiro/2026", "Março/2026", "Abril/2026", "Maio/2026"]

    def test_trimestral_cobre_ano_inteiro(self):
        buckets, ini, fim = svc._build_buckets(date(2026, 5, 1), date(2026, 5, 1), "trimestral", set())
        assert ini == date(2026, 1, 1) and fim == date(2026, 12, 31)
        assert [b["label"] for b in buckets] == [
            "1º Trimestre / 2026", "2º Trimestre / 2026", "3º Trimestre / 2026", "4º Trimestre / 2026",
        ]
        assert buckets[1]["ini"] == date(2026, 4, 1) and buckets[1]["fim"] == date(2026, 6, 30)

    def test_semestral_duas_linhas(self):
        buckets, _, _ = svc._build_buckets(date(2026, 1, 1), date(2026, 12, 31), "semestral", set())
        assert [b["label"] for b in buckets] == ["1º Semestre / 2026", "2º Semestre / 2026"]
        assert buckets[0]["fim"] == date(2026, 6, 30)
        assert buckets[1]["ini"] == date(2026, 7, 1) and buckets[1]["fim"] == date(2026, 12, 31)

    def test_anual_uma_linha_por_ano(self):
        buckets, ini, fim = svc._build_buckets(date(2025, 6, 1), date(2026, 3, 1), "anual", set())
        assert [b["label"] for b in buckets] == ["2025", "2026"]
        assert ini == date(2025, 1, 1) and fim == date(2026, 12, 31)

    def test_agrupamento_invalido_levanta(self):
        import pytest
        with pytest.raises(ValueError):
            svc._build_buckets(date(2026, 1, 1), date(2026, 1, 1), "bogus", set())


class TestCaixaAnaliticoSync:
    def test_diario_soma_por_tipo_entradas_saidas(self, monkeypatch):
        cur = (
            SqlFakeCursor()
            .when_many("pedido_venda_dinheiro", [{"data": date(2026, 7, 1), "total": 100.0}])
            .when_many("pedido_venda_cartao", [{"data": date(2026, 7, 1), "total": 50.0}])
            .when_many("entrada_caixa", [{"data": date(2026, 7, 1), "total": 20.0}])
            .when_many("saida_caixa", [{"data": date(2026, 7, 1), "total": 5.0}])
        )
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))

        out = svc._caixa_analitico_sync("srv", "bd", "2026-07-01", "2026-07-01", "diario", [0, 1, 2, 3, 4, 5, 6])
        assert out["success"] is True
        assert len(out["linhas"]) == 1
        linha = out["linhas"][0]
        assert linha["dinheiro"] == 100.0
        assert linha["credito"] == 50.0
        assert linha["total_recebidos"] == 150.0
        assert linha["total_entradas"] == 20.0
        assert linha["total_saidas"] == 5.0
        assert linha["total_caixa"] == 165.0  # 150 + 20 - 5
        assert out["totais"]["total_caixa"] == 165.0

    def test_periodo_invalido(self, monkeypatch):
        out = svc._caixa_analitico_sync("srv", "bd", "2026-07-10", "2026-07-01", "diario", [0, 1, 2, 3, 4, 5, 6])
        assert out["success"] is False

    def test_data_malformada(self, monkeypatch):
        out = svc._caixa_analitico_sync("srv", "bd", "não-é-data", "2026-07-01", "diario", [0, 1, 2, 3, 4, 5, 6])
        assert out["success"] is False

    def test_dia_sem_lancamento_fica_zerado(self, monkeypatch):
        cur = SqlFakeCursor()  # nenhuma regra -> fetchall sempre []
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cur))
        out = svc._caixa_analitico_sync("srv", "bd", "2026-07-01", "2026-07-01", "diario", [0, 1, 2, 3, 4, 5, 6])
        assert out["linhas"][0]["total_caixa"] == 0.0
