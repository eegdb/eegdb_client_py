#!/usr/bin/env python3
"""Benchmark CDT upload with different server import_block_codec values."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eegdb_client.models import StudyAttrs
from eegdb_client.readers import load_source_file
from eegdb_client.transport.tcp_client import EEGDBTCPClient
from eegdb_client.upload.pipeline import upload_source_file

EEGDB = Path("/home/qiushui/db/EEGDB")
CDT = "/mnt/d/EEGData/Control_Sub726/Control_Sub726/Experiment1_ABT/ABT_EEG/Sub726_ABT_EEG.cdt"
BASE = Path("/tmp/eegdb_codec_bench")
CODECS = ["lz4", "zstd", "flac", "wavpack", "best"]
BPS = {0x01: 2, 0x02: 4, 0x03: 4, 0x04: 8}


def fmt(n: float) -> str:
    for u in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024 or u == "GiB":
            return f"{n:.2f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.2f} GiB"


def yaml_for(codec: str, lossy: str) -> str:
    return f"""server:
  http_port: 18080
  tcp_port: 18081
  read_timeout: 30s
  write_timeout: 600s

storage:
  data_dir: {BASE / "data"}
  memtable_size: 536870912
  max_block_duration_ms: 60000
  import_max_block_duration_ms: 10000
  segment_duration_sec: 1.0
  flush_interval: 0
  ring_buffer_window_ms: 0
  compaction_interval: 0
  flush_block_codec: lz4
  import_block_codec: {codec}
  import_lossy_codec: {lossy}
  compact_block_codec: zstd

gc:
  interval: 0

auth:
  enabled: false

cluster:
  snowflake_node_id: 1

logging:
  level: info
  format: text
  perf_enabled: true
  slow_threshold_ms: 100
"""


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def start_server(codec: str, lossy: str) -> subprocess.Popen:
    BASE.mkdir(parents=True, exist_ok=True)
    if (BASE / "data").exists():
        import shutil

        shutil.rmtree(BASE / "data")
    (BASE / "data").mkdir()
    (BASE / "eegdb.yaml").write_text(yaml_for(codec, lossy))
    log = open(BASE / f"server_{codec}_{lossy}.log", "w")
    proc = subprocess.Popen(
        [str(EEGDB / "bin/eegdb"), "-config", str(BASE / "eegdb.yaml"), "-server", "-server-tcp"],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early for codec={codec} lossy={lossy}")
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"server health timeout for codec={codec} lossy={lossy}")


def sst_bytes(study_id: str) -> tuple[int, int]:
    sst_dir = BASE / "data" / "sstables"
    total = 0
    n = 0
    for p in sst_dir.glob(f"{study_id}_*.edb"):
        total += p.stat().st_size
        n += 1
    single = sst_dir / f"{study_id}.edb"
    if single.is_file():
        total += single.stat().st_size
        n += 1
    return total, n


def wait_stable(study_id: str, timeout_s: int = 600) -> tuple[int, int]:
    deadline = time.time() + timeout_s
    last = -1
    stable = 0
    while time.time() < deadline:
        total, n = sst_bytes(study_id)
        if total > 0 and total == last:
            stable += 1
            if stable >= 3:
                return total, n
        else:
            stable = 0
            last = total
        time.sleep(2)
    return sst_bytes(study_id)


def flush_ms_from_log(study_id: str) -> float | None:
    log = (BASE / "server.log").read_text() if (BASE / "server.log").exists() else ""
    # scan all server logs for this study
    for p in BASE.glob("server_*.log"):
        log += p.read_text()
    import re

    m = re.search(rf"flush_memtable duration_ms=(\d+) study_id={study_id}", log)
    return int(m.group(1)) / 1000 if m else None


def main() -> None:
    # Server-side lossy: none | uv1 | uv0.1 | uv0.01 | uv0.001 | dwt | dct
    lossy = sys.argv[1] if len(sys.argv) > 1 else "none"
    print(f"Loading CDT (server import_lossy_codec={lossy})...", flush=True)
    source = load_source_file(CDT)
    raw = sum(
        len(source.channel_data[ch.channel_id]) * BPS[ch.data_type]
        for ch in source.channels
    )
    print(f"raw payload: {fmt(raw)}", flush=True)

    results = []
    proc = None
    try:
        for codec in CODECS:
            print(f"\n=== codec={codec} lossy={lossy} ===", flush=True)
            stop_server(proc)
            proc = start_server(codec, lossy)
            t0 = time.time()
            attrs = StudyAttrs(lab="codec_bench", paradigm=f"cdt-{lossy}-{codec}", device_type="bench")
            with EEGDBTCPClient("127.0.0.1", 18081, client_name=f"codec-{codec}") as client:
                study_id = upload_source_file(client, source, attrs, batch_seconds=10.0)
            upload_s = time.time() - t0
            sst, n_files = wait_stable(study_id)
            flush_s = flush_ms_from_log(study_id)
            row = {
                "codec": codec,
                "lossy": lossy,
                "study_id": study_id,
                "raw_payload_bytes": raw,
                "sstable_bytes": sst,
                "ratio_vs_raw": sst / raw if raw else None,
                "num_sstables": n_files,
                "upload_seconds": round(upload_s, 2),
                "flush_seconds": flush_s,
            }
            results.append(row)
            print(
                f"  SSTable={fmt(sst)} ({n_files} files) vs_raw={row['ratio_vs_raw']:.4f} "
                f"upload={upload_s:.1f}s flush={flush_s or '?'}s",
                flush=True,
            )
    finally:
        stop_server(proc)

    out = BASE / f"results_{lossy}.json"
    out.write_text(json.dumps(results, indent=2))
    print("\n=== Summary ===")
    print(f"{'codec':8} {'sst':>12} {'vs_raw':>8} {'files':>5} {'upload':>8} {'flush':>8}")
    for r in results:
        print(
            f"{r['codec']:8} {fmt(r['sstable_bytes']):>12} {r['ratio_vs_raw']:8.4f} "
            f"{r['num_sstables']:5} {r['upload_seconds']:7.1f}s "
            f"{(r['flush_seconds'] or 0):7.1f}s"
        )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
