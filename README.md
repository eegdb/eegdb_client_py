# eegdb_client_py

Python clients for [EEGDB](https://github.com/eegdb/eegdb): a desktop GUI/CLI client and an HTTP API demo script.

## Project layout

```
eegdb_client_py/
├── app.py                 # GUI entry (Run / PyInstaller)
├── requirements.txt       # all Python dependencies
├── eegdb_client/          # library package (UI, CLI, transport, readers)
├── examples/
│   └── http_api_demo.py   # standalone HTTP REST API demo
└── scripts/               # build scripts and utilities
```

| Path | Description |
|------|-------------|
| `app.py` | Launch PyQt6 desktop GUI |
| `eegdb_client/` | Package: GUI, CLI, TCP upload/download |
| `examples/http_api_demo.py` | HTTP API demo: import EDF, query channels, rebuild EDF |

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

## CLI

```bash
python -m eegdb_client health
python -m eegdb_client upload recording.edf --lab mylab --paradigm resting
python -m eegdb_client list
python -m eegdb_client download <study_id> -o out.edf
```

Options: `--host`, `--port`, `-v`.

## HTTP API demo

```bash
python examples/http_api_demo.py \
  --server http://localhost:8080 \
  --edf recording.edf \
  --study-name demo-study \
  --output rebuilt.edf
```

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
