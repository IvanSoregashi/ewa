from pathlib import Path

from library.epub.utils import string_to_int_hash64


def prefix_name_with_hash(path: str | Path, content: bytes | None = None) -> Path:
    if content is None:
        if isinstance(path, str) or (isinstance(path, Path) and not path.exists()):
            raise ValueError("Cannot compute hash with provided data")
    path: Path = Path(path)
    content_bytes = content or path.read_bytes()
    _hash = string_to_int_hash64(content_bytes)
    return path.with_stem(f"{_hash}_{path.stem}")
