<#
.SYNOPSIS
  Bootstrap da 1ª instalação numa máquina nova — resolve o gap real entre
  "apply_update.ps1 sozinho" e "primeira vez que nada ainda existe" (ver
  PENDENCIAS.md > "Serviço do Sistema — Atualização").

.DESCRIPTION
  Numa máquina sem nada ainda, `apply_update.ps1 -Mode Full`/`ApplyPending`
  sozinho não consegue: a etapa de reiniciar (`Restart-BackendTask`) tenta
  religar a Tarefa Agendada `BackOn-Backend`, que ainda não existe — o
  health check falha na primeira vez mesmo com os arquivos certos no
  lugar, e o script reporta erro sem nunca ligar o backend de fato.

  Este script faz a sequência completa (antes manual, documentada em
  `README.md`) numa tacada só:
    1. Roda `apply_update.ps1 -Mode DownloadOnly` (baixa+extrai+venv —
       reaproveita a lógica já testada, nunca duplica).
    2. Cria as junctions `current-backend`/`current-frontend` apontando
       pra release baixada.
    3. Seta `FRONTEND_DIST_DIR` (Machine).
    4. Registra a Tarefa Agendada `BackOn-Backend`
       (`install-startup-task.ps1`, rodado de DENTRO da junction, pra
       gravar o caminho estável — nunca precisa reregistrar depois).
    5. Inicia a Tarefa.
    6. Health check.
    7. Se saudável: grava `state.json` (commit efetivado, limpa
       pendingCommit/etc.). Se não: avisa claramente que os arquivos já
       estão no lugar (não é preciso baixar de novo), só o processo não
       subiu — não tenta "reverter" (não existe versão anterior numa 1ª
       instalação).

  Idempotente — rodar de novo depois de uma falha (ou só pra confirmar
  que tudo está consistente) não duplica nada; junctions e Tarefa
  Agendada são recriadas do zero a cada execução.

  >>> EXECUTE COMO ADMINISTRADOR — precisa registrar Tarefa Agendada. <<<

.PARAMETER ConfigPath
  Caminho do config.json (mesmo formato de `apply_update.ps1`). Padrão:
  config.json na mesma pasta deste script. Precisa já estar preenchido
  manualmente antes de rodar — a tela "Serviço do Sistema" só existe
  depois que já existe um backend rodando, então numa 1ª instalação a
  config inicial é sempre o arquivo, nunca a tela.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\bootstrap-install.ps1
#>

param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "config.json")
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERRO: rode este script COMO ADMINISTRADOR (precisa registrar a Tarefa Agendada)." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Logging — mesmo padrão de apply_update.ps1/start-backend.ps1.
# ---------------------------------------------------------------------------
$LogDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = Join-Path $LogDir ("bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0} [BOOTSTRAP] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Fail {
    param([string]$Message)
    Write-Log $Message "ERRO"
    exit 1
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
if (-not (Test-Path $ConfigPath)) {
    Fail "Config não encontrado em $ConfigPath — copie config.exemplo.json pra config.json e preencha manifestUrl/currentBackendDir/currentFrontendDir antes de rodar o bootstrap."
}
$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json

$BackendPort = if ($cfg.backendPort) { $cfg.backendPort } else { 8081 }
$HealthTimeoutSeconds = if ($cfg.healthCheckTimeoutSeconds) { $cfg.healthCheckTimeoutSeconds } else { 30 }
$HealthRetries = if ($cfg.healthCheckRetries) { $cfg.healthCheckRetries } else { 10 }
$TaskName = "BackOn-Backend"

$CurrentBackendLink = if ($cfg.currentBackendDir) { $cfg.currentBackendDir } else { Join-Path $cfg.installDir "current-backend" }
$CurrentFrontendLink = if ($cfg.currentFrontendDir) { $cfg.currentFrontendDir } else { Join-Path $cfg.installDir "current-frontend" }
$InstallDir = if ($cfg.installDir) { $cfg.installDir } else { Split-Path -Parent $CurrentBackendLink }
$ReleasesDir = Join-Path $InstallDir "releases"
$StatePath = Join-Path $PSScriptRoot "state.json"
$ApplyScript = Join-Path $PSScriptRoot "apply_update.ps1"

if (-not (Test-Path $ApplyScript)) {
    Fail "Não encontrei $ApplyScript — este script precisa estar na mesma pasta de apply_update.ps1."
}

foreach ($d in @($InstallDir, $ReleasesDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ---------------------------------------------------------------------------
# Helpers — versões pequenas e independentes das mesmas funções de
# apply_update.ps1 (Set-Junction/Get-State/Save-State/health check).
# Duplicadas de propósito: apply_update.ps1 é um script de topo a fim (não
# um módulo) — dot-source dele executaria o dispatch inteiro (o `switch
# ($Mode)` no final) como efeito colateral. Se o formato de state.json
# mudar em apply_update.ps1, atualizar aqui também.
# ---------------------------------------------------------------------------
function Set-JunctionLocal {
    param([string]$LinkPath, [string]$TargetPath)
    if (Test-Path $LinkPath) {
        cmd /c rmdir "$LinkPath" | Out-Null
    }
    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
}

function Get-StateLocal {
    if (Test-Path $StatePath) {
        return Get-Content $StatePath -Raw | ConvertFrom-Json
    }
    return [PSCustomObject]@{
        commit = $null; backendRelease = $null; frontendRelease = $null
        requirementsHash = $null; updatedAt = $null
        pendingCommit = $null; pendingBackendRelease = $null; pendingFrontendRelease = $null
        previousCommit = $null; previousBackendRelease = $null; previousFrontendRelease = $null
    }
}

function Save-StateLocal {
    param($State)
    $State | ConvertTo-Json -Depth 5 | Set-Content -Path $StatePath -Encoding UTF8
}

function Test-BackendHealthyLocal {
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

# ---------------------------------------------------------------------------
# 1. Baixa a release publicada mais recente — reaproveita apply_update.ps1
#    -Mode DownloadOnly, nunca duplica a lógica de download/sha256/venv.
# ---------------------------------------------------------------------------
Write-Log "Baixando a release publicada mais recente..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ApplyScript -ConfigPath $ConfigPath -Mode DownloadOnly
if ($LASTEXITCODE -ne 0) {
    Fail "apply_update.ps1 -Mode DownloadOnly falhou (código $LASTEXITCODE) — ver updater\logs\updater-*.log pro detalhe."
}

$state = Get-StateLocal
$releaseInfo = $null
if ($state.pendingCommit -and $state.pendingBackendRelease -and $state.pendingFrontendRelease) {
    $releaseInfo = @{ Commit = $state.pendingCommit; Backend = $state.pendingBackendRelease; Frontend = $state.pendingFrontendRelease }
} elseif ($state.commit -and $state.backendRelease -and $state.frontendRelease) {
    Write-Log "Nenhuma atualização pendente — já existe uma versão baixada anteriormente (commit $($state.commit)). O bootstrap vai garantir que junction/tarefa/variável de ambiente estão consistentes com ela."
    $releaseInfo = @{ Commit = $state.commit; Backend = $state.backendRelease; Frontend = $state.frontendRelease }
}
if (-not $releaseInfo) {
    Fail "Nenhuma release baixada em state.json depois do DownloadOnly — algo deu errado no passo anterior."
}

$NewBackendRelease = Join-Path $ReleasesDir $releaseInfo.Backend
$NewFrontendRelease = Join-Path $ReleasesDir $releaseInfo.Frontend

# ---------------------------------------------------------------------------
# 2. Cria as junctions
# ---------------------------------------------------------------------------
Write-Log "Criando junctions current-backend/current-frontend (commit $($releaseInfo.Commit))..."
Set-JunctionLocal -LinkPath $CurrentBackendLink -TargetPath $NewBackendRelease
Set-JunctionLocal -LinkPath $CurrentFrontendLink -TargetPath $NewFrontendRelease
[Environment]::SetEnvironmentVariable("FRONTEND_DIST_DIR", $CurrentFrontendLink, "Machine")

# ---------------------------------------------------------------------------
# 3. Registra a Tarefa Agendada, apontando pro caminho ESTÁVEL da junction
#    (nunca precisa ser reregistrada nas próximas atualizações — só o que
#    a junction aponta muda).
# ---------------------------------------------------------------------------
$InstallTaskScript = Join-Path $CurrentBackendLink "scripts\install-startup-task.ps1"
if (-not (Test-Path $InstallTaskScript)) {
    Fail "Não encontrei $InstallTaskScript dentro da release baixada — o zip do backend está incompleto?"
}
Write-Log "Registrando a Tarefa Agendada '$TaskName' apontando pra $CurrentBackendLink\scripts\start-backend.ps1..."
Push-Location (Split-Path -Parent $InstallTaskScript)
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\install-startup-task.ps1" -Port $BackendPort
    if ($LASTEXITCODE -ne 0) { Fail "install-startup-task.ps1 falhou (código $LASTEXITCODE)." }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 4. Inicia a Tarefa e confere o health check
# ---------------------------------------------------------------------------
Write-Log "Iniciando a Tarefa '$TaskName'..."
Start-ScheduledTask -TaskName $TaskName

if (Test-BackendHealthyLocal) {
    Write-Log "Backend no ar — bootstrap concluído com sucesso (commit $($releaseInfo.Commit))."
    $state.commit = $releaseInfo.Commit
    $state.backendRelease = $releaseInfo.Backend
    $state.frontendRelease = $releaseInfo.Frontend
    $state.updatedAt = (Get-Date).ToString("o")
    $state.pendingCommit = $null
    $state.pendingBackendRelease = $null
    $state.pendingFrontendRelease = $null
    Save-StateLocal $state
    Write-Log "Próximo passo: abrir http://localhost:$BackendPort no navegador, logar como master, e configurar Serviço do Sistema > Atualização pela tela — a partir daqui as próximas atualizações usam esse caminho, não mais este bootstrap."
    exit 0
} else {
    Fail "Backend não respondeu ao health check depois de iniciar a Tarefa. Os arquivos já estão no lugar certo (commit $($releaseInfo.Commit)) — confira os logs em '$CurrentBackendLink\logs\' e o status da Tarefa (Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo) antes de rodar o bootstrap de novo."
}
