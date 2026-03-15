import logging
from os import PathLike
from pathlib import Path

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, path: str | PathLike) -> None:
        self.path = Path(path)
