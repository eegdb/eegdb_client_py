#!/usr/bin/env bash
# Build PyInstaller onedir bundle on Linux/macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PYTHON_BIN}" -m pip install -q pyinstaller -r requirements.txt

CODEC_ROOT="${EEGDB_CODEC_ROOT:-${ROOT}/../eegdb-codec}"
if ! "${PYTHON_BIN}" -c "import eegdb_codec" >/dev/null 2>&1; then
  if [[ -d "${CODEC_ROOT}" ]]; then
    echo "Building and installing eegdb-codec from ${CODEC_ROOT}"
    (cd "${CODEC_ROOT}" && chmod +x scripts/build-codec-wheel.sh && ./scripts/build-codec-wheel.sh)
    "${PYTHON_BIN}" -m pip install -q "${CODEC_ROOT}"/dist/python/eegdb_codec-*.whl
  else
    echo "warning: eegdb_codec is not installed and ${CODEC_ROOT} was not found." >&2
    echo "         Set EEGDB_CODEC_ROOT or install the eegdb-codec wheel before packaging local decode." >&2
  fi
fi

"${PYTHON_BIN}" -m PyInstaller --noconfirm --clean EEGDBClient.spec

echo "Build output: ${ROOT}/dist/EEGDBClient/"
echo "Run: ${ROOT}/dist/EEGDBClient/EEGDBClient"
