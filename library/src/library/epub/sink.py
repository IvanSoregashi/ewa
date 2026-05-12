from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from pathlib import Path

from library.asserts import require
from library.epub.utils_zip import zip_info_now


class EpubZipSink:
    def __init__(self, path: Path):
        self.path = path
        # TODO path validation
        self._zip_file: ZipFile | None = None

    @property
    def zip_file(self) -> ZipFile:
        # TODO consider custom exception
        # TODO consider just instantiating it?
        return require(self._zip_file, "self._zip_file")

    def _write_mimetype(self):
        mimetype_bytes = b"application/epub+zip"
        mimetype_zipinfo = ZipInfo(filename="mimetype", date_time=zip_info_now())
        self.zip_file.writestr(mimetype_zipinfo, mimetype_bytes)

    def __enter__(self):
        self._zip_file = ZipFile(self.path, "w", compression=ZIP_DEFLATED)
        self._write_mimetype()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zip_file.close()
        self._zip_file = None
