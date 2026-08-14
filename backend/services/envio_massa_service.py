"""Envio em Massa (WhatsApp/E-mail) — recurso reutilizável, não amarrado a
uma tela só (pedido explícito do usuário, 2026-08-07: "esse recurso de
envio vai ser introduzido em consulta de clientes entre outros"). Nasceu
junto com a migração de "Mala Direta" (`Geral\\FrmMalDir2.FRM`, Painel de
Relatórios > Clientes) e "Inatividade de Clientes" (ação de reengajamento),
mas não depende de nenhuma das duas — qualquer tela que já tenha uma lista
de clientes/destinatários pode chamar este serviço.

**Não reinventa nenhum mecanismo de envio** — usa exatamente a
infraestrutura já existente e testada nesta migração:
- **WhatsApp**: `services/whatsapp/service.py` (`send`, `document_type=
  'CLI'`) — o mesmo motor já usado pela tela de Telemarketing pra mandar
  mensagem avulsa a um cliente (config/provider/template/assinatura,
  histórico de envio, retry em falha transitória). Este serviço só faz o
  LOOP pelos destinatários e monta a mensagem final por substituição de
  variáveis simples (`{nome}`) — a mensagem final já pronta é passada como
  `override_message`, então o motor de WhatsApp nem tenta reconstruir a
  partir do próprio template de documento (que é pensado pra Pedido/OS,
  com `{itens}`/`{total}`/etc., que não fazem sentido aqui).
- **E-mail**: `services/email_cobranca_service.py` (`enviar_email`) — SMTP
  puro, mesma configuração já usada no envio de cobrança
  (`Controle do Sistema > aba Outros > Configuração de Emails`).

**Escopo por canal**: WhatsApp só é viável pra Cliente (o motor
`document_type=CLI` só resolve contra a tabela `cliente`, não
`fornecedor` — confirmado em `whatsapp/repository.py`). E-mail funciona
pra Cliente OU Fornecedor (ambos têm coluna `e_mail` própria) — quem
chama este serviço decide o destinatário, este serviço só dispara.

Cada destinatário sem telefone/e-mail válido é reportado individualmente
como falha (`sem_contato`), não interrompe o lote inteiro.
"""
import asyncio
from typing import Optional

from services.whatsapp import service as whatsapp_service
from services.email_cobranca_service import enviar_email


def _render(template: str, nome: str) -> str:
    return (template or "").replace("{nome}", nome or "").replace("{Nome}", nome or "")


async def enviar_whatsapp_massa(
    servidor: str, banco: str, destinatarios: list[dict], mensagem_template: str, user_id: Optional[int] = None,
) -> dict:
    """`destinatarios`: lista de {codigo, nome} (cliente.codigo)."""
    resultados = []
    for d in destinatarios:
        codigo = d.get("codigo")
        nome = (d.get("nome") or "").strip()
        mensagem = _render(mensagem_template, nome)
        r = await whatsapp_service.send(servidor, banco, "CLI", codigo, user_id, None, None, mensagem)
        if r.get("success"):
            resultados.append({"codigo": codigo, "nome": nome, "success": True})
        else:
            resultados.append({"codigo": codigo, "nome": nome, "success": False, "message": r.get("message") or "Falha no envio."})
    enviados = sum(1 for r in resultados if r["success"])
    return {
        "success": True, "resultados": resultados,
        "totais": {"enviados": enviados, "falhas": len(resultados) - enviados, "total": len(resultados)},
    }


async def enviar_email_massa(
    servidor: str, banco: str, destinatarios: list[dict], assunto_template: str, corpo_template: str,
) -> dict:
    """`destinatarios`: lista de {codigo, nome, email}."""
    resultados = []
    for d in destinatarios:
        codigo = d.get("codigo")
        nome = (d.get("nome") or "").strip()
        email = (d.get("email") or "").strip()
        if not email:
            resultados.append({"codigo": codigo, "nome": nome, "success": False, "message": "Sem e-mail cadastrado."})
            continue
        assunto = _render(assunto_template, nome)
        corpo = _render(corpo_template, nome)
        r = await enviar_email(servidor, banco, email, assunto, corpo)
        if r.get("success"):
            resultados.append({"codigo": codigo, "nome": nome, "success": True})
        else:
            resultados.append({"codigo": codigo, "nome": nome, "success": False, "message": r.get("message") or "Falha no envio."})
    enviados = sum(1 for r in resultados if r["success"])
    return {
        "success": True, "resultados": resultados,
        "totais": {"enviados": enviados, "falhas": len(resultados) - enviados, "total": len(resultados)},
    }
