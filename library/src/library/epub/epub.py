import logging
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import Protocol, Self
from zipfile import ZipInfo, is_zipfile, ZipFile, Path as ZipPath

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, path: str | PathLike) -> None:
        self.path = Path(path)
