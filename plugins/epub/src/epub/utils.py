from datetime import datetime
from hashlib import md5
from struct import unpack
from zipfile import ZipInfo

SQLITE_MAX_INT = 2**63 - 1
SQLITE_MIN_INT = -(2**63)
SIXTY_FOUR_BIT_MASK = 0xFFFFFFFFFFFFFFFF


def ts_to_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def bt_to_mb(size_in_bytes: int) -> str:
    return f"{size_in_bytes / (1024 * 1024):.2f} mb"


def string_to_int_hash_old(string: str) -> int:
    """returns a 64-bit integer hash"""
    int_hash = int(md5(string.encode("utf-8")).hexdigest(), 16)
    return int_hash % SQLITE_MAX_INT


def string_to_int_hash(string: str) -> int:
    """
    Generates a 64-bit signed integer hash from a string,
    utilizing the full SQLite INTEGER range (positive and negative).
    """
    # 1. Generate the 128-bit MD5 hash
    hash_digest = md5(string.encode("utf-8")).digest()

    # 2. Unpack the first 8 bytes (64 bits) of the hash as a signed 64-bit integer
    # '>' means big-endian, 'q' means signed long long (64-bit integer)
    # This automatically handles negative numbers when the sign bit is set.
    (signed_64bit_int,) = unpack(">q", hash_digest[:8])
    return signed_64bit_int


def timestamp_from_zip_info(zip_info: ZipInfo) -> int:
    try:
        return int(datetime(*zip_info.date_time).timestamp())
    except Exception:
        return 0
