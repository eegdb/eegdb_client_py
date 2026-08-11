"""Command-line interface for headless upload/download and e2e testing."""

from __future__ import annotations

import argparse
import logging

from .download.fetcher import download_study
from .logging_config import configure_logging, install_exception_hook
from .models import StudyAttrs
from .readers import load_source_file
from .transport.tcp_client import EEGDBTCPClient
from .upload.pipeline import upload_source_file

logger = logging.getLogger(__package__)


def _tcp_client(args: argparse.Namespace) -> EEGDBTCPClient:
    return EEGDBTCPClient(
        args.host,
        args.port,
        database=args.database,
        username=args.username,
        password=args.password,
        http_url=args.http_url,
        tls_verify=not args.insecure_skip_tls_verify,
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
    parser.add_argument("--database", default="default", help="Database name (default: default)")
    parser.add_argument("--http-url", default="https://127.0.0.1:8080", help="HTTPS login endpoint")
    parser.add_argument("--username", default="", help="Account username")
    parser.add_argument("--password", default="", help="Account password")
    parser.add_argument("--insecure-skip-tls-verify", action="store_true", help="development only")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--log-file",
        default=None,
        help="log file path (default: platform user log directory)",
    )
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
    log_path = configure_logging(verbose=args.verbose, log_file=args.log_file)
    install_exception_hook()
    logger.info("CLI command started: %s", args.command)
    try:
        args.func(args)
    except Exception:
        logger.exception("CLI command failed: %s", args.command)
        raise
    else:
        logger.info("CLI command completed: %s", args.command)
        if args.verbose:
            logger.debug("log file: %s", log_path)


if __name__ == "__main__":
    main()
