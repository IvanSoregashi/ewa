import logging
from datetime import datetime
from hashlib import md5
from struct import unpack
from zipfile import ZipInfo

logger = logging.getLogger(__name__)

SQLITE_MAX_INT = 2**63 - 1
SQLITE_MIN_INT = -(2**63)
SIXTY_FOUR_BIT_MASK = 0xFFFFFFFFFFFFFFFF


def ts_to_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def bt_to_mb(size_in_bytes: int) -> str:
    return f"{size_in_bytes / (1024 * 1024):.2f} mb"


def to_hash(data: str | bytes) -> bytes:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return md5(data).digest()


def to_hex_hash(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return md5(data).hexdigest()


def string_to_int_hash64(data: str | bytes) -> int:
    """returns a 64-bit integer hash"""
    return int(to_hex_hash(data), 16) % SQLITE_MAX_INT


def string_to_int_hash(data: str | bytes) -> int:
    """
    Generates a 64-bit signed integer hash from a string,
    utilizing the full SQLite INTEGER range (positive and negative).
    """
    # 1. Generate the 128-bit MD5 hash
    hash_digest = to_hash(data)

    # 2. Unpack the first 8 bytes (64 bits) of the hash as a signed 64-bit integer
    # '>' means big-endian, 'q' means signed long long (64-bit integer)
    # This automatically handles negative numbers when the sign bit is set.
    (signed_64bit_int,) = unpack(">q", hash_digest[:8])
    return signed_64bit_int


def timestamp_from_zip_info(zip_info: ZipInfo) -> int:
    try:
        return int(datetime(*zip_info.date_time).timestamp())
    except Exception as e:
        logger.error(f"timestamp_from_zip_info error: {e}")
        return 0
