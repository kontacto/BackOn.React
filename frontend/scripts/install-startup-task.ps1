<#
.SYNOPSIS
  Registra o frontend web Back-On para iniciar AUTOMATICAMENTE quando o Windows
  ligar, mesmo SEM ninguem fazer login (roda como SYSTEM).

.DESCRIPTION
  Cria uma Tarefa Agendada chamada "BackOn-Frontend" que executa o
  start-frontend.ps1 na inicializacao do computador, com reinicio em caso de
  falha. Mesmo padrao do backend\scripts\install-startup-task.ps1.

  >>> EXECUTE ESTE SCRIPT UMA UNICA VEZ, COMO ADMINISTRADOR. <<<
  (Clique direito no PowerShell > "Executar como administrador")

.PARAMETER Port
  Porta do dev server web. Padrao: 8082.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install-startup-task.ps1
  powershell -ExecutionPolicy Bypass -File .\install-startup-task.ps1 -Port 8082
#>

param(
    [int]$Port = 8082,
    [string]$TaskName = "BackOn-Frontend"
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
$StartScript = Join-Path $ScriptDir "start-frontend.ps1"
if (-not (Test-Path $StartScript)) {
    Write-Host "ERRO: nao encontrei $StartScript" -ForegroundColor Red
    exit 1
}

Write-Host "Registrando tarefa '$TaskName' (porta $Port)..." -ForegroundColor Cyan

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`" -Port $Port"

$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
$trigger = New-ScheduledTaskTrigger -AtStartup
# Roda como SYSTEM (nao precisa de login) e com privilegios elevados --
# mesma escolha do backend, pra nao depender de ninguem estar logado.
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
    -Description "Inicia o frontend web Back-On (Expo) automaticamente no boot." | Out-Null

Write-Host "OK! Tarefa '$TaskName' registrada." -ForegroundColor Green
Write-Host ""
Write-Host "Para iniciar agora (sem reiniciar o PC):" -ForegroundColor Cyan
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para ver o status:" -ForegroundColor Cyan
Write-Host "    Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Para remover:" -ForegroundColor Cyan
Write-Host "    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
Write-Host "Logs do frontend em: frontend\logs\frontend-AAAAMMDD.log"
