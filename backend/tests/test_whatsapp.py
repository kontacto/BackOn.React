"""Testes unitários do módulo WhatsApp (funções puras — sem DB/HTTP)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.whatsapp.service import (  # noqa: E402
    normalize_phone, is_valid_e164, sanitize_text, build_message,
)
from services.whatsapp.providers import (  # noqa: E402
    build_provider, TwilioProvider, MetaProvider, EvolutionProvider, _digits,
)


# ---------- normalize_phone / E.164 ----------
def test_normalize_phone_nacional_br():
    assert normalize_phone("(11) 99999-8888") == "+5511999998888"


def test_normalize_phone_com_mais():
    assert normalize_phone("+1 415 555 1234") == "+14155551234"


def test_normalize_phone_vazio():
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""


def test_is_valid_e164():
    assert is_valid_e164("+5511999998888")
    assert not is_valid_e164("11999998888")   # sem +
    assert not is_valid_e164("+0123")          # começa com 0
    assert not is_valid_e164("")


def test_digits():
    assert _digits("+55 (11) 99999-8888") == "5511999998888"


# ---------- sanitize ----------
def test_sanitize_remove_controle_preserva_quebras():
    raw = "Olá\x00 mundo\nlinha2"
    out = sanitize_text(raw)
    assert "\x00" not in out
    assert "\n" in out
    assert out.startswith("Olá")


# ---------- message builder ----------
def _summary_os():
    return {
        "doc_type": "OS", "doc_label": "Ordem de Serviço", "doc": 7,
        "cliente_nome": "João Silva", "data": "2026-06-25", "total": 1250.0,
        "situacao_label": "Aberto", "obs": "obs teste", "veiculo": "ABC-1234 VW Gol",
        "serie": "9BWZZZ", "descricao_cliente": "barulho", "resumo": "troca",
    }


def test_build_message_os_inclui_campos():
    msg = build_message(_summary_os(), "Equipe XYZ")
    assert "Olá João," in msg
    assert "Nº 7" in msg
    assert "25/06/2026" in msg
    assert "ABC-1234 VW Gol" in msg
    assert "R$ 1.250,00" in msg
    assert "Status: Aberto" in msg
    assert msg.strip().endswith("Equipe XYZ")


def test_build_message_pedido_sem_campos_os():
    summary = {
        "doc_type": "PED", "doc_label": "Pedido de Venda", "doc": 99,
        "cliente_nome": "Maria", "data": "2026-01-02", "total": 50.5,
        "situacao_label": "Faturado", "obs": "",
    }
    msg = build_message(summary, "Loja")
    assert "Nº 99" in msg
    assert "Veículo" not in msg
    assert "R$ 50,50" in msg


# ---------- factory / providers ----------
def test_factory_resolve_providers():
    assert isinstance(build_provider({"provider": "twilio"}), TwilioProvider)
    assert isinstance(build_provider({"provider": "meta"}), MetaProvider)
    assert isinstance(build_provider({"provider": "evolution"}), EvolutionProvider)
    assert build_provider({"provider": "inexistente"}) is None


def test_validate_config_twilio():
    assert TwilioProvider({}).validate_config() is not None
    ok = TwilioProvider({"twilio_sid": "AC1", "twilio_token": "t", "from_number": "+1"})
    assert ok.validate_config() is None


def test_validate_config_meta_evolution():
    assert MetaProvider({}).validate_config() is not None
    assert MetaProvider({"meta_phone_id": "1", "meta_token": "t"}).validate_config() is None
    assert EvolutionProvider({}).validate_config() is not None
    assert EvolutionProvider({"evolution_url": "u", "evolution_instance": "i", "evolution_apikey": "k"}).validate_config() is None
