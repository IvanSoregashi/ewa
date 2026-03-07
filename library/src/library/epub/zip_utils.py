from datetime import datetime
from pathlib import Path
from zipfile import ZipInfo

from library.epub.utils import strip_fragment


def zip_info_now() -> tuple[int, int, int, int, int, int]:
    now = datetime.now()

    if now.year > 2107:
        now = now.replace(year=2107, month=12, day=31)

    return now.year, now.month, now.day, now.hour, now.minute, now.second


def info_to_zipinfo(info: ZipInfo | str | Path) -> ZipInfo:
    if isinstance(info, ZipInfo):
        return info

    return ZipInfo(filename=str(strip_fragment(info)), date_time=zip_info_now())
