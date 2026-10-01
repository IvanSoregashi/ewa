"""Batch recipes: workers return records; the caller persists them in batches."""

import logging
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

from epub.config import settings
from epub.errors import EpubErrorReason
from epub.processing_run import ProcessingRun
from epub.recipe_analytics import record_analytics
from epub.recipe_epub import (
    _fully_process_encrypted_panda,
    _process_encrypted_panda_no_relink,
    should_process_path,
    trying_to_get_stats,
)
from epub.schema_stats import EpubSchemaStats, EpubSchemaStatsTable
from ewa.ui import print_success

logger = logging.getLogger(__name__)


def collect_schema_stats(
    directory: Path,
    max_workers: int | None = 8,
    flush_size: int = 32,
    *,
    database_url: str | None = None,
) -> list[EpubSchemaStats]:
    """Survey EPUBs recursively without changing books. None/0 workers runs synchronously.

    One row per absolute path is replaced on reruns. Failed reads have an error;
    exclude those rows from statistics. Database failures propagate.
    """
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    if max_workers is not None and max_workers < 0:
        raise ValueError("max_workers must be nonnegative")
    if flush_size < 1:
        raise ValueError("flush_size must be positive")

    paths = (path for path in directory.rglob("*") if path.suffix.lower() == ".epub" and path.is_file())
    results: list[EpubSchemaStats] = []
    buffer: list[EpubSchemaStats] = []

    def scan(path: Path) -> EpubSchemaStats:
        try:
            return trying_to_get_stats(path)
        except Exception as error:
            logger.error("Schema stats failed for %s: %r", path, error, exc_info=True)
            return EpubSchemaStats(filepath=str(path), error=repr(error))

    with EpubSchemaStatsTable(database_url or settings.database_url) as table:

        def save(rows: Iterable[EpubSchemaStats]) -> None:
            for row in rows:
                buffer.append(row)
                if len(buffer) >= flush_size:
                    flush()
            flush()

        def flush() -> None:
            if not buffer:
                return
            table.upsert_many(buffer)
            results.extend(buffer)
            buffer.clear()
            print_success(f"Schema stats: {len(results)} EPUBs saved")

        if max_workers:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                # Keep the queued work bounded even for very large libraries.
                save(pool.map(scan, paths, buffersize=max_workers * 2))
        else:
            save(map(scan, paths))

    return results


def fully_process_encrypted_pandas(
    directory: Path,
    max_workers: int | None = None,
    flush_size: int = 8,
    *,
    dry_run: bool = False,
) -> list[ProcessingRun]:
    """Process every epub under `directory` (recursively) in a process pool.

    max_workers: None or 0 = synchronous; positive values use a process pool.
    flush_size: how many accumulated results trigger an analytics flush.
    dry_run: process and record analytics, then remove output and leave originals in place.

    Paths outside the input directory or with existing destinations are filtered
    before dispatch, without analytics. Process-pool submission/result exceptions
    become error outcomes; unreturned worker evidence cannot be recovered.
    """
    return _process_encrypted_pandas(
        directory, _fully_process_encrypted_panda, max_workers, flush_size, dry_run=dry_run
    )


def process_encrypted_pandas_no_relink(
    directory: Path,
    max_workers: int | None = None,
    flush_size: int = 8,
    *,
    dry_run: bool = False,
) -> list[ProcessingRun]:
    """Use the alternative Panda recipe with the same batching, filtering, and persistence."""
    return _process_encrypted_pandas(
        directory, _process_encrypted_panda_no_relink, max_workers, flush_size, dry_run=dry_run
    )


def _process_encrypted_pandas(
    directory: Path,
    processor: Callable[..., ProcessingRun],
    max_workers: int | None,
    flush_size: int,
    *,
    dry_run: bool,
) -> list[ProcessingRun]:
    paths = [path for path in sorted(directory.rglob("*.epub")) if should_process_path(path)]
    if not paths:
        return []
    results: list[ProcessingRun] = []
    buffer: list[ProcessingRun] = []
    flush_end_time = time.time()

    def worker_failure(path: Path, error: Exception) -> ProcessingRun:
        logger.error("Worker failed for %s: %r", path, error)
        return ProcessingRun(input_path=str(path), error=EpubErrorReason.UNKNOWN, details=repr(error))

    def flush() -> None:
        nonlocal buffer, flush_end_time
        if not buffer:
            return
        length = len(buffer)
        try:
            flush_start_time = time.time()
            time_inbetween = flush_start_time - flush_end_time
            record_analytics(buffer, settings.database_url)
            flush_end_time = time.time()
            time_flush = flush_end_time - flush_start_time
            print_success(f"{length} RECORDS PROCESSING {time_inbetween:.2f}s FLUSH {time_flush:.2f}s")
        except Exception as error:
            logger.error(f"analytics flush failed for {len(buffer)} book(s): {error}")
            raise
        results.extend(buffer)
        buffer = []

    if not max_workers:
        for path in paths:
            buffer.append(processor(str(path), dry_run=dry_run))
            if len(buffer) >= flush_size:
                flush()
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for path in paths:
                try:
                    future = pool.submit(processor, str(path), dry_run=dry_run)
                except Exception as error:
                    buffer.append(worker_failure(path, error))
                    if len(buffer) >= flush_size:
                        flush()
                else:
                    futures[future] = path
            for future in as_completed(futures):
                book_path = futures[future]
                try:
                    buffer.append(future.result())
                except Exception as error:
                    buffer.append(worker_failure(book_path, error))
                if len(buffer) >= flush_size:
                    flush()

    flush()
    return results
