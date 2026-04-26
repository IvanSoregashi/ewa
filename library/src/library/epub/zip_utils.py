import time
from datetime import datetime
from zipfile import ZipInfo


def zip_info_now() -> tuple[int, int, int, int, int, int]:
    now = datetime.now()
    if now.year > 2107:
        now = now.replace(year=2107, month=12, day=31)
    return now.year, now.month, now.day, now.hour, now.minute, now.second


def zipinfo_to_timestamp(zipinfo: ZipInfo) -> int:
    return int(time.mktime(zipinfo.date_time + (0, 0, -1)))  # Add dummy values for day of week, etc.
