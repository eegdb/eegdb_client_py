# eegdb_client_py

Python TCP client for [EEGDB](https://github.com/eegdb/eegdb): Fluent-design
PyQt6 desktop GUI and CLI for EDF/BDF/FIF/CDT upload and download, plus
notebook-friendly epoch analysis helpers.

## Project layout

```text
eegdb_client_py/
|- app.py                 # GUI entry for local run / PyInstaller
|- requirements.txt
|- eegdb_client/          # library package: UI, CLI, TCP, readers, analysis
`- scripts/               # build scripts and utilities
```

| Path | Description |
|------|-------------|
| `app.py` | Launch Fluent desktop GUI |
| `eegdb_client/cli.py` | Command-line entry for health, upload, list, download |
| `eegdb_client/transport/tcp_client.py` | EEGDB TCP protocol client |
| `eegdb_client/readers/` | File readers for EDF/BDF/FIF/Curry |
| `eegdb_client/analysis/` | Epoch response container and MNE conversion helpers |

## Requirements

- Python 3.10+
- A running EEGDB server ([eegdb](https://github.com/eegdb/eegdb))
- Desktop GUI uses [PyQt6-Fluent-Widgets](https://pypi.org/project/PyQt6-Fluent-Widgets/)
  (GPLv3). Distributing a binary that includes this library requires GPL
  compliance. CLI-only use does not require the GUI dependency at runtime.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Optional local decode

For `--local-decode`, install the native read codec from the sibling
[eegdb-codec](https://github.com/eegdb/eegdb-codec) repo:

```bash
cd ../eegdb-codec
make codec-wheel
pip install dist/python/eegdb_codec-*.whl
```

Alternatively, point `EEGDB_CODEC_LIB` at `libeegdbcodec.so`, `.dylib`, or
`.dll`, then install the Python package from the codec repo.

## Desktop GUI

The GUI is a Fluent side-nav app with Connect, Upload, and Browse pages.

```bash
python app.py
# or
python -m eegdb_client
```

Connect to your EEGDB host, pick a file, set study attributes, then upload or
download. Host, port, and token name are remembered with `QSettings`; the API
token secret is not saved.

When server auth is enabled, fill in both token name and API token.

## CLI

```bash
python -m eegdb_client health
python -m eegdb_client upload recording.edf --lab mylab --paradigm resting
python -m eegdb_client upload recording.cdt --lab mylab
python -m eegdb_client list
python -m eegdb_client download <study_id> -o out.edf
```

Download with local `eegdb-codec` decode:

```bash
python -m eegdb_client download <study_id> \
  --format npz \
  --local-decode \
  --codec lz4 \
  -o subject01.npz
```

`--codec` selects the server-side block codec used to re-encode each batch:
`lz4`, `zstd`, `flac`, `wavpack`, or `best`.

Supported upload formats: `.edf`, `.bdf`, `.fif`, Curry (`.cdt`, `.ceo`,
`.dap`, `.rs3`, `.rs4`).

FLOAT channels are uploaded as-is over TCP. Compression, including `uv0.1`
lossy FLOAT compression, is configured on the EEGDB server.

Common options: `--host`, `--port`, `--token-name`, `--api-token`, `-v`.

## Epoch analysis helper

`EEGDBEpochs` wraps the server epoch API response as a NumPy tensor shaped
`(epochs, channels, samples)`, provides averaging, and can convert to
`mne.EpochsArray`.

```python
from eegdb_client import EEGDBEpochs

epochs = EEGDBEpochs.from_http(
    "http://localhost:8080",
    "STUDY_ID",
    channels=[0, 1],
    event_type="stimulus",
    code="target",
    pre_ms=200,
    post_ms=800,
    reject_artifact=True,
)

average = epochs.average()
mne_epochs = epochs.to_mne()
```

You can also use `EEGDBEpochs.from_server(client, ...)` with any client object
that implements `query_epochs(...)`.

## Authentication

EEGDB TCP uses challenge-response auth; plaintext tokens are never sent on the
wire.

After handshake, the server may send a 32-byte nonce. The client replies with
`MsgAuthProof` using `SHA256(SHA256(secret) || nonce)`.

Clients need both token name (public identifier) and token secret (shown once at
creation).

## Build standalone app

Linux / macOS:

```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
# Output: dist/EEGDBClient/
```

Windows:

```powershell
scripts/build_windows.ps1
```

The Windows installer script is `scripts/eegdb_client.iss`.

## Related

- [EEGDB server](https://github.com/eegdb/eegdb)
- [eegdb-codec](https://github.com/eegdb/eegdb-codec)
- [go-edflib](https://github.com/eegdb/go-edflib)
