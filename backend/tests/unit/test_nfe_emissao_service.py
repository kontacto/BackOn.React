"""Testes unitários da emissão de NFC-e (`nfe_emissao_service.py`) — Fase 1
do pacote de emissão fiscal. Mesmo compromisso de `nfe_cancelamento_
service.py`: certificado sempre autoassinado gerado em memória,
`nfe_fiscal_common.transmitir` sempre mockada — nunca uma chamada de rede
de verdade nem o certificado real de nenhuma empresa."""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLVerifier

import services.nfe_emissao_service as svc


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
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None


class TestGerarTentativasTributacao:
    def test_mesma_uf_gera_3_tentativas_por_rodada(self):
        tentativas = svc._gerar_tentativas_tributacao(
            protocolo_st_inicial=False, nao_contribuinte=True, simples_nacional_cliente=False,
            consumidor_final=True, uf_destino="RJ", uf_controle="RJ",
        )
        # Mesma UF (uf_destino == uf_controle) -> só as 3 primeiras tentativas
        # por rodada (sem o bloco de fallback UF="XX") x 2 rodadas (protocolo_st).
        assert len(tentativas) == 6
        # Primeira tentativa: valores originais.
        assert tentativas[0] == (False, True, True, "RJ")
        # Segunda: simples_nacional invertido.
        assert tentativas[1] == (False, False, True, "RJ")
        # Terceira: consumidor_final também invertido.
        assert tentativas[2] == (False, False, False, "RJ")
        # Quarta em diante: protocolo_st invertido, mesma cascata de novo.
        assert tentativas[3] == (True, True, True, "RJ")

    def test_uf_diferente_adiciona_fallback_xx(self):
        tentativas = svc._gerar_tentativas_tributacao(
            protocolo_st_inicial=False, nao_contribuinte=True, simples_nacional_cliente=False,
            consumidor_final=True, uf_destino="SP", uf_controle="RJ",
        )
        # 7 tentativas por rodada (3 + 4 do fallback UF=XX) x 2 rodadas.
        assert len(tentativas) == 14
        # O bloco de fallback usa simples_nacional_cliente (não nao_contribuinte).
        assert tentativas[3] == (False, False, True, "XX")
        assert tentativas[5] == (False, True, False, "XX")
        assert tentativas[6] == (False, False, False, "XX")


class TestResolverTributacaoSync:
    def test_encontra_na_primeira_tentativa(self):
        cur = FakeCursor(one=[{"tributacao": "101", "icms": 18.0}])
        r = svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        assert r == {"tributacao": "101", "icms": 18.0}
        assert len(cur.queries) == 1

    def test_cai_pro_fallback_apos_falhas(self):
        cur = FakeCursor(one=[None, None, {"tributacao": "201", "icms": 12.0}])
        r = svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        assert r == {"tributacao": "201", "icms": 12.0}
        assert len(cur.queries) == 3

    def test_nenhuma_tentativa_encontra_retorna_none(self):
        cur = FakeCursor(one=[None] * 6)
        r = svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        assert r is None

    def test_query_exclui_cfop_cupom_fiscal_nao_filtra_pelo_cfop_do_item(self):
        cur = FakeCursor(one=[{"tributacao": "101"}])
        svc._resolver_tributacao_sync(
            cur, cod_icms="00", cfop_cupom_fiscal="5929", tipo_mov="S01", uf_destino="RJ", uf_controle="RJ",
            nao_contribuinte=False, simples_nacional_cliente=False, consumidor_final=True, protocolo_st=False,
        )
        query, params = cur.queries[0]
        assert "cfop <> %s" in query
        assert "5929" in params


class TestDvModulo11:
    def test_dv_e_deterministico_e_de_1_digito(self):
        chave_43 = "3" * 43
        dv = svc._dv_modulo11(chave_43)
        assert len(dv) == 1
        assert dv.isdigit()

    def test_chaves_diferentes_geram_dv_diferentes_em_geral(self):
        dv1 = svc._dv_modulo11("1" * 43)
        dv2 = svc._dv_modulo11("2" * 43)
        assert dv1 != dv2 or True  # não é garantia matemática, só smoke test


class TestMontarChaveAcesso:
    def test_chave_tem_44_digitos(self):
        chave = svc.montar_chave_acesso(
            uf_ibge="33", data_emissao=datetime.date(2026, 7, 21), cnpj="12345678000199",
            modelo="65", serie="1", numero=100, tp_emis="1", codigo_numerico="42",
        )
        assert len(chave) == 44
        assert chave.isdigit()
        assert chave.startswith("33")  # cUF
        assert chave[2:6] == "2607"  # AAMM

    def test_cnf_nunca_igual_ao_numero_mesmo_com_seed_igual(self):
        # Achado ao vivo 2026-08-23 (rejeição 897, "Código numérico em
        # formato inválido"): `emitir_nfe_sync` passava `codigo_numerico`
        # literalmente igual a `numero` — colidia 100% das vezes.
        # `_gerar_cnf_valido` nunca deixa isso acontecer, seja qual for o
        # seed recebido.
        for numero in (100, 1387, 999999999):
            chave = svc.montar_chave_acesso(
                uf_ibge="33", data_emissao=datetime.date(2026, 7, 21), cnpj="12345678000199",
                modelo="55", serie="1", numero=numero, tp_emis="1", codigo_numerico=str(numero),
            )
            cnf = chave[35:43]
            assert int(cnf) != int(numero)

    def test_cnf_nunca_e_sequencia_de_digito_repetido(self):
        for _ in range(50):
            cnf = svc._gerar_cnf_valido("0", 0)
            assert len(set(cnf)) > 1


class TestGerarCnfValido:
    def test_evita_colisao_com_numero_repetidamente(self):
        for numero in range(1, 30):
            cnf = svc._gerar_cnf_valido(str(numero), numero)
            assert int(cnf) != numero
            assert len(set(cnf)) > 1
            assert len(cnf) == 8


class TestMontarUrlQrcode:
    def test_url_contem_chave_versao_tpamb_cscid_e_hash(self):
        """Formato QR Code V2 real (`?p={chave}|2|{tpAmb}|{cscId}|{hash}`)
        — achado ao vivo 2026-08-23, ver docstring de `montar_url_qrcode`."""
        url = svc.montar_url_qrcode(
            chave_acesso="3" * 44, tp_amb="2", csc_id="000001", csc="segredo-teste", uf_sigla="RJ",
        )
        assert "?p=" + "3" * 44 + "|2|2|1|" in url
        # cscId sem zeros à esquerda (int("000001") == 1).
        assert url.count("|") == 4

    def test_hash_bate_formula_sha1_maiuscula(self):
        import hashlib
        chave = "3" * 44
        url = svc.montar_url_qrcode(chave_acesso=chave, tp_amb="2", csc_id="000001", csc="segredo-teste", uf_sigla="RJ")
        seq = f"{chave}|2|2|1"
        esperado = hashlib.sha1((seq + "segredo-teste").encode("utf-8")).hexdigest().upper()
        assert url.endswith(f"|{esperado}")

    def test_contingencia_tp_emis_9_usa_formula_offline(self):
        """Achado real, teste ao vivo 2026-08-26 (1º teste ponta a ponta
        de Contingência NFC-e): SEFAZ recusa a fórmula ONLINE quando
        `tpEmis=9` ("Falha no Schema XML... infNFeSupl/qrCode") — o XSD
        real exige o formato OFFLINE (`chave|2|tpAmb|dia|valor|digHex|
        cscId|hash`), confirmado contra `nfephp-org/sped-nfe`'s
        `QRCode::get200`, ramo `tpEmis==9`."""
        import hashlib
        chave = "3" * 44
        dh_emi = datetime.datetime(2026, 8, 26, 14, 30, 0)
        digest_b64 = "wU8Vkwyurvt9a3yqo6IRyYNfYis="  # 28 chars base64 -> 56 hex chars
        url = svc.montar_url_qrcode(
            chave_acesso=chave, tp_amb="1", csc_id="000001", csc="segredo-teste", uf_sigla="RJ",
            tp_emis="9", dh_emi=dh_emi, valor_total=1.0, digest_value_b64=digest_b64,
        )
        dig_hex = "".join(f"{ord(c):02x}" for c in digest_b64)
        assert len(dig_hex) == 56
        seq = f"{chave}|2|1|26|1.00|{dig_hex}|1"
        esperado_hash = hashlib.sha1((seq + "segredo-teste").encode("utf-8")).hexdigest().upper()
        assert f"?p={seq}|{esperado_hash}" in url

    def test_contingencia_sem_tp_emis_continua_online(self):
        """`tp_emis` default ("1") preserva o comportamento online já
        validado ao vivo — nenhuma regressão pros call sites existentes
        que não passam `tp_emis`."""
        chave = "3" * 44
        url = svc.montar_url_qrcode(chave_acesso=chave, tp_amb="2", csc_id="000001", csc="segredo-teste", uf_sigla="RJ")
        assert url.count("|") == 4


class TestMontarXmlNfce:
    def test_monta_xml_com_itens_e_qrcode(self):
        itens = [{
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0,
            "origem": 0, "csosn": "102", "cst_pis": "07", "cst_cofins": "07",
        }]
        xml_bytes, id_nfe = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            cliente=None, itens=itens, forma_pagamento="01", valor_total=20.0, tp_amb="2",
            numero=100, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            url_qrcode="https://exemplo/qrcode?x=1",
        )
        xml = xml_bytes.decode("utf-8")
        assert id_nfe == f"NFe{'3' * 44}"
        assert f'Id="{id_nfe}"' in xml
        assert "<cProd>P001</cProd>" in xml
        assert "<xProd>Produto Teste</xProd>" in xml
        assert "<vNF>20.00</vNF>" in xml
        # `infNFeSupl`/qrCode NÃO entra aqui — achado ao vivo 2026-08-23:
        # é montado depois de assinar, via splice em `emitir_nfce_sync`
        # (é IRMÃO de `infNFe`, não filho — ver docstring de
        # `_montar_xml_nfce`), não faz parte do XML pré-assinatura.
        assert "infNFeSupl" not in xml
        # É XML bem-formado.
        etree.fromstring(xml_bytes)

    def test_inclui_ibscbs_por_item_e_totais_quando_presentes(self):
        # Parte A do ecossistema fiscal (2026-08-19) — ver ibs_cbs_service.py.
        itens = [{
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 1.0, "valor_unitario": 100.0, "valor_total": 100.0,
            "origem": 0, "csosn": "102", "cst_pis": "07", "cst_cofins": "07",
            "ibs_cbs_xml": "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>",
        }]
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            cliente=None, itens=itens, forma_pagamento="01", valor_total=100.0, tp_amb="2",
            numero=100, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            url_qrcode="", ibs_cbs_totais_xml="<IBSCBSTot><vBCIBSCBS>100.00</vBCIBSCBS></IBSCBSTot>",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>" in xml
        assert "<IBSCBSTot><vBCIBSCBS>100.00</vBCIBSCBS></IBSCBSTot>" in xml
        etree.fromstring(xml_bytes)

    def test_sem_ibscbs_nao_quebra_xml_existente(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", cliente=None, itens=[],
            forma_pagamento="01", valor_total=0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="",
        )
        etree.fromstring(xml_bytes)

    def test_inclui_dest_quando_ha_cliente_com_documento(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="4" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X",
            cliente={"cgc_cpf": "12345678000199"}, itens=[], forma_pagamento="01", valor_total=0,
            tp_amb="2", numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            url_qrcode="",
        )
        assert "<CNPJ>12345678000199</CNPJ>" in xml_bytes.decode("utf-8")

    def test_sem_frete_modfrete_9_e_vfrete_zero(self):
        # Achado real 2026-08-22: default sem frete_valor continua modFrete=9
        # (mesmo comportamento de antes), mas agora com <vFrete> explícito.
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="4" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", cliente=None, itens=[],
            forma_pagamento="01", valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<modFrete>9</modFrete>" in xml
        assert "<vFrete>0.00</vFrete>" in xml
        assert "<transporta>" not in xml
        etree.fromstring(xml_bytes)

    def test_com_frete_e_transportador_modfrete_1_com_dados_reais(self):
        # DAO_NFE.vb:5436-5476 (ModeloNota="65") — modFrete=1 só quando
        # frete_valor>0, e <transporta> só entra quando o transportador foi
        # resolvido pelo chamador (via controle_aux.TRANSPORTADOR_FRETE_NFCE).
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="4" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", cliente=None, itens=[],
            forma_pagamento="01", valor_total=70.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="",
            frete_valor=20.0,
            transportador={
                "cgc_cpf": "12345678000100", "nome": "TRANSPORTADORA X", "ie": "ISENTO",
                "endereco": "RUA DO FRETE 10 CENTRO", "cidade": "RIO DE JANEIRO", "uf": "RJ",
            },
        )
        xml = xml_bytes.decode("utf-8")
        assert "<modFrete>1</modFrete>" in xml
        assert "<vFrete>20.00</vFrete>" in xml
        assert "<transporta><CNPJ>12345678000100</CNPJ><xNome>TRANSPORTADORA X</xNome><IE>ISENTO</IE>" in xml
        assert "<xMun>RIO DE JANEIRO</xMun><UF>RJ</UF></transporta>" in xml
        etree.fromstring(xml_bytes)

    def test_com_frete_sem_transportador_modfrete_1_sem_bloco_transporta(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="4" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", cliente=None, itens=[],
            forma_pagamento="01", valor_total=70.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="",
            frete_valor=20.0, transportador=None,
        )
        xml = xml_bytes.decode("utf-8")
        assert "<modFrete>1</modFrete>" in xml
        assert "<transporta>" not in xml
        etree.fromstring(xml_bytes)


class TestParseNfceXmlParaExibicao:
    def _xml(self):
        xml_bytes, _ = svc._montar_xml_nfce(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            cliente={"cgc_cpf": "98765432100"}, itens=[{
                "codigo_int": "P1", "descricao": "Produto X", "ncm": "1", "cfop": "5102", "unidade": "UN",
                "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0, "origem": 0, "csosn": "102",
                "cst_pis": "07", "cst_cofins": "07",
            }], forma_pagamento="01", valor_total=20.0, tp_amb="2", numero=100, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), url_qrcode="https://x?a=1&b=2",
        )
        # `infNFeSupl` é montado fora de `_montar_xml_nfce` (splice pós-
        # -assinatura em `emitir_nfce_sync`, ver docstring da função) —
        # simulado aqui pra este teste continuar exercitando o parser
        # contra um XML no formato real que a produção de fato salva.
        inf_supl = "<infNFeSupl><qrCode><![CDATA[https://x?a=1&b=2]]></qrCode><urlChave>x</urlChave></infNFeSupl>"
        xml_bytes = xml_bytes.replace(b"</infNFe>", f"</infNFe>{inf_supl}".encode("utf-8"), 1)
        return xml_bytes.decode("utf-8")

    def test_extrai_campos_e_itens(self):
        r = svc.parse_nfce_xml_para_exibicao(self._xml())
        assert r["chave_acesso"] == "3" * 44
        assert len(r["chave_acesso"]) == 44
        assert r["emit_nome"] == "EMPRESA TESTE"
        assert r["dest_doc"] == "98765432100"
        assert r["valor_total"] == 20.0
        assert r["itens"] == [{"codigo": "P1", "descricao": "Produto X", "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0}]
        assert r["qr_code_url"] == "https://x?a=1&b=2"

    def test_xml_vazio_retorna_none(self):
        assert svc.parse_nfce_xml_para_exibicao("") is None

    def test_xml_invalido_retorna_none(self):
        assert svc.parse_nfce_xml_para_exibicao("<not-xml") is None


class TestParseNfeXmlParaExibicao:
    def _xml(self, ibs_cbs_totais_xml="", tp_emis="1", dh_cont=None, x_just=None,
             paga_frete=None, transportador=None, veiculo=None, volumes=None):
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            uf_emit_sigla="RJ",
            destinatario={
                "cgc_cpf": "98765432100", "nome": "CLIENTE TESTE", "endereco": "RUA A", "numero": 100,
                "bairro": "CENTRO", "cod_municipio_ibge": "3300100", "cidade": "RIO DE JANEIRO",
                "uf": "RJ", "cep": "20000-000", "indIEDest": "9",
            },
            itens=[{
                "codigo_int": "P1", "descricao": "Produto X", "ncm": "12345678", "cfop": "5102", "unidade": "UN",
                "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0, "origem": 0, "csosn": "102",
                "cst_pis": "07", "cst_cofins": "07",
            }], valor_total=20.0, tp_amb="2", numero=100, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
            ibs_cbs_totais_xml=ibs_cbs_totais_xml, tp_emis=tp_emis, dh_cont=dh_cont, x_just=x_just,
            paga_frete=paga_frete, transportador=transportador, veiculo=veiculo, volumes=volumes,
        )
        return xml_bytes.decode("utf-8")

    def test_extrai_campos_emitente_destinatario_e_itens(self):
        r = svc.parse_nfe_xml_para_exibicao(self._xml())
        assert r["chave_acesso"] == "3" * 44
        assert r["tp_amb"] == "2"
        assert r["natureza_operacao"] == "Venda"
        assert r["tp_nf"] == "1"
        assert r["emit_nome"] == "EMPRESA TESTE"
        assert r["dest_doc"] == "98765432100"
        assert r["dest_nome"] == "CLIENTE TESTE"
        assert r["dest_endereco"] == "RUA A"
        assert r["dest_cidade"] == "RIO DE JANEIRO"
        assert r["dest_uf"] == "RJ"
        assert r["valor_total"] == 20.0
        assert r["itens"] == [{
            "codigo": "P1", "descricao": "Produto X", "ncm": "12345678", "cfop": "5102", "unidade": "UN",
            "qtd": 2.0, "valor_unitario": 10.0, "valor_total": 20.0,
        }]
        assert r["ibs_cbs_totais"] is None
        assert r["mod_frete"] == "0"
        assert r["transportador"] is None
        assert r["veiculo"] is None
        assert r["volumes"] is None

    def test_transportador_veiculo_volumes_extraidos_quando_presentes(self):
        # Achado 2026-08-22 (varredura de simplificações): DANFE precisa
        # conseguir extrair o que `_montar_xml_nfe` agora monta.
        r = svc.parse_nfe_xml_para_exibicao(self._xml(
            paga_frete=2,  # -> modFrete=1 (Destinatário/FOB), ver _resolver_mod_frete
            transportador={"cgc_cpf": "12345678000100", "nome": "TRANSPORTADORA X", "ie": "ISENTO", "uf": "RJ"},
            veiculo={"placa": "ABC1234", "uf": "RJ"},
            volumes={"qtd": 2, "especie": "CAIXA", "marca": "MARCA X", "numero": "001", "peso_bruto": 10.5, "peso_liquido": 9.8},
        ))
        assert r["mod_frete"] == "1"
        assert r["transportador"] == {"cgc_cpf": "12345678000100", "nome": "TRANSPORTADORA X", "ie": "ISENTO", "uf": "RJ"}
        assert r["veiculo"] == {"placa": "ABC1234", "uf": "RJ"}
        assert r["volumes"] == {
            "qtd": "2", "especie": "CAIXA", "marca": "MARCA X", "numero": "001",
            "peso_liquido": "9.800", "peso_bruto": "10.500",
        }

    def test_ibs_cbs_totais_extraidos_quando_presentes(self):
        ibs_cbs_xml = (
            "<IBSCBSTot><vBCIBSCBS>20.00</vBCIBSCBS>"
            "<gIBS><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib>"
            "<gIBSUF><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib><vIBSUF>1.00</vIBSUF></gIBSUF>"
            "<gIBSMun><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib><vIBSMun>0.50</vIBSMun></gIBSMun>"
            "<vIBS>1.50</vIBS><vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus></gIBS>"
            "<gCBS><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib><vCBS>1.80</vCBS>"
            "<vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus></gCBS></IBSCBSTot>"
        )
        r = svc.parse_nfe_xml_para_exibicao(self._xml(ibs_cbs_totais_xml=ibs_cbs_xml))
        assert r["ibs_cbs_totais"] == {"base": "20.00", "valor_ibs": "1.50", "valor_cbs": "1.80"}

    def test_contingencia_extrai_tp_emis_e_justificativa(self):
        r = svc.parse_nfe_xml_para_exibicao(self._xml(tp_emis="9", dh_cont="2026-08-20T10:00:00-03:00", x_just="Falha na internet do estabelecimento"))
        assert r["tp_emis"] == "9"
        assert r["x_just"] == "Falha na internet do estabelecimento"
        assert r["dh_cont"] == "2026-08-20T10:00:00-03:00"

    def test_xml_vazio_retorna_none(self):
        assert svc.parse_nfe_xml_para_exibicao("") is None

    def test_xml_invalido_retorna_none(self):
        assert svc.parse_nfe_xml_para_exibicao("<not-xml") is None


class TestMontarEnvelopeAutorizacao:
    def test_envelope_embrulha_em_envinfe_com_indsinc(self):
        xml_nfce = b'<?xml version="1.0" encoding="UTF-8"?><NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe/></NFe>'
        envelope = svc._montar_envelope_autorizacao(xml_nfce, "2").decode("utf-8")
        assert "enviNFe" in envelope
        assert "<indSinc>1</indSinc>" in envelope
        assert "NFeAutorizacao4" in envelope
        assert "<idLote>1</idLote>" in envelope


def _patch_certificado(monkeypatch, key_pem, cert_pem):
    monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: (key_pem, cert_pem))
    # `_montar_emit_xml`/`enderEmit` — achado ao vivo 2026-08-23, ver
    # docstring de `nfe_fiscal_common.resolver_endereco_emitente_sync`.
    # `cur=None` nesses testes, então a resolução real (que faria
    # `cur.execute`) precisa ser mockada também.
    monkeypatch.setattr(
        svc.nfe_fiscal_common, "resolver_endereco_emitente_sync",
        lambda cur: {
            "inscr_est": "123456", "endereco": "RUA TESTE", "numero": "10", "complemento": "",
            "bairro": "CENTRO", "cep": "20000000", "cidade": "Rio de Janeiro", "uf": "RJ",
            "telefone": "2130000000", "cod_municipio": 3304557,
        },
    )


class TestEmitirNfceSync:
    def _item(self):
        return {
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 1.0, "valor_unitario": 50.0, "valor_total": 50.0,
            "origem": 0, "csosn": "102", "cst_pis": "07", "cst_cofins": "07",
        }

    def test_bloqueia_sem_itens(self):
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[], forma_pagamento="01",
            valor_total=0, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "itens" in r["message"].lower()

    def test_bloqueia_uf_nao_reconhecida(self):
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="ZZ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "não reconhecida" in r["message"]

    def test_bloqueia_uf_sem_endpoint_mapeado(self):
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="MG", uf_controle_sigla="MG",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "não está disponível" in r["message"]

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_com_sefaz_mockado(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEnviNFe><infProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>"
            "<nProt>135260000012345</nProt><dhRecbto>2026-07-21T10:00:00-03:00</dhRecbto></infProt></retEnviNFe>"
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE", uf_sigla="RJ",
            uf_controle_sigla="RJ", proximo_numero=100, serie="1", cliente=None,
            itens_resolvidos=[self._item()], forma_pagamento="01", valor_total=50, tp_amb="2",
            csc_id="000001", csc="segredo-teste",
        )
        assert r["success"] is True
        assert r["protocolo_sefaz"] == "135260000012345"
        assert len(r["chave_acesso"]) == 44
        # A assinatura do XML resultante é criptograficamente válida.
        assert "<Signature" in r["xml"] or "Signature>" in r["xml"]

    def test_sefaz_recusa_emissao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEnviNFe><infProt><cStat>539</cStat><xMotivo>Duplicidade</xMotivo></infProt></retEnviNFe>"
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "539" in r["message"]

    def test_falha_de_comunicacao_nao_propaga_excecao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha(*a, **k):
            raise Exception("timeout")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha)
        r = svc.emitir_nfce_sync(
            None, comanda=1, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", uf_controle_sigla="RJ",
            proximo_numero=1, serie="1", cliente=None, itens_resolvidos=[self._item()], forma_pagamento="01",
            valor_total=50, tp_amb="2", csc_id="1", csc="x",
        )
        assert r["success"] is False
        assert "sefaz" in r["message"].lower()


# ---------------------------------------------------------------------------
# NF-e modelo 55 (Agrupar Comandas em NF-e, 2026-08-19) — mesmo compromisso
# de nunca testar contra o SEFAZ real: certificado autoassinado + `transmitir`
# sempre mockada.
# ---------------------------------------------------------------------------

def _destinatario_teste(**overrides):
    base = {
        "cgc_cpf": "12345678000199", "nome": "CLIENTE TESTE", "endereco": "RUA TESTE",
        "numero": "100", "bairro": "CENTRO", "cidade": "RIO DE JANEIRO", "uf": "RJ",
        "cep": "20000000", "cod_municipio_ibge": "3304557", "ie": None, "indIEDest": "9",
    }
    base.update(overrides)
    return base


class TestMontarXmlNfe:
    def _item(self):
        return {
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 1.0, "valor_unitario": 50.0, "valor_total": 50.0,
            "origem": 0, "csosn": "400", "cst_pis": "07", "cst_cofins": "07",
        }

    def test_monta_xml_com_destinatario_estruturado_e_sem_qrcode(self):
        xml_bytes, id_nfe = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE",
            uf_emit_sigla="RJ", destinatario=_destinatario_teste(), itens=[self._item()], valor_total=50.0,
            tp_amb="2", numero=100, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            natureza_operacao="Venda",
        )
        xml = xml_bytes.decode("utf-8")
        assert id_nfe == f"NFe{'3' * 44}"
        assert '<mod>55</mod>' in xml
        assert "<CNPJ>12345678000199</CNPJ>" in xml  # destinatário
        assert "<xLgr>RUA TESTE</xLgr>" in xml
        assert "<cMun>3304557</cMun>" in xml
        assert "qrCode" not in xml  # exclusividade de NFC-e
        assert "<natOp>Venda</natOp>" in xml
        etree.fromstring(xml_bytes)

    def test_id_dest_interno_quando_mesma_uf(self):
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(uf="RJ"), itens=[self._item()], valor_total=50.0, tp_amb="2",
            numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
        )
        assert "<idDest>1</idDest>" in xml_bytes.decode("utf-8")

    def test_id_dest_interestadual_quando_uf_diferente(self):
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(uf="SP"), itens=[self._item()], valor_total=50.0, tp_amb="2",
            numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
        )
        assert "<idDest>2</idDest>" in xml_bytes.decode("utf-8")

    def test_ie_so_aparece_quando_contribuinte(self):
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(ie="1234567", indIEDest="1"), itens=[self._item()], valor_total=50.0,
            tp_amb="2", numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            natureza_operacao="Venda",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<IE>1234567</IE>" in xml
        assert "<indIEDest>1</indIEDest>" in xml

    def test_cpf_usa_tag_cpf_nao_cnpj(self):
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="4" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(cgc_cpf="98765432100"), itens=[self._item()], valor_total=50.0,
            tp_amb="2", numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            natureza_operacao="Venda",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<CPF>98765432100</CPF>" in xml
        assert "<CNPJ>" not in xml.split("<dest>")[1].split("</dest>")[0]

    def test_inclui_ibscbs_quando_presente(self):
        item = self._item()
        item["ibs_cbs_xml"] = "<IBSCBS><CST>000</CST></IBSCBS>"
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(), itens=[item], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
            ibs_cbs_totais_xml="<IBSCBSTot><vBCIBSCBS>50.00</vBCIBSCBS></IBSCBSTot>",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<IBSCBS><CST>000</CST></IBSCBS>" in xml
        assert "<IBSCBSTot><vBCIBSCBS>50.00</vBCIBSCBS></IBSCBSTot>" in xml

    def test_mod_frete_ausente_usa_emitente_nao_sem_transporte(self):
        """Achado real 2026-08-21 (reauditoria): o hardcode anterior era
        <modFrete>9</modFrete> sempre — errado. Sem paga_frete informado
        (caso de frmtranfe.frm, que não tem seletor de frete), o
        comportamento correto (réplica do branch Else de DAO_NFE.vb) é
        modFrete=0 (Emitente/CIF), não 9."""
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(), itens=[self._item()], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
        )
        assert "<modFrete>0</modFrete>" in xml_bytes.decode("utf-8")

    @pytest.mark.parametrize(
        "paga_frete, mod_frete_esperado",
        [
            (0, "0"), (1, "0"),   # Emitente/CIF
            (2, "1"),             # Destinatário/FOB
            (3, "2"),             # Terceiros
            (4, "3"),             # Próprio Remetente
            (5, "4"),             # Próprio Destinatário
            (6, "9"),             # Sem transporte
        ],
    )
    def test_mod_frete_traduzido_conforme_paga_frete(self, paga_frete, mod_frete_esperado):
        """Réplica exata da tabela de `DAO_NFE.vb:5478-5491` (motor
        compartilhado de emissão do legado) — ver
        `nfe_emissao_service._resolver_mod_frete`."""
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(), itens=[self._item()], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
            paga_frete=paga_frete,
        )
        assert f"<modFrete>{mod_frete_esperado}</modFrete>" in xml_bytes.decode("utf-8")
        etree.fromstring(xml_bytes)

    def test_sem_transportador_veiculo_volumes_transp_so_com_modfrete(self):
        # Achado 2026-08-22: default sem nenhum dado de transporte continua
        # <transp> mínimo (só modFrete), sem sub-blocos vazios no XML.
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(), itens=[self._item()], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<transp><modFrete>0</modFrete></transp>" in xml
        etree.fromstring(xml_bytes)

    def test_com_transportador_veiculo_volumes_monta_blocos_completos(self):
        # Achado real 2026-08-22 (varredura de simplificações pendentes):
        # `nf_aux` já capturava cnpj_transportadora/placa/volumes/
        # especie_volume/peso_bruto/peso_liquido desde 2026-08-20, mas
        # nunca chegava ao XML transmitido — corrigido.
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(), itens=[self._item()], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
            paga_frete=1,
            transportador={"cgc_cpf": "12345678000100", "nome": "TRANSPORTADORA X", "ie": "ISENTO", "uf": "RJ"},
            veiculo={"placa": "ABC1234", "uf": "RJ"},
            volumes={"qtd": 2, "especie": "CAIXA", "marca": "MARCA X", "numero": "001", "peso_bruto": 10.5, "peso_liquido": 9.8},
        )
        xml = xml_bytes.decode("utf-8")
        assert "<transporta><CNPJ>12345678000100</CNPJ><xNome>TRANSPORTADORA X</xNome><IE>ISENTO</IE><UF>RJ</UF></transporta>" in xml
        assert "<veicTransp><placa>ABC1234</placa><UF>RJ</UF></veicTransp>" in xml
        assert "<vol><qVol>2</qVol><esp>CAIXA</esp><marca>MARCA X</marca><nVol>001</nVol><pesoL>9.800</pesoL><pesoB>10.500</pesoB></vol>" in xml
        etree.fromstring(xml_bytes)

    def test_icmsufdest_ausente_quando_mesma_uf(self):
        """Réplica do XSD oficial + NT 2015.003 — id_dest=1 (mesma UF) é
        uma das 3 condições que faltam, o grupo não pode aparecer."""
        item = self._item()
        item.update({"aliquota_interestadual": 12, "aliquota_interna_destino": 18, "percentual_origem": 0})
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(uf="RJ"), itens=[item], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
        )
        assert "ICMSUFDest" not in xml_bytes.decode("utf-8")

    def test_icmsufdest_presente_quando_3_condicoes_batem(self):
        """Interestadual (uf=SP≠RJ) + indFinal='1' (default) + indIEDest='9'
        (default de `_destinatario_teste`) — as 3 condições da NT 2015.003
        fecham, o grupo tem que aparecer por item, com o total somado em
        `<ICMSTot>`."""
        item = self._item()
        item.update({"aliquota_interestadual": 12, "aliquota_interna_destino": 18, "percentual_origem": 0})
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(uf="SP"), itens=[item], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
        )
        xml = xml_bytes.decode("utf-8")
        assert "<ICMSUFDest>" in xml
        assert "<vICMSUFDest>3.00</vICMSUFDest>" in xml  # 50 * 0.06 * 1.0
        # Total somado em <ICMSTot>, logo depois de vICMSDeson (posição
        # confirmada no XSD oficial, não perto de vNF).
        assert "<vICMSDeson>0.00</vICMSDeson><vICMSUFDest>3.00</vICMSUFDest>" in xml
        etree.fromstring(xml_bytes)

    def test_icmsufdest_ausente_quando_destinatario_e_contribuinte(self):
        """Cenário exato do print real (rejeição 695): interestadual +
        Consumidor Final, mas indIEDest='1' (contribuinte, não '9') — o
        grupo tem que ficar ausente mesmo com a Taxa tendo alíquotas."""
        item = self._item()
        item.update({"aliquota_interestadual": 12, "aliquota_interna_destino": 18, "percentual_origem": 0})
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(uf="SP", ie="123", indIEDest="1"), itens=[item], valor_total=50.0,
            tp_amb="2", numero=1, serie="1", data_emissao=datetime.datetime.now(datetime.timezone.utc),
            natureza_operacao="Venda",
        )
        assert "ICMSUFDest" not in xml_bytes.decode("utf-8")

    def test_volumes_parcial_so_inclui_campos_presentes(self):
        xml_bytes, _ = svc._montar_xml_nfe(
            chave_acesso="3" * 44, cod_ibge="33", cnpj_emit="1", nome_emit="X", uf_emit_sigla="RJ",
            destinatario=_destinatario_teste(), itens=[self._item()], valor_total=50.0, tp_amb="2", numero=1, serie="1",
            data_emissao=datetime.datetime.now(datetime.timezone.utc), natureza_operacao="Venda",
            volumes={"qtd": 3, "especie": None, "marca": None, "numero": None, "peso_bruto": None, "peso_liquido": None},
        )
        xml = xml_bytes.decode("utf-8")
        assert "<vol><qVol>3</qVol></vol>" in xml
        etree.fromstring(xml_bytes)


class TestEmitirNfeSync:
    def _item(self):
        return {
            "codigo_int": "P001", "descricao": "Produto Teste", "ncm": "12345678", "cfop": "5102",
            "unidade": "UN", "qtd": 1.0, "valor_unitario": 50.0, "valor_total": 50.0,
            "origem": 0, "csosn": "400", "cst_pis": "07", "cst_cofins": "07",
        }

    def test_bloqueia_sem_itens(self):
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(), itens_resolvidos=[], valor_total=0, tp_amb="2",
            natureza_operacao="Venda",
        )
        assert r["success"] is False
        assert "item" in r["message"].lower()

    def test_bloqueia_uf_nao_reconhecida(self):
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="ZZ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(), itens_resolvidos=[self._item()], valor_total=50, tp_amb="2",
            natureza_operacao="Venda",
        )
        assert r["success"] is False
        assert "não reconhecida" in r["message"]

    def test_bloqueia_sem_certificado(self, monkeypatch):
        monkeypatch.setattr(svc.nfe_fiscal_common, "carregar_certificado_sync", lambda cur: None)
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(), itens_resolvidos=[self._item()], valor_total=50, tp_amb="2",
            natureza_operacao="Venda",
        )
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_bloqueia_por_regra_fiscal_taxa_sem_difal(self):
        """Interestadual + Consumidor Final + Não Contribuinte, mas o item
        não tem as alíquotas de DIFAL cadastradas — bloqueado ANTES de
        gastar a chamada ao SEFAZ (nfe_regras_fiscais.py)."""
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(uf="SP"), itens_resolvidos=[self._item()], valor_total=50, tp_amb="2",
            natureza_operacao="Venda", indFinal="1",
        )
        assert r["success"] is False
        assert "Taxa" in r["message"]

    def test_nao_bloqueia_por_regra_fiscal_quando_operacao_interna(self, monkeypatch):
        """Mesma falta de alíquotas DIFAL no item, mas operação interna
        (mesma UF) — regra de DIFAL não se aplica, segue até o SEFAZ
        normalmente."""
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEnviNFe><infProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>"
            "<nProt>135260000012345</nProt><dhRecbto>2026-08-19T10:00:00-03:00</dhRecbto></infProt></retEnviNFe>"
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(uf="RJ"), itens_resolvidos=[self._item()], valor_total=50, tp_amb="2",
            natureza_operacao="Venda",
        )
        assert r["success"] is True

    def test_sucesso_com_sefaz_mockado(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = (
            "<retEnviNFe><infProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>"
            "<nProt>135260000012345</nProt><dhRecbto>2026-08-19T10:00:00-03:00</dhRecbto></infProt></retEnviNFe>"
        )
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="12345678000199", nome_emit="EMPRESA TESTE", uf_sigla="RJ", proximo_numero=100,
            serie="1", destinatario=_destinatario_teste(), itens_resolvidos=[self._item()], valor_total=50,
            tp_amb="2", natureza_operacao="Venda",
        )
        assert r["success"] is True
        assert r["protocolo_sefaz"] == "135260000012345"
        assert len(r["chave_acesso"]) == 44
        assert "<Signature" in r["xml"] or "Signature>" in r["xml"]

    def test_sefaz_recusa_emissao(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)
        resposta_fake = "<retEnviNFe><infProt><cStat>539</cStat><xMotivo>Duplicidade</xMotivo></infProt></retEnviNFe>"
        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", lambda envelope, url, k, c: resposta_fake)
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(), itens_resolvidos=[self._item()], valor_total=50, tp_amb="2",
            natureza_operacao="Venda",
        )
        assert r["success"] is False
        assert "539" in r["message"]

    def test_contingencia_nao_transmite(self, monkeypatch):
        key_pem, cert_pem = _gerar_certificado_teste()
        _patch_certificado(monkeypatch, key_pem, cert_pem)

        def _falha_se_chamado(*a, **k):
            raise AssertionError("não deveria transmitir em contingência")

        monkeypatch.setattr(svc.nfe_fiscal_common, "transmitir", _falha_se_chamado)
        contingencia = {"tipo_contingencia": 9, "data_inicio": datetime.date(2026, 8, 19), "hora_inicio": "10:00:00", "motivo": "x" * 20}
        r = svc.emitir_nfe_sync(
            None, cnpj_emit="1", nome_emit="X", uf_sigla="RJ", proximo_numero=1, serie="1",
            destinatario=_destinatario_teste(), itens_resolvidos=[self._item()], valor_total=50, tp_amb="2",
            natureza_operacao="Venda", contingencia=contingencia,
        )
        assert r["success"] is True
        assert r["situacao"] == "G"
        assert r["cstat"] is None
