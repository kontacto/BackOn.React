"""Testes unitários de `_auto_abrir_dia_se_necessario` (pedido_common.py)
— lado automático da Abertura do Dia, réplica do trecho de
`MudaDataSistema` que avança `controle.Data_Movimento` sozinho quando a
empresa não usa o fluxo manual. Ver PENDENCIAS.md > "MDI Principal
(VB6)". Reconciliação de estoque do legado CONFIRMADA em desuso pela
equipe VB6 (2026-08-16) — deliberadamente não replicada, nem testada."""
from datetime import date, timedelta

import services.pedido_common as pc

HOJE = date.today().isoformat()
ONTEM = (date.today() - timedelta(days=1)).isoformat()


class SqlFakeCursor:
    """Cursor fake que responde por casamento de substring no SQL da
    última query executada — mesmo padrão de
    `test_pedido_common_doc_origem.py`/`test_pedido_common_area_atuacao.py`."""

    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self._last_q = ""
        self._one_rules: list[tuple[str, object]] = []

    def when_one(self, substr: str, value) -> "SqlFakeCursor":
        self._one_rules.append((substr, value))
        return self

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_q = q

    def fetchone(self):
        for substr, val in self._one_rules:
            if substr in self._last_q:
                return val
        return None

    def close(self):
        pass


class TestFlagLigado:
    def test_flag_ligado_nao_mexe_na_data(self):
        cur = (
            SqlFakeCursor()
            .when_one("CONTROLA_ABERTURA_DIA", {"CONTROLA_ABERTURA_DIA": True})
            .when_one("Data_Movimento FROM controle", {"Data_Movimento": ONTEM})
        )
        pc._auto_abrir_dia_se_necessario(cur)
        assert not any(q.strip().startswith("UPDATE controle") for q, _ in cur.queries)


class TestFlagDesligado:
    def test_data_ja_atualizada_nao_mexe(self):
        cur = (
            SqlFakeCursor()
            .when_one("CONTROLA_ABERTURA_DIA", {"CONTROLA_ABERTURA_DIA": False})
            .when_one("Data_Movimento FROM controle", {"Data_Movimento": HOJE})
        )
        pc._auto_abrir_dia_se_necessario(cur)
        assert not any(q.strip().startswith("UPDATE controle") for q, _ in cur.queries)

    def test_data_desatualizada_avanca_para_hoje(self):
        cur = (
            SqlFakeCursor()
            .when_one("CONTROLA_ABERTURA_DIA", {"CONTROLA_ABERTURA_DIA": False})
            .when_one("Data_Movimento FROM controle", {"Data_Movimento": ONTEM})
        )
        pc._auto_abrir_dia_se_necessario(cur)
        update_q, params = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE controle"))
        assert HOJE in params

    def test_sem_data_gravada_ainda_avanca(self):
        cur = (
            SqlFakeCursor()
            .when_one("CONTROLA_ABERTURA_DIA", {"CONTROLA_ABERTURA_DIA": False})
            .when_one("Data_Movimento FROM controle", {"Data_Movimento": None})
        )
        pc._auto_abrir_dia_se_necessario(cur)
        assert any(q.strip().startswith("UPDATE controle") for q, _ in cur.queries)


class TestFalhaSilenciosa:
    def test_excecao_nao_propaga(self):
        class BoomCursor:
            def execute(self, q, p=None):
                raise RuntimeError("coluna não existe")

        pc._auto_abrir_dia_se_necessario(BoomCursor())  # não deve levantar
