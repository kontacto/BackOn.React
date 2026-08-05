# Passo a Passo — Instalação do Agente de Impressão

Guia rápido pra instalar e testar o agente numa máquina Windows que tem
uma impressora térmica USB conectada. Para o funcionamento interno
(arquitetura, endpoints, erros comuns em detalhe), ver `README.md`.

## 1. Pré-requisitos na máquina que tem a impressora

- **Windows** (a máquina física com a impressora térmica USB conectada).
- **Python 3.10+** instalado. Se não tiver: baixe em
  [python.org/downloads](https://www.python.org/downloads/) e marque a
  opção **"Add python.exe to PATH"** durante a instalação.
- A impressora já **instalada normalmente no Windows** (com driver,
  aparecendo em `Painel de Controle > Dispositivos e Impressoras`) — o
  agente manda os bytes pro spooler do Windows, não fala direto com a
  porta USB.

## 2. Copiar a pasta do agente pra essa máquina

Copie a pasta `print-agent/` (dentro do repositório `APPIAREACT`) para a
máquina — ex.: `C:\PrintAgent\`. Pode ser via rede, pendrive, git clone, o
que for mais prático.

## 3. Instalar as dependências

Abra o PowerShell **dentro da pasta** `print-agent` e rode:

```powershell
cd C:\PrintAgent
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Isso instala `requests` (comunicação HTTP) e `pywin32` (acesso ao spooler
de impressão do Windows).

## 4. Descobrir o nome exato da impressora

Abra `Painel de Controle > Dispositivos e Impressoras` e copie o nome
**exatamente** como aparece lá (ex.: `EPSON TM-T20X`, `POS-58`, etc.) —
precisa bater com o cadastro no `config.json` mais adiante.

## 5. Configurar

```powershell
copy config.exemplo.json config.json
notepad config.json
```

Ajuste os campos:

| Campo | O que colocar |
|---|---|
| `api_base` | URL do backend, ex.: `http://192.168.0.10:8081/api` — use o **IP da máquina do backend**, não `localhost`, a menos que o agente rode na mesma máquina do backend. |
| `servidor` / `banco` | A mesma conexão (empresa) que você já usa pra logar no app. |
| `computador` | Um nome pra identificar esta máquina (ex.: `PC-CAIXA1`). |
| `impressora_padrao` | O nome exato copiado no passo 4. |
| `intervalo_segundos` | Pode deixar `3` (padrão). |

Salve e feche.

## 6. Rodar o agente

Ainda no PowerShell, dentro da pasta:

```powershell
.venv\Scripts\python agente_impressao.py
```

Deve aparecer:

```
Agente de impressão iniciado — computador='PC-CAIXA1', polling a cada 3s.
Pressione Ctrl+C para encerrar.
```

**Deixe essa janela aberta** — é o agente rodando. Fechá-la encerra o
processo.

## 7. Testar

Abra **outro** PowerShell (sem fechar o anterior), na mesma pasta:

```powershell
.venv\Scripts\python testar_enfileirar.py
```

Se tudo estiver certo, em até `intervalo_segundos` a impressora deve
imprimir um cupom de teste **sem nenhum diálogo aparecer na tela** — esse
é o sinal de sucesso.

## 8. Se der erro

- **"Nenhuma impressora informada..."** → `impressora_padrao` vazio ou
  com nome errado no `config.json`.
- **"pywin32 não instalado"** → repita `pip install -r requirements.txt`
  dentro do `.venv`.
- **Falha de conexão com o backend** → confira o `api_base` (IP/porta
  acessível a partir dessa máquina — teste abrindo essa URL num
  navegador).
- Qualquer outro erro (impressora offline, sem papel, nome errado) aparece
  direto no terminal do agente.

Por enquanto o agente precisa rodar manualmente (janela aberta) — deixar
ele iniciando sozinho com o Windows (serviço/tarefa agendada) é um passo
que ainda não implementamos.
