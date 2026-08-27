# Atualizador automático — Back-On (Backend + Frontend Web)

Mantém uma instalação de cliente atualizada automaticamente a partir das
releases publicadas pela Kontacto, sem precisar de ninguém entrando na
máquina pra rodar `git pull` manualmente. Ver `PENDENCIAS.md` >
"Serviço do Sistema — Atualização" pro desenho completo (arquitetura,
decisões, o que ficou fora de escopo).

**Atualizado 2026-08-26 — o disparo automático deixou de ser a Tarefa
Agendada `BackOn-Updater` (`install-updater-task.ps1`, PAUSADA) e virou
uma tarefa de fundo dentro do próprio processo do backend, configurada
pela tela "Serviço do Sistema" > "Atualização" (Configurações, só
usuário master).** `apply_update.ps1` ganhou um parâmetro `-Mode`
(`Full` | `DownloadOnly` | `ApplyPending` | `Rollback`) — o backend
invoca `-Mode DownloadOnly` no ciclo periódico (nunca troca a versão em
produção sozinho) e `-Mode ApplyPending`/`-Mode Rollback` quando o
usuário confirma pela tela. `-Mode Full` (padrão, sem `-Mode`) continua
existindo pra uso manual/standalone — é o comportamento original deste
script, baixa e aplica na mesma chamada.

**Esta pasta é o que se instala num cliente** — nunca o repositório
inteiro. `updater/publish/` é a única exceção: só roda na máquina da
Kontacto (ver `updater/publish/README.md`).

## Instalação — 1ª vez numa máquina nova

Pré-requisito de infraestrutura (SQL Server, Python) continua em
`BACKEND_DEPLOY_WINDOWS.md` — isso não muda. O que muda é que **não é
mais preciso subir o backend manualmente antes** — o `bootstrap-install.ps1`
faz isso por você:

1. Copie esta pasta `updater\` pra dentro do `installDir` que você vai
   usar (ex.: `C:\BackOn\updater\`).
2. Copie `config.exemplo.json` pra `config.json` e preencha `manifestUrl`
   (peça a URL com a SAS de leitura pra Kontacto — nunca é a connection
   string completa), `currentBackendDir`/`currentFrontendDir` (ex.:
   `C:\BackOn\current-backend`/`current-frontend`) e `installDir`. A tela
   "Serviço do Sistema" **não existe ainda** nesse ponto (só existe depois
   que já tem um backend rodando) — essa 1ª configuração é sempre pelo
   arquivo.
3. Rode, **como Administrador**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\bootstrap-install.ps1
   ```
   Isso baixa a release publicada mais recente, cria as junctions, registra
   a Tarefa Agendada `BackOn-Backend` (apontando pro caminho estável da
   junction — nunca precisa ser reregistrada depois) e confirma que o
   backend sobe de verdade (health check). Ver o cabeçalho de
   `bootstrap-install.ps1` pro porquê disso ser um script separado de
   `apply_update.ps1` (gap real: `apply_update.ps1` sozinho não consegue
   reiniciar um serviço que nunca existiu).
4. Com o backend no ar, abra `http://localhost:8081` no navegador, logue
   como usuário master, e vá em **Configurações > Serviço do Sistema >
   Atualização** — preencha a mesma config (agora pela tela, que grava no
   banco) e Grave. **A partir daqui**, as atualizações seguintes são
   automáticas: o próprio backend verifica periodicamente (configurável
   ali, incluindo 0 = desligado + botão "Verificar agora"), avisa via
   badge no menu lateral quando encontra algo, e "Aplicar agora"/"Reverter"
   ficam disponíveis na mesma tela. **Este é o caminho recomendado hoje**
   — não precisa mexer em Tarefa Agendada nenhuma depois do bootstrap.

### Alternativa (não recomendada hoje): Tarefa Agendada `BackOn-Updater` independente

`install-updater-task.ps1` registra uma 2ª Tarefa Agendada que roda
`apply_update.ps1` sozinha a cada 30 min, fora do backend — é o desenho
ORIGINAL desta pasta, hoje **pausado** por decisão do usuário em favor do
disparo dentro do backend (passo 4 acima). O script continua funcional
(reaproveitado, não removido) caso essa decisão mude no futuro — ver
PENDENCIAS.md > "Atualizador automático de instalações de cliente (PAUSADO)".

## Como funciona

- `apply_update.ps1` baixa `manifest.json`, compara com a última versão
  aplicada (`state.json`, gravado nesta mesma pasta), e se for diferente:
  baixa os 2 zips (backend/frontend), confere sha256, extrai em
  `<installDir>\releases\backend-<commit>\` e `frontend-<commit>\` (nunca
  sobrescreve a versão rodando), troca as junctions `current-backend`/
  `current-frontend`, reinicia a Tarefa `BackOn-Backend` e faz um health
  check (`GET /api/`).
- Se o health check falhar, desfaz a troca de junction, reinicia a versão
  anterior e loga o erro — **rollback automático**, sem intervenção manual.
  `state.json` só é atualizado em caso de sucesso, então o próximo ciclo
  tenta de novo sozinho.
- O frontend web é servido pelo PRÓPRIO processo do backend (variável de
  ambiente `FRONTEND_DIST_DIR` apontando pra `current-frontend`) — não
  existe uma Tarefa Agendada nem processo separado só pro frontend.

## Layout no disco (dentro de `installDir`)

```
C:\BackOn\
  current-backend\     <- junction -> releases\backend-<commit-atual>\
  current-frontend\    <- junction -> releases\frontend-<commit-atual>\
  releases\
    backend-<sha1>\
    backend-<sha2>\    (mantém as últimas 2, apaga o resto)
    frontend-<sha1>\
    frontend-<sha2>\
  updater\
    config.json
    state.json
    logs\
```

## Troubleshooting

- **"Já está na versão mais recente" toda vez, mas eu sei que publiquei
  algo novo**: confira se `manifest.json` realmente mudou (baixe a URL
  manualmente no navegador) e se `state.json` não ficou com um commit
  errado (apague o arquivo pra forçar reaplicar do zero).
- **Confirmar o que está rodando numa máquina**: `GET
  http://localhost:8081/api/version` devolve `{"commit", "published_at"}`
  da versão ativa.
- **Ver se a Tarefa está rodando**:
  ```powershell
  Get-ScheduledTask -TaskName "BackOn-Updater" | Get-ScheduledTaskInfo
  ```
- **Forçar uma verificação agora** (sem esperar o ciclo de 30 min):
  ```powershell
  Start-ScheduledTask -TaskName "BackOn-Updater"
  ```
