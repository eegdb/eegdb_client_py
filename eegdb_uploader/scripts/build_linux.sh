#!/usr/bin/env bash
# Build PyInstaller onedir bundle on Linux/macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="$(cd "${ROOT}/.." && pwd)"
cd "${ROOT}"

python3 -m pip install -q --break-system-packages pyinstaller -r requirements.txt 2>/dev/null \
  || python3 -m pip install -q pyinstaller -r requirements.txt

export PYTHONPATH="${CLIENT}"
pyinstaller --noconfirm --clean --windowed \
  --name EEGDBUploader \
  --paths "${CLIENT}" \
  --hidden-import eegdb_uploader \
  --hidden-import eegdb_uploader.cli \
  --hidden-import eegdb_uploader.ui.main_window \
  --hidden-import eegdb_uploader.ui.attrs_form \
  --collect-all mne \
  --collect-all PyQt6 \
  --collect-all pyedflib \
  app.py

echo "Build output: ${ROOT}/dist/EEGDBUploader/"
echo "Run: ${ROOT}/dist/EEGDBUploader/EEGDBUploader"
