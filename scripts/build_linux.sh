#!/usr/bin/env bash
# Build PyInstaller onedir bundle on Linux/macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

python3 -m pip install -q --break-system-packages pyinstaller -r requirements.txt 2>/dev/null \
  || python3 -m pip install -q pyinstaller -r requirements.txt

pyinstaller --noconfirm --clean --windowed \
  --name EEGDBClient \
  --paths "${ROOT}" \
  --hidden-import eegdb_client \
  --hidden-import eegdb_client.cli \
  --hidden-import eegdb_client.ui.main_window \
  --hidden-import eegdb_client.ui.attrs_form \
  --collect-all mne \
  --collect-all PyQt6 \
  --collect-all pyedflib \
  app.py

echo "Build output: ${ROOT}/dist/EEGDBClient/"
echo "Run: ${ROOT}/dist/EEGDBClient/EEGDBClient"
