from pathlib import Path

from epub.tables import (
    ProcessedEpubTable,
    SkippedImageModel,
    ErrorImageModel,
    SuccessfulImageModel,
    SkippedImagesTable,
    ErrorImagesTable,
    SuccessfulImagesTable,
)
from library.image.models import ImageOptimizationResult


def record_image_statistics(filepath: Path, results: list[ImageOptimizationResult], db_url: str) -> None:
    """Step 3.1: persist per-image optimization outcomes for one epub."""
    with ProcessedEpubTable(db_url) as epub_table:
        epub_id = epub_table.get_or_create_id(str(filepath.absolute()))

    skipped = [SkippedImageModel.from_result(epub_id, r) for r in results if r.skip is not None]
    errors = [ErrorImageModel.from_result(epub_id, r) for r in results if r.error is not None]
    successes = [SuccessfulImageModel.from_result(epub_id, r) for r in results if r.success]

    if skipped:
        with SkippedImagesTable(db_url) as table:
            table.insert_many(skipped)
    if errors:
        with ErrorImagesTable(db_url) as table:
            table.insert_many(errors)
    if successes:
        with SuccessfulImagesTable(db_url) as table:
            table.insert_many(successes)
