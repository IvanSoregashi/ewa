from copy import copy
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo, ZIP_STORED
from pathlib import Path

from library.asserts import require
from library.epub.media_type import STORE_AS_IS, FileName
from library.epub.resources import Resource
from library.epub.utils_zip import zip_info_now
from library.epub.xml_literals import FileTemplate
import logging

logger = logging.getLogger(__name__)


class EpubZipSink:
    def __init__(self, path: Path):
        self.path = path
        # TODO path validation
        self._zip_file: ZipFile | None = None

    def __repr__(self):
        return f"EpubZipSink({self.path})"

    @property
    def zip_file(self) -> ZipFile:
        # TODO consider custom exception
        # TODO consider just instantiating it?
        return require(self._zip_file, f"{self.path}._zip_file")

    def write_resource(self, resource: Resource):
        logger.warning(f"{self} Writing resource: {resource}")
        if resource.is_deleted:
            return
        info = copy(resource.info)
        # info.CRC = 0
        # info.file_size = 0
        # info.compress_size = 0
        if resource.media_type in STORE_AS_IS:
            info.compress_type = ZIP_STORED
        else:
            info.compress_type = ZIP_DEFLATED
        self.zip_file.writestr(info, resource.content)

    def _write_mimetype(self):
        mimetype_bytes = FileTemplate.MIMETYPE.encode("utf-8")
        mimetype_zipinfo = ZipInfo(filename=FileName.MIMETYPE, date_time=zip_info_now())
        self.zip_file.writestr(mimetype_zipinfo, mimetype_bytes)

    def _write_container(self, opf_path: str = FileName.DEFAULT_OPF):
        container_bytes = FileTemplate.CONTAINER.format(opf_path=opf_path).encode("utf-8")
        container_zipinfo = ZipInfo(filename=FileName.CONTAINER, date_time=zip_info_now())
        self.zip_file.writestr(container_zipinfo, container_bytes)

    def __enter__(self) -> "EpubZipSink":
        self._zip_file = ZipFile(self.path, "w", compression=ZIP_DEFLATED)
        # self._write_mimetype()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zip_file.close()
        self._zip_file = None
