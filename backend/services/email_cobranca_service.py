"""Envio de e-mail de cobrança — motor novo, sem equivalente 1:1 no legado
(o legado só tinha os campos de configuração `Email de Cobrança`, nunca um
envio de fato implementado — confirmado por busca no VB.NET/VB6, nenhuma
chamada real a `smtp_COBRANCA` foi encontrada além da tela de configuração).

Lê a configuração de `controle_aux` (`e_mail_COBRANCA`/`ident_COBRANCA`/
`smtp_COBRANCA`/`porta_smtp_COBRANCA`/`login_COBRANCA`/`senha_COBRANCA`/
`ssl_COBRANCA` — mesmos campos já expostos em `Controle do Sistema > aba
Outros > Configuração de Emails`, `frontend/app/controle-sistema.tsx`) e
envia via SMTP puro (`smtplib`), sem dependência de nenhum serviço externo.

**Detecção de criptografia**: `ssl_COBRANCA` é um único checkbox "Requer
SSL" no legado, que na prática cobre duas convenções SMTP diferentes —
SSL implícito (porta 465, conexão já cifrada desde o início) e STARTTLS
(porta 587, conexão em texto plano que faz upgrade pra TLS). Resolvido por
porta: 465 usa `SMTP_SSL`, qualquer outra porta com `ssl_COBRANCA` ligado
usa `SMTP` + `starttls()` — cobre o caso real testado (Titan Email, porta
587, STARTTLS) sem exigir um campo de configuração a mais.

Reutilizável por qualquer tela que precise mandar e-mail de cobrança (hoje:
nenhuma tela ainda anexa o PDF do boleto de verdade — isso depende do motor
de geração de PDF/código de barras, ainda não implementado, ver
PENDENCIAS.md > "Geração de Boletos"). Este módulo só cuida do envio em si.
"""
import asyncio
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from db.connection import _open_conn


def _buscar_config_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 e_mail_COBRANCA, ident_COBRANCA, smtp_COBRANCA, porta_smtp_COBRANCA, "
            "login_COBRANCA, senha_COBRANCA, ssl_COBRANCA FROM controle_aux WHERE empresa_aux=0"
        )
        row = cur.fetchone() or {}
        cur.close()
        return row
    finally:
        conn.close()


def _enviar_email_sync(
    servidor: str,
    banco: str,
    destinatario: str,
    assunto: str,
    corpo_html: str,
    anexos: Optional[list] = None,
) -> dict:
    cfg = _buscar_config_sync(servidor, banco)
    email_remetente = (cfg.get("e_mail_COBRANCA") or "").strip()
    smtp_host = (cfg.get("smtp_COBRANCA") or "").strip()
    smtp_porta = int(cfg.get("porta_smtp_COBRANCA") or 0)
    login = (cfg.get("login_COBRANCA") or "").strip() or email_remetente
    senha = cfg.get("senha_COBRANCA") or ""
    usa_ssl = bool(cfg.get("ssl_COBRANCA"))
    identificacao = (cfg.get("ident_COBRANCA") or "").strip() or email_remetente

    if not email_remetente or not smtp_host or not smtp_porta:
        return {
            "success": False,
            "message": "Configuração de Email de Cobrança incompleta — preencha Email, SMTP e Porta em "
            "Controle do Sistema > aba Outros > Configuração de Emails.",
        }

    msg = MIMEMultipart()
    msg["From"] = f"{identificacao} <{email_remetente}>"
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    for anexo in anexos or []:
        parte = MIMEApplication(anexo["conteudo"], Name=anexo["nome_arquivo"])
        parte["Content-Disposition"] = f'attachment; filename="{anexo["nome_arquivo"]}"'
        msg.attach(parte)

    try:
        if smtp_porta == 465:
            smtp = smtplib.SMTP_SSL(smtp_host, smtp_porta, timeout=20)
        else:
            smtp = smtplib.SMTP(smtp_host, smtp_porta, timeout=20)
            if usa_ssl:
                smtp.starttls()
        try:
            if login and senha:
                smtp.login(login, senha)
            smtp.sendmail(email_remetente, [destinatario], msg.as_string())
        finally:
            smtp.quit()
        return {"success": True, "message": f"E-mail enviado para {destinatario}."}
    except smtplib.SMTPAuthenticationError as e:
        return {"success": False, "message": f"Falha de autenticação SMTP: {e}"}
    except (smtplib.SMTPException, OSError) as e:
        return {"success": False, "message": f"Falha ao enviar e-mail: {e}"}


async def enviar_email(
    servidor: str,
    banco: str,
    destinatario: str,
    assunto: str,
    corpo_html: str,
    anexos: Optional[list] = None,
) -> dict:
    return await asyncio.to_thread(_enviar_email_sync, servidor, banco, destinatario, assunto, corpo_html, anexos)
