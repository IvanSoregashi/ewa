from datetime import datetime
from hashlib import md5
from zipfile import ZipInfo


def ts_to_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def bt_to_mb(size_in_bytes: int) -> str:
    return f"{size_in_bytes / (1024 * 1024):.2f} mb"


def string_to_int_hash(string: str) -> int:
    """returns a 64-bit integer hash"""
    return int(md5(string.encode("utf-8")).hexdigest()[:16], 16)


def timestamp_from_zip_info(zip_info: ZipInfo) -> int:
    try:
        return int(datetime(*zip_info.date_time).timestamp())
    except Exception:
        return 0
