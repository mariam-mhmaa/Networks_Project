# Dot-source from PowerShell. Uses an existing installation; process scope only.
param(
    [string]$IdfPath = $env:IDF_PATH,
    [string]$IdfToolsPath = $env:IDF_TOOLS_PATH
)
if ([string]::IsNullOrWhiteSpace($IdfPath)) {
    throw 'Supply -IdfPath pointing to your existing ESP-IDF v6.1 checkout, or activate ESP-IDF first.'
}
$exportScript = Join-Path $IdfPath 'export.ps1'
if (-not (Test-Path -LiteralPath $exportScript -PathType Leaf)) {
    throw "ESP-IDF export.ps1 was not found at the supplied -IdfPath."
}
if (-not [string]::IsNullOrWhiteSpace($IdfToolsPath)) { $env:IDF_TOOLS_PATH = $IdfToolsPath }
$env:PYTHONUTF8 = '1'
. $exportScript
