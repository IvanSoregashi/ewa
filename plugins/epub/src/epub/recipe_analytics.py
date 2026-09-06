from pathlib import Path
from typing import TYPE_CHECKING

from epub.tables import (
    SkippedImageModel,
    ErrorImageModel,
    SuccessfulImageModel,
    SkippedEpubModel,
    ErrorEpubModel,
    SuccessfulEpubModel,
    SkippedImagesTable,
    ErrorImagesTable,
    SuccessfulImagesTable,
    SkippedEpubsTable,
    ErrorEpubsTable,
    SuccessfulEpubsTable,
)

if TYPE_CHECKING:
    from epub.recipe_epub import EpubOptimizationResult


def record_analytics(filepath: Path, result: "EpubOptimizationResult", db_url: str) -> None:
    """Persist the epub-level outcome. Image results are recorded only for
    successfully processed books; skipped and errored books save no images."""
    if result.error is not None:
        with ErrorEpubsTable(db_url) as table:
            table.insert_one(ErrorEpubModel.from_result(result))
        return

    if result.skip is not None:
        with SkippedEpubsTable(db_url) as table:
            table.insert_one(SkippedEpubModel.from_result(result))
        return

    with SuccessfulEpubsTable(db_url) as table:
        row = SuccessfulEpubModel.from_result(result)
        table.insert_one(row)
        epub_id = row.id

    skipped, errors, successes = [], [], []
    for image_result in result.image_results:
        if image_result.skip is not None:
            skipped.append(SkippedImageModel.from_result(epub_id, image_result))
        elif image_result.error is not None:
            errors.append(ErrorImageModel.from_result(epub_id, image_result))
        elif image_result.success:
            successes.append(SuccessfulImageModel.from_result(epub_id, image_result))

    if skipped:
        with SkippedImagesTable(db_url) as table:
            table.insert_many(skipped)
    if errors:
        with ErrorImagesTable(db_url) as table:
            table.insert_many(errors)
    if successes:
        with SuccessfulImagesTable(db_url) as table:
            table.insert_many(successes)
