<#
.SYNOPSIS
    Builds the Warframe Ducat Calculator as a one-folder PyInstaller distribution
    and zips it. Re-run after every feature change; output always lands at
    dist/WarframeDucatCalculator/ (+ a versioned zip beside it).
#>

$ErrorActionPreference = "Stop"
$Version = "1.0.0"
$AppName = "WarframeDucatCalculator"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $RepoRoot

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Write-Warn($msg) {
    Write-Host "WARNING: $msg" -ForegroundColor Yellow
}

# --- 1. Environment validation -------------------------------------------------

Write-Step "Checking build environment"

if ($env:VIRTUAL_ENV) {
    Write-Host "Virtual env active: $env:VIRTUAL_ENV"
} else {
    Write-Warn "No virtual env detected (VIRTUAL_ENV not set) - building with the system/global Python."
}

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller is not importable in this Python environment." -ForegroundColor Red
    Write-Host "Install build dependencies first: pip install -r requirements.txt -r requirements-build.txt"
    exit 1
}
Write-Host "pyinstaller: OK"

$optionalDeps = @("PIL", "cv2", "pytesseract", "pynput", "googleapiclient", "google.auth")
foreach ($dep in $optionalDeps) {
    python -c "import $dep" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Optional dependency '$dep' is not importable - it (and any feature relying on it) will be missing from the bundle. Install requirements.txt to include it."
    } else {
        Write-Host "$dep`: OK"
    }
}

# --- 2. Refresh the seeded ducat cache ------------------------------------------

Write-Step "Refreshing seed ducat cache"

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    Push-Location (Join-Path $RepoRoot "scripts")
    try {
        npm run generate
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "npm run generate failed - keeping the existing committed seed at assets/seed/ducat_lookup.json."
        } else {
            Copy-Item (Join-Path $RepoRoot "data\ducat_lookup.json") (Join-Path $RepoRoot "assets\seed\ducat_lookup.json") -Force
            Write-Host "Seed cache refreshed at assets/seed/ducat_lookup.json"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Warn "Node not found on PATH - skipping seed refresh and using the existing committed assets/seed/ducat_lookup.json."
}

# --- 3. Clean previous build outputs --------------------------------------------

Write-Step "Cleaning previous build output"

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $RepoRoot "build")
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $RepoRoot "dist\$AppName")

# --- 4. Build ---------------------------------------------------------------------

Write-Step "Running PyInstaller"

python -m PyInstaller --noconfirm "$AppName.spec"
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller build failed." -ForegroundColor Red
    exit 1
}

$exePath = Join-Path $RepoRoot "dist\$AppName\$AppName.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "Build finished but $exePath was not found." -ForegroundColor Red
    exit 1
}

# --- 5. Zip the dist ----------------------------------------------------------------

Write-Step "Zipping distribution"

$zipPath = Join-Path $RepoRoot "dist\$AppName-$Version.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $zipPath
Compress-Archive -Path (Join-Path $RepoRoot "dist\$AppName") -DestinationPath $zipPath

# --- 6. Summary -----------------------------------------------------------------------

Write-Step "Build complete"
Write-Host "Executable: $exePath"
Write-Host "Zip:        $zipPath"
