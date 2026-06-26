# Módulo de Envio por WhatsApp

Permite enviar **Pedidos de Venda** e **Ordens de Serviço** diretamente aos
clientes via WhatsApp. Arquitetura desacoplada (Strategy Pattern) com suporte a
múltiplos provedores, configuráveis em runtime pela tela **Configurações → WhatsApp**.

## Arquitetura (SOLID / camadas)

```
routes/whatsapp.py              # Controller/API — só orquestra, sem regra de negócio
models/whatsapp_schemas.py      # DTOs (Pydantic)
services/whatsapp/
  ├─ providers.py               # Strategy: IWhatsappProvider + Twilio/Meta/Evolution + factory
  ├─ repository.py              # Repository: SQL (config, logs, documentos) + DDL automático
  └─ service.py                 # Service: validators, message builder, envio c/ retry, log
```

### Strategy Pattern (provedores)
`IWhatsappProvider` (ABC) com `validate_config()` e `send_text(to_e164, message)`.
Implementações: `TwilioProvider`, `MetaProvider`, `EvolutionProvider`.
A factory `build_provider(cfg)` instancia conforme `cfg["provider"]`.
Trocar de provedor = só mudar a config; nenhum código de negócio muda.

## Banco de Dados (criado automaticamente — CREATE TABLE IF NOT EXISTS)

### whatsapp_config (1 linha por banco/tenant)
provider, from_number, twilio_sid, twilio_token, meta_phone_id, meta_token,
evolution_url, evolution_instance, evolution_apikey, signature, enabled, updated_at.

### whatsapp_send_log
id, company_id, document_type (PED|OS), document_id, customer_id, phone_number,
message, sent_at, status (SUCCESS|FAILED), error_message, provider,
provider_message_id, duration_ms (observabilidade), user_id.
Índices: `IX_wsl_document (document_type, document_id)`, `IX_wsl_customer`, `IX_wsl_sent_at`.

## Endpoints (`/api`)
| Método | Rota | Descrição |
|---|---|---|
| GET | `/whatsapp/config?servidor&banco` | Lê config (segredos **mascarados**) |
| POST | `/whatsapp/config` | Salva config (segredos vazios = mantém os atuais) |
| GET | `/whatsapp/preview?servidor&banco&document_type&document_id` | Telefone + mensagem montada |
| POST | `/whatsapp/send` | Envia (valida, retry, registra log) |
| GET | `/whatsapp/logs?servidor&banco&document_type&document_id` | Histórico de envios |

## Segurança
- Segredos **nunca** são retornados pela API (apenas flags `*_set`).
- Ao salvar, campos de segredo vazios **preservam** o valor anterior.
- `sanitize_text` remove caracteres de controle da mensagem.
- Validação E.164 antes do envio.
- Gating de permissão no app: `PEDIDO.WHATSAPP` / `OS.WHATSAPP`.
- Credenciais ficam no SQL do tenant; nada hardcoded no código.

## Performance / Observabilidade
- Envio em thread (`asyncio.to_thread`) — não bloqueia o event loop.
- **Retry** automático (até 3x, backoff) em falhas transitórias (timeout/5xx/429).
- `duration_ms` registrado em cada envio.
- Toda falha de comunicação/autenticação é logada em `whatsapp_send_log`.

## Mensagem (exemplo OS)
```
Olá João,

Segue seu(sua) Ordem de Serviço: Nº 12345.

Data: 25/06/2026
Equipamento/Veículo: ABC-1234 VW Gol
Nº de Série/Chassi: 9BWZZZ...
Relato do cliente: ...
Serviço executado: ...
Obs: ...
Status: Aberto
Valor: R$ 1.250,00

Qualquer dúvida estamos à disposição.

Equipe XYZ
```

## Fase 2 (futuro)
- Anexos (PDF do Pedido/OS, boletos, imagens) — requer hospedagem pública do arquivo.
- Fila para envios em lote.
- Link de visualização online do documento.

## Como testar de ponta a ponta
1. Configurações → WhatsApp → escolher provedor, preencher credenciais, **Ativar** e Salvar.
2. Abrir um Pedido/OS salvo → botão **Enviar por WhatsApp** → conferir preview → Enviar.
3. Aba **Histórico** mostra o resultado (sucesso/erro) de cada envio.
