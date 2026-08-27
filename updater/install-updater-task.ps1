<#
.SYNOPSIS
  Registra a Tarefa Agendada "BackOn-Updater", que roda apply_update.ps1
  periodicamente (padrão: a cada 30 min) pra manter a instalação atualizada
  automaticamente a partir das releases publicadas pela Kontacto.

.DESCRIPTION
  Mesmo padrão de backend\scripts\install-startup-task.ps1 — Tarefa
  Agendada rodando como SYSTEM, sem depender de login.

  >>> EXECUTE ESTE SCRIPT UMA UNICA VEZ, COMO ADMINISTRADOR. <<<

  ATENÇÃO — isto liga atualização automática de verdade nesta máquina.
  Antes de registrar em produção, confirme que:
    1. config.json está preenchido corretamente (manifestUrl com a SAS de
       leitura, installDir correto).
    2. O backend já está instalado e rodando manualmente pelo menos uma vez
       (ver BACKEND_DEPLOY_WINDOWS.md — a primeira instalação continua
       manual; o atualizador cuida só das próximas).
    3. Rodou `apply_update.ps1` manualmente pelo menos uma vez com sucesso.

.PARAMETER IntervalMinutes
  Intervalo entre verificações. Padrão: 30.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install-updater-task.ps1
#>

param(
    [int]$IntervalMinutes = 30,
    [string]$TaskName = "BackOn-Updater"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERRO: rode este script COMO ADMINISTRADOR." -ForegroundColor Red
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ApplyScript = Join-Path $ScriptDir "apply_update.ps1"
$ConfigFile = Join-Path $ScriptDir "config.json"

if (-not (Test-Path $ApplyScript)) {
    Write-Host "ERRO: não encontrei $ApplyScript" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $ConfigFile)) {
    Write-Host "ERRO: não encontrei config.json em $ScriptDir — copie config.exemplo.json pra config.json e preencha antes de registrar a tarefa." -ForegroundColor Red
    exit 1
}

Write-Host "Registrando tarefa '$TaskName' (a cada $IntervalMinutes min)..." -ForegroundColor Cyan

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ApplyScript`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration ([TimeSpan]::MaxValue)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tarefa anterior removida." -ForegroundColor Yellow
}

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "Verifica e aplica atualizações do Back-On (Backend + Frontend Web) automaticamente." | Out-Null

Write-Host "OK! Tarefa '$TaskName' registrada." -ForegroundColor Green
Write-Host ""
Write-Host "Pra rodar agora (sem esperar o ciclo):" -ForegroundColor Cyan
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Pra ver o status:" -ForegroundColor Cyan
Write-Host "    Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Pra remover:" -ForegroundColor Cyan
Write-Host "    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
Write-Host "Logs em: $ScriptDir\logs\updater-AAAAMMDD.log"
