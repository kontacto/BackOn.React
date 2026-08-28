"""Testes unitários de `contingencia_nfe_service.py` — infraestrutura
mínima de Contingência NFe (migração de `Geral\\FrmConNFe.frm`) — ver
PENDENCIAS.md > blueprint item 7 pro racional completo. Mesmo padrão de
`test_contingencia_nfce_service.py`, mas com uma diferença real: os DOIS
tipos (FS-IA=2/FS-DA=5) são igualmente selecionáveis ao abrir.

`TestListarPendentesSync`/`TestValidarPendentesSync` (2026-08-20) cobrem
o equivalente de "Validar Contingência" do Gestor NFCe, adaptado pra
NF-e — reassina o XML já gravado e transmite pelo envelope de
autorização normal; nenhum teste fala com o SEFAZ de verdade."""
import datetime
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

import services.contingencia_nfe_service as svc


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


class TestContingenciaAbertaSync:
    def test_sem_contingencia_aberta(self):
        cur = FakeCursor(one=[None])
        assert svc.contingencia_aberta_sync(cur) is None

    def test_com_contingencia_aberta(self):
        linha = {"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 2}
        cur = FakeCursor(one=[linha])
        assert svc.contingencia_aberta_sync(cur) == linha


class TestAbrirContingenciaSync:
    def test_bloqueia_tipo_invalido(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=9, master=True)
        assert r["success"] is False
        assert "tipo de contingência" in r["message"].lower()

    def test_bloqueia_modulo_nfe_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: False)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, master=True)
        assert r["success"] is False
        assert "módulo nfe" in r["message"].lower()

    def test_bloqueia_motivo_curto(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="curto", tipo_contingencia=2, master=True)
        assert r["success"] is False
        assert "15 e 256" in r["message"]

    def test_bloqueia_dupla_abertura(self, monkeypatch):
        cur = FakeCursor(one=[{"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 5}])
        _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, master=True)
        assert r["success"] is False
        assert "já existe uma contingência aberta" in r["message"].lower()

    def test_sucesso_grava_tipo_fs_ia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, master=True)
        assert r["success"] is True
        assert conn.committed is True
        insert_q = [q for q in cur.queries if "INSERT INTO contingencia_nfe" in q[0]][0]
        assert insert_q[1][-1] == 2

    def test_sucesso_grava_tipo_fs_da(self, monkeypatch):
        cur = FakeCursor(one=[None])
        conn = _patch(monkeypatch, cur)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=5, master=True)
        assert r["success"] is True
        assert conn.committed is True
        insert_q = [q for q in cur.queries if "INSERT INTO contingencia_nfe" in q[0]][0]
        assert insert_q[1][-1] == 5


class TestFecharContingenciaSync:
    def test_bloqueia_sem_contingencia_aberta(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._fechar_contingencia_sync("srv", "bd", master=True)
        assert r["success"] is False
        assert "não há contingência" in r["message"].lower()

    def test_sucesso_grava_data_fim(self, monkeypatch):
        cur = FakeCursor(one=[{"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 2}])
        conn = _patch(monkeypatch, cur)
        r = svc._fechar_contingencia_sync("srv", "bd", master=True)
        assert r["success"] is True
        assert conn.committed is True
        assert any("UPDATE contingencia_nfe SET data_fim" in q[0] and "WHERE data_fim IS NULL" in q[0] for q in cur.queries)


class TestStatusContingenciaSync:
    def test_sem_contingencia(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch(monkeypatch, cur)
        r = svc._status_contingencia_sync("srv", "bd")
        assert r == {"success": True, "aberta": False}

    def test_com_contingencia(self, monkeypatch):
        cur = FakeCursor(one=[{"data_inicio": "2026-08-20", "hora_inicio": "09:00:00", "motivo": "x" * 20, "tipo_contingencia": 5}])
        _patch(monkeypatch, cur)
        r = svc._status_contingencia_sync("srv", "bd")
        assert r["success"] is True
        assert r["aberta"] is True
        assert r["tipo_contingencia"] == 5


class TestSemPermissao:
    def test_bloqueia_abrir_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._abrir_contingencia_sync("srv", "bd", motivo="x" * 20, tipo_contingencia=2, classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_fechar_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._fechar_contingencia_sync("srv", "bd", classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()


class TestListarPendentesSync:
    def test_lista_notas_em_g(self, monkeypatch):
        linha = {"codigo": 1, "num_nf": 101, "serie_nf": "1", "chave_acesso": "3" * 44, "valor_total": 100.0, "data_nf": "2026-08-20"}
        cur = FakeCursor(many=[[linha]])
        _patch(monkeypatch, cur)
        r = svc._listar_pendentes_sync("srv", "bd")
        assert r["success"] is True
        assert r["pendentes"] == [linha]
        assert "situacao = 'G'" in cur.queries[-1][0]

    def test_falha_conexao(self, monkeypatch):
        monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: (_ for _ in ()).throw(Exception("timeout")))
        r = svc._listar_pendentes_sync("srv", "bd")
        assert r["success"] is False


class TestValidarPendentesSync:
    def test_bloqueia_sem_notas(self):
        r = svc._validar_pendentes_sync("srv", "bd", notas=[], master=True)
        assert r["success"] is False

    def test_sem_permissao(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc, "tem_permissao", lambda *a, **k: False)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], classe=2, master=False)
        assert r["success"] is False
        assert "permissão" in r["message"].lower()

    def test_bloqueia_modulo_desligado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "modulo_nfe_ativo_sync", lambda cur: False)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "módulo nfe" in r["message"].lower()

    def test_sem_certificado(self, monkeypatch):
        cur = FakeCursor()
        _patch(monkeypatch, cur)
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_uf_nao_reconhecida(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        cur = FakeCursor(one=[{"uf": "ZZ"}])
        _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "não reconhecida" in r["message"]

    def test_endpoint_nao_disponivel_pra_uf_fora_do_grupo_svrs(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        cur = FakeCursor(one=[{"uf": "MG"}])
        _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "não disponível" in r["message"].lower()

    def test_nota_fora_de_situacao_g_bloqueia_essa_linha(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        cur = FakeCursor(one=[{"uf": "RJ"}, {"codigo": 1, "situacao": "A", "chave_acesso": "x", "xml": "<x/>"}])
        conn = _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert r["resultados"][0]["message"] == "Nota não está aguardando contingência."
        assert conn.committed is True

    def test_xml_nao_encontrado_bloqueia_essa_linha(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        cur = FakeCursor(one=[{"uf": "RJ"}, {"codigo": 1, "situacao": "G", "chave_acesso": "x", "xml": None}])
        _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "xml" in r["resultados"][0]["message"].lower()

    def test_sucesso_grava_situacao_a(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        resposta = '<retNFe><protNFe><infProt><cStat>100</cStat><nProt>135260000012345</nProt><dhRecbto>2026-08-20T10:00:00-03:00</dhRecbto></infProt></protNFe></retNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda *a, **k: resposta)
        cur = FakeCursor(one=[{"uf": "RJ"}, {
            "codigo": 1, "situacao": "G", "chave_acesso": "3" * 44,
            "xml": f'<NFe xmlns="{svc.nfe_fiscal_common.NFE_NS}"><infNFe Id="NFe{"3" * 44}" versao="4.00"><ide><nNF>1</nNF></ide></infNFe></NFe>',
        }])
        conn = _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is True
        assert r["resultados"][0]["protocolo_sefaz"] == "135260000012345"
        assert conn.committed is True
        update_q = next(q for q in cur.queries if q[0].startswith("UPDATE n_fiscal SET situacao = 'A'"))
        assert update_q[1][0] == "100"
        # Achado 2026-08-24 (mesmo bug já corrigido no MDF-e 2026-08-23):
        # `dh_recbto` cru do SEFAZ (com offset "-03:00") quebra numa coluna
        # DATETIME — precisa chegar como `datetime` NAIVE já convertido.
        import datetime as _dt
        assert update_q[1][2] == _dt.datetime(2026, 8, 20, 10, 0, 0)
        assert any("UPDATE comanda_nf SET situacao = 'A'" in q[0] for q in cur.queries)

    def test_xml_ja_assinado_e_relimpo_antes_de_reassinar(self, monkeypatch):
        """Achado real (teste ao vivo, 2026-08-26, lado NFC-e — corrigido
        aqui por analogia/consistência antes do teste ao vivo do lado
        NF-e): `xml_guardado` é o documento JÁ ASSINADO da emissão
        original em contingência (a assinatura antiga nunca foi
        removida). Reassinar isso do jeito que está deixaria a
        assinatura antiga presente junto da nova — mesma classe de bug
        confirmada com rejeição real do SEFAZ pro lado NFC-e ("Falha no
        Schema XML")."""
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        chave = "3" * 44
        xml_ja_assinado = (
            f'<NFe xmlns="{svc.nfe_fiscal_common.NFE_NS}"><infNFe Id="NFe{chave}" versao="4.00">'
            '<ide><nNF>1</nNF></ide></infNFe>'
            '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
            '<ds:SignedInfo><ds:Reference URI="#antiga"/></ds:SignedInfo>'
            '<ds:SignatureValue>ASSINATURA-ANTIGA-INVALIDA</ds:SignatureValue></ds:Signature>'
            "</NFe>"
        )
        resposta = '<retNFe><protNFe><infProt><cStat>100</cStat><nProt>1</nProt><dhRecbto>2026-08-26T10:00:00-03:00</dhRecbto></infProt></protNFe></retNFe>'
        capturado = {}

        def _fake_envelope(xml_assinado, tp_amb):
            capturado["xml_assinado"] = xml_assinado
            return "<envelope/>"

        monkeypatch.setattr(svc.nfe_emissao_service, "_montar_envelope_autorizacao", _fake_envelope)
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda *a, **k: resposta)
        cur = FakeCursor(one=[{"uf": "RJ"}, {"codigo": 1, "situacao": "G", "chave_acesso": chave, "xml": xml_ja_assinado}])
        _patch(monkeypatch, cur)

        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is True
        xml_final = capturado["xml_assinado"].decode("utf-8")
        assert "ASSINATURA-ANTIGA-INVALIDA" not in xml_final
        assert len(re.findall(r"<ds:Signature[ >]", xml_final)) == 1

    def test_cstat_do_lote_nao_confunde_com_cstat_do_documento(self, monkeypatch):
        # Achado 2026-08-24: mesmo bug já corrigido em `emitir_nfce_sync`/
        # `emitir_nfe_sync` 2026-08-23 (o `cStat` do LOTE, nível externo,
        # sempre vem ANTES do `cStat` do DOCUMENTO dentro de `infProt` na
        # resposta real do SEFAZ) — aqui replicado com um `cStat` de lote
        # (104, neutro) que NÃO deve ser confundido com o 100 real.
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        resposta = (
            '<retEnviNFe><cStat>104</cStat><xMotivo>Lote processado</xMotivo>'
            '<protNFe><infProt><cStat>100</cStat><nProt>888</nProt>'
            '<dhRecbto>2026-08-24T10:00:00-03:00</dhRecbto></infProt></protNFe></retEnviNFe>'
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda *a, **k: resposta)
        cur = FakeCursor(one=[{"uf": "RJ"}, {
            "codigo": 1, "situacao": "G", "chave_acesso": "3" * 44,
            "xml": f'<NFe xmlns="{svc.nfe_fiscal_common.NFE_NS}"><infNFe Id="NFe{"3" * 44}" versao="4.00"><ide><nNF>1</nNF></ide></infNFe></NFe>',
        }])
        conn = _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is True
        assert r["resultados"][0]["protocolo_sefaz"] == "888"
        assert conn.committed is True

    def test_sefaz_recusa_bloqueia_essa_linha(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
        resposta = '<retNFe><protNFe><infProt><cStat>110</cStat><xMotivo>Uso Denegado</xMotivo></infProt></protNFe></retNFe>'
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda *a, **k: resposta)
        cur = FakeCursor(one=[{"uf": "RJ"}, {
            "codigo": 1, "situacao": "G", "chave_acesso": "3" * 44,
            "xml": f'<NFe xmlns="{svc.nfe_fiscal_common.NFE_NS}"><infNFe Id="NFe{"3" * 44}" versao="4.00"><ide><nNF>1</nNF></ide></infNFe></NFe>',
        }])
        _patch(monkeypatch, cur)
        monkeypatch.setattr(
            svc.apoio_fiscal_service, "notificar_rejeicoes_lote_sync",
            lambda *a, **k: {"total": 1, "grupos": [], "notificado_suporte": {"email": True, "whatsapp": False}},
        )
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "110" in r["resultados"][0]["message"]
        assert r["apoio_fiscal_lote"]["notificado_suporte"]["email"] is True

    def test_falha_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha)
        cur = FakeCursor(one=[{"uf": "RJ"}, {
            "codigo": 1, "situacao": "G", "chave_acesso": "3" * 44,
            "xml": f'<NFe xmlns="{svc.nfe_fiscal_common.NFE_NS}"><infNFe Id="NFe{"3" * 44}" versao="4.00"><ide><nNF>1</nNF></ide></infNFe></NFe>',
        }])
        _patch(monkeypatch, cur)
        r = svc._validar_pendentes_sync("srv", "bd", notas=[1], master=True)
        assert r["success"] is False
        assert "falha ao comunicar" in r["resultados"][0]["message"].lower()
