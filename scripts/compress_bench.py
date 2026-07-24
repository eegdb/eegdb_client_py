#!/usr/bin/env python3
"""Upload files via TCP and report EEGDB compression ratios."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eegdb_client.models import DT_FLOAT32, DT_FLOAT64, DT_INT16, DT_INT24, DT_INT64, StudyAttrs
from eegdb_client.readers import load_source_file
from eegdb_client.transport.tcp_client import EEGDBTCPClient
from eegdb_client.upload.pipeline import upload_source_file

BYTES_PER_SAMPLE = {
    DT_INT16: 2,
    DT_INT24: 4,
    DT_FLOAT32: 4,
    DT_FLOAT64: 8,
    DT_INT64: 8,
}


def fmt_bytes(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024 or unit == "GiB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.2f} GiB"


def raw_payload_bytes(source) -> int:
    total = 0
    for ch in source.channels:
        arr = source.channel_data[ch.channel_id]
        bps = BYTES_PER_SAMPLE[ch.data_type]
        total += len(arr) * bps
    return total


def sstable_bytes_on_disk(study_id: str, sst_dir: str) -> tuple[int, int]:
    root = Path(sst_dir)
    total = 0
    n = 0
    for p in root.glob(f"{study_id}_*.edb"):
        total += p.stat().st_size
        n += 1
    # also single-file import style {study_id}.edb
    single = root / f"{study_id}.edb"
    if single.is_file():
        total += single.stat().st_size
        n += 1
    return total, n


def wait_sstable_stable(study_id: str, sst_dir: str, timeout_s: int = 180) -> tuple[int, int]:
    deadline = time.time() + timeout_s
    last_total = -1
    stable_ticks = 0
    while time.time() < deadline:
        total, n = sstable_bytes_on_disk(study_id, sst_dir)
        if total > 0 and total == last_total:
            stable_ticks += 1
            if stable_ticks >= 3:
                return total, n
        else:
            stable_ticks = 0
            last_total = total
        time.sleep(1)
    return sstable_bytes_on_disk(study_id, sst_dir)


def analyze(path: str, host: str, port: int, sst_dir: str) -> dict:
    path = os.path.abspath(path)
    source_size = os.path.getsize(path)
    t0 = time.time()
    print(f"\n=== Loading {path} ===", flush=True)
    source = load_source_file(path)
    load_s = time.time() - t0
    raw_bytes = raw_payload_bytes(source)
    n_ch = len(source.channels)
    n_samp = len(next(iter(source.channel_data.values()))) if source.channel_data else 0
    dtype = source.channels[0].data_type if source.channels else None
    print(
        f"loaded in {load_s:.1f}s  format={source.format}  channels={n_ch}  "
        f"samples/ch={n_samp}  dtype=0x{dtype:02x}  raw={fmt_bytes(raw_bytes)}  "
        f"file={fmt_bytes(source_size)}",
        flush=True,
    )

    attrs = StudyAttrs(lab="compress_test", paradigm=source.format, device_type="bench")
    t1 = time.time()
    with EEGDBTCPClient(host, port, client_name="compress-bench") as client:
        last_pct = [-1]

        def progress(msg: str, frac: float) -> None:
            pct = int(frac * 100)
            if pct != last_pct[0] and (pct % 5 == 0 or pct in (5, 100)):
                last_pct[0] = pct
                print(f"  [{pct:3d}%] {msg}", flush=True)

        study_id = upload_source_file(
            client, source, attrs, batch_seconds=10.0, on_progress=progress
        )
        study = client.get_study(study_id)
    upload_s = time.time() - t1

    sst, n_sst = wait_sstable_stable(study_id, sst_dir)
    result = {
        "path": path,
        "name": source.name,
        "format": source.format,
        "study_id": study_id,
        "channels": n_ch,
        "samples_per_channel": n_samp,
        "data_type": dtype,
        "source_file_bytes": source_size,
        "raw_payload_bytes": raw_bytes,
        "sstable_bytes": sst,
        "ratio_vs_raw": (sst / raw_bytes) if raw_bytes else None,
        "ratio_vs_file": (sst / source_size) if source_size else None,
        "load_seconds": load_s,
        "upload_seconds": upload_s,
        "num_sstables": n_sst,
        "study_num_samples": study.get("num_samples"),
    }
    print(
        f"study={study_id}  sstables={n_sst}  "
        f"SSTable={fmt_bytes(sst)}  vs_raw={result['ratio_vs_raw']:.4f}  "
        f"vs_file={result['ratio_vs_file']:.4f}  upload={upload_s:.1f}s",
        flush=True,
    )
    return result


def main() -> None:
    host = os.environ.get("EEGDB_HOST", "127.0.0.1")
    port = int(os.environ.get("EEGDB_PORT", "18081"))
    sst_dir = os.environ.get("EEGDB_SST_DIR", "/tmp/eegdb_compress_test/data/sstables")
    paths = sys.argv[1:]
    if not paths:
        raise SystemExit("usage: compress_bench.py FILE [FILE...]")
    results = [analyze(p, host, port, sst_dir) for p in paths]
    out = Path("/tmp/eegdb_compress_test/results.json")
    out.write_text(json.dumps(results, indent=2))
    print("\n=== Summary ===")
    print(f"{'file':40} {'format':6} {'src':>10} {'raw':>10} {'sst':>10} {'vs_raw':>8} {'vs_file':>8}")
    for r in results:
        print(
            f"{Path(r['path']).name:40} {r['format']:6} "
            f"{fmt_bytes(r['source_file_bytes']):>10} {fmt_bytes(r['raw_payload_bytes']):>10} "
            f"{fmt_bytes(r['sstable_bytes']):>10} {r['ratio_vs_raw']:8.4f} {r['ratio_vs_file']:8.4f}"
        )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
