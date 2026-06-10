# eegdb_client_py

Python clients for [EEGDB](https://github.com/eegdb/eegdb): an HTTP API demo script and a desktop/CLI uploader for EDF, BDF, and FIF files.

## Components

| Path | Description |
|------|-------------|
| `eegdb_client.py` | HTTP API demo: import EDF, query channels, rebuild EDF from server data |
| `eegdb_uploader/` | PyQt6 GUI + CLI: TCP upload/download, HTTP health check |

## Requirements

- Python 3.10+
- A running EEGDB server ([eegdb](https://github.com/eegdb/eegdb))

### HTTP demo client

```bash
pip install -r requirements.txt
```

### Desktop uploader

```bash
pip install -r eegdb_uploader/requirements.txt
```

## HTTP API demo (`eegdb_client.py`)

```bash
# Upload an EDF and download it back
python3 eegdb_client.py \
  --server http://localhost:8080 \
  --edf recording.edf \
  --study-id demo-study \
  --output rebuilt.edf
```

## Uploader GUI

```bash
export PYTHONPATH="$(pwd)"
python3 -m eegdb_uploader
```

Connect to your EEGDB host (default HTTP `:8080`, TCP `:9090`), pick a file, set study attributes, then upload or download.

## Uploader CLI

```bash
export PYTHONPATH="$(pwd)"

python3 -m eegdb_uploader health
python3 -m eegdb_uploader upload recording.edf --lab mylab --paradigm resting
python3 -m eegdb_uploader list
python3 -m eegdb_uploader download <study_id> -o out.edf
```

Options: `--host`, `--tcp-port`, `--http-port`, `-v`.

## Build standalone app (Linux)

```bash
cd eegdb_uploader
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
# Output: eegdb_uploader/dist/EEGDBUploader/
```

Windows builds use `scripts/build_windows.ps1` and Inno Setup (`scripts/eegdb_uploader.iss`).

## Related

- [EEGDB server](https://github.com/eegdb/eegdb)
- [go-edflib](https://github.com/eegdb/go-edflib)
