"""Importable helpers for real process-pool failure and isolation tests."""

import os
from pathlib import Path
from unittest.mock import patch


def forbid_worker_database(marker_dir: Path) -> None:
    (marker_dir / str(os.getpid())).touch()
    for target in ("sqlmodel.create_engine", "sqlalchemy.create_engine", "sqlite3.connect"):
        patch(target, side_effect=AssertionError("Worker opened a database")).start()


def raise_in_worker(path: str, *, dry_run: bool = False):
    raise RuntimeError("Worker failed outside the processing context")


def terminate_worker(path: str, *, dry_run: bool = False):
    os._exit(1)
