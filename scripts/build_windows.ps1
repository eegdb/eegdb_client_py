# PyInstaller + Inno Setup for Windows.
# Prerequisites: Python 3.10+, pip, optional Inno Setup 6 (ISCC.exe on PATH).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing build dependencies..."
python -m pip install -q pyinstaller -r requirements.txt

Write-Host "Running PyInstaller..."
pyinstaller --noconfirm --clean --windowed `
  --name EEGDBClient `
  --paths $Root `
  --hidden-import eegdb_client `
  --hidden-import eegdb_client.cli `
  --hidden-import eegdb_client.ui.main_window `
  --hidden-import eegdb_client.ui.attrs_form `
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
