<#
.SYNOPSIS
  Compila e roda o app Windows (react-native-windows) com todos os workarounds
  necessarios para este ambiente (Visual Studio 2026 / MSBuild 18.7).

.DESCRIPTION
  react-native-windows 0.81 nao foi testado contra o VS 2026 (lancado depois do
  RNW ser publicado). Sem esses parametros o build falha em varios pontos
  diferentes -- cada um foi diagnosticado manualmente, ver CLAUDE.md secao
  "Windows Build Workarounds" para o detalhe de cada um. Este script existe para
  nao ter que redigitar/redescobrir essa lista toda vez.

  Correcoes aplicadas:
  - PowerShell 7 (pwsh.exe) precisa estar no PATH: as ferramentas do RNW CLI
    dependem dele para funcoes auxiliares; sem isso, o CLI nem registra os
    comandos "run-windows"/"init-windows" (falha silenciosa).
  - MinimumVisualStudioVersion=18.0: o RNW tem "17.11.0" hardcoded como minimo,
    e calcula o teto como major+1 ("18.0") -- exclui o VS 2026 (v18.7) por
    engano. Setar essa env var e' o escape hatch oficial do proprio RNW.
  - CL=/D_SILENCE_EXPERIMENTAL_COROUTINE_DEPRECATION_WARNINGS: o MSVC do VS2026
    (14.51.x) barra como ERRO (nao mais so aviso) o uso de <experimental/coroutine>
    que o C++ do RNW ainda usa. IMPORTANTE: definir via $env:CL no PowerShell,
    NUNCA via Bash/Git Bash -- o MSYS reescreve "/D..." como se fosse um path
    Unix e corrompe o valor.
  - WindowsTargetPlatformVersion / TargetPlatformVersion=10.0.26100.0: o RNW
    fixa 10.0.22621.0, que nao esta instalado (so temos SDKs mais novos).
  - WindowsAppSDKVerifyTransitiveDependencies=false: flag oficial da Microsoft
    (documentada no proprio .targets do WindowsAppSDK) para desligar uma
    checagem de dependencias transitivas do NuGet excessivamente estrita para
    projetos baseados em packages.config.
  - _WindowsAppSDKFoundationPlatform / _MrtCoreRuntimeIdentifier / HermesPlatform
    = x64: essas propriedades internas (usadas para montar caminhos de .lib)
    ficam vazias em builds via solution (nao foi diagnosticado o motivo exato --
    provavelmente negociacao de plataforma entre projetos C++ referenciados so
    via ProjectReference, sem entrada na .sln). Forcar via /p: resolve.
  - RnwNewArch=true: o template "cpp-app" que este projeto usa e' WinUI3/
    Composition, que exige New Architecture (Fabric) no Microsoft.ReactNative
    core -- sem isso da conflito de tipos entre Microsoft.UI.Xaml (WinUI3) e
    Windows.UI.Xaml (UWP) em codigo "Paper-only" (ex: DevMenuControl).
  - sync-windows-overrides.js (chamado no topo deste script, tambem roda no
    postinstall): react-native-windows nao tem um passo automatico que copia
    seus proprios arquivos ".windows.js" (Platform, View, ScrollView, Alert,
    etc.) para dentro de node_modules/react-native -- sem isso o bundle do
    Metro falha ("Cannot read property 'OS' of undefined") ou nem builda
    (ReactDevToolsSettingsManager ausente). `npm install` some com essas
    copias porque ficam em node_modules; por isso roda no postinstall tambem.

.PARAMETER Launch
  Se passado, abre o app depois de compilar (equivalente a omitir --no-launch).
  Por padrao so compila/implanta, sem abrir a janela.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1
  powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -Launch
#>

param(
    [switch]$Launch
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$FrontendDir = Split-Path -Parent $ScriptDir
Set-Location $FrontendDir

$pwshDir = "$env:LocalAppData\Microsoft\powershell7"
if (Test-Path "$pwshDir\pwsh.exe") {
    $env:Path = "$pwshDir;" + $env:Path
} else {
    Write-Warning "PowerShell 7 nao encontrado em $pwshDir. Instale com:`n  Invoke-Expression `"& { `$(Invoke-RestMethod 'https://aka.ms/install-powershell.ps1') } -Destination '$pwshDir' -AddToPath`""
}

node "$ScriptDir\sync-windows-overrides.js"

$env:MinimumVisualStudioVersion = "18.0"
$env:CL = "/D_SILENCE_EXPERIMENTAL_COROUTINE_DEPRECATION_WARNINGS"

$msbuildProps = @(
    "Platform=x64",
    "RnwNewArch=true",
    "_WindowsAppSDKFoundationPlatform=x64",
    "_MrtCoreRuntimeIdentifier=x64",
    "HermesPlatform=x64",
    "WindowsTargetPlatformVersion=10.0.26100.0",
    "TargetPlatformVersion=10.0.26100.0",
    "WindowsAppSDKVerifyTransitiveDependencies=false"
) -join ","

$rnwArgs = @("run-windows", "--msbuildprops", $msbuildProps)
if (-not $Launch) {
    $rnwArgs += "--no-launch"
}

npx @react-native-community/cli @rnwArgs
