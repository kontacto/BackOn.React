"""Testes unitários do envio de e-mail de cobrança (ver
services/email_cobranca_service.py) — smtplib mockado, sem conexão real."""
import services.email_cobranca_service as svc


class FakeCursor:
    def __init__(self, row=None):
        self._row = row

    def execute(self, q, p=None):
        pass

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self, as_dict=False):
        return FakeCursor(self._row)

    def close(self):
        pass


CFG_VALIDA = {
    "e_mail_COBRANCA": "adm@kontacto.com.br", "ident_COBRANCA": "Adm Kontacto",
    "smtp_COBRANCA": "smtp.titan.email", "porta_smtp_COBRANCA": 587,
    "login_COBRANCA": "adm@kontacto.com.br", "senha_COBRANCA": "segredo", "ssl_COBRANCA": True,
}


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, user, senha):
        self.logged_in = (user, senha)

    def sendmail(self, de, para, msg):
        self.sent = (de, para, msg)

    def quit(self):
        self.quit_called = True


def _patch(monkeypatch, cfg):
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: FakeConn(cfg))
    FakeSMTP.instances = []
    monkeypatch.setattr(svc.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(svc.smtplib, "SMTP_SSL", FakeSMTP)


class TestEnviarEmail:
    def test_configuracao_incompleta(self, monkeypatch):
        _patch(monkeypatch, {})
        r = svc._enviar_email_sync("srv", "bd", "dest@teste.com", "Assunto", "<p>corpo</p>")
        assert r["success"] is False
        assert "incompleta" in r["message"]

    def test_envia_com_starttls_porta_587(self, monkeypatch):
        _patch(monkeypatch, CFG_VALIDA)
        r = svc._enviar_email_sync("srv", "bd", "dest@teste.com", "Assunto", "<p>corpo</p>")
        assert r["success"] is True
        smtp = FakeSMTP.instances[0]
        assert smtp.host == "smtp.titan.email"
        assert smtp.port == 587
        assert smtp.started_tls is True
        assert smtp.logged_in == ("adm@kontacto.com.br", "segredo")
        assert smtp.sent[0] == "adm@kontacto.com.br"
        assert smtp.sent[1] == ["dest@teste.com"]
        assert smtp.quit_called is True

    def test_envia_com_ssl_implicito_porta_465(self, monkeypatch):
        cfg = {**CFG_VALIDA, "porta_smtp_COBRANCA": 465}
        _patch(monkeypatch, cfg)
        r = svc._enviar_email_sync("srv", "bd", "dest@teste.com", "Assunto", "<p>corpo</p>")
        assert r["success"] is True
        smtp = FakeSMTP.instances[0]
        assert smtp.port == 465
        assert smtp.started_tls is False  # SMTP_SSL já cifra a conexão, não precisa de starttls

    def test_anexo_incluido_no_corpo(self, monkeypatch):
        _patch(monkeypatch, CFG_VALIDA)
        r = svc._enviar_email_sync(
            "srv", "bd", "dest@teste.com", "Assunto", "<p>corpo</p>",
            anexos=[{"nome_arquivo": "boleto.pdf", "conteudo": b"conteudo-fake"}],
        )
        assert r["success"] is True
        smtp = FakeSMTP.instances[0]
        assert "boleto.pdf" in smtp.sent[2]

    def test_falha_autenticacao(self, monkeypatch):
        _patch(monkeypatch, CFG_VALIDA)

        class FakeSMTPAuthFail(FakeSMTP):
            def login(self, user, senha):
                raise svc.smtplib.SMTPAuthenticationError(535, b"bad credentials")

        monkeypatch.setattr(svc.smtplib, "SMTP", FakeSMTPAuthFail)
        r = svc._enviar_email_sync("srv", "bd", "dest@teste.com", "Assunto", "<p>corpo</p>")
        assert r["success"] is False
        assert "autenticação" in r["message"]
