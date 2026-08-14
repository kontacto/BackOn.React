"""Testes unitários de `decode_codigo_barras_peso_variavel` (pedido_common.py)
— decodificação de código de barras EAN-13 de peso variável (etiqueta
impressa por balança de pré-pesagem). Ver PENDENCIAS.md > "KPDV" > "Balança
Toledo + Pré-Pesagem" pro resumo da pesquisa (best-effort, não validado
contra etiqueta real) e CLAUDE.md pro contexto do módulo Automação Comercial.

Função pura (sem cursor/conexão) — nenhum fake de banco necessário aqui.
"""
import services.pedido_common as pc

# Código válido construído à mão: prefixo "2" + código produto "00123" +
# peso "00500" (500g = 0,5kg) + dígito extra "0" + dígito verificador EAN-13
# (calculado abaixo, mesmo algoritmo mod-10 padrão usado pela função).
CODIGO_VALIDO = "2001230050009"


def test_decode_codigo_valido():
    r = pc.decode_codigo_barras_peso_variavel(CODIGO_VALIDO)
    assert r == {"codigo_produto": "00123", "peso_kg": 0.5}


def test_decode_rejeita_prefixo_errado():
    # Troca o prefixo "2" por "1" e recalcula o dígito verificador certo
    # (senão o teste falharia por checksum, não por prefixo).
    doze_digitos = "1" + CODIGO_VALIDO[1:12]
    digitos = [int(c) for c in doze_digitos]
    soma = sum(d if i % 2 == 0 else d * 3 for i, d in enumerate(digitos))
    dv = (10 - (soma % 10)) % 10
    codigo_final = doze_digitos + str(dv)
    assert pc.decode_codigo_barras_peso_variavel(codigo_final) is None


def test_decode_rejeita_checksum_errado():
    codigo_invalido = CODIGO_VALIDO[:-1] + str((int(CODIGO_VALIDO[-1]) + 1) % 10)
    assert pc.decode_codigo_barras_peso_variavel(codigo_invalido) is None


def test_decode_rejeita_tamanho_errado():
    assert pc.decode_codigo_barras_peso_variavel(CODIGO_VALIDO[:-1]) is None
    assert pc.decode_codigo_barras_peso_variavel(CODIGO_VALIDO + "1") is None


def test_decode_rejeita_nao_numerico():
    codigo = "2AA123005000" + "9"
    assert pc.decode_codigo_barras_peso_variavel(codigo) is None


def test_decode_rejeita_codigo_curto_normal():
    # Código de produto comum (não é peso variável) não deve ser confundido.
    assert pc.decode_codigo_barras_peso_variavel("12345") is None


def test_decode_aceita_vazio_ou_none():
    assert pc.decode_codigo_barras_peso_variavel("") is None
    assert pc.decode_codigo_barras_peso_variavel(None) is None
