# Guia de Instalação — Back-On (Backend + Frontend Web)

> Para: Juan · Este guia cobre a instalação de uma máquina de cliente **nova** (sem nada do Back-On rodando ainda) e como funciona o dia a dia das atualizações depois disso. Qualquer dúvida durante o processo, me chama.

## O quadro geral, antes de começar

Cada cliente roda seu próprio Backend (Python) + Frontend Web (a tela do sistema) na própria máquina, conversando com o SQL Server dele. A Kontacto publica versões novas num "repositório de distribuição" próprio (um Blob da Azure — não é o GitHub), e cada máquina de cliente baixa essas versões sozinha, sem precisar de acesso ao código-fonte nem a nenhuma senha do GitHub.

```
Kontacto publica uma versão nova
        │
        ▼
  Blob de distribuição (Azure)
        │
        │  a máquina do cliente baixa sozinha
        ▼
  Backend + Frontend rodando no cliente
```

Existem **dois momentos** diferentes, e este guia cobre os dois:

1. **1ª instalação** — a máquina não tem nada ainda. Você roda um script uma vez, ele resolve tudo.
2. **Dia a dia depois disso** — não precisa mais mexer em nada manualmente. O próprio sistema verifica sozinho se há versão nova, avisa, e quem aplica é o usuário master, direto pela tela.

---

## Parte 1 — Pré-requisitos da máquina

Antes de tocar em qualquer coisa deste guia, a máquina precisa ter:

- **SQL Server** configurado com o banco do cliente já restaurado.
- **Python** instalado (versão compatível — ver `BACKEND_DEPLOY_WINDOWS.md` na raiz do repositório para a versão exata e o driver do SQL Server).

> Esses dois itens **não mudam** com este guia — é a mesma preparação de sempre. O que muda é tudo que vem depois: não precisa mais clonar o repositório git nem instalar as dependências Python na mão.

---

## Parte 2 — 1ª instalação (máquina nova)

### Passo 1 — Copiar a pasta do instalador

Você vai receber (ou copiar de outra máquina/pendrive) só a pasta `updater\` — **não precisa do repositório inteiro**, só dessa pasta.

Copie ela para dentro de onde o sistema vai morar nessa máquina. Exemplo, usando `C:\BackOn` como pasta raiz:

```
C:\BackOn\updater\
```

### Passo 2 — Preencher a configuração

Dentro de `C:\BackOn\updater\`, existe um arquivo `config.exemplo.json`. Copie ele e renomeie a cópia para `config.json`, no mesmo lugar.

Abra `config.json` num editor de texto e preencha:

```json
{
  "manifestUrl": "COLE AQUI A URL QUE A KONTACTO TE PASSOU",
  "installDir": "C:\\BackOn",
  "currentBackendDir": "C:\\BackOn\\current-backend",
  "currentFrontendDir": "C:\\BackOn\\current-frontend",
  "backendPort": 8081,
  "healthCheckTimeoutSeconds": 30,
  "healthCheckRetries": 10,
  "keepReleases": 2
}
```

> **`manifestUrl`**: é uma URL específica que a Kontacto te fornece, terminando em algo como `.../manifest.json?sv=...&sig=...`. Essa URL já tem embutida a credencial de leitura — não precisa (e não dá) de usar link do GitHub aqui, é um endereço completamente diferente, aponta pro Blob de distribuição da Kontacto.
>
> Os outros campos (`installDir`, `currentBackendDir`, `currentFrontendDir`) você mesmo escolhe — só troque `C:\BackOn` pelo caminho que fizer sentido nessa máquina, mantendo a mesma estrutura (uma pasta raiz + duas subpastas `current-backend`/`current-frontend`).

### Passo 3 — Rodar o instalador

Abra o **PowerShell como Administrador** (botão direito → "Executar como administrador"), navegue até a pasta e rode:

```powershell
cd C:\BackOn\updater
powershell -ExecutionPolicy Bypass -File .\bootstrap-install.ps1
```

Isso faz tudo sozinho:

1. Baixa a versão mais recente publicada pela Kontacto.
2. Confere a integridade dos arquivos baixados (um "checksum" de segurança).
3. Coloca o Backend e o Frontend no lugar certo.
4. Registra o serviço do Windows que mantém o Backend rodando sempre, mesmo depois de reiniciar o PC.
5. Liga esse serviço.
6. Confirma que o Backend realmente respondeu (um "teste de saúde").

Acompanhe a saída no terminal — cada linha é logada também em `C:\BackOn\updater\logs\bootstrap-AAAAMMDD.log`, caso precise revisar depois.

**Se terminar sem erro**: pronto, o sistema está no ar.

**Se der erro no passo 6** (o teste de saúde): não entre em pânico — normalmente os arquivos já foram colocados corretamente, só o processo não conseguiu subir a tempo. O próprio script te diz isso na mensagem final. Confira:
```powershell
Get-ScheduledTask -TaskName "BackOn-Backend" | Get-ScheduledTaskInfo
```
e os logs dentro de `C:\BackOn\current-backend\logs\`. Depois de identificar/corrigir o problema, pode rodar `bootstrap-install.ps1` de novo — ele não duplica nada, é seguro repetir.

### Passo 4 — Configurar pela tela (e não mexer mais em arquivo nenhum)

Com o Backend no ar, abra `http://localhost:8081` num navegador nessa mesma máquina. Faça login com o usuário **master**.

Vá em **Configurações → Serviço do Sistema → Atualização** e preencha os **mesmos dados** que você já colocou no `config.json` (URL do manifest, pastas, e agora também o **intervalo de verificação em minutos** — ex.: 30). Clique em **Gravar**.

A partir deste momento, o `config.json` que você editou no Passo 2 deixa de ser a fonte de verdade — é essa tela que manda daqui pra frente, e o próprio Backend passa a verificar sozinho, no intervalo configurado, se existe uma versão nova.

---

## Parte 3 — Dia a dia (depois de instalado)

Nenhum passo manual daqui pra frente. O fluxo normal é:

1. A Kontacto publica uma versão nova (do lado deles).
2. O sistema do cliente verifica sozinho (no intervalo configurado) e já baixa se encontrar algo novo — mas **nunca troca a versão em produção sozinho**.
3. Quando há algo baixado e pronto, aparece uma **bolinha vermelha de aviso** no ícone "Configurações" do menu lateral, visível pra qualquer usuário logado.
4. O usuário **master** abre Configurações → Serviço do Sistema → Atualização e vê "Atualização disponível — pronta para aplicar", com um botão **Aplicar agora**.
5. Clicar em "Aplicar agora" troca a versão de verdade e reinicia o Backend — leva alguns segundos, durante os quais o sistema fica temporariamente fora do ar pra quem estiver usando.
6. Se algo der errado depois de aplicar, existe sempre um botão **Reverter para versão anterior** na mesma tela, disponível a qualquer momento (não só logo depois de atualizar).

Outros dois botões úteis na mesma tela:

- **Verificar agora**: dispara a checagem na hora, sem esperar o intervalo automático. Não precisa de confirmação, não reinicia nada, é só um "checa de novo".
- **Intervalo = 0**: desliga a verificação automática por completo — nesse caso, só o botão "Verificar agora" checa, manualmente, quando alguém clicar.

---

## Perguntas frequentes

**"O que eu coloco no campo URL do manifest?"**
A URL específica que a Kontacto te passa, terminando em `manifest.json?...` com uma credencial embutida. Nunca é a URL do GitHub.

**"Se eu colocar o link do repositório do GitHub, funciona só que sem mostrar a credencial?"**
Não — esse campo não fala com o GitHub de jeito nenhum. É uma URL de um serviço de armazenamento diferente (Azure Blob), formato específico. Colar a URL do GitHub aí resulta em erro ao tentar baixar.

**"O sistema sabe sozinho onde colocar o Backend e onde colocar o Frontend?"**
Sim — o pacote publicado pela Kontacto já vem separado em duas partes, e cada uma vai pra pasta configurada (`currentBackendDir`/`currentFrontendDir`), automaticamente.

**"Preciso ficar de olho pra aplicar toda atualização assim que sai?"**
Não precisa ser imediato — "Aplicar agora" fica disponível esperando até você (ou o cliente, se ele for master) decidir o melhor momento, geralmente fora do horário de expediente da loja.

---

## Se algo der errado

| Sintoma | O que provavelmente é |
|---|---|
| `config.json` não encontrado | Esqueceu de copiar `config.exemplo.json` → `config.json`, ou está rodando o script de outra pasta. |
| Erro de "sha256 não confere" | Falha rara de rede no download — rode o script de novo. |
| Health check falha no bootstrap | Ver Passo 3 acima — normalmente é só questão de tempo/serviço não ter subido a tempo; os arquivos já estão certos. |
| Tela mostra "Falha ao gravar a configuração" | Confirme que o Backend foi reiniciado depois de qualquer atualização de código (isso só deve acontecer em ambiente de desenvolvimento/teste, não em produção). |

Qualquer coisa fora desse padrão, me chama antes de tentar forçar — prefiro ver o log real (`updater\logs\` ou `current-backend\logs\`) a adivinhar.
