<#
.SYNOPSIS
  Inicia o Agente de Impressão Silenciosa e o mantém no ar, reiniciando
  automaticamente se ele cair (ex.: backend ainda não pronto logo no boot).

.DESCRIPTION
  - Detecta a pasta do agente automaticamente (este script fica em print-agent\scripts\).
  - Usa o Python do ambiente virtual (print-agent\.venv) se existir; senão usa o python do PATH.
  - Inicia "agente_impressao.py" com o diretório de trabalho na pasta print-agent.
  - Grava log diário em print-agent\logs\agent-AAAAMMDD.log.
  - Loop de supervisão: se o processo encerrar (erro, crash), espera alguns
    segundos e reinicia — mesmo padrão de backend\scripts\start-backend.ps1.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start-print-agent.ps1
#>

param(
    [int]$StartupDelaySeconds = 10,   # espera o Windows/rede estabilizarem após o boot
    [int]$RestartDelaySeconds = 10    # espera antes de reiniciar caso o agente caia
)

$ErrorActionPreference = "Stop"

# --- Caminhos (script está em print-agent\scripts) ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AgentDir  = Split-Path -Parent $ScriptDir          # ...\print-agent
$VenvPython = Join-Path $AgentDir ".venv\Scripts\python.exe"
$VenvCfg    = Join-Path $AgentDir ".venv\pyvenv.cfg"
$LogDir     = Join-Path $AgentDir "logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("agent-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

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

Write-Log "==== Iniciando supervisor do Agente de Impressao ===="
Write-Log "AgentDir = $AgentDir"
Write-Log "Python   = $Python"

if (-not (Test-Path (Join-Path $AgentDir "config.json"))) {
    Write-Log "ERRO: config.json nao encontrado em $AgentDir. Copie config.exemplo.json e ajuste os valores antes de rodar."
    exit 1
}

if ($StartupDelaySeconds -gt 0) {
    Write-Log "Aguardando $StartupDelaySeconds s para o sistema/rede estabilizarem..."
    Start-Sleep -Seconds $StartupDelaySeconds
}

Set-Location $AgentDir

# Preflight para falhar de forma clara quando o ambiente Python nao estiver pronto.
try {
    & $Python -c "import win32print, requests" 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERRO: dependencias indisponiveis no Python selecionado ($Python)."
        Write-Log "ERRO: rode 'pip install -r requirements.txt' no venv antes de subir o supervisor."
        exit 1
    }
} catch {
    Write-Log "ERRO no preflight do Python: $($_.Exception.Message)"
    exit 1
}

# Mesma razao ja documentada em start-backend.ps1: com ErrorActionPreference=Stop,
# qualquer saida em stderr de um processo nativo derruba o supervisor mesmo em
# sucesso — a partir daqui usamos "Continue".
$ErrorActionPreference = "Continue"

# --- Loop de supervisão: mantém o agente sempre no ar ---
while ($true) {
    Write-Log "Subindo agente_impressao.py ..."
    try {
        & $Python "agente_impressao.py" 2>&1 | Tee-Object -FilePath $LogFile -Append
        $code = $LASTEXITCODE
        Write-Log "agente encerrou (exit code $code)."
    } catch {
        Write-Log "ERRO ao executar o agente: $($_.Exception.Message)"
    }
    Write-Log "Reiniciando em $RestartDelaySeconds s..."
    Start-Sleep -Seconds $RestartDelaySeconds
}
