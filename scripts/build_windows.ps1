# PyInstaller + Inno Setup for Windows.
# Prerequisites: Python 3.10+, pip, optional Inno Setup 6 (ISCC.exe on PATH).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing build dependencies..."
python -m pip install -q pyinstaller -r requirements.txt

function Test-PythonImport([string]$ModuleName) {
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        python -c "import $ModuleName" *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
}

$CodecRoot = if ($env:EEGDB_CODEC_ROOT) {
    $env:EEGDB_CODEC_ROOT
} else {
    Resolve-Path (Join-Path $Root "..\eegdb-codec") -ErrorAction SilentlyContinue
}
if (-not (Test-PythonImport "eegdb_codec")) {
    if ($CodecRoot -and (Test-Path $CodecRoot)) {
        Write-Host "Building and installing eegdb-codec from $CodecRoot"
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $CodecRoot "scripts\build-codec-wheel.ps1")
        $wheel = Get-ChildItem (Join-Path $CodecRoot "dist\python\eegdb_codec-*.whl") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $wheel) {
            throw "eegdb-codec wheel was not produced under $CodecRoot\dist\python"
        }
        python -m pip install -q $wheel.FullName
    } else {
        Write-Warning "eegdb_codec is not installed and eegdb-codec was not found. Set EEGDB_CODEC_ROOT or install the wheel before packaging local decode."
    }
}

Write-Host "Running PyInstaller..."
pyinstaller --noconfirm --clean --windowed `
  --name EEGDBClient `
  --paths $Root `
  --hidden-import eegdb_client `
  --hidden-import eegdb_codec `
  --hidden-import eegdb_client.cli `
  --hidden-import eegdb_client.ui.main_window `
  --hidden-import eegdb_client.ui.attrs_form `
  --collect-binaries eegdb_codec `
  --collect-all mne `
  --collect-all PyQt6 `
  --collect-all pyedflib `
  app.py

$DistDir = Join-Path $Root "dist\EEGDBClient"
if (-not (Test-Path (Join-Path $DistDir "EEGDBClient.exe"))) {
    throw "PyInstaller output not found under dist/EEGDBClient"
}
Write-Host "PyInstaller OK: $DistDir"

$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($Iscc) {
    Write-Host "Building installer with Inno Setup..."
    & iscc (Join-Path $PSScriptRoot "eegdb_client.iss")
    Write-Host "Installer: $Root\dist\installer\EEGDBClient-setup-0.1.0.exe"
} else {
    Write-Host "Inno Setup (iscc) not found — skip installer. Zip dist/EEGDBClient manually."
}
