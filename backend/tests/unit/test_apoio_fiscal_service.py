"""Testes unitários de Apoio Fiscal BackOn
(services/apoio_fiscal_service.py) — tradução de rejeição conhecida vs.
fallback genérico, e-mail sempre tentado (best-effort), WhatsApp só
tentado quando habilitado+Cel Suporte preenchido, e nenhuma falha de
canal de notificação propaga exceção nem muda a tradução devolvida."""
import services.apoio_fiscal_service as svc


class FakeCursor:
    def __init__(self, one=None):
        self._one = list(one or [])
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        pass

    def close(self):
        pass


def _patch_open_conn(monkeypatch, fantasia="LOJA TESTE", cel_suporte=""):
    cur = FakeCursor(one=[{"fantasia": fantasia}, {"cel_suporte": cel_suporte}])
    conn = FakeConn(cur)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn, cur


def _patch_email(monkeypatch, success=True):
    chamadas = []

    def fake_enviar(servidor, banco, destinatario, assunto, corpo_html, anexos=None):
        chamadas.append((servidor, banco, destinatario, assunto, corpo_html))
        return {"success": success}

    monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", fake_enviar)
    return chamadas


def _patch_whatsapp_desabilitado(monkeypatch):
    monkeypatch.setattr(svc.whatsapp_repository, "get_config_raw", lambda *a, **k: {"enabled": False})


class TestResolverErroFiscal:
    def test_codigo_conhecido_devolve_traducao_especifica(self):
        erro = svc.resolver_erro_fiscal("539")
        assert erro.titulo == "Numeração duplicada"
        assert "não é um erro na sua nota" in erro.explicacao_curta

    def test_difal_695_conhecido(self):
        erro = svc.resolver_erro_fiscal("695")
        assert "DIFAL" in erro.titulo or "ICMS" in erro.titulo

    def test_codigo_desconhecido_cai_no_fallback(self):
        erro = svc.resolver_erro_fiscal("999999")
        assert erro is svc.FALLBACK_GENERICO
        assert erro.titulo == "Apoio Fiscal BackOn"


class TestNotificarRejeicaoSync:
    def test_email_sempre_tentado(self, monkeypatch):
        _patch_open_conn(monkeypatch, fantasia="LOJA TESTE", cel_suporte="")
        chamadas = _patch_email(monkeypatch, success=True)
        _patch_whatsapp_desabilitado(monkeypatch)

        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NFC-e", codigo_rejeicao="539",
            mensagem_original="Duplicidade de NFC-e", referencia="chave123",
        )
        assert r["titulo"] == "Numeração duplicada"
        assert r["notificado_suporte"]["email"] is True
        assert len(chamadas) == 1
        assert chamadas[0][2] == "suporte@kontacto.com.br"
        assert "539" in chamadas[0][3] and "LOJA TESTE" in chamadas[0][3]

    def test_whatsapp_nao_tentado_quando_desabilitado(self, monkeypatch):
        _patch_open_conn(monkeypatch, cel_suporte="11999998888")
        _patch_email(monkeypatch, success=True)
        _patch_whatsapp_desabilitado(monkeypatch)

        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NFC-e", codigo_rejeicao="897",
            mensagem_original="cNF inválido",
        )
        assert r["notificado_suporte"]["whatsapp"] is False

    def test_whatsapp_nao_tentado_sem_cel_suporte(self, monkeypatch):
        _patch_open_conn(monkeypatch, cel_suporte="")
        _patch_email(monkeypatch, success=True)
        monkeypatch.setattr(
            svc.whatsapp_repository, "get_config_raw",
            lambda *a, **k: {"enabled": True, "provider": "twilio"},
        )
        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NFC-e", codigo_rejeicao="897",
            mensagem_original="cNF inválido",
        )
        assert r["notificado_suporte"]["whatsapp"] is False

    def test_whatsapp_tentado_quando_habilitado_e_cel_preenchido(self, monkeypatch):
        _patch_open_conn(monkeypatch, cel_suporte="11999998888")
        _patch_email(monkeypatch, success=True)
        monkeypatch.setattr(
            svc.whatsapp_repository, "get_config_raw",
            lambda *a, **k: {"enabled": True, "provider": "twilio", "twilio_sid": "x", "twilio_token": "y", "from_number": "+15550000"},
        )

        class FakeResult:
            success = True

        chamadas = []

        class FakeProvider:
            def send_text(self, to_e164, message):
                chamadas.append((to_e164, message))
                return FakeResult()

        monkeypatch.setattr(svc, "whatsapp_build_provider", lambda cfg: FakeProvider())

        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NF-e", codigo_rejeicao="695",
            mensagem_original="Informado indevidamente o grupo de ICMS para a UF de destino",
        )
        assert r["notificado_suporte"]["whatsapp"] is True
        assert len(chamadas) == 1
        assert chamadas[0][0].startswith("+55")

    def test_falha_email_nao_derruba_resposta(self, monkeypatch):
        _patch_open_conn(monkeypatch)

        def boom(*a, **k):
            raise Exception("SMTP fora do ar")

        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", boom)
        _patch_whatsapp_desabilitado(monkeypatch)

        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NFC-e", codigo_rejeicao="539",
            mensagem_original="Duplicidade de NFC-e",
        )
        assert r["titulo"] == "Numeração duplicada"
        assert r["notificado_suporte"]["email"] is False

    def test_falha_whatsapp_nao_derruba_resposta(self, monkeypatch):
        _patch_open_conn(monkeypatch, cel_suporte="11999998888")
        _patch_email(monkeypatch, success=True)
        monkeypatch.setattr(
            svc.whatsapp_repository, "get_config_raw",
            lambda *a, **k: {"enabled": True, "provider": "twilio"},
        )

        def boom(cfg):
            raise Exception("provider indisponível")

        monkeypatch.setattr(svc, "whatsapp_build_provider", boom)

        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NFC-e", codigo_rejeicao="539",
            mensagem_original="Duplicidade de NFC-e",
        )
        assert r["notificado_suporte"]["email"] is True
        assert r["notificado_suporte"]["whatsapp"] is False

    def test_codigo_desconhecido_usa_fallback_mas_ainda_notifica(self, monkeypatch):
        _patch_open_conn(monkeypatch)
        _patch_email(monkeypatch, success=True)
        _patch_whatsapp_desabilitado(monkeypatch)

        r = svc.notificar_rejeicao_sync(
            "srv", "bd", tipo_documento="NFS-e", codigo_rejeicao="ADN_GENERICO",
            mensagem_original="Erro não catalogado ainda",
        )
        assert r["titulo"] == "Apoio Fiscal BackOn"
        assert r["notificado_suporte"]["email"] is True


class TestNotificarRejeicoesLoteSync:
    def test_lista_vazia_devolve_none_e_nao_notifica(self, monkeypatch):
        chamadas = _patch_email(monkeypatch, success=True)
        r = svc.notificar_rejeicoes_lote_sync("srv", "bd", tipo_documento="Cancelamento NFC-e (lote)", itens_falhos=[])
        assert r is None
        assert len(chamadas) == 0

    def test_agrupa_por_codigo_uma_notificacao_so(self, monkeypatch):
        _patch_open_conn(monkeypatch, fantasia="LOJA TESTE")
        chamadas = _patch_email(monkeypatch, success=True)
        _patch_whatsapp_desabilitado(monkeypatch)

        itens_falhos = [
            {"referencia": 101, "codigo_rejeicao": "539", "mensagem_original": "Duplicidade de NFC-e"},
            {"referencia": 102, "codigo_rejeicao": "539", "mensagem_original": "Duplicidade de NFC-e"},
            {"referencia": 103, "codigo_rejeicao": "897", "mensagem_original": "cNF inválido"},
        ]
        r = svc.notificar_rejeicoes_lote_sync(
            "srv", "bd", tipo_documento="Cancelamento NFC-e (lote)", itens_falhos=itens_falhos,
        )
        assert r["total"] == 3
        # 1 SÓ e-mail, cobrindo os 3 itens — nunca 1 por item.
        assert len(chamadas) == 1
        assert "3" in chamadas[0][3]  # assunto menciona o total
        grupos = {g["codigo_rejeicao"]: g for g in r["grupos"]}
        assert grupos["539"]["quantidade"] == 2
        assert grupos["539"]["referencias"] == ["101", "102"]
        assert grupos["897"]["quantidade"] == 1
        assert r["notificado_suporte"]["email"] is True

    def test_codigo_desconhecido_no_lote_usa_fallback(self, monkeypatch):
        _patch_open_conn(monkeypatch)
        _patch_email(monkeypatch, success=True)
        _patch_whatsapp_desabilitado(monkeypatch)
        itens_falhos = [{"referencia": 1, "codigo_rejeicao": "XYZ_NUNCA_VISTO", "mensagem_original": "erro raro"}]
        r = svc.notificar_rejeicoes_lote_sync(
            "srv", "bd", tipo_documento="Inutilização NFC-e (lote)", itens_falhos=itens_falhos,
        )
        assert r["grupos"][0]["titulo"] == "Apoio Fiscal BackOn"

    def test_falha_email_nao_derruba_resposta(self, monkeypatch):
        _patch_open_conn(monkeypatch)
        _patch_whatsapp_desabilitado(monkeypatch)

        def boom(*a, **k):
            raise Exception("SMTP fora do ar")

        monkeypatch.setattr(svc.email_cobranca_service, "_enviar_email_sync", boom)
        itens_falhos = [{"referencia": 1, "codigo_rejeicao": "539", "mensagem_original": "Duplicidade"}]
        r = svc.notificar_rejeicoes_lote_sync(
            "srv", "bd", tipo_documento="Cancelamento NFC-e (lote)", itens_falhos=itens_falhos,
        )
        assert r["notificado_suporte"]["email"] is False
        assert r["total"] == 1

    def test_whatsapp_tentado_uma_vez_para_o_lote_inteiro(self, monkeypatch):
        _patch_open_conn(monkeypatch, cel_suporte="11999998888")
        _patch_email(monkeypatch, success=True)
        monkeypatch.setattr(
            svc.whatsapp_repository, "get_config_raw",
            lambda *a, **k: {"enabled": True, "provider": "twilio"},
        )

        class FakeResult:
            success = True

        chamadas = []

        class FakeProvider:
            def send_text(self, to_e164, message):
                chamadas.append((to_e164, message))
                return FakeResult()

        monkeypatch.setattr(svc, "whatsapp_build_provider", lambda cfg: FakeProvider())
        itens_falhos = [
            {"referencia": 1, "codigo_rejeicao": "539", "mensagem_original": "x"},
            {"referencia": 2, "codigo_rejeicao": "897", "mensagem_original": "y"},
        ]
        r = svc.notificar_rejeicoes_lote_sync(
            "srv", "bd", tipo_documento="Retransmitir NFC-e (lote)", itens_falhos=itens_falhos,
        )
        assert len(chamadas) == 1
        assert r["notificado_suporte"]["whatsapp"] is True
