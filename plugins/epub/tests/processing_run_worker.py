"""Importable worker used to exercise Windows spawn with unsaved analytics."""

import os
import sys
from pathlib import Path
from unittest.mock import patch


def process_book(path: Path, status: str):
    with (
        patch("sqlmodel.create_engine", side_effect=AssertionError("Worker opened a database")),
        patch("sqlalchemy.create_engine", side_effect=AssertionError("Worker opened a database")),
        patch("sqlite3.connect", side_effect=AssertionError("Worker opened a database")),
    ):
        from epub.image_analytics import ImageOptimizationRecord
        from epub.processing import ProcessingContext
        from epub.processing_run import ProcessingRun
        from epub.recipe_image import perform_image_optimization
        from epub.verification import OPFPath
        from library.asserts import require
        from library.epub.epub import EPUB

        with ProcessingContext() as context:
            context.open_epub(path)
            image = require(context.epub.resources.by_path("cover.png"))
            result = perform_image_optimization(image)
            context.analytics.append(ImageOptimizationRecord.from_result(context.run_id, result))
            if status == "skip":
                context.verify(OPFPath("unexpected.opf"))
            elif status == "error":
                raise RuntimeError("Failure after collecting image evidence")
            else:
                destination = path.with_name(f"{context.run_id}.epub")
                context.epub.package_into(destination)
                context.succeed(EPUB(destination).info())

        outcome = require(context.result)
        assert outcome.id == context.run_id
        assert isinstance(outcome, ProcessingRun)
        assert "epub.config" not in sys.modules
        assert "ewa.config" not in sys.modules
        return os.getpid(), outcome
