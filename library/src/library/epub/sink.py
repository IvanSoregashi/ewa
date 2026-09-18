from copy import copy
from pathlib import Path
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZIP_STORED

from library.epub.media_type import STORE_AS_IS, FileName
from library.epub.resources import Resource
from library.zip import ZipSink


class EpubZipSink(ZipSink):
    def __init__(self, path: str | Path | BinaryIO, *, stream_resources: bool = False):
        """Write resource.content by default, loading and caching source bytes.

        Opt into streaming to avoid caching unloaded resources. Resource.stream()
        still prefers assigned content, so edits are preserved in either mode.
        The mimetype entry always uses a byte write to avoid ZIP64 extra fields.
        """
        super().__init__(path)
        self.stream_resources = stream_resources

    def write_resource(self, resource: Resource):
        info = copy(resource.info)

        if resource.media_type in STORE_AS_IS or resource.filename == FileName.MIMETYPE:
            info.compress_type = ZIP_STORED
        else:
            info.compress_type = ZIP_DEFLATED

        if not self.stream_resources or resource.filename == FileName.MIMETYPE:
            # EPUB forbids extra fields (including ZIP64) in the mimetype header.
            self.zip_file.writestr(info, resource.content)
        else:
            with resource.stream() as stream:
                self.write_stream(info, stream)
