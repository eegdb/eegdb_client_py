# PyInstaller + Inno Setup for Windows.
# Prerequisites: Python 3.10+, pip, optional Inno Setup 6 (ISCC.exe on PATH).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Client = Split-Path -Parent $Root
Set-Location $Root

Write-Host "Installing build dependencies..."
python -m pip install -q pyinstaller -r requirements.txt

$env:PYTHONPATH = $Client
Write-Host "Running PyInstaller..."
pyinstaller --noconfirm --clean --windowed `
  --name EEGDBUploader `
  --paths $Client `
  --hidden-import eegdb_uploader `
  --hidden-import eegdb_uploader.cli `
  --hidden-import eegdb_uploader.ui.main_window `
  --hidden-import eegdb_uploader.ui.attrs_form `
  --collect-all mne `
  --collect-all PyQt6 `
  --collect-all pyedflib `
  app.py

$DistDir = Join-Path $Root "dist\EEGDBUploader"
if (-not (Test-Path (Join-Path $DistDir "EEGDBUploader.exe"))) {
    throw "PyInstaller output not found under dist/EEGDBUploader"
}
Write-Host "PyInstaller OK: $DistDir"

$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($Iscc) {
    Write-Host "Building installer with Inno Setup..."
    & iscc (Join-Path $PSScriptRoot "eegdb_uploader.iss")
    Write-Host "Installer: $Root\dist\installer\EEGDBUploader-setup-0.1.0.exe"
} else {
    Write-Host "Inno Setup (iscc) not found — skip installer. Zip dist/EEGDBUploader manually."
}
