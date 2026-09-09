"""Parent-side multiprocessing orchestration: workers run the pure conversion
(str in, dataclass out, no DB access), the parent accumulates results and
flushes analytics to the database in batches while conversions continue.
"""

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from epub.config import settings
from epub.recipe_analytics import record_analytics
from epub.recipe_epub import EpubOperationResult, _fully_process_encrypted_panda
from ewa.ui import print_success

logger = logging.getLogger(__name__)


def fully_process_encrypted_pandas(
    directory: Path,
    max_workers: int | None = None,
    flush_size: int = 8,
) -> list[EpubOperationResult]:
    """Process every epub under `directory` (recursively) in a process pool.

    max_workers: None = cpu count, 0 = synchronous (no pool, current process).
    flush_size: how many accumulated results trigger an analytics flush.

    Returns every book's result; lost books (worker raised) are logged and
    skipped.
    """
    paths = sorted(path for path in directory.rglob("*.epub"))
    results: list[EpubOperationResult] = []
    buffer: list[EpubOperationResult] = []
    flush_end_time = time.time()

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
        results.extend(buffer)
        buffer = []

    if not max_workers:
        for path in paths:
            buffer.append(_fully_process_encrypted_panda(str(path)))
            if len(buffer) >= flush_size:
                flush()
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fully_process_encrypted_panda, str(path)): path for path in paths}
            for future in as_completed(futures):
                book_path = futures[future]
                try:
                    buffer.append(future.result())
                except Exception as error:
                    logger.error(f"book lost {str(book_path)!s}, worker raised: {error}")
                    continue
                if len(buffer) >= flush_size:
                    flush()

    flush()
    return results
