"""Command-line interface for headless upload/download and e2e testing."""

from __future__ import annotations

import argparse
import os
import sys

from .download.fetcher import download_study
from .models import StudyAttrs
from .readers.edf_reader import read_edf
from .readers.fif_reader import read_fif
from .transport.http_client import EEGDBHTTPClient
from .transport.tcp_client import EEGDBTCPClient
from .upload.pipeline import upload_source_file


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

    with EEGDBTCPClient(args.host, args.tcp_port) as client:
        study_id = upload_source_file(
            client,
            source,
            attrs,
            batch_seconds=args.batch_seconds,
            on_progress=progress if args.verbose else None,
        )
    print(study_id)


def cmd_list(args: argparse.Namespace) -> None:
    with EEGDBTCPClient(args.host, args.tcp_port) as client:
        studies = client.list_studies()
    for s in studies:
        print(
            f"{s.get('study_id')}\t{s.get('name')}\t"
            f"ch={s.get('num_channels')}\tn={s.get('num_samples')}"
        )


def cmd_download(args: argparse.Namespace) -> None:
    def progress(msg: str, frac: float) -> None:
        print(f"[{frac * 100:5.1f}%] {msg}")

    with EEGDBTCPClient(args.host, args.tcp_port) as client:
        path = download_study(
            client,
            args.study_id,
            args.output,
            fmt=args.format,
            on_progress=progress if args.verbose else None,
        )
    print(path)


def cmd_health(args: argparse.Namespace) -> None:
    base = f"http://{args.host}:{args.http_port}"
    data = EEGDBHTTPClient(base).health()
    print(data)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eegdb-uploader")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=9090)
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="HTTP health check")
    p_health.set_defaults(func=cmd_health)

    p_upload = sub.add_parser("upload", help="Upload EDF/BDF/FIF via TCP")
    p_upload.add_argument("file")
    p_upload.add_argument("--lab", default="")
    p_upload.add_argument("--paradigm", default="")
    p_upload.add_argument("--device", default="")
    p_upload.add_argument("--batch-seconds", type=float, default=1.0)
    p_upload.set_defaults(func=cmd_upload)

    p_list = sub.add_parser("list", help="List studies via TCP")
    p_list.set_defaults(func=cmd_list)

    p_dl = sub.add_parser("download", help="Download study via TCP")
    p_dl.add_argument("study_id")
    p_dl.add_argument("-o", "--output", required=True)
    p_dl.add_argument("-f", "--format", default="edf", choices=["edf", "bdf", "fif"])
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
