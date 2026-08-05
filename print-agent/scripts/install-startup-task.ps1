<#
.SYNOPSIS
  Registra o Agente de Impressão Silenciosa para iniciar AUTOMATICAMENTE
  quando o Windows ligar, mesmo SEM ninguém fazer login (roda como SYSTEM).

.DESCRIPTION
  Cria uma Tarefa Agendada chamada "BackOn-PrintAgent" que executa o
  start-print-agent.ps1 na inicialização do computador, com reinício em
  caso de falha — mesmo padrão já usado por
  backend\scripts\install-startup-task.ps1 pro backend.

  >>> EXECUTE ESTE SCRIPT UMA ÚNICA VEZ, COMO ADMINISTRADOR. <<<
  (Clique direito no PowerShell > "Executar como administrador")

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install-startup-task.ps1
#>

param(
    [string]$TaskName = "BackOn-PrintAgent"
)

$ErrorActionPreference = "Stop"

# Confere se esta como administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERRO: rode este script COMO ADMINISTRADOR." -ForegroundColor Red
    exit 1
}

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$StartScript = Join-Path $ScriptDir "start-print-agent.ps1"
if (-not (Test-Path $StartScript)) {
    Write-Host "ERRO: nao encontrei $StartScript" -ForegroundColor Red
    exit 1
}

$AgentDir = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $AgentDir "config.json"))) {
    Write-Host "AVISO: config.json nao encontrado em $AgentDir." -ForegroundColor Yellow
    Write-Host "AVISO: copie config.exemplo.json para config.json e ajuste os valores antes de reiniciar o PC." -ForegroundColor Yellow
}

Write-Host "Registrando tarefa '$TaskName'..." -ForegroundColor Cyan

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
$trigger = New-ScheduledTaskTrigger -AtStartup
# Roda como SYSTEM (nao precisa de login) e com privilegios elevados —
# impressoras USB locais instaladas normalmente no Windows (com driver) ficam
# visiveis pro SYSTEM tambem, sem depender de sessao de usuario logado.
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

# Remove versao anterior, se existir
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tarefa anterior removida." -ForegroundColor Yellow
}

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "Inicia o Agente de Impressao Silenciosa (print-agent) automaticamente no boot." | Out-Null

Write-Host "OK! Tarefa '$TaskName' registrada." -ForegroundColor Green
Write-Host ""
Write-Host "Para iniciar agora (sem reiniciar o PC):" -ForegroundColor Cyan
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para ver o status:" -ForegroundColor Cyan
Write-Host "    Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Para remover:" -ForegroundColor Cyan
Write-Host "    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
Write-Host "Logs do agente em: print-agent\logs\agent-AAAAMMDD.log"
