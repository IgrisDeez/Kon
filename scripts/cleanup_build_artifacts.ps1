$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$targets = @()
$targets += Get-ChildItem -Path $root -Recurse -File -Filter *.exe |
    Where-Object { $_.FullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) }

foreach ($name in @("dist", "build")) {
    $path = Join-Path $root $name
    if (Test-Path -LiteralPath $path) {
        $targets += Get-Item -LiteralPath $path
    }
}

$targets += Get-ChildItem -Path $root -Recurse -Directory -Filter __pycache__ |
    Where-Object { $_.FullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) }

$targets = $targets | Sort-Object { if ($_.PSIsContainer) { 1 } else { 0 } }, FullName -Unique

if (-not $targets) {
    Write-Host "No build artifacts found."
    exit 0
}

Write-Host "Deleting build artifacts:"
$targets | ForEach-Object { Write-Host $_.FullName }

foreach ($target in $targets) {
    if (-not $target.FullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete outside project: $($target.FullName)"
    }
    if (Test-Path -LiteralPath $target.FullName) {
        Remove-Item -LiteralPath $target.FullName -Recurse -Force
    }
}

Write-Host "Cleanup complete."
