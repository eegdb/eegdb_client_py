#!/usr/bin/env bash
# Build a signed PyInstaller .app bundle and zip archive on macOS.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_macos.sh must run on macOS" >&2
  exit 1
fi

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
    echo "         Set EEGDB_CODEC_ROOT or install the codec wheel before packaging local decode." >&2
  fi
fi

"${PYTHON_BIN}" -m PyInstaller --noconfirm --clean EEGDBClient.spec

APP_PATH="${ROOT}/dist/EEGDBClient.app"
APP_EXECUTABLE="${APP_PATH}/Contents/MacOS/EEGDBClient"
if [[ ! -x "${APP_EXECUTABLE}" ]]; then
  echo "PyInstaller app bundle not found at ${APP_PATH}" >&2
  exit 1
fi

# Use MACOS_SIGN_IDENTITY="Developer ID Application: ..." for a distributable
# Developer ID signature. The default ad-hoc signature makes local/CI bundles
# structurally valid but does not replace Apple notarization.
SIGN_IDENTITY="${MACOS_SIGN_IDENTITY:--}"
codesign --force --deep --sign "${SIGN_IDENTITY}" "${APP_PATH}"
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

ARCH="$(uname -m)"
ARCHIVE="${ROOT}/dist/EEGDBClient-macos-${ARCH}.zip"
rm -f "${ARCHIVE}"
ditto -c -k --sequesterRsrc --keepParent "${APP_PATH}" "${ARCHIVE}"

echo "App bundle: ${APP_PATH}"
echo "Release archive: ${ARCHIVE}"
