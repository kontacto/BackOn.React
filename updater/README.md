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

## Pré-requisito — primeira instalação continua manual

O atualizador cuida das atualizações **seguintes**; a primeira instalação
de uma máquina nova ainda segue o guia manual em
`BACKEND_DEPLOY_WINDOWS.md` (SQL Server, Python, backend rodando pelo
menos uma vez via `install-startup-task.ps1`). Só depois que existe uma
instalação funcionando é que o atualizador assume.

## Instalação (numa máquina já com o backend manual rodando)

1. Copie esta pasta `updater\` pra dentro do `installDir` que você vai
   usar (ex.: `C:\BackOn\updater\`).
2. Copie `config.exemplo.json` pra `config.json` e preencha:
   - `manifestUrl`: URL do `manifest.json` com a SAS de leitura (peça pra
     Kontacto — nunca é a connection string completa).
   - `installDir`: pasta raiz onde as releases vão ficar (ex.:
     `C:\BackOn`).
3. Rode uma vez manualmente pra confirmar que funciona:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\apply_update.ps1
   ```
   Confira o log em `updater\logs\updater-AAAAMMDD.log` — deve baixar,
   trocar a versão e passar no health check.
4. **Só depois de confirmar o passo 3**, registre a Tarefa Agendada que
   roda isso sozinho a cada 30 min:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-updater-task.ps1
   ```
   (precisa ser Administrador — mesmo padrão de
   `backend\scripts\install-startup-task.ps1`.)

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
