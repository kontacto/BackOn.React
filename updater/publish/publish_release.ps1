<#
.SYNOPSIS
  [SÓ RODA NA MÁQUINA DA KONTACTO — nunca instalar em cliente]
  Publica uma release (Backend + Frontend Web) no Blob de distribuição, pra
  as instalações de cliente baixarem via updater/apply_update.ps1.

.DESCRIPTION
  1. Empacota backend/ (sem .venv/__pycache__/logs/.env) + grava VERSION
     dentro do zip.
  2. Roda `npx expo export -p web` e empacota frontend/dist/.
  3. Calcula sha256 dos 2 zips.
  4. Sobe os 2 zips + manifest.json (commit, sha256, published_at) pro
     container "releases" no Azure Blob Storage.

  Requer o módulo Az.Storage (`Install-Module -Name Az.Storage -Scope
  CurrentUser`) e a CONNECTION STRING COMPLETA (leitura+escrita) do Storage
  Account de distribuição — NUNCA a mesma string que vai pro cliente; o
  cliente recebe só uma SAS de leitura (ver updater/README.md).

  A connection string vem da variável de ambiente
  BACKON_RELEASES_CONNECTION_STRING (nunca hardcoded neste arquivo, nunca
  commitada) — configure antes de rodar:
    $env:BACKON_RELEASES_CONNECTION_STRING = "DefaultEndpointsProtocol=..."

.PARAMETER Commit
  Commit a publicar. Padrão: HEAD do repositório (git rev-parse --short HEAD).

.PARAMETER ContainerName
  Nome do container no Blob. Padrão: "releases".

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\publish_release.ps1
#>

param(
    [string]$Commit = $null,
    [string]$ContainerName = "releases"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"

if (-not $env:BACKON_RELEASES_CONNECTION_STRING) {
    Write-Host "ERRO: defina `$env:BACKON_RELEASES_CONNECTION_STRING antes de publicar." -ForegroundColor Red
    exit 1
}

if (-not $Commit) {
    Push-Location $RepoRoot
    $Commit = (git rev-parse --short HEAD).Trim()
    $dirty = git status --porcelain
    Pop-Location
    if ($dirty) {
        Write-Host "AVISO: há mudanças não commitadas no repositório — publicando mesmo assim o HEAD ($Commit), mas confirme que é isso que você quer." -ForegroundColor Yellow
    }
}

Write-Host "Publicando release do commit $Commit..." -ForegroundColor Cyan

$StagingDir = Join-Path $env:TEMP ("backon-publish-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
$BackendStage = Join-Path $StagingDir "backend"
$FrontendStage = Join-Path $StagingDir "frontend"

# ---------------------------------------------------------------------------
# 1. Empacota backend
# ---------------------------------------------------------------------------
Write-Host "Empacotando backend..." -ForegroundColor Cyan
$excludeDirs = @(".venv", "__pycache__", "logs", ".pytest_cache", ".git")
robocopy $BackendDir $BackendStage /MIR /XD $excludeDirs /XF ".env" "*.pyc" /NFL /NDL /NJH /NJS | Out-Null

$versionPayload = @{
    commit = $Commit
    published_at = (Get-Date).ToString("o")
} | ConvertTo-Json
Set-Content -Path (Join-Path $BackendStage "VERSION") -Value $versionPayload -Encoding UTF8

$backendZipName = "backend-$Commit.zip"
$backendZipPath = Join-Path $StagingDir $backendZipName
Compress-Archive -Path (Join-Path $BackendStage "*") -DestinationPath $backendZipPath -Force

# ---------------------------------------------------------------------------
# 2. Build + empacota frontend web
# ---------------------------------------------------------------------------
Write-Host "Rodando expo export (frontend web)..." -ForegroundColor Cyan
Push-Location $FrontendDir
try {
    npx expo export -p web
    if ($LASTEXITCODE -ne 0) { throw "expo export falhou (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$frontendDistDir = Join-Path $FrontendDir "dist"
if (-not (Test-Path $frontendDistDir)) {
    Write-Host "ERRO: $frontendDistDir não foi gerado pelo expo export." -ForegroundColor Red
    exit 1
}

$frontendZipName = "frontend-$Commit.zip"
$frontendZipPath = Join-Path $StagingDir $frontendZipName
Compress-Archive -Path (Join-Path $frontendDistDir "*") -DestinationPath $frontendZipPath -Force

# ---------------------------------------------------------------------------
# 3. sha256 (lowercase hex — apply_update.ps1 espera esse formato)
# ---------------------------------------------------------------------------
function Get-Sha256Lower {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$backendSha = Get-Sha256Lower $backendZipPath
$frontendSha = Get-Sha256Lower $frontendZipPath

Write-Host "backend:  $backendZipName  sha256=$backendSha"
Write-Host "frontend: $frontendZipName  sha256=$frontendSha"

# ---------------------------------------------------------------------------
# 4. Upload pro Blob
# ---------------------------------------------------------------------------
if (-not (Get-Module -ListAvailable -Name Az.Storage)) {
    Write-Host "ERRO: módulo Az.Storage não instalado. Rode: Install-Module -Name Az.Storage -Scope CurrentUser" -ForegroundColor Red
    exit 1
}
Import-Module Az.Storage

$ctx = New-AzStorageContext -ConnectionString $env:BACKON_RELEASES_CONNECTION_STRING

Write-Host "Enviando $backendZipName..." -ForegroundColor Cyan
Set-AzStorageBlobContent -Container $ContainerName -File $backendZipPath -Blob $backendZipName -Context $ctx -Force | Out-Null

Write-Host "Enviando $frontendZipName..." -ForegroundColor Cyan
Set-AzStorageBlobContent -Container $ContainerName -File $frontendZipPath -Blob $frontendZipName -Context $ctx -Force | Out-Null

$manifest = @{
    commit = $Commit
    published_at = (Get-Date).ToString("o")
    backend = @{ file = $backendZipName; sha256 = $backendSha }
    frontend = @{ file = $frontendZipName; sha256 = $frontendSha }
} | ConvertTo-Json -Depth 5

$manifestPath = Join-Path $StagingDir "manifest.json"
Set-Content -Path $manifestPath -Value $manifest -Encoding UTF8

Write-Host "Enviando manifest.json..." -ForegroundColor Cyan
Set-AzStorageBlobContent -Container $ContainerName -File $manifestPath -Blob "manifest.json" -Context $ctx -Force -Properties @{ContentType = "application/json"} | Out-Null

Remove-Item $StagingDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Release $Commit publicada com sucesso." -ForegroundColor Green
Write-Host "As instalações de cliente vão pegar essa versão no próximo ciclo da Tarefa 'BackOn-Updater' (até 30 min)." -ForegroundColor Green
