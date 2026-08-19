"""Testes unitários de `_chassi_obrigatorio_ok` (pedido_common.py) —
`controle.exige_chassi_os`, avisado pela equipe VB6 2026-08-17: decide se o
Chassi é obrigatório ao gravar uma O.S. do segmento Oficina. Ver
PENDENCIAS.md > "O.S. — Chassi obrigatório (Oficina)"."""
import services.pedido_common as pc


class SqlFakeCursor:
    """Cursor fake que responde por casamento de substring no SQL da última
    query executada — mesmo padrão de `test_pedido_common_area_atuacao.py`."""

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


class TestChassiPreenchido:
    def test_chassi_preenchido_sempre_ok_nem_consulta_banco(self):
        cur = SqlFakeCursor()
        assert pc._chassi_obrigatorio_ok(cur, "9BW1234567890ABCD") is True
        assert cur.queries == []

    def test_chassi_so_espacos_conta_como_vazio(self):
        cur = SqlFakeCursor().when_one("controle_configuracao", {"Oficina": True}).when_one("FROM controle", {"exige_chassi_os": True})
        assert pc._chassi_obrigatorio_ok(cur, "   ") is False


class TestModuloOficinaDesligado:
    def test_sem_modulo_oficina_libera_mesmo_com_flag_ligado(self):
        cur = SqlFakeCursor().when_one("controle_configuracao", {"Oficina": False})
        assert pc._chassi_obrigatorio_ok(cur, "") is True

    def test_sem_registro_controle_configuracao_libera(self):
        cur = SqlFakeCursor()
        assert pc._chassi_obrigatorio_ok(cur, "") is True


class TestModuloOficinaLigado:
    def test_flag_desligado_libera(self):
        cur = SqlFakeCursor().when_one("controle_configuracao", {"Oficina": True}).when_one("FROM controle", {"exige_chassi_os": False})
        assert pc._chassi_obrigatorio_ok(cur, "") is True

    def test_flag_ligado_bloqueia_chassi_vazio(self):
        cur = SqlFakeCursor().when_one("controle_configuracao", {"Oficina": True}).when_one("FROM controle", {"exige_chassi_os": True})
        assert pc._chassi_obrigatorio_ok(cur, "") is False

    def test_sem_registro_controle_libera(self):
        cur = SqlFakeCursor().when_one("controle_configuracao", {"Oficina": True})
        assert pc._chassi_obrigatorio_ok(cur, None) is True
