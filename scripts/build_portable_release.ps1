param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")
Set-Location -LiteralPath $root

if (-not $Python) {
    $Python = "python"
}

$version = & $Python -c "from aelrith_forge.version import APP_VERSION; print(APP_VERSION)"
if (-not $version) {
    throw "Could not read Kon. APP_VERSION."
}

$releaseName = "Kon-$version-portable"
$releaseRoot = Join-Path -Path $root -ChildPath "dist\releases"
$releaseDir = Join-Path -Path $releaseRoot -ChildPath $releaseName
$zipPath = Join-Path -Path $releaseRoot -ChildPath "$releaseName.zip"

Write-Host "Building $releaseName"

if (-not (& $Python -m PyInstaller --version 2>$null)) {
    throw "PyInstaller is not installed. Run: $Python -m pip install -r requirements-dev.txt"
}

Remove-Item -LiteralPath (Join-Path -Path $root -ChildPath "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path -Path $root -ChildPath "dist\Kon") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $releaseDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue

& $Python -m PyInstaller AelrithForge.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$builtDir = Join-Path -Path $root -ChildPath "dist\Kon"
if (-not (Test-Path -LiteralPath (Join-Path -Path $builtDir -ChildPath "Kon.exe"))) {
    throw "PyInstaller output is missing dist\Kon\Kon.exe."
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Get-ChildItem -LiteralPath $builtDir -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $releaseDir -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path -Path $root -ChildPath "README.md") -Destination $releaseDir -Force
Copy-Item -LiteralPath (Join-Path -Path $root -ChildPath "LICENSE.txt") -Destination $releaseDir -Force
Copy-Item -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "update_kon.ps1") -Destination $releaseDir -Force

@"
Kon. Portable Release

1. Extract this ZIP into a normal folder, for example Documents\Kon.
2. Install Tesseract OCR if it is not already installed:
   C:\Program Files\Tesseract-OCR\tesseract.exe
3. Run Kon.exe.
4. In Kon., configure Specs or Powers targets, OCR regions, Auto/reroll/confirm click points, and optional Discord webhook.
5. Use the preview/test buttons before leaving the macro unattended.

Auto updates:
- Kon. checks GitHub Releases when the packaged app starts.
- It asks before installing an update.
- Updates preserve local config, webhook settings, output, logs, screenshots, and diagnostics.
"@ | Set-Content -Path (Join-Path -Path $releaseDir -ChildPath "README_FIRST.txt") -Encoding UTF8

$forbidden = @(
    "config",
    "output",
    ".git",
    "__pycache__",
    ".pytest_cache"
)
foreach ($name in $forbidden) {
    if (Test-Path -LiteralPath (Join-Path -Path $releaseDir -ChildPath $name)) {
        throw "Release directory unexpectedly contains $name."
    }
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Compress-Archive -Path (Join-Path -Path $releaseDir -ChildPath "*") -DestinationPath $zipPath -Force

Write-Host "Portable release created:"
Write-Host "  $zipPath"
