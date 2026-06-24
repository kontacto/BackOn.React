"""Testes UNITÁRIOS dos serializadores/helpers de db.connection (sem banco)."""
from datetime import datetime, date
from decimal import Decimal

from db.connection import _to_json_safe, _trunc


class TestToJsonSafe:
    def test_none(self):
        assert _to_json_safe(None) is None

    def test_datetime_e_date_para_iso(self):
        out = _to_json_safe({"dt": datetime(2026, 6, 24, 10, 30, 0), "d": date(2026, 6, 24)})
        assert out["dt"].startswith("2026-06-24T10:30")
        assert out["d"] == "2026-06-24"

    def test_decimal_para_float(self):
        out = _to_json_safe({"v": Decimal("54.50")})
        assert out["v"] == 54.5 and isinstance(out["v"], float)

    def test_bytes_decodificado(self):
        out = _to_json_safe({"b": "café".encode("utf-8")})
        assert out["b"] == "café"

    def test_tipos_simples_inalterados(self):
        out = _to_json_safe({"i": 3, "s": "x", "n": None, "f": 1.2})
        assert out == {"i": 3, "s": "x", "n": None, "f": 1.2}


class TestTrunc:
    SIZES = {"nome": 60, "telefone_cli": 8, "obs": -1}  # -1 = nvarchar(MAX)

    def test_none_passa(self):
        assert _trunc(None, self.SIZES, "nome") is None

    def test_nao_string_inalterado(self):
        assert _trunc(123, self.SIZES, "nome") == 123

    def test_trunca_no_tamanho_da_coluna(self):
        assert _trunc("X" * 100, self.SIZES, "nome") == "X" * 60
        assert _trunc("123456789", self.SIZES, "telefone_cli") == "12345678"

    def test_coluna_desconhecida_usa_fallback(self):
        assert _trunc("Y" * 100, self.SIZES, "inexistente", fallback=10) == "Y" * 10

    def test_nvarchar_max_sem_limite(self):
        big = "Z" * 500
        assert _trunc(big, self.SIZES, "obs") == big
