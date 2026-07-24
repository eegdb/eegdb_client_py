#!/usr/bin/env bash
# Build PyInstaller onedir bundle on Linux/macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

python3 -m pip install -q --break-system-packages pyinstaller -r requirements.txt 2>/dev/null \
  || python3 -m pip install -q pyinstaller -r requirements.txt

CODEC_ROOT="${EEGDB_CODEC_ROOT:-${ROOT}/../eegdb-codec}"
if ! python3 -c "import eegdb_codec" >/dev/null 2>&1; then
  if [[ -d "${CODEC_ROOT}" ]]; then
    echo "Building and installing eegdb-codec from ${CODEC_ROOT}"
    (cd "${CODEC_ROOT}" && chmod +x scripts/build-codec-wheel.sh && ./scripts/build-codec-wheel.sh)
    python3 -m pip install -q "${CODEC_ROOT}"/dist/python/eegdb_codec-*.whl
  else
    echo "warning: eegdb_codec is not installed and ${CODEC_ROOT} was not found." >&2
    echo "         Set EEGDB_CODEC_ROOT or install the eegdb-codec wheel before packaging local decode." >&2
  fi
fi

pyinstaller --noconfirm --clean --windowed \
  --name EEGDBClient \
  --paths "${ROOT}" \
  --hidden-import eegdb_client \
  --hidden-import eegdb_codec \
  --hidden-import eegdb_client.cli \
  --hidden-import eegdb_client.ui.main_window \
  --hidden-import eegdb_client.ui.attrs_form \
  --collect-binaries eegdb_codec \
  --collect-all mne \
  --collect-all PyQt6 \
  --collect-all pyedflib \
  app.py

echo "Build output: ${ROOT}/dist/EEGDBClient/"
echo "Run: ${ROOT}/dist/EEGDBClient/EEGDBClient"
