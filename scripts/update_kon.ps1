param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [string]$AppDir,

    [string]$ExeName = "Kon.exe",

    [int]$ParentPid = 0
)

$ErrorActionPreference = "Stop"

function Write-KonUpdateLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logDir = Join-Path -Path $env:TEMP -ChildPath "KonUpdateLogs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Add-Content -Path (Join-Path -Path $logDir -ChildPath "update.log") -Value "[$stamp] $Message"
}

function Resolve-UpdateSource {
    param([string]$ExtractDir)
    $directExe = Join-Path -Path $ExtractDir -ChildPath $ExeName
    if (Test-Path -LiteralPath $directExe) {
        return $ExtractDir
    }

    $konDir = Join-Path -Path $ExtractDir -ChildPath "Kon"
    if (Test-Path -LiteralPath (Join-Path -Path $konDir -ChildPath $ExeName)) {
        return $konDir
    }

    $candidate = Get-ChildItem -LiteralPath $ExtractDir -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path -Path $_.FullName -ChildPath $ExeName) } |
        Select-Object -First 1
    if ($candidate) {
        return $candidate.FullName
    }

    throw "The update ZIP does not contain $ExeName."
}

function Restore-KonBackup {
    param(
        [string]$BackupDir,
        [string]$TargetDir,
        [string[]]$PreserveNames
    )
    if (-not (Test-Path -LiteralPath $BackupDir)) {
        return
    }
    Get-ChildItem -LiteralPath $TargetDir -Force | ForEach-Object {
        if ($PreserveNames -notcontains $_.Name) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }
    Get-ChildItem -LiteralPath $BackupDir -Force | ForEach-Object {
        if ($PreserveNames -notcontains $_.Name) {
            Copy-Item -LiteralPath $_.FullName -Destination $TargetDir -Recurse -Force
        }
    }
}

$appPath = Resolve-Path -LiteralPath $AppDir
$zipFile = Resolve-Path -LiteralPath $ZipPath
$appRoot = $appPath.Path
$workRoot = Join-Path -Path $env:TEMP -ChildPath ("KonUpdate_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
$extractDir = Join-Path -Path $workRoot -ChildPath "extract"
$backupDir = Join-Path -Path $workRoot -ChildPath "backup"
$preserve = @(
    "config",
    "output",
    "logs",
    "screenshots",
    "debug",
    "godroll_captures",
    "json",
    "ocr_debug_crops",
    "diagnostic_snapshots"
)

try {
    Write-KonUpdateLog "Starting update | app=$appRoot | zip=$zipFile"

    if ($ParentPid -gt 0) {
        try {
            Wait-Process -Id $ParentPid -Timeout 90 -ErrorAction Stop
        } catch {
            Write-KonUpdateLog "Parent process wait ended: $($_.Exception.Message)"
        }
    }

    New-Item -ItemType Directory -Force -Path $extractDir, $backupDir | Out-Null

    Expand-Archive -LiteralPath $zipFile -DestinationPath $extractDir -Force
    $sourceDir = Resolve-UpdateSource -ExtractDir $extractDir

    Get-ChildItem -LiteralPath $appRoot -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $backupDir -Recurse -Force
    }

    Get-ChildItem -LiteralPath $appRoot -Force | ForEach-Object {
        if ($preserve -notcontains $_.Name) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }

    Get-ChildItem -LiteralPath $sourceDir -Force | ForEach-Object {
        if ($preserve -notcontains $_.Name) {
            Copy-Item -LiteralPath $_.FullName -Destination $appRoot -Recurse -Force
        }
    }

    $exePath = Join-Path -Path $appRoot -ChildPath $ExeName
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "Updated app is missing $ExeName."
    }

    Write-KonUpdateLog "Update installed successfully."
    Start-Process -FilePath $exePath -WorkingDirectory $appRoot
} catch {
    Write-KonUpdateLog "Update failed: $($_.Exception.Message)"
    try {
        Restore-KonBackup -BackupDir $backupDir -TargetDir $appRoot -PreserveNames $preserve
        Write-KonUpdateLog "Backup restored after failed update."
    } catch {
        Write-KonUpdateLog "Backup restore failed: $($_.Exception.Message)"
    }
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Kon. update failed:`n$($_.Exception.Message)`n`nYour existing settings and files were preserved.", "Kon. Update Failed", "OK", "Error") | Out-Null
    $exePath = Join-Path -Path $appRoot -ChildPath $ExeName
    if (Test-Path -LiteralPath $exePath) {
        Start-Process -FilePath $exePath -WorkingDirectory $appRoot
    }
    exit 1
}
