"""Testes unitários de `_checklist_veiculo_pendente_bloqueia`
(pedido_common.py) — Checklist de Entrada de Veículo obrigatório POR
PERMISSÃO DE GRUPO (`OS_COMP.CHECKLIST_OBRIG`), pedido explícito do
usuário 2026-08-26: "O CHECKLIST DEVE SER OBRIGATÓRIO VIA PERMISSÃO. Se
na permissão estiver marcado para o grupo de usuário que tem que fazer o
checklist, tem que obrigar a fazer". A integração com os pontos que
CHAMAM este helper (incluir item, fechar, faturar) é coberta em
`test_os_itens_service.py::TestChecklistObrigatorioBloqueiaAddItem` e
`test_os_service.py::TestChecklistObrigatorioBloqueiaFecharFaturar` —
aqui só a função isolada."""
import services.pedido_common as pc


class SqlFakeCursor:
    """Cursor fake que responde por casamento de substring no SQL da
    última query executada — mesmo padrão de
    `test_pedido_common_chassi_obrigatorio.py`."""

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


class TestSemClasse:
    def test_classe_none_libera_sem_consultar_banco(self):
        cur = SqlFakeCursor()
        assert pc._checklist_veiculo_pendente_bloqueia(cur, 1, None) is None
        assert cur.queries == []


class TestGrupoSemObrigatoriedade:
    def test_grupo_sem_o_botao_marcado_libera_sem_consultar_mais_nada(self):
        cur = SqlFakeCursor().when_one("FROM permissoes", None)
        assert pc._checklist_veiculo_pendente_bloqueia(cur, 1, 5) is None
        # só a query de permissão rodou — nem placa nem os_checklist foram
        # consultados, já que a obrigatoriedade nem se aplica a este grupo
        assert len(cur.queries) == 1


class TestGrupoComObrigatoriedadeOsNaoOficina:
    def test_sem_placa_libera_mesmo_com_obrigatoriedade_marcada(self):
        cur = (
            SqlFakeCursor()
            .when_one("FROM permissoes", {"ok": 1})
            .when_one("FROM os WHERE", {"placa": ""})
        )
        assert pc._checklist_veiculo_pendente_bloqueia(cur, 1, 5) is None
        assert len(cur.queries) == 2  # nunca chegou a consultar os_checklist

    def test_os_nao_encontrada_libera(self):
        cur = SqlFakeCursor().when_one("FROM permissoes", {"ok": 1}).when_one("FROM os WHERE", None)
        assert pc._checklist_veiculo_pendente_bloqueia(cur, 1, 5) is None


class TestGrupoComObrigatoriedadeOficina:
    def test_checklist_nao_concluido_bloqueia(self):
        cur = (
            SqlFakeCursor()
            .when_one("FROM permissoes", {"ok": 1})
            .when_one("FROM os WHERE", {"placa": "ABC1234"})
            .when_one("FROM os_checklist", None)
        )
        msg = pc._checklist_veiculo_pendente_bloqueia(cur, 1, 5)
        assert msg is not None
        assert "Checklist de Entrada" in msg

    def test_checklist_concluido_libera(self):
        cur = (
            SqlFakeCursor()
            .when_one("FROM permissoes", {"ok": 1})
            .when_one("FROM os WHERE", {"placa": "ABC1234"})
            .when_one("FROM os_checklist", {"ok": 1})
        )
        assert pc._checklist_veiculo_pendente_bloqueia(cur, 1, 5) is None
