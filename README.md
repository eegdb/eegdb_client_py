# eegdb_client_py

Python TCP client for [EEGDB](https://github.com/eegdb/eegdb): Fluent-design PyQt6 desktop GUI and CLI for EDF/BDF/FIF/CDT upload and download.

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
| `app.py` | Launch Fluent desktop GUI |
| `eegdb_client/` | Package: GUI, CLI, TCP upload/download |

## Requirements

- Python 3.10+
- A running EEGDB server ([eegdb](https://github.com/eegdb/eegdb))
- Desktop GUI uses [PyQt6-Fluent-Widgets](https://pypi.org/project/PyQt6-Fluent-Widgets/) (**GPLv3**). Distributing a binary that includes this library requires GPL compliance. CLI-only use of this package does not require that GUI dependency at runtime.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Optional: local decode (`eegdb-codec`)

For `--local-decode`, install the native read codec from the sibling
[eegdb-codec](https://github.com/eegdb/eegdb-codec) repo (current architecture:
`pkg/wire` + `pkg/codec` C ABI):

```bash
cd ../eegdb-codec
make codec-wheel
pip install dist/python/eegdb_codec-*.whl
```

Or point `EEGDB_CODEC_LIB` at `libeegdbcodec.so` / `.dylib` / `.dll` and install
the Python package (`pip install -e ../eegdb-codec/python`).

## Desktop GUI

Fluent side-nav app with **Connect**, **Upload**, and **Browse** pages (light/dark theme toggle in the nav footer).

```bash
python app.py
# or
python -m eegdb_client
```

Connect to your EEGDB host (default TCP port `8081`), pick a file, set study attributes, then upload or download. Host / port / token name are remembered via `QSettings`; the API token secret is not saved.

When the server has `auth.enabled: true`, fill in **Token name** and **API token** (from `eegdb -auth-token-create`).

## CLI

```bash
python -m eegdb_client health
python -m eegdb_client upload recording.edf --lab mylab --paradigm resting
python -m eegdb_client upload recording.cdt --lab mylab
python -m eegdb_client list
python -m eegdb_client download <study_id> -o out.edf
```

Download with **local** eegdb-codec decode (TCP `ReadCompressedBatch` + native decode):

```bash
python -m eegdb_client download <study_id> \
  --format npz \
  --local-decode \
  --codec lz4 \
  -o subject01.npz
```

`--codec` selects the server-side block codec used to re-encode each batch
(`lz4|zstd|flac|wavpack|best`). The response carries a wire `algo` byte; the
client calls `eegdb_codec.EEGDBCodec.decode(data_type, algo, …)`.

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
- [eegdb-codec](https://github.com/eegdb/eegdb-codec) — wire constants + native read codec
- [go-edflib](https://github.com/eegdb/go-edflib)
