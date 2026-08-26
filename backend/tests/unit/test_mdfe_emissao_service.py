"""Testes UNITÁRIOS do MDF-e — Fase B (emissão real, encerrar, cancelar,
consultar, gerar XML), `mdfe_emissao_service.py`. Mesmo padrão de sempre:
cursor falso + monkeypatch nas peças que falariam com o SEFAZ de verdade
(`nfe_fiscal_common.transmitir`/`assinar_xml`/`carregar_certificado_sync`)
— nenhuma chamada de rede real, nenhum documento fiscal transmitido."""
import base64
import gzip

import services.mdfe_emissao_service as svc
from services import nfe_fiscal_common


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


def _sem_rede(monkeypatch, *, cert=(b"key", b"cert"), transmitido="<cStat>100</cStat><nProt>P1</nProt><dhRecbto>D1</dhRecbto>"):
    """Neutraliza toda peça que falaria de verdade com o SEFAZ/certificado —
    usado pelos testes de orquestração (gating de situação, validações),
    que não precisam exercitar o builder de XML real."""
    monkeypatch.setattr(nfe_fiscal_common, "carregar_certificado_sync", lambda cur: cert)
    monkeypatch.setattr(nfe_fiscal_common, "resolver_tp_amb_sync", lambda cur: "2")
    monkeypatch.setattr(nfe_fiscal_common, "resolver_endpoint_mdfe", lambda servico, tp_amb: "https://mdfe-homologacao.svrs.rs.gov.br/ws/x.asmx")
    monkeypatch.setattr(nfe_fiscal_common, "assinar_xml", lambda xml_bytes, id_ref, key_pem, cert_pem, **kw: xml_bytes)
    monkeypatch.setattr(nfe_fiscal_common, "transmitir", lambda envelope, url, key_pem, cert_pem, timeout=30: transmitido)
    monkeypatch.setattr(svc, "_montar_xml_mdfe_sync", lambda cur, cod_mdfe: b"<MDFe/>")


class TestMontarEnvelopeSoapGzipB64:
    def test_round_trip_gzip_base64(self):
        xml_original = b'<infMDFe Id="MDFe12345">conteudo</infMDFe>'
        envelope = nfe_fiscal_common.montar_envelope_soap_gzip_b64(
            xml_original, "MDFeRecepcaoSinc", nfe_fiscal_common.MDFE_NS,
        )
        texto = envelope.decode("utf-8")
        assert "<mdfeDadosMsg" in texto
        assert nfe_fiscal_common.MDFE_NS in texto
        inicio = texto.index(">", texto.index("<mdfeDadosMsg")) + 1
        fim = texto.index("</mdfeDadosMsg>")
        b64 = texto[inicio:fim]
        descomprimido = gzip.decompress(base64.b64decode(b64))
        assert descomprimido == xml_original


class TestMontarEnvelopeSoapNsCustomizavel:
    def test_default_preserva_nfe(self):
        envelope = nfe_fiscal_common.montar_envelope_soap(b"<evento/>", "NFeRecepcaoEvento4")
        texto = envelope.decode("utf-8")
        assert "nfeDadosMsg" in texto
        assert nfe_fiscal_common.NFE_NS in texto

    def test_ns_customizado_pro_mdfe(self):
        envelope = nfe_fiscal_common.montar_envelope_soap(
            b"<eventoMDFe/>", "MDFeRecepcaoEvento", ns=nfe_fiscal_common.MDFE_NS, tag="mdfeDadosMsg",
        )
        texto = envelope.decode("utf-8")
        assert "mdfeDadosMsg" in texto
        assert nfe_fiscal_common.MDFE_NS in texto
        assert nfe_fiscal_common.NFE_NS not in texto


class TestExtrairBloco:
    def test_extrai_elemento_com_atributos(self):
        xml = '<retMDFe><protMDFe versao="3.00"><infProt><nProt>1</nProt></infProt></protMDFe></retMDFe>'
        bloco = nfe_fiscal_common.extrair_bloco(xml, "protMDFe")
        assert bloco == '<protMDFe versao="3.00"><infProt><nProt>1</nProt></infProt></protMDFe>'

    def test_ausente_devolve_none(self):
        assert nfe_fiscal_common.extrair_bloco("<a></a>", "protMDFe") is None


class TestEmitirMdfeSync:
    def test_bloqueia_situacao_ja_transmitida(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "T"}])
        r = svc.emitir_mdfe_sync(cur, 1, "user")
        assert r["success"] is False
        assert "edição ou não transmitidos" in r["message"]

    def test_bloqueia_sem_notas_anexadas(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "A"}, {"qtd": 0}])
        r = svc.emitir_mdfe_sync(cur, 1, "user")
        assert r["success"] is False
        assert "Anexe pelo menos uma Nota" in r["message"]

    def test_bloqueia_sem_veiculo_ou_motorista(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "A", "veiculo": None, "motorista": 5}, {"qtd": 1}])
        r = svc.emitir_mdfe_sync(cur, 1, "user")
        assert r["success"] is False
        assert "Veículo e Motorista" in r["message"]

    def test_bloqueia_sem_certificado(self, monkeypatch):
        _sem_rede(monkeypatch, cert=None)
        cur = FakeCursor(one=[{"situacao": "A", "veiculo": 3, "motorista": 5}, {"qtd": 1}])
        r = svc.emitir_mdfe_sync(cur, 1, "user")
        assert r["success"] is False
        assert "certificado" in r["message"].lower()

    def test_sucesso_grava_situacao_t_e_numeracao(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[
            {"situacao": "A", "veiculo": 3, "motorista": 5}, {"qtd": 1},
            {"cgc": "12345678000199", "uf": "RJ"},
            {"cidade": "Rio de Janeiro", "uf": "RJ"},  # _resolver_origem_empresa_sync passo 1
            {"codmun": 3304557},                        # _resolver_origem_empresa_sync passo 2 (JOIN municipio)
            {"numero_MDFE": 10, "serie_MDFE": "1"},
        ])
        r = svc.emitir_mdfe_sync(cur, 1, "user")
        assert r["success"] is True
        assert r["num_mdfe"] == 11
        update_final = next(q for q, p in cur.queries if "SET situacao='T'" in q)
        assert update_final
        aux_update = next((q, p) for q, p in cur.queries if q.strip().startswith("UPDATE controle_aux"))
        assert aux_update[1] == (11, "1")

    def test_sefaz_recusa_nao_grava_situacao_t(self, monkeypatch):
        _sem_rede(monkeypatch, transmitido="<cStat>225</cStat><xMotivo>Falha de schema</xMotivo>")
        cur = FakeCursor(one=[
            {"situacao": "A", "veiculo": 3, "motorista": 5}, {"qtd": 1},
            {"cgc": "12345678000199", "uf": "RJ"},
            {"cidade": "Rio de Janeiro", "uf": "RJ"},
            {"codmun": 3304557},
            {"numero_MDFE": 10, "serie_MDFE": "1"},
        ])
        r = svc.emitir_mdfe_sync(cur, 1, "user")
        assert r["success"] is False
        assert "225" in r["message"]
        assert not any("SET situacao='T'" in q for q, p in cur.queries)
        assert not any(q.strip().startswith("UPDATE controle_aux") for q, p in cur.queries)


class TestEncerrarMdfeSync:
    def test_exige_situacao_transmitida(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "A"}])
        r = svc.encerrar_mdfe_sync(cur, 1, 3304557, "user")
        assert r["success"] is False
        assert "Transmitido" in r["message"]

    def test_exige_municipio_encerra(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "T", "chave_acesso": "3" + "0" * 43}])
        r = svc.encerrar_mdfe_sync(cur, 1, None, "user")
        assert r["success"] is False
        assert "Município de Encerramento" in r["message"]

    def test_sucesso_grava_situacao_e(self, monkeypatch):
        _sem_rede(monkeypatch, transmitido="<cStat>135</cStat>")
        cur = FakeCursor(one=[
            {"situacao": "T", "chave_acesso": "33" + "0" * 42, "protocolo_sefaz": "P1", "tp_amb": "2", "historico": None},
            {"cgc": "12345678000199"},
        ])
        r = svc.encerrar_mdfe_sync(cur, 1, 3304557, "user")
        assert r["success"] is True
        update = next((q, p) for q, p in cur.queries if "SET situacao='E'" in q)
        assert update[1][0] == 3304557


class TestCancelarMdfeSync:
    def test_exige_motivo_minimo_15_chars(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor()
        r = svc.cancelar_mdfe_sync(cur, 1, "curto", "user")
        assert r["success"] is False
        assert "15 caracteres" in r["message"]

    def test_exige_situacao_transmitida(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "A"}])
        r = svc.cancelar_mdfe_sync(cur, 1, "motivo bem detalhado do cancelamento", "user")
        assert r["success"] is False
        assert "Transmitido" in r["message"]

    def test_sucesso_grava_situacao_c(self, monkeypatch):
        _sem_rede(monkeypatch, transmitido="<cStat>135</cStat>")
        cur = FakeCursor(one=[
            {"situacao": "T", "chave_acesso": "33" + "0" * 42, "protocolo_sefaz": "P1", "tp_amb": "2", "historico": None},
            {"cgc": "12345678000199"},
        ])
        r = svc.cancelar_mdfe_sync(cur, 1, "motivo bem detalhado do cancelamento", "user")
        assert r["success"] is True
        assert any("SET situacao='C'" in q for q, p in cur.queries)


class TestConsultarSituacaoMdfeSync:
    def test_sem_chave_nao_consulta(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"chave_acesso": None}])
        r = svc.consultar_situacao_mdfe_sync(cur, 1)
        assert r["success"] is False
        assert "nada a consultar" in r["message"]

    def test_com_protocolo_atualiza_situacao_t(self, monkeypatch):
        _sem_rede(monkeypatch, transmitido='<retMDFe><protMDFe versao="3.00"><infProt><cStat>100</cStat><nProt>P9</nProt><dhRecbto>D9</dhRecbto></infProt></protMDFe></retMDFe>')
        cur = FakeCursor(one=[{"chave_acesso": "33" + "0" * 42, "tp_amb": "2"}])
        r = svc.consultar_situacao_mdfe_sync(cur, 1)
        assert r["success"] is True
        assert r["protocolo_sefaz"] == "P9"
        assert any("SET situacao='T'" in q for q, p in cur.queries)


class TestGerarXmlMdfeSync:
    def test_exige_ja_transmitido(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "A"}])
        r = svc.gerar_xml_mdfe_sync(cur, 1)
        assert r["success"] is False
        assert "já transmitido" in r["message"]

    def test_sucesso_reaproveita_xml_protmdfe_ja_salvo(self, monkeypatch):
        _sem_rede(monkeypatch)
        cur = FakeCursor(one=[{"situacao": "T", "xml_protMDFe": "<protMDFe/>", "chave_acesso": "33" + "0" * 42}])
        r = svc.gerar_xml_mdfe_sync(cur, 1)
        assert r["success"] is True
        assert "<mdfeProc" in r["xml"]
        assert "<protMDFe/>" in r["xml"]


class TestMontarXmlMdfeSyncTpTransp:
    """Corrige o bug do legado (`Command7_Click` sempre passa `TpTransp=
    "2"` e `MontaXMLMDFe` só emite a tag quando o valor é DIFERENTE de
    "2" — a tag nunca sai no XML de produção hoje). Aqui a tag sai sempre
    que `mdfe.tptransp` estiver preenchido, `"2"` incluso."""

    def _cursor_minimo(self, tptransp):
        m = {
            "codigo": 1, "chave_acesso": "33" + "1" * 42, "tp_amb": "2", "dhemi": "2026-08-22T10:00:00",
            "serie_mdfe": "1", "num_mdfe": 11, "ufini": "RJ", "uffim": "RJ", "percurso": "", "obs": None,
            "tptransp": tptransp, "placa": "ABC1234", "doc_proprietario": None, "reboque": None, "ajudante": None,
            "motorista": 5, "veiculo": 3, "tpRod": "01", "tpCar": "00", "uf_veiculo": "RJ",
        }
        motorista = {"nome": "JOAO DA SILVA", "cpf": "11122233344"}
        controle = {
            "cgc": "12345678000199", "rz_social": "EMPRESA TESTE", "fantasia": "", "inscr_est": "123",
            "endereco": "RUA X", "numero": 10, "complemento": "", "bairro": "CENTRO", "cep": "20000000",
            "uf": "RJ", "telefone": "2130000000",
        }
        origem = {"cidade": "Rio de Janeiro", "uf": "RJ", "cod_municipio": 3304557}
        return FakeCursor(
            one=[m, motorista, controle, {"cidade": "Rio de Janeiro", "uf": "RJ"}, {"codmun": 3304557}],
            many=[[], []],
        )

    def test_emite_tag_quando_preenchido_com_valor_2(self, monkeypatch):
        cur = self._cursor_minimo(tptransp=2)
        xml = svc._montar_xml_mdfe_sync(cur, 1)
        assert b"<tpTransp>2</tpTransp>" in xml

    def test_omite_tag_quando_vazio(self, monkeypatch):
        cur = self._cursor_minimo(tptransp=None)
        xml = svc._montar_xml_mdfe_sync(cur, 1)
        assert b"<tpTransp>" not in xml

    def test_numero_endereco_int_nao_quebra_montagem(self, monkeypatch):
        """Achado ao vivo 2026-08-22 (1ª emissão real de MDF-e, ARGEN
        TESTE): `controle.numero` é `INT` no banco real, não string — o
        código original fazia `(controle.get("numero") or "").strip()`,
        que quebra com `AttributeError: 'int' object has no attribute
        'strip'` assim que `numero` vem preenchido (valor truthy, nunca
        cai no fallback `""`). `_cursor_minimo` já usa `numero=10` (int)
        pra refletir o schema real — este teste só deixa a asserção
        explícita, em vez de só "não lançou exceção"."""
        cur = self._cursor_minimo(tptransp=2)
        xml = svc._montar_xml_mdfe_sync(cur, 1)
        assert b"<nro>10</nro>" in xml

    def test_infadic_fecha_infcpl_corretamente(self, monkeypatch):
        """Achado ao vivo 2026-08-22 (2ª emissão real de MDF-e, ARGEN
        TESTE, depois de corrigir o bug do `numero`): a tag `<infCpl>`
        nunca era fechada antes de `</infAdic>` — SEFAZ recusou o XML
        com "Opening and ending tag mismatch". `_cursor_minimo` tinha
        `obs=None` em todo teste anterior, então esse ramo nunca foi
        exercitado pela suíte até agora."""
        m_extra = self._cursor_minimo(tptransp=2)
        m_extra._one[0]["obs"] = "Observação de teste"
        xml = svc._montar_xml_mdfe_sync(m_extra, 1)
        assert b"<infAdic><infCpl>Observa" in xml
        assert b"</infCpl></infAdic>" in xml

    def test_cmuncarrega_cmundescarga_sempre_int_puro(self, monkeypatch):
        """Achado ao vivo 2026-08-22 (3ª emissão real de MDF-e, ARGEN
        TESTE): SEFAZ recusou com "Falha no schema XML... valor
        '3304557.0' inválido" — `mdfe_notas.origem`/`.destino` já são
        `INT` reais (normalizados na Fase A), mas o builder buscava
        `municipio.codigo` (FLOAT) de novo pra `cMunDescarga` em vez de
        reaproveitar `mn.destino` já limpo — o valor saía com sufixo
        ".0", inválido pro schema MDF-e (`TCodMunIBGE`). Corrigido pra
        usar `mn.destino`/`mn.origem` direto (sempre `int(...)` também,
        defesa em profundidade)."""
        m = {
            "codigo": 1, "chave_acesso": "33" + "2" * 42, "tp_amb": "2", "dhemi": "2026-08-22T10:00:00",
            "serie_mdfe": "1", "num_mdfe": 11, "ufini": "RJ", "uffim": "RJ", "percurso": "", "obs": None,
            "tptransp": 2, "placa": "ABC1234", "doc_proprietario": None, "reboque": None, "ajudante": None,
            "motorista": 5, "veiculo": 3, "tpRod": "01", "tpCar": "00", "uf_veiculo": "RJ",
        }
        motorista = {"nome": "JOAO DA SILVA", "cpf": "11122233344"}
        controle = {
            "cgc": "12345678000199", "rz_social": "EMPRESA TESTE", "fantasia": "", "inscr_est": "123",
            "endereco": "RUA X", "numero": 10, "complemento": "", "bairro": "CENTRO", "cep": "20000000",
            "uf": "RJ", "telefone": "2130000000",
        }
        cur = FakeCursor(
            one=[m, motorista, controle, {"cidade": "Rio de Janeiro", "uf": "RJ"}, {"codmun": 3304557}],
            many=[
                [{"origem": 3304557, "descricao": "Rio de Janeiro"}],
                [{"chave_acesso": "33" + "0" * 42, "valor_total": 2.45, "peso_bruto": 0.0,
                  "destino": 3304557, "descricao": "Rio de Janeiro"}],
            ],
        )
        xml = svc._montar_xml_mdfe_sync(cur, 1)
        assert b"<cMunCarrega>3304557</cMunCarrega>" in xml
        assert b"<cMunDescarga>3304557</cMunDescarga>" in xml
        assert b"3304557.0" not in xml
