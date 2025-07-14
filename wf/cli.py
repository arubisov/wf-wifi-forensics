#!/usr/bin/env python3
"""
CLI entry point for the wf-Wi-Fi-forensics toolkit.

Defines the following commands:
  wf ingest NAME <src_dir>
  wf analyze NAME [--from ISO8601] [--to ISO8601]
  wf export NAME --all|--cotravel|--stats [--outdir DIR]
  wf serve NAME [--port 8000]
  wf version
"""

import sys
import os
import hashlib
import uuid
from argparse import ArgumentParser, Namespace
from importlib.metadata import PackageNotFoundError, version as _get_version

import uvicorn

from wf.utils.log import get_logger
from wf.storage.dao import DAO
from wf.server import create_app
from wf.parsers import kismet
from wf.analysis.config import ClassifierConfig
from wf.analysis.classifier import ClassifierPipeline

logger = get_logger(__name__)


def _compute_sha256(file_path: str, chunk_size: int = 8192) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest(mission: str, src_dir: str) -> None:
    """
    Ingest raw capture files into the Mission DB.

    Parameters
    ----------
    mission
        Mission name, which dictates the SQLite database file name.
    src_dir
        Path to the directory containing raw `.kismet`/`.csv` files.
    """
    logger.info("Ingest: mission=%s, src_dir=%s", mission, src_dir)
    
    db_path = f"wf_{mission}.sqlite"
    dao = DAO(db_path)
    # start with a clean drive_path
    dao.recreate_drive_path_table()

    # Recursively find and ingest .kismet files
    for root, _, files in os.walk(src_dir):
        for filename in files:
            if not filename.endswith(".kismet"):
                continue
            file_path = os.path.join(root, filename)
            sha256 = _compute_sha256(file_path)
            if dao.session_exists(sha256):
                logger.info("Skipping already ingested file: %s", file_path)
                continue

            # Generate a new session ID
            session_id = str(uuid.uuid4())
            
            # Parse the file into normalized records (three generators)
            devices_iter, obs_iter, paths_iter = kismet.parse_kismet(file_path, session_id)
            
            # Insert session metadata with dummy timestamps
            dao.add_session(session_id, mission, file_path, sha256, 0, 0)
            
            # Batch‐insert observations, devices, and drive_path
            dao.add_devices_bulk(devices_iter)
            dao.add_observations_bulk(obs_iter)
            dao.add_paths_bulk(paths_iter)
            
            # update session start/end timestamps
            start_ts, end_ts = dao.get_session_time_bounds(session_id)
            dao.update_session_times(session_id, start_ts, end_ts)


def analyze(mission: str, from_ts: str | None, to_ts: str | None) -> None:
    """
    Populate derived tables (co_travelers, atmospherics, stats).

    Parameters
    ----------
    mission
        Mission name, which dictates the SQLite database file name.
    from_ts
        Optional ISO8601 start timestamp filter.
    to_ts
        Optional ISO8601 end timestamp filter.
    """
    logger.info("Analyze: mission=%s, from=%s, to=%s", mission, from_ts, to_ts)
    db_path = f"wf_{mission}.sqlite"
    dao = DAO(db_path)
    # run classifier
    cfg = ClassifierConfig.driving()
    ClassifierPipeline(dao, cfg).run()
    # TODO: run atmospherics, stats population


def export(mission: str, all: bool, cotravel: bool, stats: bool, outdir: str | None) -> None:
    """
    Export processed data to CSV/GeoJSON/XLSX or Leaflet map.

    Parameters
    ----------
    mission
        Mission name, which dictates the SQLite database file name.
    all
        Export all tables.
    cotravel
        Export co_travelers.csv.
    stats
        Export atmospherics (stats) CSV.
    outdir
        Directory to write exported files into.
    """
    logger.info(
        "Export: mission=%s, all=%s, cotravel=%s, stats=%s, outdir=%s",
        mission, all, cotravel, stats, outdir,
    )
    # TODO: dispatch to wf.export.csv, wf.export.geojson, etc.


def serve(mission: str, port: int) -> None:
    """
    Spin up FastAPI+Uvicorn to serve an interactive map.

    Parameters
    ----------
    mission
        Mission name, which dictates the SQLite database file name.
    port
        Port on which to serve HTTP.
    """
    logger.info("Serve: mission=%s, port=%d", mission, port)
    # create an app bound to the mission
    app = create_app(mission)
    uvicorn.run(app, host="127.0.0.1", port=port)

def version() -> None:
    """
    Print the installed wf package version.
    """
    try:
        ver = _get_version("wf")
    except PackageNotFoundError:
        ver = "unknown"
    logger.info("wf version %s", ver)


def parse_args() -> Namespace:
    """
    Parse command-line arguments and return the populated namespace.
    """
    parser = ArgumentParser(prog="wf")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # wf ingest
    p = subparsers.add_parser("ingest", help="Ingest raw capture files.")
    p.add_argument("mission", type=str, help="Mission name.")
    p.add_argument("src_dir", type=str, help="Source directory of raw capture files.")

    # wf analyze
    p = subparsers.add_parser("analyze", help="Analyze the database.")
    p.add_argument("mission", type=str, help="Mission name.")
    p.add_argument(
        "--from", dest="from_ts", type=str, help="ISO8601 start time filter."
    )
    p.add_argument(
        "--to", dest="to_ts", type=str, help="ISO8601 end time filter."
    )

    # wf export
    p = subparsers.add_parser("export", help="Export processed data.")
    p.add_argument("mission", type=str, help="Mission name.")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--all", action="store_true", help="Export all data.")
    grp.add_argument("--cotravel", action="store_true", help="Export co-travelers.")
    grp.add_argument("--stats", action="store_true", help="Export atmospherics stats.")
    p.add_argument("--outdir", type=str, help="Output directory.")

    # wf serve
    p = subparsers.add_parser("serve", help="Serve via FastAPI + Uvicorn.")
    p.add_argument("mission", type=str, help="Mission name.")
    p.add_argument(
        "--port", type=int, default=8000, help="Port number to serve on."
    )

    # wf version
    subparsers.add_parser("version", help="Show wf version and exit.")

    return parser.parse_args()


def main() -> None:
    """
    Entry point: dispatch to the selected subcommand.
    """
    args = parse_args()
    match args.command:
        case "ingest":
            ingest(args.mission, args.src_dir)
        case "analyze":
            analyze(args.mission, args.from_ts, args.to_ts)
        case "export":
            export(args.mission, args.all, args.cotravel, args.stats, args.outdir)
        case "serve":
            serve(args.mission, args.port)
        case "version":
            version()
        case _:
            sys.exit(1)


if __name__ == "__main__":
    main()