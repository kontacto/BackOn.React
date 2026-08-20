"""Testes unitários de `gestor_nfce_service.py` (Gestor NFCe — migração de
`Geral\\FrmTraNFC.frm`) — ver PENDENCIAS.md > "Gestor NFCe" pro racional
completo, e a docstring do próprio módulo pros achados da releitura da
fonte (bloqueio "alguma linha ruim" vs. homogeneidade, contingência
bloqueando só 3 das 6 ações, etc.).

**Importantíssimo**: nenhum teste aqui fala com o SEFAZ de verdade nem usa
certificado real — `nfe_fiscal_common.transmitir`/`carregar_certificado_
sync` são sempre mockados (mesmo padrão de `test_nfe_emissao_service.py`/
`test_nfe_cancelamento_service.py`), e ações que dependem de outro service
(`nfe_cancelamento_service.cancelar_nfe_sync`,
`comanda_service._emitir_nfce_comanda_sync`) mockam esse service
diretamente, sem duplicar a lógica interna dele aqui."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
import pytest

import services.gestor_nfce_service as svc
from services.nfe_fiscal_common import NFE_NS


@pytest.fixture(autouse=True)
def _modulo_nfce_ativo(monkeypatch):
    # Módulo "NFCe" (controle_aux.emite_nfce, 2026-08-20) — checado em
    # runtime; mockado True por padrão pra não exigir mais uma linha no
    # FakeCursor de todo teste já existente (nenhum testa módulo desligado).
    monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfce_ativo_sync", lambda cur: True)


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


def _sem_contingencia(monkeypatch):
    monkeypatch.setattr(svc.contingencia_nfce_service, "contingencia_aberta_sync", lambda cur: None)


def _com_contingencia(monkeypatch, tipo=9):
    monkeypatch.setattr(
        svc.contingencia_nfce_service, "contingencia_aberta_sync",
        lambda cur: {"id": 1, "data_inicio": datetime.date(2026, 8, 19), "hora_inicio": "10:00:00", "motivo": "x" * 20, "tipo_contingencia": tipo},
    )


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


# ---------------------------------------------------------------------------
# Listagem + detecção de gaps
# ---------------------------------------------------------------------------

class TestListNfceSync:
    def test_sem_permissao_bloqueia(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._list_nfce_sync("srv", "bd", classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_lista_basica_monta_itens(self, monkeypatch):
        linha = {
            "comanda": 1, "data": datetime.date(2026, 8, 19), "valor_venda": 50.0, "cliente": 10,
            "cliente_nome": "FULANO", "num_nfce": 100, "serie_nfce": "1", "situacao": "F",
            "dhemi": datetime.datetime(2026, 8, 19, 10, 0, 0), "protocolo_sefaz": "123", "chave_acesso": "3" * 44,
            "vnf": 50.0,
        }
        cur = FakeCursor(many=[[linha]])
        _patch(monkeypatch, cur)
        r = svc._list_nfce_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert len(r["itens"]) == 1
        assert r["itens"][0]["comanda"] == 1
        assert r["itens"][0]["cliente_nome"] == "FULANO"
        assert r["gaps"] == []

    def test_filtro_periodo_venda_entra_no_where(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_nfce_sync("srv", "bd", data_venda_de="2026-08-01", data_venda_ate="2026-08-19", master=True)
        query = cur.queries[-1][0]
        assert "c.data >= %s" in query
        assert "c.data <= %s" in query

    def test_filtro_situacoes_com_incluir_sem_nfce(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_nfce_sync("srv", "bd", situacoes=["A", "F"], incluir_sem_nfce=True, master=True)
        query = cur.queries[-1][0]
        assert "cn.situacao IN (%s,%s) OR cn.situacao IS NULL" in query

    def test_filtro_situacoes_sem_incluir_sem_nfce(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_nfce_sync("srv", "bd", situacoes=["A"], incluir_sem_nfce=False, master=True)
        query = cur.queries[-1][0]
        assert "OR cn.situacao IS NULL" not in query
        assert "cn.situacao IN (%s)" in query

    def test_sem_situacoes_e_sem_incluir_sem_nfce_exige_ter_nfce(self, monkeypatch):
        cur = FakeCursor(many=[[]])
        _patch(monkeypatch, cur)
        svc._list_nfce_sync("srv", "bd", incluir_sem_nfce=False, master=True)
        query = cur.queries[-1][0]
        assert "cn.situacao IS NOT NULL" in query

    def test_somente_gaps_filtra_itens_e_devolve_gaps(self, monkeypatch):
        linhas = [
            {"comanda": 1, "data": None, "valor_venda": 1, "cliente": None, "cliente_nome": "X", "num_nfce": 1,
             "serie_nfce": "1", "situacao": "F", "dhemi": None, "protocolo_sefaz": None, "chave_acesso": None, "vnf": None},
            {"comanda": 2, "data": None, "valor_venda": 1, "cliente": None, "cliente_nome": "X", "num_nfce": 2,
             "serie_nfce": "1", "situacao": "F", "dhemi": None, "protocolo_sefaz": None, "chave_acesso": None, "vnf": None},
            {"comanda": 3, "data": None, "valor_venda": 1, "cliente": None, "cliente_nome": "X", "num_nfce": 3,
             "serie_nfce": "1", "situacao": "F", "dhemi": None, "protocolo_sefaz": None, "chave_acesso": None, "vnf": None},
        ]
        faixa = [{"serie_nfce": "1", "minimo": 1, "maximo": 3}]
        existentes = [{"num_nfce": 1}, {"num_nfce": 3}]
        cur = FakeCursor(many=[linhas, faixa, existentes])
        _patch(monkeypatch, cur)
        r = svc._list_nfce_sync("srv", "bd", somente_gaps=True, master=True)
        assert r["success"] is True
        assert r["gaps"] == [{"serie": "1", "numero": 2}]
        assert [i["comanda"] for i in r["itens"]] == [2]


class TestDetectarGapsSync:
    def test_min_igual_max_nao_gera_gap(self):
        cur = FakeCursor(many=[[{"serie_nfce": "1", "minimo": 5, "maximo": 5}]])
        gaps = svc._detectar_gaps_sync(cur, data_nfce_de=None, data_nfce_ate=None)
        assert gaps == []

    def test_detecta_numero_ausente_no_meio_da_faixa(self):
        cur = FakeCursor(many=[[{"serie_nfce": "1", "minimo": 1, "maximo": 4}], [{"num_nfce": 1}, {"num_nfce": 2}, {"num_nfce": 4}]])
        gaps = svc._detectar_gaps_sync(cur, data_nfce_de=None, data_nfce_ate=None)
        assert gaps == [{"serie": "1", "numero": 3}]


# ---------------------------------------------------------------------------
# Cancelar
# ---------------------------------------------------------------------------

class TestCancelarNfceSync:
    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._cancelar_nfce_sync("srv", "bd", comandas=[1], motivo="cliente desistiu", classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_contingencia_aberta(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        _com_contingencia(monkeypatch)
        r = svc._cancelar_nfce_sync("srv", "bd", comandas=[1], motivo="cliente desistiu", master=True)
        assert r["success"] is False
        assert "contingência" in r["message"].lower()

    def test_comanda_sem_nfce_bloqueia_essa_linha(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._cancelar_nfce_sync("srv", "bd", comandas=[1], motivo="cliente desistiu", master=True)
        assert r["success"] is False
        assert r["resultados"][0]["message"] == "Comanda sem NFC-e emitida."
        assert conn.committed is True

    def test_nfce_ja_cancelada_bloqueia_essa_linha(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "C", "protocolo_sefaz": "1", "chave_acesso": "3" * 44}
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, linha])
        _patch(monkeypatch, cur)
        r = svc._cancelar_nfce_sync("srv", "bd", comandas=[1], motivo="cliente desistiu", master=True)
        assert r["success"] is False
        assert "já cancelada" in r["resultados"][0]["message"].lower()

    def test_sucesso_atualiza_situacao_c(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "F", "protocolo_sefaz": "1", "chave_acesso": "3" * 44}
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, linha])
        conn = _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_cancelamento_service, "cancelar_nfe_sync", lambda cur, **kw: {"success": True, "protocolo_cancelamento": "999"})
        r = svc._cancelar_nfce_sync("srv", "bd", comandas=[1], motivo="cliente desistiu, item errado", master=True)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE comanda_nfce SET situacao = 'C'" in q[0] for q in cur.queries)

    def test_sefaz_recusa_cancelamento_nao_atualiza_situacao(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "F", "protocolo_sefaz": "1", "chave_acesso": "3" * 44}
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, linha])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_cancelamento_service, "cancelar_nfe_sync", lambda cur, **kw: {"success": False, "message": "SEFAZ recusou"})
        r = svc._cancelar_nfce_sync("srv", "bd", comandas=[1], motivo="cliente desistiu, item errado", master=True)
        assert r["success"] is False
        assert not any("UPDATE comanda_nfce SET situacao = 'C'" in q[0] for q in cur.queries)


# ---------------------------------------------------------------------------
# Consultar situação
# ---------------------------------------------------------------------------

class TestConsultarSituacaoSync:
    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_contingencia_aberta(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        _com_contingencia(monkeypatch)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "contingência" in r["message"].lower()

    def test_comanda_sem_chave_de_acesso(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is True
        assert r["resultados"][0]["success"] is False
        assert r["resultados"][0]["message"] == "Comanda sem NFC-e emitida."

    def test_endpoint_nao_disponivel_pra_uf(self, monkeypatch):
        # cUF "31" (MG) não está no grupo SVRS mapeado.
        _sem_contingencia(monkeypatch)
        chave = "31" + "1" * 42
        cur = FakeCursor(one=[{"chave_acesso": chave}])
        _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], master=True)
        assert r["resultados"][0]["success"] is False
        assert "não disponível" in r["resultados"][0]["message"].lower()

    def test_sem_certificado(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        chave = "3" * 44
        cur = FakeCursor(one=[{"chave_acesso": chave}])
        _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], master=True)
        assert r["resultados"][0]["success"] is False
        assert "certificado" in r["resultados"][0]["message"].lower()

    def test_sucesso_extrai_cstat_de_dentro_de_protnfe(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        _patch_certificado(monkeypatch, b"key", b"cert")
        resposta_fake = (
            f'<retConsSitNFe xmlns="{NFE_NS}">'
            f'<protNFe><infProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>'
            f'<nProt>135260000012345</nProt></infProt></protNFe>'
            f'</retConsSitNFe>'
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        chave = "3" * 44
        cur = FakeCursor(one=[{"chave_acesso": chave}])
        _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], master=True)
        assert r["resultados"][0]["success"] is True
        assert r["resultados"][0]["situacao_sefaz"] == "100"
        assert r["resultados"][0]["protocolo"] == "135260000012345"

    def test_resposta_sem_protnfe_usa_cstat_geral(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        _patch_certificado(monkeypatch, b"key", b"cert")
        resposta_fake = f'<retConsSitNFe xmlns="{NFE_NS}"><cStat>108</cStat><xMotivo>Serviço Paralisado</xMotivo></retConsSitNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        chave = "3" * 44
        cur = FakeCursor(one=[{"chave_acesso": chave}])
        _patch(monkeypatch, cur)
        r = svc._consultar_situacao_sync("srv", "bd", comandas=[1], master=True)
        assert r["resultados"][0]["success"] is True
        assert r["resultados"][0]["situacao_sefaz"] == "108"
        assert r["resultados"][0]["protocolo"] is None


# ---------------------------------------------------------------------------
# Inutilizar faixa
# ---------------------------------------------------------------------------

def _fake_transmitir_inutilizacao(*, consulta_resposta=None, inut_resposta=None):
    def _fn(envelope, url, k, c):
        if "NfeConsulta" in url:
            return consulta_resposta
        return inut_resposta
    return _fn


class TestMontarXmlInutilizacao:
    def test_monta_id_inut_e_xml_bem_formado(self):
        xml, id_inut = svc._montar_xml_inutilizacao(
            cod_ibge="33", cnpj="12345678000199", serie="1", numero_inicial=10, numero_final=10,
            motivo="Erro de digitação no valor total", tp_amb="1",
        )
        # "ID" + cUF(2) + ano(2) + CNPJ(14) + mod(2) + serie(3) + nNFIni(9) + nNFFin(9) = 43 chars.
        assert len(id_inut) == 43
        assert id_inut.startswith("ID33")
        assert "12345678000199" in id_inut
        assert id_inut.endswith("001" + "000000010" + "000000010")
        assert 'Id="' + id_inut + '"' in xml.decode("utf-8")
        etree.fromstring(xml)


class TestInutilizarFaixaSync:
    def test_bloqueia_motivo_curto(self):
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[1], serie="1", motivo="curto", master=True)
        assert r["success"] is False
        assert "15 caracteres" in r["message"]

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[1], serie="1", motivo="Erro de digitação encontrado", classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_contingencia_aberta(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        _com_contingencia(monkeypatch)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[1], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is False
        assert "contingência" in r["message"].lower()

    def test_uf_nao_reconhecida(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "ZZ"}])
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[1], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is False
        assert "não reconhecida" in r["message"]

    def test_sem_certificado(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}])
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[1], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_numero_ja_autorizado_bloqueia(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        consulta_resposta = f'<retConsSitNFe xmlns="{NFE_NS}"><protNFe><infProt><cStat>100</cStat><nProt>1</nProt></infProt></protNFe></retConsSitNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir_inutilizacao(consulta_resposta=consulta_resposta))
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, {"chave_acesso": "3" * 44}])
        conn = _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[10], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is False
        assert "já autorizado" in r["resultados"][0]["message"].lower()
        assert conn.committed is True

    def test_sucesso_sem_nfce_previa_grava_inutilizacao(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        inut_resposta = '<retInutNFe><infInut><cStat>102</cStat><xMotivo>Inutilização homologada</xMotivo><nProt>987654321</nProt></infInut></retInutNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir_inutilizacao(inut_resposta=inut_resposta))
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, None])
        conn = _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[10], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is True
        assert r["resultados"][0]["protocolo_sefaz"] == "987654321"
        assert conn.committed is True
        assert any("INSERT INTO inutilizacao_nfe" in q[0] for q in cur.queries)
        assert any("UPDATE comanda_nfce SET situacao = 'I'" in q[0] for q in cur.queries)

    def test_sefaz_recusa_inutilizacao(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        inut_resposta = '<retInutNFe><infInut><cStat>563</cStat><xMotivo>Faixa já inutilizada</xMotivo></infInut></retInutNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _fake_transmitir_inutilizacao(inut_resposta=inut_resposta))
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, None])
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[10], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is False
        assert "563" in r["resultados"][0]["message"]

    def test_falha_comunicacao_nao_propaga_excecao(self, monkeypatch):
        _sem_contingencia(monkeypatch)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha)
        cur = FakeCursor(one=[{"cgc": "12345678000199", "uf": "RJ"}, None])
        _patch(monkeypatch, cur)
        r = svc._inutilizar_faixa_sync("srv", "bd", numeros=[10], serie="1", motivo="Erro de digitação encontrado", master=True)
        assert r["success"] is False
        assert "falha ao comunicar" in r["resultados"][0]["message"].lower()


# ---------------------------------------------------------------------------
# Retransmitir — exige homogeneidade (todas sem NFC-e ativa).
# ---------------------------------------------------------------------------

class TestRetransmitirSync:
    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        result = svc._retransmitir_sync("srv", "bd", comandas=[1], classe=2, master=False)
        assert result["success"] is False
        assert "permissão" in result["message"].lower()

    def test_bloqueia_se_alguma_comanda_ja_tem_nfce(self, monkeypatch):
        cur = FakeCursor(one=[{"ok": 1}])
        _patch(monkeypatch, cur)
        r = svc._retransmitir_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is False
        assert "sem nfc-e emitida" in r["message"].lower()

    def test_sucesso_delega_para_comanda_service(self, monkeypatch):
        import services.comanda_service as comanda_service_mod

        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)
        chamadas = []

        def _fake_emitir(req, comanda):
            chamadas.append(comanda)
            return {"success": True, "protocolo_sefaz": f"prot-{comanda}"}

        monkeypatch.setattr(comanda_service_mod, "_emitir_nfce_comanda_sync", _fake_emitir)
        r = svc._retransmitir_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is True
        assert chamadas == [1, 2]
        assert r["resultados"][0]["protocolo_sefaz"] == "prot-1"

    def test_alguma_emissao_falha_marca_lote_como_falho(self, monkeypatch):
        import services.comanda_service as comanda_service_mod

        cur = FakeCursor(one=[None, None])
        _patch(monkeypatch, cur)

        def _fake_emitir(req, comanda):
            if comanda == 2:
                return {"success": False, "message": "SEFAZ recusou"}
            return {"success": True}

        monkeypatch.setattr(comanda_service_mod, "_emitir_nfce_comanda_sync", _fake_emitir)
        r = svc._retransmitir_sync("srv", "bd", comandas=[1, 2], master=True)
        assert r["success"] is False


# ---------------------------------------------------------------------------
# Validar Contingência — exige homogeneidade (todas situacao='G').
# ---------------------------------------------------------------------------

class TestValidarContingenciaSync:
    def _xml_guardado(self, num_nfce):
        return f'<NFe xmlns="{NFE_NS}"><infNFe Id="NFe{num_nfce}" versao="4.00"><ide><nNF>{num_nfce}</nNF></ide></infNFe></NFe>'

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_comanda_fora_do_estado_g(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "F", "xml": self._xml_guardado(10)}
        cur = FakeCursor(one=[linha])
        _patch(monkeypatch, cur)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "situação 'g'" in r["message"].lower()

    def test_sem_certificado(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "G", "xml": self._xml_guardado(10)}
        cur = FakeCursor(one=[linha])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_xml_ausente_bloqueia_essa_linha(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "G", "xml": None}
        cur = FakeCursor(one=[linha])
        _patch(monkeypatch, cur)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "xml da nfc-e não encontrado" in r["resultados"][0]["message"].lower()

    def test_endpoint_nao_disponivel(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "G", "xml": self._xml_guardado(10)}
        cur = FakeCursor(one=[linha, {"uf": "MG"}])
        _patch(monkeypatch, cur)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "endpoint sefaz não disponível" in r["resultados"][0]["message"].lower()

    def test_sucesso_transmite_e_marca_situacao_f(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "G", "xml": self._xml_guardado(10), "chave_acesso": "3" * 44}
        cur = FakeCursor(one=[linha, {"uf": "RJ"}])
        conn = _patch(monkeypatch, cur)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEnviNFe><infProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>"
            "<nProt>555</nProt><dhRecbto>2026-08-19T10:00:00-03:00</dhRecbto></infProt></retEnviNFe>"
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is True
        assert r["resultados"][0]["protocolo_sefaz"] == "555"
        assert conn.committed is True
        assert any("UPDATE comanda_nfce SET situacao = 'F'" in q[0] for q in cur.queries)
        assert any("UPDATE n_fiscal SET situacao = 'A'" in q[0] for q in cur.queries)

    def test_sefaz_recusa_nao_atualiza_situacao(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "G", "xml": self._xml_guardado(10), "chave_acesso": "3" * 44}
        cur = FakeCursor(one=[linha, {"uf": "RJ"}])
        _patch(monkeypatch, cur)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEnviNFe><infProt><cStat>539</cStat><xMotivo>Duplicidade</xMotivo></infProt></retEnviNFe>"
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert not any("UPDATE comanda_nfce SET situacao = 'F'" in q[0] for q in cur.queries)

    def test_falha_comunicacao_nao_propaga_excecao(self, monkeypatch):
        linha = {"comanda": 1, "num_nfce": 10, "situacao": "G", "xml": self._xml_guardado(10), "chave_acesso": "3" * 44}
        cur = FakeCursor(one=[linha, {"uf": "RJ"}])
        _patch(monkeypatch, cur)
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha)
        r = svc._validar_contingencia_sync("srv", "bd", comandas=[1], master=True)
        assert r["success"] is False
        assert "falha ao comunicar" in r["resultados"][0]["message"].lower()


# ---------------------------------------------------------------------------
# Gerar XML — trivial, só devolve o já armazenado.
# ---------------------------------------------------------------------------

class TestGerarXmlSync:
    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._gerar_xml_sync("srv", "bd", comanda=1, classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_comanda_sem_nfce(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._gerar_xml_sync("srv", "bd", comanda=1, master=True)
        assert r["success"] is False
        assert r["message"] == "Comanda sem NFC-e emitida."

    def test_sucesso_devolve_xml_e_chave(self, monkeypatch):
        cur = FakeCursor(one=[{"xml": "<NFe/>", "chave_acesso": "3" * 44}])
        _patch(monkeypatch, cur)
        r = svc._gerar_xml_sync("srv", "bd", comanda=1, master=True)
        assert r["success"] is True
        assert r["xml"] == "<NFe/>"
        assert r["chave_acesso"] == "3" * 44
