"""Parent-side multiprocessing orchestration: workers run the pure conversion
(str in, unsaved run out, no DB access), the parent accumulates results and
flushes analytics to the database in batches while conversions continue.
"""

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from epub.config import settings
from epub.errors import EpubErrorReason
from epub.recipe_analytics import record_analytics
from epub.processing_run import ProcessingRun
from epub.recipe_epub import _fully_process_encrypted_panda, should_process_path
from ewa.ui import print_success

logger = logging.getLogger(__name__)


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
            buffer.append(_fully_process_encrypted_panda(str(path), dry_run=dry_run))
            if len(buffer) >= flush_size:
                flush()
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for path in paths:
                try:
                    future = pool.submit(_fully_process_encrypted_panda, str(path), dry_run=dry_run)
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
