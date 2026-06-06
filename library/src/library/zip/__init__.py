from datetime import datetime
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import io

from library.epub.utils_zip import zip_info_now


def make_zipinfo(
    filename: str,
    date_time: datetime | None = None,
    compress_type: int = ZIP_DEFLATED,
    comment: str = "Generated via file stream",
) -> ZipInfo:
    zinfo = ZipInfo(filename=filename)
    zinfo.date_time = zip_info_now(date_time)
    zinfo.compress_type = compress_type
    zinfo.comment = comment.encode()
    # zinfo.external_attr = 0o644 << 16
    return zinfo


def zip_the_bytestream(incoming_byte_stream: io.BytesIO, zip_file_path: str, filename: str):
    with ZipFile(zip_file_path, mode="w", compression=ZIP_DEFLATED) as zf:
        zinfo = make_zipinfo(filename=filename)
        with zf.open(zinfo, mode="w") as internal_file:
            while True:
                chunk = incoming_byte_stream.read(65536)
                if not chunk:
                    break
                internal_file.write(chunk)
