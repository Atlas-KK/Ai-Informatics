[CmdletBinding()]
param(
    [switch]$SkipCommands
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Run powershell -File scripts/bootstrap.ps1 first.'
}

$arguments = @('-B', (Join-Path $PSScriptRoot 'phase8_audit.py'))
if ($SkipCommands) {
    $arguments += '--skip-commands'
}
& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw 'Phase 8 local audit failed. See docs/phase8/phase8-acceptance-report.md.'
}

Write-Output 'Phase 8 report generated under docs/phase8.'
