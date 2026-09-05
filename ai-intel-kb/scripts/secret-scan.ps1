[CmdletBinding()]
param(
    [string]$ScanRoot
)

$ErrorActionPreference = 'Stop'
$projectRoot = if ($ScanRoot) {
    (Resolve-Path -LiteralPath $ScanRoot).Path
}
else {
    Split-Path -Parent $PSScriptRoot
}
$excludedParts = @('\.git\', '\.venv\', '\node_modules\', '\dist\', '\data\', '\coverage\')
$allowedNames = @('.gitignore', '.gitattributes', '.env.example')
$allowedExtensions = @('.py', '.toml', '.json', '.ts', '.tsx', '.js', '.css', '.html', '.md', '.ps1', '.yml', '.yaml')
$patterns = @(
    '(?i)sk-[a-z0-9_-]{20,}',
    '(?i)AKIA[0-9A-Z]{16}',
    '(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["''][a-z0-9_./+=-]{12,}["'']'
)

$secretMatches = [System.Collections.Generic.List[string]]::new()
$files = Get-ChildItem -LiteralPath $projectRoot -File -Recurse | Where-Object {
    $path = $_.FullName
    $excluded = $false
    foreach ($part in $excludedParts) {
        if ($path.IndexOf($part, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $excluded = $true
            break
        }
    }
    -not $excluded -and ($_.Name -in $allowedNames -or $_.Extension -in $allowedExtensions)
}

foreach ($file in $files) {
    $content = Get-Content -LiteralPath $file.FullName -Raw
    foreach ($pattern in $patterns) {
        if ($content -match $pattern) {
            $secretMatches.Add($file.FullName)
            break
        }
    }
}

if ($secretMatches.Count -gt 0) {
    throw "Potential secret material detected in: $($secretMatches -join ', ')"
}

Write-Output "Secret scan passed across $($files.Count) source/configuration files."
