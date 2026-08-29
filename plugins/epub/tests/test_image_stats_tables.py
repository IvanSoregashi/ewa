"""Integration test for image optimization statistics tables (epub.tables)."""

import random
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipInfo

from PIL import Image

from epub.tables import (
    ErrorImageModel,
    ProcessedEpubModel,
    SkippedImageModel,
    SuccessfulImageModel,
    record_image_statistics,
)
from library.epub.recipe_image import perform_image_optimization
from library.epub.resources import Resource
from library.image.constants import ImageFormat, ImageMode
from library.image.models import ImageErrorReason, ImageSkipReason


def make_resource(data: bytes, filename: str) -> Resource:
    info = ZipInfo(filename)
    info.file_size = len(data)
    return Resource(info=info, stream_bytes=lambda i: BytesIO(data))


def generate_image_bytes(image_format: ImageFormat, mode: ImageMode, size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new(str(mode), size, "red").save(buffer, format=str(image_format))
    return buffer.getvalue()


def test_record_image_statistics(tmp_path: Path):
    # success: noisy png large enough for the conversion path (png -> jpg)
    buffer = BytesIO()
    Image.frombytes("RGB", (1500, 1500), random.randbytes(1500 * 1500 * 3)).save(buffer, format="PNG")
    success_result = perform_image_optimization(make_resource(buffer.getvalue(), "big.png"))

    # skip: small image below the 50KB threshold
    skip_result = perform_image_optimization(
        make_resource(generate_image_bytes(ImageFormat.PNG, ImageMode.RGB, (64, 32)), "small.png")
    )

    # error: garbage payload
    error_result = perform_image_optimization(make_resource(b"not an image at all" * 50, "garbage.png"))

    db_url = f"sqlite:///{tmp_path}/stats.db"
    book = tmp_path / "book.epub"
    record_image_statistics(book, [success_result, skip_result, error_result], db_url)

    # rerun of the same book must not duplicate the epub row
    record_image_statistics(book, [skip_result], db_url)

    epubs = ProcessedEpubModel.__table__  # smoke: table exists
    from sqlmodel import Session, select
    from sqlalchemy import create_engine

    engine = create_engine(db_url)
    with Session(engine) as session:
        epub_rows = session.exec(select(ProcessedEpubModel)).all()
        assert len(epub_rows) == 1
        epub_id = epub_rows[0].id
        assert epub_rows[0].filepath == str(book.absolute())

        skipped = session.exec(select(SkippedImageModel)).all()
        assert len(skipped) == 2  # skip from first run + rerun
        assert skipped[0].skip_reason == int(ImageSkipReason.SMALL_IMAGE)
        assert skipped[0].size == "64x32"
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
        assert s.new_format == "JPEG"  # conversion happened
        assert s.new_filesize > 0
