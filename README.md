# eegdb_client_py

Python clients for [EEGDB](https://github.com/eegdb/eegdb): a desktop GUI/CLI client plus HTTP and PyTorch examples.

## Project layout

```text
eegdb_client_py/
|- app.py                        # GUI entry (Run / PyInstaller)
|- requirements.txt              # all Python dependencies
|- eegdb_client/                 # library package (UI, CLI, transport, readers)
|- examples/
|  |- http_api_demo.py           # standalone HTTP REST API demo
|  `- pytorch_chunk_dataset.py   # PyTorch sliding-window dataset demo
`- scripts/                      # build scripts and utilities
```

| Path | Description |
|------|-------------|
| `app.py` | Launch PyQt6 desktop GUI |
| `eegdb_client/` | Package: GUI, CLI, TCP upload/download |
| `examples/http_api_demo.py` | HTTP API demo: import EDF, query channels, rebuild EDF |
| `examples/pytorch_chunk_dataset.py` | PyTorch sliding-window dataset example |

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
python -m eegdb_client upload recording.vhdr --lab mylab --paradigm oddball
python -m eegdb_client upload recording.set --lab mylab --paradigm oddball
python -m eegdb_client import-bids /data/bids --subject sub-01 --task oddball
python -m eegdb_client import-bids /data/bids --force
python -m eegdb_client list
python -m eegdb_client download <study_id> -o out.edf
python -m eegdb_client download <study_id> -o out.npz -f npz --local-decode --codec lz4
python -m eegdb_client export-bids <study_id> /data/exported-bids --subject sub-01 --task oddball
```

Upload supports EDF/BDF, FIF, BrainVision `.vhdr`, and EEGLAB `.set` files. BrainVision and EEGLAB markers are uploaded through the standard EEGDB event schema.
BIDS import discovers EEG files, reads `*_events.tsv`, sidecar JSON, and `participants.tsv`, then uploads each matching run as an EEGDB study.
It writes `.eegdb_import_state.json` in the dataset root by default so interrupted imports can resume.
BIDS export downloads a study through TCP and writes raw EEG, sidecar JSON, `channels.tsv`, `events.tsv`, and `participants.tsv`.

Options: `--host`, `--tcp-port`, `--http-port`, `--token-name`, `--api-token`, `-v`.

For local compressed decode, install the standalone `eegdb-codec` wheel first or let the packaging scripts build it from a sibling `../eegdb-codec` checkout.

With auth enabled:

```bash
python -m eegdb_client upload recording.edf \
  --token-name uploader --api-token eegdb_...
```

## HTTP API demo

```bash
python examples/http_api_demo.py \
  --server http://localhost:8080 \
  --token-name uploader --api-token eegdb_... \
  --edf recording.edf \
  --study-name demo-study \
  --output rebuilt.edf
```

## PyTorch example

```bash
python examples/pytorch_chunk_dataset.py \
  --server http://localhost:8080 \
  --study-id STUDY_ID \
  --channel 0 \
  --window 512 \
  --stride 256
```

Install `torch` separately when you need the dataset example.

## Authentication

EEGDB uses challenge-response auth; **plaintext tokens are never sent on the wire**.

- **TCP**: after handshake, server sends a 32-byte nonce; client replies with `MsgAuthProof` using `SHA256(SHA256(secret) || nonce)`.
- **HTTP**: `GET /api/v1/auth/nonce`, then headers `X-EEGDB-Nonce` and `Authorization: EEGDB-Proof <name>:<proof_hex>`.

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
