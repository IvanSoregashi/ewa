"""Parent-side multiprocessing orchestration: workers run the pure conversion
(str in, dataclass out, no DB access), the parent accumulates results and
flushes analytics to the database in batches while conversions continue.
"""

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from epub.config import settings
from epub.recipe_analytics import record_analytics
from epub.recipe_epub import EpubOptimizationResult, _fully_process_encrypted_panda

logger = logging.getLogger(__name__)


def fully_process_encrypted_pandas(
    directory: Path,
    max_workers: int | None = None,
    flush_size: int = 8,
) -> list[EpubOptimizationResult]:
    """Process every epub under `directory` (recursively) in a process pool.

    max_workers: None = cpu count, 0 = synchronous (no pool, current process).
    flush_size: how many accumulated results trigger an analytics flush.

    Returns every book's result; lost books (worker raised) are logged and
    skipped.
    """
    paths = sorted(path for path in directory.rglob("*.epub"))
    results: list[EpubOptimizationResult] = []
    buffer: list[EpubOptimizationResult] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        try:
            record_analytics(buffer, settings.database_url)
        except Exception as error:
            logger.error(f"analytics flush failed for {len(buffer)} book(s): {error}")
        results.extend(buffer)
        buffer = []

    if max_workers == 0:
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
