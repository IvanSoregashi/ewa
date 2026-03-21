import io
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
from typing import overload

logger = logging.getLogger(__name__)
mimetypes_path = Path(__file__).parent / "mime.types"


def parse_mime_types(path: Path | str) -> dict[str, str]:
    """
    Parses a mime.types file into a nested dictionary structure.
    Structure: { filetype: mimetype }
    Example: {"ice": "x-conference/x-cooltalk"}
    """
    path = Path(path)
    parsed = {}
    if not path.exists():
        return {}

    for line in path.read_text(encoding="utf-8").splitlines():
        strip_line = line.strip()
        if not strip_line or strip_line.startswith("#"):
            continue
        parts = strip_line.split()
        if len(parts) < 2:
            logger.warning(f"failed to parse line '{strip_line}'")
            continue

        mimetype = parts[0]
        filetypes = parts[1:]

        for filetype in filetypes:
            parsed[filetype] = mimetype

    return parsed


@overload
def write_mime_types(data: dict[str, str]) -> str: ...
@overload
def write_mime_types(data: dict[str, str], file: None) -> str: ...
@overload
def write_mime_types(data: dict[str, str], file: str | Path) -> None: ...


def write_mime_types(data: dict[str, str], file: str | Path | None = None) -> str | None:
    categories = list(sorted(set(mimetype.split("/")[0] if "/" in mimetype else "other" for mimetype in data.values())))

    max_mimetype_len = 0

    mimetype_to_filetype = defaultdict(set)
    for filetype, mimetype in data.items():
        mimetype_to_filetype[mimetype].add(filetype)
        max_mimetype_len = max(max_mimetype_len, len(mimetype))

    padding = max_mimetype_len + 4

    mimetypes = io.StringIO(newline="\n")
    try:
        if file is not None:
            mimetypes = Path(file).open(mode="w", encoding="utf-8", newline="\n")
        for category in categories:
            mimetypes.write(f"\n# =========================================\n")
            mimetypes.write(f"# {category.upper()} TYPES\n")
            mimetypes.write(f"# =========================================\n\n")

            category_mimetypes = sorted(
                [
                    mimetype
                    for mimetype in mimetype_to_filetype.keys()
                    if (mimetype.startswith(f"{category}/") if category != "other" else "/" not in mimetype)
                ]
            )

            for mimetype in category_mimetypes:
                filetypes = " ".join(sorted(mimetype_to_filetype[mimetype]))
                mimetypes.write(f"{mimetype.ljust(padding)}{filetypes}\n")
        if file is not None:
            mimetypes.close()
    except Exception as e:
        logging.error(f"error on writing mimetypes to {str(file) if file is not None else 'StringIO'}: {e}")
        if file is not None:
            mimetypes.close()

    return mimetypes.getvalue() if file is None else None


@contextmanager
def modify_mime_types():
    mimetypes = parse_mime_types(mimetypes_path)
    yield mimetypes
    write_mime_types(mimetypes, mimetypes_path)
