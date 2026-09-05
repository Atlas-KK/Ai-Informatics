[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

& $python -B -m pytest tests/phase7/test_phase7_acceptance.py -q -s -k ten_thousand_item_dashboard_and_filter_performance
if ($LASTEXITCODE -ne 0) { throw '10k repository performance test failed.' }

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'quality.ps1') -Scope e2e
if ($LASTEXITCODE -ne 0) { throw 'Real-browser performance test failed.' }
