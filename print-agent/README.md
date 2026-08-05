# Agente de Impressão Silenciosa

Resolve a impressão **sem diálogo** para impressoras térmicas conectadas
por **USB local** (não-rede) numa máquina Windows — nenhum navegador
oferece uma API de impressão silenciosa, então esse pedaço roda fora do
navegador, como um processo Python independente na própria máquina que
tem a impressora fisicamente conectada.

Para impressoras de **rede** (Ethernet/Wi-Fi, aceitam conexão TCP crua na
porta 9100), não é necessário nada disso — o backend já manda os bytes
direto pro socket da impressora (`POST /api/impressao/rede`,
`services/impressao_service.py::enviar_rede`). Este agente só é necessário
para impressoras USB-local.

## Como funciona

1. Alguma tela do app (ex.: Checkout, Pedido Bar) enfileira um job:
   `POST /api/impressao/fila` com `computador` (o nome da máquina que tem
   a impressora), `impressora` (nome dela no Windows) e `conteudo` (texto
   do cupom).
2. Este agente, rodando naquela máquina, faz **polling** a cada poucos
   segundos: `GET /api/impressao/fila/pendentes?computador=X`.
3. Para cada job pendente, manda os bytes crus pro spooler do Windows via
   `win32print` (modo `RAW` — sem diálogo, sem preview, sem nada visível
   na tela do usuário).
4. Confirma o resultado ao backend: `POST /api/impressao/fila/{id}/confirmar`.

Se o agente cair no meio de um job (buscou mas nunca confirmou), o
backend recoloca esse job como pendente depois de alguns minutos
(`RECUPERACAO_ENVIADO_MINUTOS` em `impressao_service.py`) — não fica
travado para sempre.

## Instalação

Guia passo a passo (com explicação de cada campo, erros comuns e critério
de teste de sucesso): ver **`INSTALACAO.md`**.

Resumo rápido:

```powershell
cd print-agent
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.exemplo.json config.json
notepad config.json    # ajustar servidor/banco/computador/impressora
```

### `config.json`

| Campo               | Descrição                                                                 |
|----------------------|---------------------------------------------------------------------------|
| `api_base`           | URL base da API, ex.: `http://192.168.0.10:8081/api` (IP do servidor backend, não `localhost`, a menos que o agente rode na mesma máquina do backend). |
| `servidor`/`banco`   | Mesma conexão (empresa) já usada pelo login do app.                       |
| `computador`         | Nome que identifica esta máquina — deve bater com o `computador` que a tela usa ao enfileirar. Sugestão: o mesmo "Nome do Computador" já cadastrado em Controle do Sistema > Impressoras. |
| `impressora_padrao`  | Nome exato da impressora no Windows (`Painel de Controle > Dispositivos e Impressoras`), usado quando o job não especifica uma. |
| `intervalo_segundos` | Intervalo do polling (padrão 3s).                                         |

## Rodando

```powershell
.venv\Scripts\python agente_impressao.py
```

Deixa rodando em primeiro plano num terminal (Ctrl+C encerra). Rodar como
serviço Windows/tarefa agendada (pra sobreviver a reboot sem precisar
logar) é um passo futuro, fora desta primeira versão.

## Testando

Com o agente rodando em um terminal, em outro:

```powershell
.venv\Scripts\python testar_enfileirar.py
```

Enfileira um cupom de teste pro `computador` do `config.json`. Se tudo
estiver certo, o cupom sai na impressora configurada em até
`intervalo_segundos`, sem nenhum diálogo aparecer na tela — esse é o
critério de sucesso do teste.

## Erros comuns

- **"Nenhuma impressora informada no job nem configurada como padrão"**:
  `impressora_padrao` vazio no `config.json` e o job não veio com
  `impressora` preenchida.
- **"pywin32 não instalado"**: rode `pip install pywin32` (já está em
  `requirements.txt`, só falha se instalado fora do Windows).
- **Falha de conexão com o backend**: confere `api_base` — precisa ser o
  IP/porta acessível a partir desta máquina, não necessariamente
  `localhost`.
- Erros do próprio Windows ao abrir a impressora (nome errado, impressora
  offline/sem papel) aparecem na mensagem de erro confirmada ao backend
  (`mensagem_erro` na tabela `impressao_fila`) — consultável também via
  `GET /api/impressao/fila/pendentes` enquanto ainda não foi confirmado.
