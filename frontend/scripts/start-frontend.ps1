<#
.SYNOPSIS
  Inicia o frontend web Back-On (Expo/Metro) e o mantem no ar, reiniciando
  automaticamente se ele cair.

.DESCRIPTION
  - Detecta a pasta do frontend automaticamente (este script fica em frontend\scripts\).
  - Roda "npx expo start --port <Port>" (SEM --web -- esse flag abre um navegador
    sozinho, o que nao faz sentido rodando como tarefa/servico sem sessao
    interativa; o dev server do Metro serve o bundle web normalmente sem ele).
  - Grava log diario em frontend\logs\frontend-AAAAMMDD.log.
  - Loop de supervisao: se o processo do Expo encerrar, espera alguns segundos
    e reinicia. Mesmo padrao do backend\scripts\start-backend.ps1.

.PARAMETER Port
  Porta do dev server web. Padrao: 8082 (a mesma que o Expo ja escolhe sozinho
  neste projeto, ja que a 8081 e' do backend).

.PARAMETER BindHost
  Tipo de hospedagem do Expo (lan/tunnel/localhost). Padrao: lan (mesmo default
  do Expo -- acessivel na rede local / celular).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1
  powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1 -Port 8082
#>

param(
    [int]$Port = 8082,
    [string]$BindHost = "lan",
    [int]$StartupDelaySeconds = 20,   # espera rede/backend estabilizarem apos o boot
    [int]$RestartDelaySeconds = 10    # espera antes de reiniciar caso o Expo caia
)

$ErrorActionPreference = "Stop"

# --- Caminhos (script esta em frontend\scripts) ---
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$FrontendDir = Split-Path -Parent $ScriptDir          # ...\frontend
$LogDir      = Join-Path $FrontendDir "logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("frontend-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    $line | Tee-Object -FilePath $LogFile -Append
}

# Resolve node/npx por caminho absoluto -- rodando como tarefa agendada
# (SYSTEM, sem login) o PATH de usuario pode nao estar populado mesmo com
# o Node.js instalado no PATH de maquina. Mesma cautela ja usada no
# start-backend.ps1 com o python do venv (nao confiar so no PATH).
$NodeDir = "C:\Program Files\nodejs"
$NpxCmd  = Join-Path $NodeDir "npx.cmd"

Write-Log "==== Iniciando supervisor do frontend Back-On (web) ===="
Write-Log "FrontendDir = $FrontendDir"
Write-Log "Porta       = $Port"
Write-Log "Host        = $BindHost"

if ($StartupDelaySeconds -gt 0) {
    Write-Log "Aguardando $StartupDelaySeconds s para o sistema/rede estabilizarem..."
    Start-Sleep -Seconds $StartupDelaySeconds
}

Set-Location $FrontendDir

# Preflight -- falha de forma clara em vez de entrar num loop de erro obscuro.
if (-not (Test-Path $NpxCmd)) {
    Write-Log "ERRO: npx nao encontrado em $NpxCmd. Node.js esta instalado?"
    exit 1
}
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Log "ERRO: node_modules nao encontrado em $FrontendDir. Rode 'npm install' antes de usar este supervisor."
    exit 1
}

# IMPORTANTE: o Expo/Metro escreve avisos e progresso no STDERR. Com
# $ErrorActionPreference = "Stop", o PowerShell trata QUALQUER saida em
# stderr de um processo nativo como erro TERMINANTE e cai no catch, reiniciando
# em loop mesmo com o dev server no ar. A partir daqui usamos "Continue" --
# mesma solucao ja aplicada no start-backend.ps1.
$ErrorActionPreference = "Continue"

# --- Loop de supervisao: mantem o Expo sempre no ar ---
while ($true) {
    Write-Log "Subindo Expo (web) na porta $Port ..."
    try {
        & $NpxCmd expo start --port $Port --host $BindHost 2>&1 |
            Tee-Object -FilePath $LogFile -Append
        $code = $LASTEXITCODE
        Write-Log "Expo encerrou (exit code $code)."
    } catch {
        Write-Log "ERRO ao executar o Expo: $($_.Exception.Message)"
    }
    Write-Log "Reiniciando em $RestartDelaySeconds s..."
    Start-Sleep -Seconds $RestartDelaySeconds
}
