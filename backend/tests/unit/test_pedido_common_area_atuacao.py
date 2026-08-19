"""Testes unitários de `_check_area_atuacao` (pedido_common.py) — réplica de
`VerificaAreaAtuacao` (`MdiPrincipal`/`Geral\\mdl_proc.bas`), bloqueia abrir
Pedido/O.S. quando o funcionário logado não está vinculado à Área de
Atuação selecionada. Ver PENDENCIAS.md > "MDI Principal (VB6)"."""
import services.pedido_common as pc


class SqlFakeCursor:
    """Cursor fake que responde por casamento de substring no SQL da última
    query executada — mesmo padrão de `test_pedido_common_doc_origem.py`."""

    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self._last_q = ""
        self._many_rules: list[tuple[str, object]] = []
        self._one_rules: list[tuple[str, object]] = []

    def when_many(self, substr: str, value) -> "SqlFakeCursor":
        self._many_rules.append((substr, value))
        return self

    def when_one(self, substr: str, value) -> "SqlFakeCursor":
        self._one_rules.append((substr, value))
        return self

    def execute(self, q, p=None):
        self.queries.append((q, p))
        self._last_q = q

    def fetchall(self):
        for substr, val in self._many_rules:
            if substr in self._last_q:
                return val
        return []

    def fetchone(self):
        for substr, val in self._one_rules:
            if substr in self._last_q:
                return val
        return None

    def close(self):
        pass


class TestSemDadosPraChecar:
    def test_sem_funcionario_permite(self):
        cur = SqlFakeCursor()
        ok, label = pc._check_area_atuacao(cur, None, 1)
        assert ok is True and label == ""
        assert cur.queries == []  # nem consulta o banco

    def test_sem_area_atuacao_permite(self):
        cur = SqlFakeCursor()
        ok, label = pc._check_area_atuacao(cur, 5, None)
        assert ok is True and label == ""
        assert cur.queries == []


class TestFuncionarioSemRestricao:
    def test_funcionario_sem_nenhuma_area_configurada_permite_qualquer(self):
        cur = SqlFakeCursor().when_many("funcionarios_area_atuacao", [])
        ok, label = pc._check_area_atuacao(cur, 5, 3)
        assert ok is True and label == ""


class TestFuncionarioComRestricao:
    def test_area_permitida_libera(self):
        cur = SqlFakeCursor().when_many("funcionarios_area_atuacao", [{"area": 1}, {"area": 3}])
        ok, label = pc._check_area_atuacao(cur, 5, 3)
        assert ok is True and label == ""

    def test_area_nao_permitida_bloqueia_com_descricao(self):
        cur = (
            SqlFakeCursor()
            .when_many("funcionarios_area_atuacao", [{"area": 1}, {"area": 2}])
            .when_one("area_atuacao WHERE area", {"descricao": "Oficina"})
        )
        ok, label = pc._check_area_atuacao(cur, 5, 9)
        assert ok is False
        assert label == "Oficina"

    def test_area_nao_permitida_sem_descricao_cadastrada_usa_codigo(self):
        cur = SqlFakeCursor().when_many("funcionarios_area_atuacao", [{"area": 1}])
        ok, label = pc._check_area_atuacao(cur, 5, 9)
        assert ok is False
        assert label == "9"
