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
| `eegdb_client/transport/tcp_client.py` | EEGDB EDB/Protobuf v1 TCP client |
| `eegdb_client/protocol/v1/protocol_pb2.py` | Generated TCP schema binding; do not edit by hand |
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
download. Host, port, database, and username are remembered with `QSettings`;
the account password is not saved.

When server auth is enabled, fill in the database account username and password.
The client logs in over HTTPS, then uses the short-lived token on the TLS TCP connection.

## CLI

```bash
python -m eegdb_client health
python -m eegdb_client --username uploader --password 'ACCOUNT_PASSWORD' upload recording.edf --lab mylab --paradigm resting
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

Common options: `--host`, `--port`, `--database`, `--http-url`, `--username`,
`--password`, and `-v`. Use `--insecure-skip-tls-verify` only with a local
self-signed development certificate.

## Logs

Both the GUI and CLI write rotating logs to the platform user log directory.
On Linux the default is typically:

```text
~/.local/state/EEGDBClient/log/eegdb-client.log
```

Use `-v` for debug-level CLI and file logs, or `--log-file PATH` to select a
different CLI log file. Logs rotate at 5 MiB and retain three backups. Account
passwords and access tokens are never logged.

## Epoch analysis helper

`EEGDBEpochs` wraps the server epoch API response as a NumPy tensor shaped
`(epochs, channels, samples)`, provides averaging, and can convert to
`mne.EpochsArray`.

```python
from eegdb_client import EEGDBEpochs

epochs = EEGDBEpochs.from_http(
    "https://localhost:8080",
    "STUDY_ID",
    database="default",
    username="reader",
    password="ACCOUNT_PASSWORD",
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

## HTTP query helper

Uploads and downloads use TCP. For analysis and admin reads, use
`EEGDBQueryClient` against the EEGDB HTTP API:

```python
from eegdb_client import EEGDBQueryClient

client = EEGDBQueryClient(
    "https://localhost:8080",
    database="default",
    username="reader",
    password="ACCOUNT_PASSWORD",
)

studies = client.list_studies()
study = client.get_study("STUDY_ID")
events = client.query_events("STUDY_ID", event_type="stimulus", code="target")
quality = client.quality_scores("STUDY_ID", channels=[0, 1], range_samples=1024)
psd = client.query_psd("STUDY_ID", channels=[0, 1], idx_start=0, idx_end=4096)

job = client.submit_job(
    "quality_scan",
    study_id="STUDY_ID",
    detector_options={"window_samples": 512},
)
status = client.get_job(job["job_id"])
```

## Authentication

EEGDB uses database accounts and TLS. The client posts the username and password
to `https://HOST:HTTP_PORT/api/v1/databases/{database}/auth/login`, receives a
short-lived access token, then sends it as `AuthRequest.access_token` on the TLS
TCP connection. Tokens expire, stop working immediately when the account is
disabled, and cannot be reused with another database.

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
