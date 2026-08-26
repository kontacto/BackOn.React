"""Testes UNITÁRIOS do "Sugerir com IA" (Descomplicar Taxas, Apoio
Fiscal/"João") — `taxas_ia_service.py`. Nenhum teste aqui chama a API
Anthropic de verdade — o SDK `anthropic` é sempre um módulo FALSO
injetado via `sys.modules` (o `import anthropic` dentro da função é
local, igual `layout_service.py`, então o monkeypatch precisa acontecer
ANTES da chamada, não depois de um `import` de topo de arquivo)."""
import json
import sys
import types

import services.taxas_ia_service as svc
from services import fiscal_referencia_nacional as ref


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = list(one or [])
        self._many = list(many or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch_conn(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class FakeUsage:
    input_tokens = 100
    output_tokens = 50


class FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, payload: dict, stop_reason: str = "end_turn"):
        self.content = [FakeTextBlock(json.dumps(payload))]
        self.usage = FakeUsage()
        self.stop_reason = stop_reason


class FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._response


class FakeMessagesAPI:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.response)


def _install_fake_anthropic(monkeypatch, response):
    messages_api = FakeMessagesAPI(response)

    class _Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.messages = messages_api

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    return messages_api


# ============ _montar_schema — o enum nunca é aberto ============
class TestMontarSchema:
    def test_crt_simples_oferece_apenas_csosn(self):
        schema = svc._montar_schema({"crt": 1, "eh_simples": True}, "S01", tem_classtrib=False)
        enum = schema["properties"]["tributacao"]["properties"]["codigo"]["enum"]
        assert set(enum) == set(ref.CSOSN.keys())

    def test_crt_normal_oferece_apenas_cst_icms(self):
        schema = svc._montar_schema({"crt": 3, "eh_simples": False}, "S01", tem_classtrib=False)
        enum = schema["properties"]["tributacao"]["properties"]["codigo"]["enum"]
        assert set(enum) == set(ref.CST_ICMS.keys())

    def test_tipo_mov_saida_usa_tabela_de_saida(self):
        schema = svc._montar_schema({"crt": 3, "eh_simples": False}, "S01", tem_classtrib=False)
        enum = schema["properties"]["cst_pis"]["properties"]["codigo"]["enum"]
        assert set(enum) == set(ref.CST_PIS_COFINS_SAIDA.keys())

    def test_tipo_mov_entrada_usa_tabela_de_entrada(self):
        schema = svc._montar_schema({"crt": 3, "eh_simples": False}, "E01", tem_classtrib=False)
        enum = schema["properties"]["cst_cofins"]["properties"]["codigo"]["enum"]
        assert set(enum) == set(ref.CST_PIS_COFINS_ENTRADA.keys())

    def test_classtrib_vazia_omite_bloco_ibs_cbs(self):
        schema = svc._montar_schema({"crt": 3, "eh_simples": False}, "S01", tem_classtrib=False)
        assert "ibs_cbs" not in schema["properties"]
        assert "ibs_cbs" not in schema["required"]

    def test_classtrib_disponivel_inclui_bloco_ibs_cbs(self):
        schema = svc._montar_schema({"crt": 3, "eh_simples": False}, "S01", tem_classtrib=True)
        assert "ibs_cbs" in schema["properties"]
        assert "ibs_cbs" in schema["required"]


# ============ _anexar_descricoes_oficiais ============
class TestAnexarDescricoesOficiais:
    def test_csosn_quando_simples(self):
        sugestao = {"tributacao": {"codigo": "102", "motivo": "x"}}
        svc._anexar_descricoes_oficiais({"eh_simples": True}, sugestao)
        assert sugestao["tributacao"]["descricao_oficial"] == ref.CSOSN["102"]

    def test_cst_icms_quando_normal(self):
        sugestao = {"tributacao": {"codigo": "00", "motivo": "x"}}
        svc._anexar_descricoes_oficiais({"eh_simples": False}, sugestao)
        assert sugestao["tributacao"]["descricao_oficial"] == ref.CST_ICMS["00"]

    def test_pis_cofins(self):
        sugestao = {"cst_pis": {"codigo": "01", "motivo": "x"}, "cst_cofins": {"codigo": "06", "motivo": "y"}}
        svc._anexar_descricoes_oficiais({"eh_simples": False}, sugestao)
        assert sugestao["cst_pis"]["descricao_oficial"] == ref.CST_PIS_COFINS["01"]
        assert sugestao["cst_cofins"]["descricao_oficial"] == ref.CST_PIS_COFINS["06"]


# ============ _anexar_derivados_classtrib ============
class TestAnexarDerivadosClasstrib:
    def test_sem_bloco_ibs_cbs_nao_faz_nada(self, monkeypatch):
        chamado = []
        monkeypatch.setattr(svc.tabelas_aux_service, "_classtrib_lookup_sync", lambda *a, **k: chamado.append(1))
        sugestao = {"tributacao": {"codigo": "00", "motivo": "x"}}
        svc._anexar_derivados_classtrib("srv", "bd", sugestao)
        assert not chamado
        assert "ibs_cbs" not in sugestao

    def test_par_valido_anexa_valores_reais(self, monkeypatch):
        monkeypatch.setattr(
            svc.tabelas_aux_service, "_classtrib_lookup_sync",
            lambda servidor, banco, cst, cclasstrib: {
                "success": True, "pred_ibs": 12.5, "pred_cbs": 3.2, "g_trib_regular": True,
                "g_mono_padrao": False, "g_mono_reten": False, "g_mono_ret": False, "g_mono_dif": False,
            },
        )
        sugestao = {"ibs_cbs": {"cst": "000", "cclasstrib": "000001", "motivo": "x"}}
        svc._anexar_derivados_classtrib("srv", "bd", sugestao)
        assert sugestao["ibs_cbs"]["pred_ibs"] == 12.5
        assert sugestao["ibs_cbs"]["pred_cbs"] == 3.2
        assert sugestao["ibs_cbs"]["g_trib_regular"] is True

    def test_par_invalido_descarta_bloco_inteiro(self, monkeypatch):
        monkeypatch.setattr(
            svc.tabelas_aux_service, "_classtrib_lookup_sync",
            lambda *a, **k: {"success": False, "message": "Não foi encontrada essa combinação de CST e ClassTrib!"},
        )
        sugestao = {"ibs_cbs": {"cst": "999", "cclasstrib": "999999", "motivo": "x"}}
        svc._anexar_derivados_classtrib("srv", "bd", sugestao)
        assert "ibs_cbs" not in sugestao


# ============ _sugerir_tributacao_sync — fluxo completo ============
class TestSugerirTributacaoSync:
    def _kwargs(self, **over):
        base = dict(
            destino="1", cfop="5102", cod_icms="1", tipo_mov="S01",
            simples_nacional=False, consumidor_final=False, descricao_operacao=None,
        )
        base.update(over)
        return base

    def test_sem_chave_api_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"ANTHROPIC_API_KEY": ""}])
        _patch_conn(monkeypatch, cur)
        r = svc._sugerir_tributacao_sync("srv", "bd", **self._kwargs())
        assert r["success"] is False
        assert "IA Key" in r["message"]

    def test_sem_regime_configurado_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[
            {"ANTHROPIC_API_KEY": "sk-ant-teste"},
            {"Regime_Trib": None, "opcao_simples": False},
        ])
        _patch_conn(monkeypatch, cur)
        r = svc._sugerir_tributacao_sync("srv", "bd", **self._kwargs())
        assert r["success"] is False
        assert "Regime Tributário" in r["message"]

    def test_stop_reason_refusal(self, monkeypatch):
        cur = FakeCursor(one=[
            {"ANTHROPIC_API_KEY": "sk-ant-teste"},
            {"Regime_Trib": 3, "opcao_simples": False},
            None,  # classtrib vazia
        ])
        _patch_conn(monkeypatch, cur)
        _install_fake_anthropic(monkeypatch, FakeResponse({}, stop_reason="refusal"))
        r = svc._sugerir_tributacao_sync("srv", "bd", **self._kwargs())
        assert r["success"] is False
        assert "recusado" in r["message"].lower()
        assert r["custo"]["tokens_entrada"] == 100

    def test_caminho_feliz_sem_classtrib(self, monkeypatch):
        cur = FakeCursor(one=[
            {"ANTHROPIC_API_KEY": "sk-ant-teste"},
            {"Regime_Trib": 3, "opcao_simples": False},
            None,  # classtrib vazia — bloco ibs_cbs nunca pedido
        ])
        _patch_conn(monkeypatch, cur)
        payload = {
            "tributacao": {"codigo": "00", "motivo": "Venda tributada integralmente."},
            "cst_pis": {"codigo": "01", "motivo": "Alíquota básica."},
            "cst_cofins": {"codigo": "01", "motivo": "Alíquota básica."},
        }
        messages_api = _install_fake_anthropic(monkeypatch, FakeResponse(payload))
        r = svc._sugerir_tributacao_sync("srv", "bd", **self._kwargs())
        assert r["success"] is True
        assert r["sugestao"]["tributacao"]["codigo"] == "00"
        assert r["sugestao"]["tributacao"]["descricao_oficial"] == ref.CST_ICMS["00"]
        assert "ibs_cbs" not in r["sugestao"]
        # confirma que o schema mandado pra IA veio das tabelas reais, não solto
        schema_mandado = messages_api.calls[0]["output_config"]["format"]["schema"]
        assert "ibs_cbs" not in schema_mandado["properties"]
        assert set(schema_mandado["properties"]["tributacao"]["properties"]["codigo"]["enum"]) == set(ref.CST_ICMS.keys())

    def test_caminho_feliz_com_classtrib_anexa_derivados(self, monkeypatch):
        cur = FakeCursor(one=[
            {"ANTHROPIC_API_KEY": "sk-ant-teste"},
            {"Regime_Trib": 1, "opcao_simples": True},
            {"ok": 1},  # classtrib tem linhas
        ])
        _patch_conn(monkeypatch, cur)
        payload = {
            "tributacao": {"codigo": "102", "motivo": "Simples Nacional sem crédito."},
            "cst_pis": {"codigo": "01", "motivo": "x"},
            "cst_cofins": {"codigo": "01", "motivo": "x"},
            "ibs_cbs": {"cst": "000", "cclasstrib": "000001", "motivo": "Tributação regular."},
        }
        _install_fake_anthropic(monkeypatch, FakeResponse(payload))
        monkeypatch.setattr(
            svc.tabelas_aux_service, "_classtrib_lookup_sync",
            lambda servidor, banco, cst, cclasstrib: {
                "success": True, "pred_ibs": 0.0, "pred_cbs": 0.0, "g_trib_regular": True,
                "g_mono_padrao": False, "g_mono_reten": False, "g_mono_ret": False, "g_mono_dif": False,
            },
        )
        r = svc._sugerir_tributacao_sync("srv", "bd", **self._kwargs())
        assert r["success"] is True
        assert r["sugestao"]["tributacao"]["codigo"] == "102"
        assert r["sugestao"]["ibs_cbs"]["g_trib_regular"] is True

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        cur = FakeCursor(one=[
            {"ANTHROPIC_API_KEY": "sk-ant-teste"},
            {"Regime_Trib": 3, "opcao_simples": False},
            None,
        ])
        _patch_conn(monkeypatch, cur)

        class _BoomClient:
            def __init__(self, api_key=None):
                raise Exception("timeout")

        fake_module = types.ModuleType("anthropic")
        fake_module.Anthropic = _BoomClient
        monkeypatch.setitem(sys.modules, "anthropic", fake_module)

        r = svc._sugerir_tributacao_sync("srv", "bd", **self._kwargs())
        assert r["success"] is False
