[CmdletBinding()]
param(
    [ValidateSet('foundation', 'backend', 'frontend', 'e2e', 'full')]
    [string]$Scope = 'foundation'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$bundledRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Run powershell -File scripts/bootstrap.ps1 first.'
}

$bundledNodeBin = Join-Path $bundledRoot 'node\bin'
if (Test-Path -LiteralPath (Join-Path $bundledNodeBin 'node.exe')) {
    $env:PATH = "$bundledNodeBin;$env:PATH"
}
elseif (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found.'
}

$pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
if (-not $pnpmCommand) {
    $fallbackPnpm = Join-Path $bundledRoot 'bin\fallback\pnpm.cmd'
    if (Test-Path -LiteralPath $fallbackPnpm) {
        $pnpm = $fallbackPnpm
    }
    else {
        throw 'pnpm was not found.'
    }
}
else {
    $pnpm = $pnpmCommand.Source
}

function Invoke-BackendGate {
    Push-Location $projectRoot
    try {
        & $python -B -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed.' }
        & $python -B -m ruff format --check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }
        & $python -B -m mypy
        if ($LASTEXITCODE -ne 0) { throw 'Mypy failed.' }
        & $python -B -m pytest
        if ($LASTEXITCODE -ne 0) { throw 'Pytest failed.' }
    }
    finally {
        Pop-Location
    }
}

function Invoke-FrontendGate {
    Push-Location (Join-Path $projectRoot 'web')
    try {
        & $pnpm lint
        if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed.' }
        & $pnpm test
        if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
        & $pnpm build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
    finally {
        Pop-Location
    }
}

function Invoke-SecretGate {
    & (Join-Path $PSScriptRoot 'secret-scan.ps1')
}

function Invoke-E2EGate {
    param([switch]$SkipBuild)

    $webRoot = Join-Path $projectRoot 'web'
    if (-not $SkipBuild) {
        Push-Location $webRoot
        try {
            & $pnpm build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build for browser E2E failed.' }
        }
        finally {
            Pop-Location
        }
    }

    $localPlaywright = Join-Path $webRoot 'node_modules\playwright\package.json'
    $bundledNodeModules = Join-Path $bundledRoot 'node\node_modules'
    if (-not (Test-Path -LiteralPath $localPlaywright)) {
        if (-not (Test-Path -LiteralPath (Join-Path $bundledNodeModules 'playwright\package.json'))) {
            throw 'Playwright is unavailable. Install playwright or use the bundled workspace runtime.'
        }
        $env:NODE_PATH = $bundledNodeModules
    }
    & node (Join-Path $webRoot 'e2e\phase7.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Browser E2E failed.' }
    & node (Join-Path $webRoot 'e2e\phase8-integration.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Real backend browser integration E2E failed.' }
}

switch ($Scope) {
    'backend' { Invoke-BackendGate }
    'frontend' { Invoke-FrontendGate }
    'e2e' { Invoke-E2EGate }
    'foundation' {
        Invoke-SecretGate
        Invoke-BackendGate
        Invoke-FrontendGate
    }
    'full' {
        Invoke-SecretGate
        Invoke-BackendGate
        Invoke-FrontendGate
        Invoke-E2EGate -SkipBuild
    }
}

Write-Output "Quality gate '$Scope' passed."
