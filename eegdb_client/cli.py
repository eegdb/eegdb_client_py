"""Command-line interface for headless upload/download and e2e testing."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .download.fetcher import download_study
from .models import StudyAttrs
from .readers.edf_reader import read_edf
from .readers.fif_reader import read_fif
from .transport.tcp_client import EEGDBTCPClient
from .upload.pipeline import upload_source_file


def _tcp_client(args: argparse.Namespace) -> EEGDBTCPClient:
    return EEGDBTCPClient(
        args.host,
        args.tcp_port,
        token_name=args.token_name,
        api_token=args.api_token,
    )


def _load_source(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fif":
        return read_fif(path)
    if ext in (".edf", ".bdf"):
        return read_edf(path)
    raise SystemExit(f"unsupported file type: {ext}")


def cmd_upload(args: argparse.Namespace) -> None:
    source = _load_source(args.file)
    attrs = StudyAttrs(
        lab=args.lab or "",
        paradigm=args.paradigm or "",
        device_type=args.device or "",
    )

    def progress(msg: str, frac: float) -> None:
        print(f"[{frac * 100:5.1f}%] {msg}")

    with _tcp_client(args) as client:
        study_id = upload_source_file(
            client,
            source,
            attrs,
            batch_seconds=args.batch_seconds,
            on_progress=progress if args.verbose else None,
        )
    print(study_id)


def cmd_list(args: argparse.Namespace) -> None:
    with _tcp_client(args) as client:
        studies = client.list_studies()
    for s in studies:
        print(
            f"{s.get('study_id')}\t{s.get('name')}\t"
            f"ch={s.get('num_channels')}\tn={s.get('num_samples')}"
        )


def cmd_download(args: argparse.Namespace) -> None:
    def progress(msg: str, frac: float) -> None:
        print(f"[{frac * 100:5.1f}%] {msg}")

    with _tcp_client(args) as client:
        path = download_study(
            client,
            args.study_id,
            args.output,
            fmt=args.format,
            local_decode=args.local_decode,
            codec=args.codec,
            on_progress=progress if args.verbose else None,
        )
    print(path)


def cmd_health(args: argparse.Namespace) -> None:
    with _tcp_client(args) as client:
        data = client.health()
    print(json.dumps(data, ensure_ascii=False))


def cmd_stats(args: argparse.Namespace) -> None:
    with _tcp_client(args) as client:
        data = client.stats()
    print(json.dumps(data, ensure_ascii=False))


def cmd_delete(args: argparse.Namespace) -> None:
    with _tcp_client(args) as client:
        data = client.delete_study(args.study_id)
    print(json.dumps(data, ensure_ascii=False))


def cmd_query_channel(args: argparse.Namespace) -> None:
    reference = None
    if args.reference:
        reference = [int(part.strip()) for part in args.reference.split(",") if part.strip()]
    with _tcp_client(args) as client:
        data = client.query_channel(
            args.study_id,
            args.channel_id,
            idx_start=args.idx_start,
            idx_end=args.idx_end,
            start_us=args.start_us,
            end_us=args.end_us,
            physical=args.physical,
            downsample=args.downsample,
            method=args.method,
            reference=reference,
        )
    print(json.dumps(data, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eegdb-client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=8081)
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--token-name", default="", help="API token name (when server auth enabled)")
    parser.add_argument("--api-token", default="", help="API token secret (when server auth enabled)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="TCP health check")
    p_health.set_defaults(func=cmd_health)

    p_stats = sub.add_parser("stats", help="Show TCP + DB stats")
    p_stats.set_defaults(func=cmd_stats)

    p_upload = sub.add_parser("upload", help="Upload EDF/BDF/FIF via TCP")
    p_upload.add_argument("file")
    p_upload.add_argument("--lab", default="")
    p_upload.add_argument("--paradigm", default="")
    p_upload.add_argument("--device", default="")
    p_upload.add_argument("--batch-seconds", type=float, default=1.0)
    p_upload.set_defaults(func=cmd_upload)

    p_list = sub.add_parser("list", help="List studies via TCP")
    p_list.set_defaults(func=cmd_list)

    p_delete = sub.add_parser("delete", help="Delete study via TCP")
    p_delete.add_argument("study_id")
    p_delete.set_defaults(func=cmd_delete)

    p_dl = sub.add_parser("download", help="Download study via TCP")
    p_dl.add_argument("study_id")
    p_dl.add_argument("-o", "--output", required=True)
    p_dl.add_argument("-f", "--format", default="edf", choices=["edf", "bdf", "fif", "npz"])
    p_dl.add_argument(
        "--local-decode",
        action="store_true",
        help="download compressed TCP batches and decode locally with the Go codec shared library",
    )
    p_dl.add_argument("--codec", default="lz4", choices=["lz4", "zstd", "flac", "wavpack", "best"])
    p_dl.set_defaults(func=cmd_download)

    p_query = sub.add_parser("query-channel", help="Query one channel via TCP")
    p_query.add_argument("study_id")
    p_query.add_argument("channel_id", type=int)
    p_query.add_argument("--idx-start", type=int)
    p_query.add_argument("--idx-end", type=int)
    p_query.add_argument("--start-us", type=int)
    p_query.add_argument("--end-us", type=int)
    p_query.add_argument("--physical", action="store_true")
    p_query.add_argument("--downsample", type=int)
    p_query.add_argument("--method", default="")
    p_query.add_argument("--reference", default="", help="comma-separated reference channel IDs")
    p_query.set_defaults(func=cmd_query_channel)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
