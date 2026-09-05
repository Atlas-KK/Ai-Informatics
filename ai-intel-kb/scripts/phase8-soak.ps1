[CmdletBinding()]
param(
    [string]$Database,
    [string]$ReportDate
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Run powershell -File scripts/bootstrap.ps1 first.'
}

$arguments = @('-B', (Join-Path $PSScriptRoot 'phase8_observe.py'))
if ($Database) {
    $arguments += @('--database', $Database)
}
if ($ReportDate) {
    $arguments += @('--report-date', $ReportDate)
}
& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw 'Phase 8 scheduled-run observation failed.'
}

Write-Output 'Observation appended. This script does not create or trigger a system schedule.'
