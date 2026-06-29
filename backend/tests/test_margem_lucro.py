"""Testes unitários do relatório de Margem de Lucro (cálculos + montagem de SQL).

Não dependem de banco de dados — cobrem a lógica de domínio pura.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import margem_lucro_service as svc  # noqa: E402


# --------------------------------------------------------------------------- #
# _margem_pct
# --------------------------------------------------------------------------- #
def test_margem_pct_nao_operacional():
    # (venda - custo) / venda * 100  => (100-60)/100 = 40%
    assert svc._margem_pct(100, 60, operacional=False) == 40.0


def test_margem_pct_operacional():
    # (venda - custo) / custo * 100 => (100-60)/60 = 66.67%
    assert svc._margem_pct(100, 60, operacional=True) == 66.67


def test_margem_pct_custo_zero_operacional_retorna_100():
    assert svc._margem_pct(100, 0, operacional=True) == 100.0


def test_margem_pct_venda_zero_nao_operacional_retorna_0():
    assert svc._margem_pct(0, 50, operacional=False) == 0.0


# --------------------------------------------------------------------------- #
# _agregar
# --------------------------------------------------------------------------- #
def _row(**kw):
    base = {"situacao_item": 0, "cliente_nome": "Cli", "data_dav": "2026-01-10",
            "doc": 1, "tipo": "PED", "item_codigo": "X", "item_descricao": "Item",
            "qtd": 1, "bruto": 0, "desconto": 0, "acrescimo": 0, "liquido": 0, "custo": 0}
    base.update(kw)
    return base


def test_agregar_item_e_dav_nao_operacional():
    rows = [
        _row(doc=10, qtd=2, liquido=50, custo=30),   # venda=100 custo=60 lucro=40
        _row(doc=10, qtd=1, liquido=200, custo=100),  # venda=200 custo=100 lucro=100
    ]
    davs, venda, custo, _desc = svc._agregar(rows, operacional=False)
    assert len(davs) == 1
    dav = davs[0]
    assert dav["total_venda"] == 300.0
    assert dav["total_custo"] == 160.0
    assert dav["lucro"] == 140.0
    # margem nível item ×100 (correção do bug legado): (100-60)/100 = 40%
    assert dav["itens"][0]["margem_pct"] == 40.0
    # margem do DAV: (300-160)/300*100 = 46.67%
    assert dav["margem_pct"] == 46.67
    assert venda == 300.0 and custo == 160.0


def test_agregar_os_item_nao_cobrado_zera_venda_mas_mantem_custo():
    # situacao_item > 0 => venda zerada, custo continua (regra legada)
    rows = [_row(tipo="OS", doc=5, situacao_item=2, qtd=3, liquido=80, custo=20)]
    davs, venda, custo, _desc = svc._agregar(rows, operacional=False)
    item = davs[0]["itens"][0]
    assert item["total_venda"] == 0.0
    assert item["total_custo"] == 60.0  # 3 * 20
    assert venda == 0.0 and custo == 60.0


def test_agregar_separa_davs_por_tipo_e_doc():
    rows = [
        _row(tipo="PED", doc=1, qtd=1, liquido=10, custo=5),
        _row(tipo="OS", doc=1, qtd=1, liquido=20, custo=5),
        _row(tipo="PED", doc=1, qtd=1, liquido=10, custo=5),
    ]
    davs, _, _, _ = svc._agregar(rows, operacional=False)
    # PED-1 (2 itens) e OS-1 (1 item) => 2 DAVs
    assert len(davs) == 2


def test_agregar_itens_aparecem_em_resultado_operacional():
    # Bug legado: itens sumiam quando operacional=True. Aqui devem aparecer.
    rows = [_row(qtd=1, liquido=100, custo=50)]
    davs, _, _, _ = svc._agregar(rows, operacional=True)
    assert len(davs[0]["itens"]) == 1
    assert davs[0]["itens"][0]["margem_pct"] == 100.0  # (100-50)/50*100


# --------------------------------------------------------------------------- #
# _montar_query  (parametrização / segurança)
# --------------------------------------------------------------------------- #
def _filtros(**kw):
    base = {"data_ini": "2026-01-01", "data_fim": "2026-12-31",
            "incluir_pedidos": True, "incluir_os": True, "incluir_comandas": True,
            "retorna_produtos": True, "retorna_servicos": True,
            "davs_abertos": True, "davs_fechados": True, "davs_faturados": True}
    base.update(kw)
    return base


def test_montar_query_placeholders_batem_com_params():
    sql, params = svc._montar_query(_filtros())
    assert sql.count("%s") == len(params)


def test_montar_query_sem_fontes_retorna_vazio():
    sql, params = svc._montar_query(_filtros(incluir_pedidos=False, incluir_os=False, incluir_comandas=False))
    assert sql == "" and params == []


def test_montar_query_nivel_em_chunks_de_3():
    sql, params = svc._montar_query(_filtros(
        incluir_os=False, incluir_comandas=False, retorna_servicos=False, nivel="001002"))
    # nivel1='001' e nivel2='002' presentes como parâmetros
    assert "001" in params and "002" in params
    assert "pe.nivel1 = %s" in sql and "pe.nivel2 = %s" in sql


def test_montar_query_nao_concatena_valores_de_filtro():
    # cod_dav/area/cliente NUNCA podem aparecer literalmente no SQL (anti SQL-injection)
    sql, params = svc._montar_query(_filtros(cod_dav=999, area_atuacao=7, cod_cliente=42))
    assert "999" not in sql and "= 7" not in sql and "42" not in sql
    assert 999 in params and 7 in params and 42 in params


def test_montar_query_situacao_in_com_placeholders():
    sql, params = svc._montar_query(_filtros(
        incluir_comandas=False, incluir_os=False, retorna_servicos=False,
        davs_abertos=True, davs_fechados=False, davs_faturados=False))
    assert "pv.situacao IN (%s)" in sql
    assert "A" in params


def test_montar_query_somente_venda_direta_usa_subquery():
    sql, _ = svc._montar_query(_filtros(
        incluir_pedidos=False, incluir_os=False, retorna_servicos=False,
        somente_venda_direta=True))
    assert "comanda_os" in sql and "comanda_ped" in sql
