"""Testes UNITÁRIOS dos services — puros, SEM acesso ao banco.

Cobrem regras de negócio determinísticas: validação CPF/CNPJ (inclui CNPJ
alfanumérico 2026), cifra de senha, rateio de totais, limites de desconto e os
helpers que recebem um cursor (testados com um cursor falso/queue).

Executar: cd /app/backend && python -m pytest tests/test_unit_services.py -q
"""
from services.clientes_service import (  # noqa: E402
    _valid_cpf, _valid_cnpj, _validate_cgc_cpf, _only_alnum_upper, _normalize_cgc,
)
from services.auth_service import (  # noqa: E402
    criptografa_frase, _enrich_usuario, _enrich_funcionario, _build_master_session,
)
from services.relatorios_service import _ratear_totais_por_pedido  # noqa: E402
from services.pedido_common import (  # noqa: E402
    _item_total, _check_pedido_aberto, _resolve_produto, _recalc_pedido_total,
)
from services.descontos_service import (  # noqa: E402
    _limite_por_funcao, _validar_limite_desconto, _log_desconto_item,
)


# --------------------------------------------------------------------------
# Cursor falso: enfileira retornos de fetchone/fetchall e grava as queries.
# --------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, params=None):
        self.queries.append((q, params))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []


# =====================================================================
# Validação CPF / CNPJ
# =====================================================================
class TestValidacaoDocumentos:
    def test_cpf_valido(self):
        assert _valid_cpf("111.444.777-35") is True

    def test_cpf_invalido_digito(self):
        assert _valid_cpf("111.444.777-30") is False

    def test_cpf_todos_iguais(self):
        assert _valid_cpf("00000000000") is False

    def test_cnpj_numerico_valido(self):
        assert _valid_cnpj("11.222.333/0001-81") is True

    def test_cnpj_numerico_invalido(self):
        assert _valid_cnpj("11222333000180") is False

    def test_cnpj_alfanumerico_2026_valido(self):
        # CNPJ alfanumérico (RFB 2026) com DV numérico correto
        assert _valid_cnpj("12ABC34501DE35") is True

    def test_cnpj_repetido_rejeitado(self):
        assert _valid_cnpj("00000000000000") is False

    def test_validate_vazio_ok(self):
        assert _validate_cgc_cpf("") == (True, "")
        assert _validate_cgc_cpf("   ") == (True, "")

    def test_validate_tamanho_invalido(self):
        ok, msg = _validate_cgc_cpf("123")
        assert ok is False and "11" in msg

    def test_validate_cpf_path(self):
        # callers usam apenas o bool; a msg vem preenchida (comportamento legado)
        assert _validate_cgc_cpf("11144477735")[0] is True
        assert _validate_cgc_cpf("11144477730")[0] is False

    def test_only_alnum_upper(self):
        assert _only_alnum_upper("12.abc-34/5") == "12ABC345"
        assert _normalize_cgc("11.144.477/35") == "1114447735"


# =====================================================================
# Cifra de senha (Criptografa_Frase) + enriquecimento de sessão
# =====================================================================
class TestAuth:
    def test_criptografa_frase_cesar_mais_3(self):
        assert criptografa_frase("admin") == "dgplq"   # confere com usuarios.senha do ADM
        assert criptografa_frase("123") == "456"
        assert criptografa_frase("321") == "654"
        assert criptografa_frase("") == ""

    def test_criptografa_frase_strip(self):
        assert criptografa_frase("  admin  ") == criptografa_frase("admin")

    def test_enrich_usuario_classe_label(self):
        out = _enrich_usuario({"usuario": "X", "classe": 3, "administrador": 0, "classe_descricao": "SÓCIO"})
        assert out["classe_label"] == "3 - SÓCIO"
        assert out["administrador_label"] == "Não"

    def test_enrich_usuario_admin_sim(self):
        out = _enrich_usuario({"usuario": "ADM", "classe": 1, "administrador": 1, "classe_descricao": "ADMIN"})
        assert out["administrador_label"] == "Sim"

    def test_enrich_usuario_none(self):
        assert _enrich_usuario(None) is None

    def test_enrich_funcionario_telefones(self):
        out = _enrich_funcionario({
            "situacao": "A", "ddd_prof": "21", "tel_prof": "12345678",
            "ddd_cel_prof": "21", "tel_cel_prof": "999998888",
        })
        assert out["situacao_label"] == "Ativo"
        assert out["telefone"] == "(21) 12345678"
        assert out["celular"] == "(21) 999998888"

    def test_master_session(self):
        s = _build_master_session("BARESTEL", "srv", "BDREACTAPP")
        assert s.success is True
        assert s.usuario["master"] is True and s.usuario["classe"] == 0
        assert s.empresa == "BARESTEL"


# =====================================================================
# Rateio de totais (Dashboard / Relatório de Pedidos)
# =====================================================================
class TestRateioTotais:
    def test_pedido_so_produto(self):
        agg = _ratear_totais_por_pedido([
            {"total": 54.50, "item_sum": 54.50, "serv_sum": 0, "custo_sum": 30.11, "desc_sum": 2.40},
        ])
        assert agg["produtos"] == 54.50
        assert agg["servicos"] == 0.0
        assert agg["margem"] == 24.39
        assert agg["margem_pct"] == 44.75

    def test_reconciliacao_produtos_mais_servicos_igual_total(self):
        # produtos + serviços deve bater com a soma dos pedido.total
        rows = [
            {"total": 100.0, "item_sum": 80.0, "serv_sum": 20.0, "custo_sum": 40.0, "desc_sum": 5.0},
            {"total": 50.0, "item_sum": 50.0, "serv_sum": 0.0, "custo_sum": 10.0, "desc_sum": 0.0},
        ]
        agg = _ratear_totais_por_pedido(rows)
        assert round(agg["produtos"] + agg["servicos"], 2) == 150.0
        assert agg["venda"] == 150.0
        assert agg["qtd_pedidos"] == 2

    def test_pedido_sem_itens_classificados(self):
        agg = _ratear_totais_por_pedido([{"total": 30.0, "item_sum": 0, "serv_sum": 0, "custo_sum": 0, "desc_sum": 0}])
        assert agg["produtos"] == 30.0 and agg["servicos"] == 0.0

    def test_vazio(self):
        agg = _ratear_totais_por_pedido([])
        assert agg["venda"] == 0.0 and agg["margem_pct"] == 0.0


# =====================================================================
# Helpers de item / pedido (com cursor falso)
# =====================================================================
class TestPedidoCommon:
    def test_item_total(self):
        assert _item_total(2, 27.25) == 54.50
        assert _item_total(0, 10) == 0.0

    def test_check_pedido_aberto_existe(self):
        cur = FakeCursor(one=[{"situacao": "A"}])
        assert _check_pedido_aberto(cur, 1) == (True, "A")

    def test_check_pedido_inexistente(self):
        cur = FakeCursor(one=[None])
        assert _check_pedido_aberto(cur, 999) == (False, "")

    def test_resolve_produto_peca(self):
        cur = FakeCursor(one=[{
            "codigo": "P001", "descricao": "Parafuso", "codigo_fab": "F1",
            "valor": 10.0, "uni": "UN", "custo_reposicao": 4.0,
        }])
        p = _resolve_produto(cur, "P001")
        assert p["tipo"] == "P" and p["valor"] == 10.0 and p["custo"] == 4.0

    def test_resolve_produto_servico(self):
        # pecas não acha (None), servicos acha
        cur = FakeCursor(one=[None, {"codigo": "S1", "descricao": "Hora téc.", "valor": 80.0}])
        p = _resolve_produto(cur, "S1")
        assert p["tipo"] == "S" and p["unidade"] == "HR" and p["valor"] == 80.0

    def test_resolve_produto_inexistente(self):
        cur = FakeCursor(one=[None, None])
        assert _resolve_produto(cur, "ZZZ") is None

    def test_recalc_pedido_total(self):
        cur = FakeCursor(one=[{"total": 120.5}])  # UPDATE não usa fetch; SELECT retorna total
        assert _recalc_pedido_total(cur, 1) == 120.5


# =====================================================================
# Descontos: limite por função e log
# =====================================================================
class TestDescontos:
    def test_limite_por_funcao(self):
        lim = {"gerente": 30.0, "supervisor": 20.0, "vendedor": 10.0}
        assert _limite_por_funcao(lim, 1) == 30.0
        assert _limite_por_funcao(lim, 2) == 20.0
        assert _limite_por_funcao(lim, 3) == 10.0

    def test_validar_master_ignora_limite(self):
        cur = FakeCursor()
        # usuario_codigo -2 (master) → None mesmo com desconto alto, sem tocar no banco
        assert _validar_limite_desconto(cur, 3, -2, 100.0, 90.0, 90.0) is None
        assert cur.queries == []

    def test_validar_dentro_do_limite(self):
        cur = FakeCursor(one=[{"desconto_pdv_gerente": 30, "desconto_pdv_supervisor": 20, "desconto_pdv_vendedor": 10}])
        # vendedor (3), 5% <= 10% → OK
        assert _validar_limite_desconto(cur, 3, 5, 100.0, 5.0, 5.0) is None

    def test_validar_acima_do_limite(self):
        cur = FakeCursor(one=[{"desconto_pdv_gerente": 30, "desconto_pdv_supervisor": 20, "desconto_pdv_vendedor": 10}])
        # vendedor (3), 15% > 10% → mensagem de erro
        msg = _validar_limite_desconto(cur, 3, 5, 100.0, 15.0, 15.0)
        assert msg is not None and "limite" in msg.lower()

    def test_validar_sem_funcao_passa(self):
        cur = FakeCursor()
        assert _validar_limite_desconto(cur, None, 5, 100.0, 50.0, 0.0) is None

    def test_log_desconto_sem_valor_so_delete(self):
        cur = FakeCursor()
        _log_desconto_item(cur, 1, 10, 0, 0, 5)
        assert len(cur.queries) == 1
        assert cur.queries[0][0].strip().upper().startswith("DELETE")

    def test_log_desconto_com_valor_delete_e_insert(self):
        cur = FakeCursor()
        _log_desconto_item(cur, 1, 10, 10.0, 2.40, 5)
        assert len(cur.queries) == 2
        assert "INSERT" in cur.queries[1][0].upper()
