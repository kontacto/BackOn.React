"""Testes unitários de `inutilizacao_nfe_service.py` (lado NFe de
Inutilização de Faixa — migração de `Geral\\FrmTraINF.frm`). Ver
PENDENCIAS.md > "Inutilização de Faixa NFe" pro racional completo,
inclusive a diferença real vs. o lado NFC-e já implementado (`gestor_
nfce_service._inutilizar_faixa_sync`): aqui a checagem de "faixa já
emitida" é 100% local (`n_fiscal`), sem consultar o SEFAZ número a número.

**Importantíssimo**: nenhum teste aqui fala com o SEFAZ de verdade —
`nfe_fiscal_common.transmitir`/`carregar_certificado_sync` são sempre
mockados, mesmo padrão de `test_gestor_nfce_service.py`."""
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import datetime
import pytest

import services.inutilizacao_nfe_service as svc
from services.nfe_fiscal_common import NFE_NS


@pytest.fixture(autouse=True)
def _modulo_nfe_ativo(monkeypatch):
    monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: True)


@pytest.fixture(autouse=True)
def _tp_amb_producao(monkeypatch):
    # Ambiente NFe (controle_aux.ambiente_nfe, 2026-08-20) — antes
    # hardcodado "1" (produção); agora resolvido em runtime. Mockado "1"
    # por padrão (mesmo racional do fixture acima).
    monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "1")


def _gerar_certificado_teste():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE UNITARIO")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome).issuer_name(nome).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - datetime.timedelta(days=1))
        .not_valid_after(agora + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


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
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


def _fake_transmitir(*, resposta):
    def _t(envelope, url, key_pem, cert_pem, timeout=30, soap_action=None):
        return resposta
    return _t


# ---------------------------------------------------------------------------
# Séries disponíveis
# ---------------------------------------------------------------------------

class TestSeriesDisponiveisSync:
    def test_so_serie_principal(self, monkeypatch):
        cur = FakeCursor(one=[{"serie_nf": "1", "numero_nf": 100}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._series_disponiveis_sync("srv", "bd")
        assert r["success"] is True
        assert r["series"] == [{"serie": "1", "ultimo_numero": 100}]

    def test_principal_mais_adicionais(self, monkeypatch):
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}],
            many=[[{"serie_nf": "2", "numero_nf": 50}, {"serie_nf": "3", "numero_nf": 10}]],
        )
        _patch(monkeypatch, cur)
        r = svc._series_disponiveis_sync("srv", "bd")
        assert r["success"] is True
        assert r["series"] == [
            {"serie": "1", "ultimo_numero": 100},
            {"serie": "2", "ultimo_numero": 50},
            {"serie": "3", "ultimo_numero": 10},
        ]

    def test_sem_nenhuma_serie_cadastrada(self, monkeypatch):
        cur = FakeCursor(one=[{"serie_nf": None, "numero_nf": None}], many=[[]])
        _patch(monkeypatch, cur)
        r = svc._series_disponiveis_sync("srv", "bd")
        assert r["success"] is False
        assert "não cadastrada" in r["message"].lower()


# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------

class TestHistoricoSync:
    def test_filtra_modelo_55(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        r = svc._historico_sync("srv", "bd")
        assert r["success"] is True
        assert "modelo = '55'" in cur.queries[-1][0]
        assert "ORDER BY codauto_inutilizacao DESC" in cur.queries[-1][0]

    def test_devolve_linhas(self, monkeypatch):
        linha = {
            "codauto_inutilizacao": 1, "numero_inicial": 10, "numero_final": 10, "serie": "1",
            "motivo": "Erro de digitação encontrado", "protocolo_sefaz": "999", "data_registro": "01/01/2026 às 10:00:00",
            "usuario": "JOAOZINHO",
        }
        cur = FakeCursor(many=[[linha]])
        _patch(monkeypatch, cur)
        r = svc._historico_sync("srv", "bd")
        assert r["historico"] == [linha]


# ---------------------------------------------------------------------------
# Inutilizar faixa
# ---------------------------------------------------------------------------

class TestInutilizarFaixaNfeSync:
    def test_bloqueia_motivo_curto(self):
        r = svc._inutilizar_faixa_nfe_sync("srv", "bd", serie="1", numero_inicial=1, numero_final=1, motivo="curto", master=True)
        assert r["success"] is False
        assert "15 caracteres" in r["message"]

    def test_bloqueia_motivo_longo(self):
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=1, numero_final=1, motivo="x" * 51, master=True,
        )
        assert r["success"] is False
        assert "no máximo 50" in r["message"]

    def test_bloqueia_numero_final_menor_que_inicial(self):
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=5,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "menor que o Número Inicial" in r["message"]

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=1, numero_final=1,
            motivo="Erro de digitação encontrado", classe=2, master=False,
        )
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: False)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=1, numero_final=1,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "desativado" in r["message"].lower()

    def test_serie_nao_cadastrada_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"serie_nf": "1", "numero_nf": 100}, None])
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="9", numero_inicial=1, numero_final=1,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "não está cadastrada" in r["message"].lower()

    def test_numero_final_maior_que_ultimo_emitido_bloqueia(self, monkeypatch):
        cur = FakeCursor(one=[{"serie_nf": "1", "numero_nf": 100}, None])
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=95, numero_final=150,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "somente até o número 100" in r["message"]

    def test_faixa_com_notas_emitidas_bloqueia_e_lista_numeros(self, monkeypatch):
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None],
            many=[[{"num_nf": 10.0}, {"num_nf": 12.0}]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "10, 12" in r["message"]

    def test_uf_nao_reconhecida(self, monkeypatch):
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None, {"cgc": "12345678000199", "uf": "ZZ"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "não reconhecida" in r["message"]

    def test_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None, {"cgc": "12345678000199", "uf": "RJ"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_grava_inutilizacao_com_serie_adicional(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta = '<retInutNFe><infInut><cStat>102</cStat><xMotivo>Inutilização homologada</xMotivo><nProt>987654321</nProt></infInut></retInutNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir(resposta=resposta))
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, {"numero_nf": 40}, {"cgc": "12345678000199", "uf": "RJ"}],
            many=[[]],
        )
        conn = _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="2", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is True
        assert r["protocolo_sefaz"] == "987654321"
        assert conn.committed is True
        insert_q, insert_p = next(q for q in cur.queries if "INSERT INTO inutilizacao_nfe" in q[0])
        assert "'55'" in insert_q
        assert insert_p[0] == 10 and insert_p[1] == 15 and insert_p[2] == "2"

    def test_ambiente_homologacao_usa_endpoint_de_homologacao(self, monkeypatch):
        # Prova que a conexão real da conting-2026-08-20 funciona de ponta
        # a ponta, não só o resolvedor isolado: com ambiente_nfe=2, a URL
        # de homologação é a de fato usada na transmissão — sobrescreve o
        # mock padrão "1" (produção) do fixture `_tp_amb_producao`.
        monkeypatch.setattr(svc.nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "2")
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta = '<retInutNFe><infInut><cStat>102</cStat><xMotivo>Inutilização homologada</xMotivo><nProt>1</nProt></infInut></retInutNFe>'
        capturado = {}

        def _fake_transmitir_captura(envelope, url, key_pem, cert_pem, timeout=30, soap_action=None):
            capturado["url"] = url
            return resposta

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir_captura)
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None, {"cgc": "12345678000199", "uf": "RJ"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is True
        assert capturado["url"] == svc.nfe_fiscal_common.ENDPOINTS_INUTILIZACAO["55"]["2"]
        assert capturado["url"] != svc.nfe_fiscal_common.ENDPOINTS_INUTILIZACAO["55"]["1"]

    def test_sucesso_com_serie_principal_sem_adicional(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta = '<retInutNFe><infInut><cStat>102</cStat><xMotivo>Inutilização homologada</xMotivo><nProt>111</nProt></infInut></retInutNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir(resposta=resposta))
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None, {"cgc": "12345678000199", "uf": "RJ"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is True
        assert r["protocolo_sefaz"] == "111"

    def test_sefaz_recusa_inutilizacao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta = '<retInutNFe><infInut><cStat>563</cStat><xMotivo>Faixa já inutilizada</xMotivo></infInut></retInutNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir(resposta=resposta))
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None, {"cgc": "12345678000199", "uf": "RJ"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "563" in r["message"]

    def test_falha_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha)
        cur = FakeCursor(
            one=[{"serie_nf": "1", "numero_nf": 100}, None, {"cgc": "12345678000199", "uf": "RJ"}],
            many=[[]],
        )
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "falha ao comunicar" in r["message"].lower()

    def test_falha_conexao_nao_propaga_excecao(self, monkeypatch):
        def _falha(*a, **k):
            raise Exception("conexão recusada")

        monkeypatch.setattr(svc, "_open_conn", _falha)
        r = svc._inutilizar_faixa_nfe_sync(
            "srv", "bd", serie="1", numero_inicial=10, numero_final=15,
            motivo="Erro de digitação encontrado", master=True,
        )
        assert r["success"] is False
        assert "falha conexão" in r["message"].lower()
