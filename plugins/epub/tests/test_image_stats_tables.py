"""Integration test for image optimization statistics tables (epub.tables).

Uses the shared image test utils (library.test_utils.utils_image) and an
in-memory SQLite database (shared-cache URI, kept alive by a keeper connection
so it survives the per-table engine sessions).
"""

import sqlite3
from pathlib import Path

from sqlmodel import Session, select
from sqlalchemy import create_engine

from epub.tables import (
    ErrorImageModel,
    ProcessedEpubModel,
    SkippedImageModel,
    SuccessfulImageModel,
)
from epub.recipe_analytics import record_image_statistics
from library.epub.recipe_image import perform_image_optimization
from library.image.constants import ImageFormat, ImageMode
from library.image.models import ImageErrorReason, ImageSkipReason
from library.test_utils.utils_image import generate_image, make_resource

MEM_DB_URI = "file:test_image_stats?mode=memory&cache=shared"
DB_URL = "sqlite+pysqlite:///file:test_image_stats?mode=memory&cache=shared&uri=true"


def test_record_image_statistics():
    # success: noisy png large enough for the conversion path (png -> jpg)
    data, _ = generate_image(ImageFormat.PNG, ImageMode.RGB, (1500, 1500), noise=True)
    success_result = perform_image_optimization(make_resource(data, "big.png"))

    # skip: small image below the 50KB threshold
    small_data, _ = generate_image(ImageFormat.PNG, ImageMode.RGB, (64, 32))
    skip_result = perform_image_optimization(make_resource(small_data, "small.png"))

    # error: garbage payload
    error_result = perform_image_optimization(make_resource(b"not an image at all" * 50, "garbage.png"))

    db_url = DB_URL
    keeper = sqlite3.connect(MEM_DB_URI, uri=True, check_same_thread=False)  # keeps the memory db alive
    try:
        book = Path("/fake/books/book.epub")
        record_image_statistics(book, [success_result, skip_result, error_result], db_url)
        # rerun of the same book must not duplicate the epub row
        record_image_statistics(book, [skip_result], db_url)

        engine = create_engine(db_url)
        with Session(engine) as session:
            epub_rows = session.exec(select(ProcessedEpubModel)).all()
            assert len(epub_rows) == 1
            assert epub_rows[0].filepath == str(book)

            skipped = session.exec(select(SkippedImageModel)).all()
            assert len(skipped) == 2  # skip from first run + rerun
            assert skipped[0].skip_reason == int(ImageSkipReason.SMALL_IMAGE)
            assert skipped[0].width == 64 and skipped[0].height == 32
            assert skipped[0].format == "PNG"

            errors = session.exec(select(ErrorImageModel)).all()
            assert len(errors) == 1
            assert errors[0].error == int(ImageErrorReason.DECODE_FAILED)
            assert errors[0].filepath == "garbage.png"
            assert errors[0].filesize == len(b"not an image at all" * 50)

            successes = session.exec(select(SuccessfulImageModel)).all()
            assert len(successes) == 1
            s = successes[0]
            assert s.original_format == "PNG"
            assert s.original_width == 1500
            assert s.new_format == "JPEG"  # conversion happened
            assert s.new_width == 1080  # resized to MEDIUM_WIDTH_SIZE
            assert s.new_filesize > 0
    finally:
        keeper.close()
