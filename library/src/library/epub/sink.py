from copy import copy
from typing import BinaryIO
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from pathlib import Path

from library.asserts import require
from library.epub.media_type import STORE_AS_IS, FileName
from library.epub.resources import Resource
import logging

logger = logging.getLogger(__name__)


class EpubZipSink:
    def __init__(self, path: Path | BinaryIO):
        # ZipFile accepts both a filesystem path and a binary file object.        self.path = path
        self.path = path
        # TODO path validation
        self._zip_file: ZipFile | None = None

    def __repr__(self):
        return f"EpubZipSink({self.path!r})"

    @property
    def zip_file(self) -> ZipFile:
        # TODO consider custom exception
        # TODO consider just instantiating it?
        return require(self._zip_file, f"{self}._zip_file")

    def write_resource(self, resource: Resource):
        info = copy(resource.info)

        if resource.media_type in STORE_AS_IS or resource.filename == FileName.MIMETYPE:
            info.compress_type = ZIP_STORED
        else:
            info.compress_type = ZIP_DEFLATED

        self.zip_file.writestr(info, resource.content)

    def __enter__(self) -> "EpubZipSink":
        self._zip_file = ZipFile(self.path, "w", compression=ZIP_DEFLATED)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zip_file.close()
        self._zip_file = None
