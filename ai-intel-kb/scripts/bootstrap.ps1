[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$bundledRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'

function Resolve-Python {
    $bundledPython = Join-Path $bundledRoot 'python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        return $bundledPython
    }

    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) {
        $minorVersion = & $systemPython.Source -B -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))'
        if ($LASTEXITCODE -eq 0 -and $minorVersion -eq '3.12') {
            return $systemPython.Source
        }
    }

    throw 'Python 3.12 was not found. Install Python 3.12 or run from Codex desktop.'
}

function Enable-Bundled-Node {
    if (Get-Command node -ErrorAction SilentlyContinue) {
        return
    }

    $bundledNodeBin = Join-Path $bundledRoot 'node\bin'
    if (Test-Path -LiteralPath (Join-Path $bundledNodeBin 'node.exe')) {
        $env:PATH = "$bundledNodeBin;$env:PATH"
    }
}

function Resolve-Pnpm {
    $command = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $bundledPnpm = Join-Path $bundledRoot 'bin\fallback\pnpm.cmd'
    if (Test-Path -LiteralPath $bundledPnpm) {
        return $bundledPnpm
    }

    throw 'pnpm was not found. Install pnpm or run from Codex desktop.'
}

Push-Location $projectRoot
try {
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $runtimePython = Resolve-Python
        & $runtimePython -B -m venv '.venv'
        if ($LASTEXITCODE -ne 0) {
            throw "Virtual environment creation failed with exit code $LASTEXITCODE."
        }
    }
    else {
        $venvMinor = & $venvPython -B -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))'
        if ($LASTEXITCODE -ne 0 -or $venvMinor -ne '3.12') {
            throw "Existing .venv uses Python $venvMinor; Python 3.12 is required."
        }
    }

    & $venvPython -B -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed with exit code $LASTEXITCODE."
    }
    & $venvPython -B -m pip install --disable-pip-version-check -e '.[dev]'
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency installation failed with exit code $LASTEXITCODE."
    }

    Enable-Bundled-Node
    $pnpm = Resolve-Pnpm
    Push-Location (Join-Path $projectRoot 'web')
    try {
        & $pnpm install
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend dependency installation failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

Write-Output 'Project dependencies are installed.'
