import os
import time
from datetime import datetime
from pathlib import Path
from zipfile import ZipInfo
import logging

logger = logging.getLogger(__name__)


def zip_info_now(date_time: datetime | None = None) -> tuple[int, int, int, int, int, int]:
    if date_time is None:
        date_time = datetime.now()
    assert date_time is not None
    if date_time.year > 2107:
        date_time = date_time.replace(year=2107, month=12, day=31)
    assert date_time is not None
    return date_time.year, date_time.month, date_time.day, date_time.hour, date_time.minute, date_time.second


def timestamp_from_zipinfo(zipinfo: ZipInfo) -> int:
    """Get timestamp from zipinfo via time.mktime."""
    return int(time.mktime(zipinfo.date_time + (0, 0, -1)))  # Add dummy values for day of week, etc.

def timestamp_from_zip_info(zip_info: ZipInfo) -> int:
    """Get timestamp from zipinfo via datetime.timestamp."""
    try:
        return int(datetime(*zip_info.date_time).timestamp())
    except Exception as e:
        logger.error(f"timestamp_from_zip_info error: {e}")
        return 0


def apply_zipinfo_timestamp_to_file(zipinfo: ZipInfo, path: Path) -> None:
    """Preserve timestamp from zipinfo on extracted file."""
    timestamp = timestamp_from_zipinfo(zipinfo)
    os.utime(path, times=(timestamp, timestamp))  # Set the access and modification times
