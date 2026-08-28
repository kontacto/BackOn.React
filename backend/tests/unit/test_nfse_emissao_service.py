"""Testes unitários da emissão de NFS-e via DPS Nacional
(`nfse_emissao_service.py`) — Fase 3 do pacote de emissão fiscal. Mesmo
compromisso do resto do pacote: certificado sempre autoassinado gerado em
memória, `nfe_fiscal_common.transmitir_json_mtls` sempre mockada — nunca
uma chamada de rede de verdade nem o certificado real de nenhuma empresa."""
import base64
import datetime
import gzip

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree

import services.nfse_emissao_service as svc

# `cTribMun` (por serviço, `servicos.cod_servico_municipio`) e `cNBS`
# (por empresa, `controle_aux.codigo_nbs`) — rastreados até a raiz na
# fonte VB6 real (`DAO_NFE.vb`) em 2026-08-24, ver comentários em
# `nfse_emissao_service._montar_xml_dps`. Valores abaixo são os mesmos
# confirmados ao vivo contra ARGEN TESTE (S200 "VISITA TECNIA").
_COD_SERVICO_MUNICIPIO_TESTE = "015"
_CODIGO_NBS_TESTE = "120018900"
_SIMPLES_SERVICO_PCT_TESTE = 13.8


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


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))


def _item(**overrides):
    base = {
        "codigo_int": "SALD", "descricao": "Alinhamento Dianteiro", "cod_lista_servico": "140101",
        "cod_servico_municipio": _COD_SERVICO_MUNICIPIO_TESTE, "valor": 100.0,
    }
    base.update(overrides)
    return base


class TestMontarIdDps:
    def test_id_tem_45_caracteres_e_prefixo_dps(self):
        id_dps = svc.montar_id_dps(
            cod_municipio="3304557", tipo_inscricao="2", inscricao_federal="12345678000199",
            serie="1", numero_dps=100,
        )
        assert len(id_dps) == 45
        assert id_dps.startswith("DPS")
        assert id_dps[3:10] == "3304557"
        assert id_dps[10] == "2"
        assert id_dps[11:25] == "12345678000199"
        assert id_dps[25:30] == "00001"
        assert id_dps[30:45] == "0" * 12 + "100"

    def test_serie_e_numero_com_zeros_a_esquerda(self):
        id_dps = svc.montar_id_dps(
            cod_municipio="1400159", tipo_inscricao="2", inscricao_federal="1",
            serie="900", numero_dps=1028360962,
        )
        assert id_dps == "DPS" + "1400159" + "2" + "0" * 13 + "1" + "00900" + "000001028360962"


class TestMontarXmlDps:
    def test_monta_xml_com_servico_e_valores(self):
        itens = [_item(valor=100.0)]
        xml_bytes, id_dps = svc._montar_xml_dps(
            id_dps="DPS" + "3304557" + "2" + "12345678000199" + "00001" + "0" * 14 + "1",
            tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="12345678000199",
            opcao_simples_nacional=True, regime_especial_tributacao=0,
            tomador={"cgc_cpf": "12345678901", "nome": "CLIENTE TESTE"}, itens=itens,
            codigo_nbs=_CODIGO_NBS_TESTE, simples_servico_pct=_SIMPLES_SERVICO_PCT_TESTE,
        )
        xml = xml_bytes.decode("utf-8")
        assert f'Id="{id_dps}"' in xml
        assert "<cTribNac>140101</cTribNac>" in xml
        assert "<xDescServ>Alinhamento Dianteiro</xDescServ>" in xml
        assert "<vServ>100.00</vServ>" in xml
        # opSimpNac real (XSD oficial): 1=Não Optante, 2=MEI, 3=ME/EPP —
        # opcao_simples_nacional=True mapeia pra 3, nunca 1 (achado ao
        # vivo 2026-08-23, rejeição E0160, o mapeamento anterior estava
        # invertido).
        assert "<opSimpNac>3</opSimpNac>" in xml
        assert "<CPF>12345678901</CPF>" in xml
        assert "<xNome>CLIENTE TESTE</xNome>" in xml
        # É XML bem-formado.
        etree.fromstring(xml_bytes)

    def test_regapstribsn_obrigatorio_quando_optante_meepp(self):
        # Achado ao vivo 2026-08-23 (E0166): `regApTribSN` é obrigatório
        # quando `opSimpNac=3` (ME/EPP) — ausente antes, causava recusa.
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=True, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], codigo_nbs=_CODIGO_NBS_TESTE, simples_servico_pct=_SIMPLES_SERVICO_PCT_TESTE,
        )
        assert "<regApTribSN>1</regApTribSN>" in xml_bytes.decode("utf-8")

    def test_regapstribsn_ausente_quando_nao_optante(self):
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert "<regApTribSN>" not in xml_bytes.decode("utf-8")

    def test_opsimpnac_nao_optante_quando_flag_falsa(self):
        # Complementa o teste acima — trava os dois lados do enum real
        # (1=Não Optante quando a empresa não é Simples Nacional).
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert "<opSimpNac>1</opSimpNac>" in xml_bytes.decode("utf-8")

    def test_soma_valores_de_multiplos_itens(self):
        itens = [
            _item(codigo_int="A", descricao="Serviço A", valor=30.0),
            _item(codigo_int="B", descricao="Serviço B", valor=20.5),
        ]
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None, itens=itens,
            codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert "<vServ>50.50</vServ>" in xml_bytes.decode("utf-8")

    def test_ibs_cbs_cst_classtrib_nao_produzem_gibscbs_invalido(self):
        # Achado ao vivo 2026-08-23 (validação contra o XSD oficial,
        # `schema_v101.xsd`): `<gIBSCBS>` dentro de `<serv>` NUNCA existiu
        # no schema real — o grupo IBS/CBS de verdade (`TCRTCInfoIBSCBS`)
        # é filho de `infDPS`, irmão de `valores`, com estrutura própria
        # bem maior (`finNFSe`/`cIndOp`/`indDest`/valores IBS-CBS), ainda
        # não implementada aqui. Os parâmetros continuam aceitos (não
        # removidos pra não quebrar os call sites que já calculam CST/
        # cClassTrib) mas não geram XML nenhum por enquanto — ver
        # PENDENCIAS.md > "NFS-e (DPS Nacional)".
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], ibs_cbs_cst="000", ibs_cbs_classtrib="000001", codigo_nbs=_CODIGO_NBS_TESTE,
        )
        xml = xml_bytes.decode("utf-8")
        assert "gIBSCBS" not in xml
        etree.fromstring(xml_bytes)

    def test_cservi_tem_ctribmun_e_cnbs_reais_do_cadastro(self):
        # Corrigido 2026-08-24 — rastreamento até a raiz de `DAO_NFE.vb`
        # (`Backon.Data`) revelou que `cTribMun` já é um cadastro real POR
        # SERVIÇO (`servicos.cod_servico_municipio`, DAO_NFE.vb:1140/1216)
        # e `cNBS` é um cadastro real POR EMPRESA (`controle_aux.
        # codigo_nbs`, DAO_NFE.vb:625) — nenhum dos dois é inventado ou
        # mapeado por `cod_lista_servico` como a 1ª versão fazia; ambos
        # são passados por quem chama (já resolvidos via JOIN/SELECT em
        # `comanda_service.py`/`nfe_agrupada_service.py`).
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[_item(cod_servico_municipio="15")], codigo_nbs=_CODIGO_NBS_TESTE,
        )
        xml = xml_bytes.decode("utf-8")
        # `cTribMun` (3 dígitos, `TCCodTribMun`) — zero-preenchido à
        # esquerda a partir do cadastro real (`"15"` vira `"015"`, mesmo
        # valor real já cadastrado em `servicos.cod_servico_municipio`
        # pra "VISITA TECNIA"/S200 no ARGEN TESTE).
        assert "<cTribMun>015</cTribMun>" in xml
        # `cNBS` (9 dígitos, `TSCodNBS`) — zero-preenchido a partir do
        # cadastro real da empresa (`controle_aux.codigo_nbs`).
        assert f"<cNBS>{_CODIGO_NBS_TESTE}</cNBS>" in xml
        etree.fromstring(xml_bytes)

    def test_servico_sem_cod_servico_municipio_bloqueia_com_erro_claro(self):
        # Regra de Kelvin: nunca inventar código fiscal — serviço sem
        # `cod_servico_municipio` cadastrado (Cadastro de Serviços > aba
        # Fiscal) bloqueia explicitamente em vez de mandar um valor vazio/
        # inventado. Confirmado com o usuário 2026-08-24 ("Bloquear com
        # mensagem clara").
        try:
            svc._montar_xml_dps(
                id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
                data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
                opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
                itens=[_item(cod_servico_municipio="", descricao="Serviço Sem Cadastro")],
                codigo_nbs=_CODIGO_NBS_TESTE,
            )
            assert False, "deveria ter levantado ValueError"
        except ValueError as e:
            assert "Serviço Sem Cadastro" in str(e)
            assert "Tributação Municipal" in str(e)

    def test_empresa_sem_codigo_nbs_bloqueia_com_erro_claro(self):
        # Mesma regra acima, aplicada ao campo por-empresa: `controle_aux.
        # codigo_nbs` vazio bloqueia a emissão, nunca inventa um NBS.
        try:
            svc._montar_xml_dps(
                id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
                data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
                opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
                itens=[_item()], codigo_nbs="",
            )
            assert False, "deveria ter levantado ValueError"
        except ValueError as e:
            assert "NBS" in str(e)

    def test_trib_tem_tpretissqn_e_tottrib_obrigatorios(self):
        # Achado ao vivo 2026-08-23: `TCTribMunicipal.tpRetISSQN` e
        # `TCInfoTributacao.totTrib` são obrigatórios pelo XSD oficial —
        # sem eles o ADN recusa com "E1235 - Falha no esquema XML".
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], codigo_nbs=_CODIGO_NBS_TESTE,
        )
        xml = xml_bytes.decode("utf-8")
        assert "<tpRetISSQN>1</tpRetISSQN>" in xml
        assert "<totTrib><indTotTrib>0</indTotTrib></totTrib>" in xml
        etree.fromstring(xml_bytes)

    def test_tottrib_usa_ptottribsn_real_quando_optante_meepp(self):
        # Achado ao vivo 2026-08-23 (E0712): `indTotTrib` só é aceito pra
        # empresa NÃO optante — ME/EPP precisa de `pTotTribSN` (percentual
        # aproximado, campo informativo da Lei da Transparência, nunca
        # afeta o ISS calculado). **Corrigido 2026-08-24**: rastreado até
        # `controle.simples_servico` (DAO_NFE.vb:585-587) — é um cadastro
        # real por empresa, não uma estimativa fixa (a 1ª versão usava
        # 6.00% fixo, decisão do usuário só pra validar o mecanismo).
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=True, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], codigo_nbs=_CODIGO_NBS_TESTE, simples_servico_pct=_SIMPLES_SERVICO_PCT_TESTE,
        )
        xml = xml_bytes.decode("utf-8")
        assert "<totTrib><pTotTribSN>13.80</pTotTribSN></totTrib>" in xml
        assert "indTotTrib" not in xml
        etree.fromstring(xml_bytes)

    def test_sem_tomador_nao_inclui_tag_toma(self):
        xml_bytes, _ = svc._montar_xml_dps(
            id_dps="DPS" + "0" * 42, tp_amb="1", cod_municipio="3304557", serie="1", numero_dps=1,
            data_competencia=datetime.date(2026, 7, 21), cnpj_prest="1",
            opcao_simples_nacional=False, regime_especial_tributacao=0, tomador=None,
            itens=[_item()], codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert "<toma>" not in xml_bytes.decode("utf-8")


class TestEmpacotarDps:
    def test_ida_e_volta_preserva_conteudo(self):
        xml_original = b"<DPS>conteudo de teste</DPS>"
        empacotado = svc._empacotar_dps(xml_original)
        # formato esperado pelo ADN: base64 de um gzip.
        assert gzip.decompress(base64.b64decode(empacotado)) == xml_original


class TestEmitirNfseSync:
    def test_bloqueia_sem_itens(self):
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None, itens=[], tp_amb="1",
        )
        assert r["success"] is False
        assert "serviço" in r["message"].lower()

    def test_bloqueia_sem_codigo_municipio(self):
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1",
        )
        assert r["success"] is False
        assert "município" in r["message"].lower()

    def test_bloqueia_ambiente_nao_reconhecido(self):
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="9",
        )
        assert r["success"] is False
        assert "ambiente" in r["message"].lower()

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_bloqueia_sem_cod_servico_municipio_do_item(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item(cod_servico_municipio="")], tp_amb="1", codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert r["success"] is False
        assert "Tributação Municipal" in r["message"]

    def test_bloqueia_sem_codigo_nbs_da_empresa(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1", codigo_nbs="",
        )
        assert r["success"] is False
        assert "NBS" in r["message"]

    def test_sucesso_com_adn_mockado(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        nfse_xml_fake = b"<NFse><infNFse>autorizada</infNFse></NFse>"
        resposta_fake = {
            "chaveAcesso": "3" * 50,
            "nfseXmlGZipB64": base64.b64encode(gzip.compress(nfse_xml_fake)).decode("ascii"),
        }
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", lambda payload, url, k, c: resposta_fake)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="12345678000199", cod_municipio="3304557",
            opcao_simples_nacional=True, regime_especial_tributacao=0, proximo_numero=100, serie="1",
            tomador=None, itens=[_item()], tp_amb="1",
            codigo_nbs=_CODIGO_NBS_TESTE, simples_servico_pct=_SIMPLES_SERVICO_PCT_TESTE,
        )
        assert r["success"] is True
        assert r["chave_acesso"] == "3" * 50
        assert r["xml_nfse"] == nfse_xml_fake.decode("utf-8")
        assert "<Signature" in r["xml_dps"] or "Signature>" in r["xml_dps"]

    def test_adn_recusa_emissao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = {"_erro_http": 400, "mensagens": [{"codigo": "E0714", "descricao": "Arquivo enviado com erro na assinatura"}]}
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", lambda payload, url, k, c: resposta_fake)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1", codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert r["success"] is False
        assert "E0714" in r["message"]

    def test_adn_recusa_dispara_apoio_fiscal_quando_servidor_banco_informados(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = {"_erro_http": 400, "mensagens": [{"codigo": "E0714", "descricao": "Arquivo enviado com erro na assinatura"}]}
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", lambda payload, url, k, c: resposta_fake)
        chamada = {}

        def _fake_notificar(servidor, banco, *, tipo_documento, codigo_rejeicao, mensagem_original, referencia=None):
            chamada.update(servidor=servidor, banco=banco, tipo_documento=tipo_documento, codigo_rejeicao=codigo_rejeicao)
            return {"titulo": "x", "explicacao_curta": "y", "explicacao_detalhada": "z", "acao_usuario": None,
                    "notificado_suporte": {"email": True, "whatsapp": False}}

        monkeypatch.setattr(svc.apoio_fiscal_service, "notificar_rejeicao_sync", _fake_notificar)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1", codigo_nbs=_CODIGO_NBS_TESTE,
            servidor="srv", banco="bd",
        )
        assert r["success"] is False
        assert r["apoio_fiscal"]["notificado_suporte"]["email"] is True
        assert chamada == {"servidor": "srv", "banco": "bd", "tipo_documento": "NFS-e", "codigo_rejeicao": "E0714"}

    def test_adn_recusa_sem_servidor_banco_nao_chama_apoio_fiscal(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = {"_erro_http": 400, "mensagens": [{"codigo": "E0714", "descricao": "Arquivo enviado com erro na assinatura"}]}
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", lambda payload, url, k, c: resposta_fake)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1", codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert r["success"] is False
        assert "apoio_fiscal" not in r

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir_json_mtls", _falha)
        r = svc.emitir_nfse_sync(
            None, comanda=1, cnpj_prest="1", cod_municipio="3304557", opcao_simples_nacional=True,
            regime_especial_tributacao=0, proximo_numero=1, serie="1", tomador=None,
            itens=[_item()], tp_amb="1", codigo_nbs=_CODIGO_NBS_TESTE,
        )
        assert r["success"] is False
        assert "adn" in r["message"].lower()
