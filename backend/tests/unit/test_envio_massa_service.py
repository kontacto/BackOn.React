"""Testes unitários de Envio em Massa (WhatsApp/E-mail) — recurso
reutilizável (ver docstring do service), usado por Mala Direta e
Inatividade de Clientes. Reaproveita `whatsapp/service.send` e
`email_cobranca_service.enviar_email` já existentes — este serviço só faz
o loop + render de `{nome}`, mockados aqui."""
import asyncio

import services.envio_massa_service as svc


class FakeWhatsapp:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def send(self, servidor, banco, doc_type, doc_id, user_id, company_id, override_phone, override_message):
        self.chamadas.append((doc_type, doc_id, override_message))
        return self.respostas.pop(0)


class FakeEmail:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def enviar(self, servidor, banco, destinatario, assunto, corpo_html):
        self.chamadas.append((destinatario, assunto, corpo_html))
        return self.respostas.pop(0)


def test_render_substitui_nome():
    assert svc._render("Olá {nome}, tudo bem?", "Zé") == "Olá Zé, tudo bem?"
    assert svc._render("Olá {Nome}!", "Maria") == "Olá Maria!"


class TestWhatsappMassa:
    def test_conta_sucesso_e_falha(self, monkeypatch):
        fake = FakeWhatsapp([{"success": True}, {"success": False, "message": "Sem celular válido"}])
        monkeypatch.setattr(svc.whatsapp_service, "send", fake.send)
        r = asyncio.run(svc.enviar_whatsapp_massa("srv", "bd", [
            {"codigo": 1, "nome": "Zé"}, {"codigo": 2, "nome": "Maria"},
        ], "Olá {nome}, promoção especial!"))
        assert r["totais"] == {"enviados": 1, "falhas": 1, "total": 2}
        assert fake.chamadas[0] == ("CLI", 1, "Olá Zé, promoção especial!")
        assert r["resultados"][1]["message"] == "Sem celular válido"

    def test_lista_vazia(self, monkeypatch):
        fake = FakeWhatsapp([])
        monkeypatch.setattr(svc.whatsapp_service, "send", fake.send)
        r = asyncio.run(svc.enviar_whatsapp_massa("srv", "bd", [], "oi"))
        assert r["totais"] == {"enviados": 0, "falhas": 0, "total": 0}


class TestEmailMassa:
    def test_sem_email_reporta_falha_sem_chamar_envio(self, monkeypatch):
        fake = FakeEmail([{"success": True}])
        monkeypatch.setattr(svc, "enviar_email", fake.enviar)
        r = asyncio.run(svc.enviar_email_massa("srv", "bd", [
            {"codigo": 1, "nome": "Zé", "email": ""}, {"codigo": 2, "nome": "Maria", "email": "maria@x.com"},
        ], "Assunto {nome}", "Corpo pra {nome}"))
        assert r["totais"] == {"enviados": 1, "falhas": 1, "total": 2}
        assert r["resultados"][0]["message"] == "Sem e-mail cadastrado."
        assert len(fake.chamadas) == 1
        assert fake.chamadas[0] == ("maria@x.com", "Assunto Maria", "Corpo pra Maria")

    def test_falha_no_envio_smtp(self, monkeypatch):
        fake = FakeEmail([{"success": False, "message": "Falha de autenticação SMTP"}])
        monkeypatch.setattr(svc, "enviar_email", fake.enviar)
        r = asyncio.run(svc.enviar_email_massa("srv", "bd", [
            {"codigo": 1, "nome": "Zé", "email": "ze@x.com"},
        ], "Assunto", "Corpo"))
        assert r["resultados"][0]["success"] is False
        assert r["resultados"][0]["message"] == "Falha de autenticação SMTP"
