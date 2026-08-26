<#
.SYNOPSIS
  Atualizador automático do Back-On (Backend + Frontend Web) numa instalação
  de cliente — baixa a release publicada pela Kontacto, troca a versão em
  produção e reinicia, com rollback automático (health check) ou manual
  (versão anterior) sempre disponível.

.DESCRIPTION
  Historicamente disparado por uma Tarefa Agendada Windows independente
  (`install-updater-task.ps1`, pausada — ver PENDENCIAS.md > "Serviço do
  Sistema — Atualização"). Agora é invocado pelo próprio backend (tarefa de
  fundo dentro do processo Python, configurada pela tela "Serviço do
  Sistema" > "Atualização"), em 3 modos separados via `-Mode`:

    - **Full** (padrão, comportamento original): baixa (se houver versão
      nova) E aplica na hora — check → download+sha256+extração → venv →
      troca de junction → restart → health check → rollback automático se
      falhar. Continua funcionando standalone/manual, como sempre.
    - **DownloadOnly**: só as etapas de baixar/verificar/extrair/preparar
      venv — PARA antes de trocar qualquer junction. Grava
      `pendingBackendRelease`/`pendingFrontendRelease`/`pendingCommit` em
      `state.json`. É o modo usado pelo ciclo periódico do backend — nunca
      troca a versão em produção sozinho.
    - **ApplyPending**: aplica o que um `DownloadOnly` anterior já baixou
      (lido de `state.json`) — troca junction/restart/health-check/
      rollback-automático, sem baixar nada de novo. Ação do usuário
      (botão "Aplicar agora" na tela).
    - **Rollback**: ignora manifest/download por completo — volta pra
      `previousBackendRelease`/`previousFrontendRelease` (gravados no
      último `ApplyPending` bem-sucedido) e reinicia. Ação do usuário
      (botão "Reverter para versão anterior").

  Ver PENDENCIAS.md > "Serviço do Sistema — Atualização" pro desenho
  completo (Protocolo Gauntlet: Carlos + Thomé).

.PARAMETER ConfigPath
  Caminho do config.json. Padrão: config.json na mesma pasta deste script.

.PARAMETER Mode
  Full (padrão) | DownloadOnly | ApplyPending | Rollback — ver acima.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\apply_update.ps1
  powershell -ExecutionPolicy Bypass -File .\apply_update.ps1 -Mode DownloadOnly
  powershell -ExecutionPolicy Bypass -File .\apply_update.ps1 -Mode ApplyPending
  powershell -ExecutionPolicy Bypass -File .\apply_update.ps1 -Mode Rollback
#>

param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "config.json"),
    [ValidateSet("Full", "DownloadOnly", "ApplyPending", "Rollback")]
    [string]$Mode = "Full"
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Logging — mesmo padrão de start-backend.ps1 (log diário, sem ferramenta 3rd
# party, console + arquivo).
# ---------------------------------------------------------------------------
$LogDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = Join-Path $LogDir ("updater-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0} [{1}] [{2}] {3}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Mode, $Level, $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Fail {
    param([string]$Message)
    Write-Log $Message "ERRO"
    exit 1
}

# ---------------------------------------------------------------------------
# Config + state
# ---------------------------------------------------------------------------
if (-not (Test-Path $ConfigPath)) {
    Fail "Config não encontrado em $ConfigPath — copie config.exemplo.json pra config.json e preencha manifestUrl (ou grave pela tela Serviço do Sistema > Atualização)."
}
$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json

# `currentBackendDir`/`currentFrontendDir` (novos, opcionais) SUBSTITUEM os
# valores derivados de `installDir` quando presentes — é o que a tela
# "Serviço do Sistema" grava (2 campos de pasta explícitos, um por
# Backend/Frontend, em vez de só uma raiz `installDir`). Sem eles, continua
# igual a antes (compatível com quem só configurou `installDir` na mão).
# `installDir` (onde `releases/` vive) também passa a ser opcional — se
# ausente, é derivado como a pasta PAI de `currentBackendDir`.
$BackendPort = if ($cfg.backendPort) { $cfg.backendPort } else { 8081 }
$HealthTimeoutSeconds = if ($cfg.healthCheckTimeoutSeconds) { $cfg.healthCheckTimeoutSeconds } else { 30 }
$HealthRetries = if ($cfg.healthCheckRetries) { $cfg.healthCheckRetries } else { 10 }
$KeepReleases = if ($cfg.keepReleases) { $cfg.keepReleases } else { 2 }
$TaskName = "BackOn-Backend"

$CurrentBackendLink = if ($cfg.currentBackendDir) { $cfg.currentBackendDir } else { Join-Path $cfg.installDir "current-backend" }
$CurrentFrontendLink = if ($cfg.currentFrontendDir) { $cfg.currentFrontendDir } else { Join-Path $cfg.installDir "current-frontend" }
$InstallDir = if ($cfg.installDir) { $cfg.installDir } else { Split-Path -Parent $CurrentBackendLink }
$ReleasesDir = Join-Path $InstallDir "releases"
$StatePath = Join-Path $PSScriptRoot "state.json"

foreach ($d in @($InstallDir, $ReleasesDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

function Get-State {
    if (Test-Path $StatePath) {
        return Get-Content $StatePath -Raw | ConvertFrom-Json
    }
    return [PSCustomObject]@{
        commit = $null
        backendRelease = $null
        frontendRelease = $null
        requirementsHash = $null
        updatedAt = $null
        pendingCommit = $null
        pendingBackendRelease = $null
        pendingFrontendRelease = $null
        previousCommit = $null
        previousBackendRelease = $null
        previousFrontendRelease = $null
    }
}

function Save-State {
    param($State)
    $State | ConvertTo-Json -Depth 5 | Set-Content -Path $StatePath -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Junction helpers — `rmdir` via cmd remove só o reparse point (nunca recursa
# no conteúdo real da pasta apontada), diferente de Remove-Item -Recurse que
# em alguns cenários já mostrou comportamento perigoso com junctions.
# ---------------------------------------------------------------------------
function Set-Junction {
    param([string]$LinkPath, [string]$TargetPath)
    if (Test-Path $LinkPath) {
        cmd /c rmdir "$LinkPath" | Out-Null
    }
    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
}

function Get-JunctionTarget {
    param([string]$LinkPath)
    if (-not (Test-Path $LinkPath)) { return $null }
    $item = Get-Item $LinkPath -Force
    if ($item.LinkType -eq "Junction") { return $item.Target }
    return $null
}

function Get-Sha256Lower {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ManifestBaseUrl {
    # manifestUrl inclui a SAS query string (?sv=...&sig=...) — os arquivos
    # dos zips vivem no MESMO container/SAS, só troca o nome do blob.
    $uri = [uri]$cfg.manifestUrl
    $basePath = $uri.GetLeftPart([UriPartial]::Path)
    $baseDir = $basePath.Substring(0, $basePath.LastIndexOf("/") + 1)
    return @{ Dir = $baseDir; Query = $uri.Query }
}

function Get-ReleaseAsset {
    param([string]$FileName, [string]$DestPath, [string]$ExpectedSha256)
    $base = Get-ManifestBaseUrl
    $url = $base.Dir + $FileName + $base.Query
    Write-Log "Baixando $FileName..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $DestPath -UseBasicParsing -TimeoutSec 300
    } catch {
        Fail "Falha ao baixar $FileName`: $($_.Exception.Message)"
    }
    $actual = Get-Sha256Lower $DestPath
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) {
        Fail "sha256 de $FileName não confere (esperado $ExpectedSha256, obtido $actual) — release corrompida ou adulterada."
    }
    Write-Log "$FileName baixado e verificado (sha256 OK)."
}

function Test-BackendHealthy {
    for ($i = 1; $i -le $HealthRetries; $i++) {
        Start-Sleep -Seconds ([math]::Ceiling($HealthTimeoutSeconds / $HealthRetries))
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$BackendPort/api/" -UseBasicParsing -TimeoutSec 10
            if ($r.StatusCode -eq 200 -and $r.Content -match "Back-On API ativo") {
                Write-Log "Health check /api/ OK (tentativa $i/$HealthRetries)."
                return $true
            }
        } catch {
            Write-Log "Health check /api/ falhou na tentativa $i/$HealthRetries ($($_.Exception.Message))." "WARN"
        }
    }
    return $false
}

function Restart-BackendTask {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    # Mata processos remanescentes que porventura não tenham sido derrubados
    # pelo Stop-ScheduledTask (mesmo padrão de limpeza de supervisor duplicado
    # já usado manualmente nesta migração).
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "uvicorn" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Start-ScheduledTask -TaskName $TaskName
    } else {
        Write-Log "Tarefa '$TaskName' ainda não existe — rode install-startup-task.ps1 (backend\scripts\) uma vez, apontando pra $CurrentBackendLink\scripts\start-backend.ps1, antes do atualizador poder reiniciar o serviço." "WARN"
    }
}

# ---------------------------------------------------------------------------
# Etapa "Download" (Full e DownloadOnly) — manifest → compara → baixa+sha256
# → extrai em pasta nova versionada → prepara venv. Nunca troca junction.
# ---------------------------------------------------------------------------
function Invoke-Download {
    param($State)

    Write-Log "Verificando atualização (manifest)..."
    try {
        $manifestRaw = Invoke-WebRequest -Uri $cfg.manifestUrl -UseBasicParsing -TimeoutSec 30
        $manifest = $manifestRaw.Content | ConvertFrom-Json
    } catch {
        Fail "Falha ao baixar manifest.json: $($_.Exception.Message)"
    }

    if ($State.commit -eq $manifest.commit) {
        Write-Log "Já está na versão mais recente (commit $($manifest.commit)). Nada a fazer."
        return $null
    }
    Write-Log "Nova versão disponível: $($manifest.commit) (atual: $($State.commit))"

    $TempDir = Join-Path $env:TEMP ("backon-update-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

    $backendZip = Join-Path $TempDir $manifest.backend.file
    $frontendZip = Join-Path $TempDir $manifest.frontend.file
    Get-ReleaseAsset -FileName $manifest.backend.file -DestPath $backendZip -ExpectedSha256 $manifest.backend.sha256
    Get-ReleaseAsset -FileName $manifest.frontend.file -DestPath $frontendZip -ExpectedSha256 $manifest.frontend.sha256

    $NewBackendRelease = Join-Path $ReleasesDir ("backend-" + $manifest.commit)
    $NewFrontendRelease = Join-Path $ReleasesDir ("frontend-" + $manifest.commit)
    if (Test-Path $NewBackendRelease) { Remove-Item $NewBackendRelease -Recurse -Force }
    if (Test-Path $NewFrontendRelease) { Remove-Item $NewFrontendRelease -Recurse -Force }

    Write-Log "Extraindo backend em $NewBackendRelease..."
    Expand-Archive -Path $backendZip -DestinationPath $NewBackendRelease -Force
    Write-Log "Extraindo frontend em $NewFrontendRelease..."
    Expand-Archive -Path $frontendZip -DestinationPath $NewFrontendRelease -Force
    Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

    # Venv — só roda `pip install` se requirements-windows.txt mudou; senão
    # copia o venv da release anterior (ver racional no README/histórico do
    # arquivo — python de um venv resolve seu próprio prefixo pela
    # localização do executável, não por caminho absoluto gravado na criação).
    $reqFile = Join-Path $NewBackendRelease "requirements-windows.txt"
    $newReqHash = if (Test-Path $reqFile) { Get-Sha256Lower $reqFile } else { $null }
    $prevBackendRelease = if ($State.backendRelease) { Join-Path $ReleasesDir $State.backendRelease } else { $null }
    $prevVenv = if ($prevBackendRelease) { Join-Path $prevBackendRelease ".venv" } else { $null }
    $newVenv = Join-Path $NewBackendRelease ".venv"
    $reuseVenv = $newReqHash -and ($newReqHash -eq $State.requirementsHash) -and $prevVenv -and (Test-Path $prevVenv)

    if ($reuseVenv) {
        Write-Log "requirements-windows.txt sem mudança — copiando venv da release anterior (sem reinstalar pacotes)."
        robocopy $prevVenv $newVenv /MIR /NFL /NDL /NJH /NJS | Out-Null
    } else {
        Write-Log "Criando venv novo e instalando dependências (requirements-windows.txt mudou ou é a primeira instalação)..."
        $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $pythonExe) { Fail "python não encontrado no PATH — necessário pra criar o venv do backend." }
        & $pythonExe -m venv $newVenv
        if ($LASTEXITCODE -ne 0) { Fail "Falha ao criar o venv em $newVenv." }
        $venvPip = Join-Path $newVenv "Scripts\pip.exe"
        if (Test-Path $reqFile) {
            & $venvPip install -r $reqFile
            if ($LASTEXITCODE -ne 0) { Fail "Falha ao instalar requirements-windows.txt no venv novo." }
        }
    }

    return [PSCustomObject]@{
        Commit = $manifest.commit
        BackendRelease = Split-Path -Leaf $NewBackendRelease
        FrontendRelease = Split-Path -Leaf $NewFrontendRelease
        RequirementsHash = $newReqHash
    }
}

# ---------------------------------------------------------------------------
# Etapa "Apply" (Full e ApplyPending) — troca junction/restart/health-check/
# rollback-automático em caso de falha. NÃO mexe em manifest/download.
# ---------------------------------------------------------------------------
function Invoke-Apply {
    param($State, [string]$Commit, [string]$BackendReleaseName, [string]$FrontendReleaseName, [string]$RequirementsHash)

    $NewBackendRelease = Join-Path $ReleasesDir $BackendReleaseName
    $NewFrontendRelease = Join-Path $ReleasesDir $FrontendReleaseName
    $prevBackendTarget = Get-JunctionTarget $CurrentBackendLink
    $prevFrontendTarget = Get-JunctionTarget $CurrentFrontendLink

    Write-Log "Trocando versão ativa pra commit $Commit..."
    Set-Junction -LinkPath $CurrentBackendLink -TargetPath $NewBackendRelease
    Set-Junction -LinkPath $CurrentFrontendLink -TargetPath $NewFrontendRelease
    [Environment]::SetEnvironmentVariable("FRONTEND_DIST_DIR", $CurrentFrontendLink, "Machine")
    Restart-BackendTask

    if (Test-BackendHealthy) {
        Write-Log "Atualização aplicada com sucesso — commit $Commit."
        # Guarda a versão que estava rodando ANTES desta troca como
        # "previous" — é o que o modo Rollback usa depois.
        $State.previousCommit = $State.commit
        $State.previousBackendRelease = $State.backendRelease
        $State.previousFrontendRelease = $State.frontendRelease
        $State.commit = $Commit
        $State.backendRelease = $BackendReleaseName
        $State.frontendRelease = $FrontendReleaseName
        $State.requirementsHash = $RequirementsHash
        $State.updatedAt = (Get-Date).ToString("o")
        $State.pendingCommit = $null
        $State.pendingBackendRelease = $null
        $State.pendingFrontendRelease = $null
        Save-State $State

        foreach ($prefix in @("backend-", "frontend-")) {
            Get-ChildItem $ReleasesDir -Directory -Filter "$prefix*" |
                Sort-Object LastWriteTime -Descending |
                Select-Object -Skip $KeepReleases |
                ForEach-Object {
                    Write-Log "Removendo release antiga: $($_.Name)"
                    Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                }
        }
        return $true
    } else {
        Write-Log "Health check falhou — desfazendo pra versão anterior." "ERRO"
        if ($prevBackendTarget) { Set-Junction -LinkPath $CurrentBackendLink -TargetPath $prevBackendTarget }
        if ($prevFrontendTarget) { Set-Junction -LinkPath $CurrentFrontendLink -TargetPath $prevFrontendTarget }
        [Environment]::SetEnvironmentVariable("FRONTEND_DIST_DIR", $CurrentFrontendLink, "Machine")
        Restart-BackendTask
        if (Test-BackendHealthy) {
            Write-Log "Rollback automático concluído — versão anterior voltou a responder normalmente."
        } else {
            Write-Log "Rollback automático também não respondeu ao health check — intervenção manual necessária." "ERRO"
        }
        # NÃO limpa pendingCommit/pendingBackendRelease/pendingFrontendRelease
        # — a release já baixada continua lá, um novo ApplyPending pode
        # tentar de novo sem precisar baixar tudo outra vez.
        Save-State $State
        return $false
    }
}

# ---------------------------------------------------------------------------
# Etapa "Rollback" — volta pra `previousBackendRelease`/`previousFrontendRelease`
# (gravados no último Apply bem-sucedido). Não mexe em manifest/download.
# ---------------------------------------------------------------------------
function Invoke-Rollback {
    param($State)

    if (-not $State.previousBackendRelease -or -not $State.previousFrontendRelease) {
        Fail "Não há versão anterior registrada pra reverter."
    }

    $PrevBackendRelease = Join-Path $ReleasesDir $State.previousBackendRelease
    $PrevFrontendRelease = Join-Path $ReleasesDir $State.previousFrontendRelease
    if (-not (Test-Path $PrevBackendRelease) -or -not (Test-Path $PrevFrontendRelease)) {
        Fail "A pasta da versão anterior ($($State.previousCommit)) não existe mais em disco (provavelmente já foi limpa pela política de retenção de releases) — não é possível reverter."
    }

    Write-Log "Revertendo pra versão anterior (commit $($State.previousCommit))..."
    Set-Junction -LinkPath $CurrentBackendLink -TargetPath $PrevBackendRelease
    Set-Junction -LinkPath $CurrentFrontendLink -TargetPath $PrevFrontendRelease
    [Environment]::SetEnvironmentVariable("FRONTEND_DIST_DIR", $CurrentFrontendLink, "Machine")
    Restart-BackendTask

    if (Test-BackendHealthy) {
        Write-Log "Reversão concluída com sucesso — voltou pro commit $($State.previousCommit)."
        $State.commit = $State.previousCommit
        $State.backendRelease = $State.previousBackendRelease
        $State.frontendRelease = $State.previousFrontendRelease
        # Não suporta "refazer" (voltar pra frente) — depois de reverter, só
        # uma atualização nova (baixada de novo) avança a versão outra vez.
        $State.previousCommit = $null
        $State.previousBackendRelease = $null
        $State.previousFrontendRelease = $null
        Save-State $State
        return $true
    } else {
        Write-Log "Health check falhou depois da reversão — intervenção manual necessária." "ERRO"
        return $false
    }
}

# ---------------------------------------------------------------------------
# Dispatch por modo
# ---------------------------------------------------------------------------
$state = Get-State

switch ($Mode) {
    "Full" {
        $downloaded = Invoke-Download -State $state
        if ($null -eq $downloaded) { exit 0 }
        $ok = Invoke-Apply -State $state -Commit $downloaded.Commit `
            -BackendReleaseName $downloaded.BackendRelease -FrontendReleaseName $downloaded.FrontendRelease `
            -RequirementsHash $downloaded.RequirementsHash
        if (-not $ok) { exit 1 }
        exit 0
    }
    "DownloadOnly" {
        $downloaded = Invoke-Download -State $state
        if ($null -eq $downloaded) { exit 0 }
        $state.pendingCommit = $downloaded.Commit
        $state.pendingBackendRelease = $downloaded.BackendRelease
        $state.pendingFrontendRelease = $downloaded.FrontendRelease
        $state.requirementsHash = $downloaded.RequirementsHash
        Save-State $state
        Write-Log "Download concluído — commit $($downloaded.Commit) pronto pra aplicar (pendingCommit em state.json)."
        exit 0
    }
    "ApplyPending" {
        if (-not $state.pendingCommit -or -not $state.pendingBackendRelease -or -not $state.pendingFrontendRelease) {
            Fail "Não há atualização pendente baixada pra aplicar — rode -Mode DownloadOnly primeiro (ou espere o próximo ciclo automático)."
        }
        $ok = Invoke-Apply -State $state -Commit $state.pendingCommit `
            -BackendReleaseName $state.pendingBackendRelease -FrontendReleaseName $state.pendingFrontendRelease `
            -RequirementsHash $state.requirementsHash
        if (-not $ok) { exit 1 }
        exit 0
    }
    "Rollback" {
        $ok = Invoke-Rollback -State $state
        if (-not $ok) { exit 1 }
        exit 0
    }
}
