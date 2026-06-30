<#
.SYNOPSIS
  Inicia o backend Back-On (FastAPI/uvicorn) e o mantém no ar, reiniciando
  automaticamente se ele cair (ex.: SQL Server ainda não pronto logo no boot).

.DESCRIPTION
  - Detecta a pasta do backend automaticamente (este script fica em backend\scripts\).
  - Usa o Python do ambiente virtual (backend\.venv) se existir; senão usa o python do PATH.
  - Inicia "uvicorn server:app" com o diretório de trabalho na pasta backend.
  - Grava log diário em backend\logs\backend-AAAAMMDD.log.
  - Loop de supervisão: se o uvicorn encerrar, espera alguns segundos e reinicia.

.PARAMETER Port
  Porta TCP do backend. Padrão: 8081 (a mesma usada na sua conexão do app).

.PARAMETER BindHost
  Endereço de bind. Padrão: 0.0.0.0 (aceita conexões da rede local / celular).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
  powershell -ExecutionPolicy Bypass -File .\start-backend.ps1 -Port 8081
#>

param(
    [int]$Port = 8081,
    [string]$BindHost = "0.0.0.0",
    [int]$StartupDelaySeconds = 15,   # espera o Windows/SQL estabilizarem após o boot
    [int]$RestartDelaySeconds = 10    # espera antes de reiniciar caso o uvicorn caia
)

$ErrorActionPreference = "Stop"

# --- Caminhos (script está em backend\scripts) ---
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BackendDir = Split-Path -Parent $ScriptDir          # ...\backend
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$VenvCfg    = Join-Path $BackendDir ".venv\pyvenv.cfg"
$LogDir     = Join-Path $BackendDir "logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("backend-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    $line | Tee-Object -FilePath $LogFile -Append
}

# --- Escolhe o Python (venv de preferência) ---
if ((Test-Path $VenvPython) -and (Test-Path $VenvCfg)) {
    $Python = $VenvPython
} elseif (Test-Path $VenvPython) {
  $Python = "python"
  Write-Log "AVISO: venv encontrado, mas sem pyvenv.cfg em $VenvCfg (venv corrompido)."
  Write-Log "AVISO: usando 'python' do PATH temporariamente. Recrie o .venv para corrigir em definitivo."
} else {
    $Python = "python"
    Write-Log "AVISO: venv nao encontrado em $VenvPython. Usando 'python' do PATH."
}

Write-Log "==== Iniciando supervisor do backend Back-On ===="
Write-Log "BackendDir = $BackendDir"
Write-Log "Python     = $Python"
Write-Log "Bind       = $BindHost`:$Port"

if ($StartupDelaySeconds -gt 0) {
    Write-Log "Aguardando $StartupDelaySeconds s para o sistema/SQL estabilizarem..."
    Start-Sleep -Seconds $StartupDelaySeconds
}

Set-Location $BackendDir

# Preflight para falhar de forma clara quando o ambiente Python nao estiver pronto.
try {
  & $Python -c "import uvicorn" 2>&1 | Tee-Object -FilePath $LogFile -Append
  if ($LASTEXITCODE -ne 0) {
    Write-Log "ERRO: modulo 'uvicorn' indisponivel no Python selecionado ($Python)."
    Write-Log "ERRO: execute a recriacao do venv e instalacao de dependencias antes de subir o supervisor."
    exit 1
  }
} catch {
  Write-Log "ERRO no preflight do Python: $($_.Exception.Message)"
  exit 1
}

# IMPORTANTE: o uvicorn escreve os logs (INFO/WARNING) no STDERR. Com
# $ErrorActionPreference = "Stop", o PowerShell trata QUALQUER saida em stderr de
# um processo nativo como erro TERMINANTE, cai no catch e reinicia em loop infinito
# (mesmo o backend tendo subido com sucesso). Por isso, a partir daqui usamos
# "Continue" para que a saida do uvicorn no stderr NAO derrube o supervisor.
$ErrorActionPreference = "Continue"

# --- Loop de supervisão: mantém o uvicorn sempre no ar ---
while ($true) {
    Write-Log "Subindo uvicorn server:app em $BindHost`:$Port ..."
    try {
        # Sem --reload (modo produção). Junta stderr ao stdout (2>&1) e grava no log.
        # NAO usar "*>>" com ErrorActionPreference=Stop (vira excecao no boot do uvicorn).
        & $Python -m uvicorn "server:app" --host $BindHost --port $Port 2>&1 |
            Tee-Object -FilePath $LogFile -Append
        $code = $LASTEXITCODE
        Write-Log "uvicorn encerrou (exit code $code)."
    } catch {
        Write-Log "ERRO ao executar uvicorn: $($_.Exception.Message)"
    }
    Write-Log "Reiniciando em $RestartDelaySeconds s..."
    Start-Sleep -Seconds $RestartDelaySeconds
}
