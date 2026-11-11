"""Command-line interface for headless upload/download and e2e testing."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .download.fetcher import download_study
from .logging_config import configure_logging, install_exception_hook
from .models import StudyAttrs
from .readers import load_source_file, record_lsl
from .readers.bids import attach_bids_events, discover_bids_recordings
from .transport import EEGDBStorageClient, EEGDBTCPClient, TransferClient
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


def _client(args: argparse.Namespace) -> TransferClient:
    if args.backend == "local":
        if not args.storage_path:
            raise SystemExit("--storage-path is required with --backend local")
        return EEGDBStorageClient(args.storage_path, library_path=args.storage_library or None)
    return _tcp_client(args)


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

    with _client(args) as client:
        study_id = upload_source_file(
            client,
            source,
            attrs,
            batch_seconds=args.batch_seconds,
            on_progress=progress if args.verbose else None,
            resume=not args.no_resume,
            checkpoint_path=args.checkpoint,
        )
    print(study_id)


def cmd_list(args: argparse.Namespace) -> None:
    with _client(args) as client:
        studies = client.list_studies()
    for s in studies:
        print(
            f"{s.get('study_id')}\t{s.get('name')}\t"
            f"ch={s.get('num_channels')}\tn={s.get('num_samples')}"
        )


def cmd_download(args: argparse.Namespace) -> None:
    def progress(msg: str, frac: float) -> None:
        print(f"[{frac * 100:5.1f}%] {msg}")

    if args.backend == "local" and args.local_decode:
        raise SystemExit("--local-decode only applies to the TCP backend")
    with _client(args) as client:
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


def cmd_import_dir(args: argparse.Namespace) -> None:
    root = Path(args.directory).expanduser()
    if not root.is_dir():
        raise SystemExit(f"directory not found: {root}")
    allowed = {".edf", ".bdf", ".fif", ".cdt", ".vhdr", ".set", ".xdf"}
    iterator = root.rglob("*") if args.recursive else root.glob("*")
    paths = sorted(path for path in iterator if path.is_file() and path.suffix.lower() in allowed)
    if not paths:
        raise SystemExit(f"no supported EEG files found in {root}")

    attrs = StudyAttrs(lab=args.lab, paradigm=args.paradigm, device_type=args.device)
    failures: list[tuple[Path, Exception]] = []
    for index, path in enumerate(paths, 1):
        print(f"[{index}/{len(paths)}] {path}")
        try:
            with _client(args) as client:
                source = load_source_file(str(path))
                study_id = upload_source_file(
                    client,
                    source,
                    attrs,
                    batch_seconds=args.batch_seconds,
                    resume=not args.no_resume,
                )
            print(f"  uploaded {study_id}")
        except Exception as exc:
            logger.exception("batch import failed: %s", path)
            failures.append((path, exc))
            print(f"  failed: {exc}")
    if failures:
        raise SystemExit(f"{len(failures)} of {len(paths)} imports failed; rerun to resume")


def cmd_import_bids(args: argparse.Namespace) -> None:
    try:
        recordings = discover_bids_recordings(args.directory)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not recordings:
        raise SystemExit(f"no supported EEG recordings found in {args.directory}")

    failures = []
    for index, recording in enumerate(recordings, 1):
        print(f"[{index}/{len(recordings)}] {recording.path}")
        attrs = recording.attrs
        attrs.lab = args.lab
        attrs.device_type = args.device
        try:
            with _client(args) as client:
                source = attach_bids_events(
                    load_source_file(str(recording.path)), recording.path
                )
                study_id = upload_source_file(
                    client,
                    source,
                    attrs,
                    batch_seconds=args.batch_seconds,
                    resume=not args.no_resume,
                )
            print(f"  uploaded {study_id}")
        except Exception as exc:
            logger.exception("BIDS import failed: %s", recording.path)
            failures.append((recording.path, exc))
            print(f"  failed: {exc}")
    if failures:
        raise SystemExit(
            f"{len(failures)} of {len(recordings)} BIDS imports failed; rerun to resume"
        )


def cmd_export(args: argparse.Namespace) -> None:
    if args.backend == "local" and args.local_decode:
        raise SystemExit("--local-decode only applies to the TCP backend")
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[tuple[str, Exception]] = []
    for index, study_id in enumerate(args.study_ids, 1):
        output = output_dir / f"{study_id}.{args.format}"
        print(f"[{index}/{len(args.study_ids)}] {study_id}")
        try:
            with _client(args) as client:
                saved = download_study(
                    client,
                    study_id,
                    str(output),
                    fmt=args.format,
                    local_decode=args.local_decode,
                    block_codec=args.codec,
                )
            print(f"  saved {saved}")
        except Exception as exc:
            logger.exception("batch export failed: %s", study_id)
            failures.append((study_id, exc))
            print(f"  failed: {exc}")
    if failures:
        raise SystemExit(f"{len(failures)} of {len(args.study_ids)} exports failed")


def cmd_upload_lsl(args: argparse.Namespace) -> None:
    source = record_lsl(
        args.duration,
        stream_name=args.stream_name,
        stream_type=args.stream_type,
        resolve_timeout=args.resolve_timeout,
    )
    attrs = StudyAttrs(lab=args.lab, paradigm=args.paradigm, device_type="LSL")
    with _client(args) as client:
        study_id = upload_source_file(client, source, attrs, resume=False)
    print(study_id)


def cmd_health(args: argparse.Namespace) -> None:
    with _client(args) as client:
        studies = client.list_studies()
    target = args.storage_path if args.backend == "local" else f"{args.host}:{args.port}"
    print(f"ok  backend={args.backend}  target={target}  studies={len(studies)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eegdb-client")
    parser.add_argument(
        "--backend",
        choices=["tcp", "local"],
        default="tcp",
        help="remote TCP server or embedded local storage (default: tcp)",
    )
    parser.add_argument(
        "--storage-path",
        default="",
        help="local EEGDB directory for --backend local",
    )
    parser.add_argument(
        "--storage-library",
        default="",
        help="optional path to the eegdb-storage native library",
    )
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

    p_health = sub.add_parser("health", help="Check the selected backend")
    p_health.set_defaults(func=cmd_health)

    p_upload = sub.add_parser(
        "upload", help="Import EDF/BDF/FIF/CDT/BrainVision/EEGLAB/XDF"
    )
    p_upload.add_argument("file")
    p_upload.add_argument("--lab", default="")
    p_upload.add_argument("--paradigm", default="")
    p_upload.add_argument("--device", default="")
    p_upload.add_argument("--batch-seconds", type=float, default=10.0)
    p_upload.add_argument(
        "--no-resume", action="store_true", help="disable upload checkpoint recovery"
    )
    p_upload.add_argument("--checkpoint", default=None, help="custom upload checkpoint path")
    p_upload.set_defaults(func=cmd_upload)

    p_import = sub.add_parser("import-dir", help="Import all supported EEG files in a directory")
    p_import.add_argument("directory")
    p_import.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True)
    p_import.add_argument("--lab", default="")
    p_import.add_argument("--paradigm", default="")
    p_import.add_argument("--device", default="")
    p_import.add_argument("--batch-seconds", type=float, default=10.0)
    p_import.add_argument("--no-resume", action="store_true")
    p_import.set_defaults(func=cmd_import_dir)

    p_bids = sub.add_parser("import-bids", help="Import a BIDS EEG dataset")
    p_bids.add_argument("directory")
    p_bids.add_argument("--lab", default="")
    p_bids.add_argument("--device", default="")
    p_bids.add_argument("--batch-seconds", type=float, default=10.0)
    p_bids.add_argument("--no-resume", action="store_true")
    p_bids.set_defaults(func=cmd_import_bids)

    p_lsl = sub.add_parser("upload-lsl", help="Capture and upload a bounded LSL EEG stream")
    p_lsl.add_argument("--duration", type=float, required=True, help="capture duration in seconds")
    p_lsl.add_argument("--stream-name", default="")
    p_lsl.add_argument("--stream-type", default="EEG")
    p_lsl.add_argument("--resolve-timeout", type=float, default=5.0)
    p_lsl.add_argument("--lab", default="")
    p_lsl.add_argument("--paradigm", default="")
    p_lsl.set_defaults(func=cmd_upload_lsl)

    p_list = sub.add_parser("list", help="List studies")
    p_list.set_defaults(func=cmd_list)

    p_dl = sub.add_parser("download", help="Download or export a study")
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
        default="balanced",
        choices=["lz4", "zstd", "flac", "wavpack", "fast", "balanced", "smallest"],
        help="block codec for --local-decode (server re-encodes the batch; default: balanced)",
    )
    p_dl.set_defaults(func=cmd_download)

    p_export = sub.add_parser("export", help="Export one or more studies")
    p_export.add_argument("study_ids", nargs="+")
    p_export.add_argument("-o", "--output-dir", required=True)
    p_export.add_argument("-f", "--format", default="edf", choices=["edf", "bdf", "fif", "npz"])
    p_export.add_argument("--local-decode", action="store_true")
    p_export.add_argument(
        "--codec",
        default="balanced",
        choices=["lz4", "zstd", "flac", "wavpack", "fast", "balanced", "smallest"],
    )
    p_export.set_defaults(func=cmd_export)

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
