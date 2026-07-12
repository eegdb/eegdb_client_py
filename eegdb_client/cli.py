"""Command-line interface for headless upload/download and e2e testing."""

from __future__ import annotations

import argparse

from .download.fetcher import download_study
from .models import StudyAttrs
from .readers import load_source_file
from .transport.tcp_client import EEGDBTCPClient
from .upload.pipeline import upload_source_file


def _tcp_client(args: argparse.Namespace) -> EEGDBTCPClient:
    return EEGDBTCPClient(
        args.host,
        args.port,
        token_name=args.token_name,
        api_token=args.api_token,
    )


def cmd_upload(args: argparse.Namespace) -> None:
    try:
        source = load_source_file(args.file)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
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
            on_progress=progress if args.verbose else None,
            local_decode=args.local_decode,
            block_codec=args.codec,
        )
    print(path)


def cmd_health(args: argparse.Namespace) -> None:
    with _tcp_client(args) as client:
        studies = client.list_studies()
    print(f"ok  host={args.host}  port={args.port}  studies={len(studies)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eegdb-client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--token-name", default="", help="API token name (when server auth enabled)")
    parser.add_argument("--api-token", default="", help="API token secret (when server auth enabled)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="TCP connection check")
    p_health.set_defaults(func=cmd_health)

    p_upload = sub.add_parser("upload", help="Upload EDF/BDF/FIF/CDT via TCP")
    p_upload.add_argument("file")
    p_upload.add_argument("--lab", default="")
    p_upload.add_argument("--paradigm", default="")
    p_upload.add_argument("--device", default="")
    p_upload.add_argument("--batch-seconds", type=float, default=10.0)
    p_upload.set_defaults(func=cmd_upload)

    p_list = sub.add_parser("list", help="List studies via TCP")
    p_list.set_defaults(func=cmd_list)

    p_dl = sub.add_parser("download", help="Download study via TCP")
    p_dl.add_argument("study_id")
    p_dl.add_argument("-o", "--output", required=True)
    p_dl.add_argument(
        "-f",
        "--format",
        default="edf",
        choices=["edf", "bdf", "fif", "npz"],
        help="output format (default: edf)",
    )
    p_dl.add_argument(
        "--local-decode",
        action="store_true",
        help="download compressed batches and decode locally with eegdb-codec",
    )
    p_dl.add_argument(
        "--codec",
        default="best",
        choices=["lz4", "zstd", "flac", "wavpack", "best"],
        help="block codec for --local-decode (server re-encodes the batch; default: best)",
    )
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
