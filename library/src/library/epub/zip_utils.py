import os
import time
from datetime import datetime
from pathlib import Path
from zipfile import ZipInfo


def zip_info_now() -> tuple[int, int, int, int, int, int]:
    now = datetime.now()
    if now.year > 2107:
        now = now.replace(year=2107, month=12, day=31)
    return now.year, now.month, now.day, now.hour, now.minute, now.second


def timestamp_from_zipinfo(zipinfo: ZipInfo) -> int:
    return int(time.mktime(zipinfo.date_time + (0, 0, -1)))  # Add dummy values for day of week, etc.


def apply_zipinfo_timestamp_to_file(zipinfo: ZipInfo, path: Path) -> None:
    """Preserve timestamp from zipinfo on extracted file."""
    timestamp = timestamp_from_zipinfo(zipinfo)
    os.utime(path, times=(timestamp, timestamp))  # Set the access and modification times
