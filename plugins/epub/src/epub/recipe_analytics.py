from epub.results import EpubOptimizationResult
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


def record_analytics(results: list[EpubOptimizationResult], db_url: str) -> None:
    """Persist a batch of epub outcomes: one bulk insert per table. Image rows
    are recorded only for successfully processed books, attributed to their
    successful_epubs row."""
    skipped_results = [r for r in results if r.skip is not None]
    error_results = [r for r in results if r.error is not None]
    success_results = [r for r in results if r.success]

    if skipped_results:
        with SkippedEpubsTable(db_url) as table:
            table.insert_many([SkippedEpubModel.from_result(r) for r in skipped_results])

    if error_results:
        with ErrorEpubsTable(db_url) as table:
            table.insert_many([ErrorEpubModel.from_result(r) for r in error_results])

    if not success_results:
        return

    with SuccessfulEpubsTable(db_url) as table:
        epub_rows = [SuccessfulEpubModel.from_result(r) for r in success_results]
        table.insert_many(epub_rows)
        id_by_path = {row.path: row.id for row in epub_rows}

    skipped, errors, successes = [], [], []
    for result in success_results:
        epub_id = id_by_path[str(result.new_epub.path)]
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
