# eegdb_client_py

Python TCP client for [EEGDB](https://github.com/eegdb/eegdb): PyQt6 desktop GUI and CLI for EDF/BDF/FIF/CDT upload and download.

## Project layout

```
eegdb_client_py/
├── app.py                 # GUI entry (Run / PyInstaller)
├── requirements.txt
├── eegdb_client/          # library package (UI, CLI, TCP, readers)
└── scripts/               # build scripts and utilities
```

| Path | Description |
|------|-------------|
| `app.py` | Launch PyQt6 desktop GUI |
| `eegdb_client/` | Package: GUI, CLI, TCP upload/download |

## Requirements

- Python 3.10+
- A running EEGDB server ([eegdb](https://github.com/eegdb/eegdb))

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Desktop GUI

```bash
python app.py
# or
python -m eegdb_client
```

Connect to your EEGDB host (default TCP port `8081`), pick a file, set study attributes, then upload or download.

When the server has `auth.enabled: true`, fill in **Token name** and **API token** (from `eegdb -auth-token-create`).

## CLI

```bash
python -m eegdb_client health
python -m eegdb_client upload recording.edf --lab mylab --paradigm resting
python -m eegdb_client upload recording.cdt --lab mylab
python -m eegdb_client list
python -m eegdb_client download <study_id> -o out.edf
```

Supported upload formats: `.edf`, `.bdf`, `.fif`, Curry (`.cdt` / `.ceo` / `.dap` / `.rs3` / `.rs4`).

FLOAT channels are uploaded as-is over TCP. Compression (including µV-step lossy for FLOAT)
is configured on the EEGDB server, e.g. `storage.import_lossy_codec: uv0.1`.

Options: `--host`, `--port`, `--token-name`, `--api-token`, `-v`.

With auth enabled:

```bash
python -m eegdb_client upload recording.edf \
  --token-name uploader --api-token eegdb_...
```

## Authentication

EEGDB TCP uses challenge-response auth; **plaintext tokens are never sent on the wire**.

After handshake, the server may send a 32-byte nonce; the client replies with `MsgAuthProof` using `SHA256(SHA256(secret) || nonce)`.

Clients need both **token name** (public identifier) and **token secret** (shown once at creation).

## Build standalone app

**Linux / macOS:**

```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
# Output: dist/EEGDBClient/
```

**Windows:** run `scripts/build_windows.ps1`; optional Inno Setup installer via `scripts/eegdb_client.iss`.

## Related

- [EEGDB server](https://github.com/eegdb/eegdb)
- [go-edflib](https://github.com/eegdb/go-edflib)
