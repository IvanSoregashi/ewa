import fnmatch
import string

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

strPath = str | Path
StrPathT = TypeVar("StrPathT", str, Path, strPath)


def is_sublist(sublist, superlist):
    """This does consider duplicates"""

    subcount = Counter(sublist)
    supercount = Counter(superlist)

    for item, count in subcount.items():
        if count > supercount[item]:
            return False

    return True


def sanitize_filename(unsafe_string):
    """Sanitizes a string to be safe for use as a filename."""
    safe_chars = set(string.printable) - set('/\\:*?"<>|')
    cleaned_filename = "".join(c for c in unsafe_string if c in safe_chars)

    return cleaned_filename.strip()


def ignore_absolute_paths(absolute_paths: list[Path]) -> Callable[[str, list[str]], set[str]]:
    """Function that can be used as copytree() ignore parameter.
    based on shutil.ignore_patterns

    Args:
        absolute_paths: a sequence of absolute paths to be skipped when copying data.
    """
    dictionary = {}
    for absolute_path in absolute_paths:
        dictionary.setdefault(str(absolute_path.parent), list()).append(absolute_path.name)

    def _ignore_patterns(path: str, names: list[str]) -> set[str]:
        ignored_names = []
        patterns = dictionary.get(path, [])
        for pattern in patterns:
            ignored_names.extend(fnmatch.filter(names, pattern))
        return set(ignored_names)

    return _ignore_patterns


def verify_destination(destination: str | Path, filename: str, suffix: str| None = None) -> Path:
    destination: Path = Path(destination)
    filename: Path = Path(filename)

    if suffix is None and filename.suffix:
        suffix = filename.suffix.lower()

    if not suffix and not destination.suffix:
        raise ValueError("Suffix must be provided.")

    if suffix and destination.suffix.lower() != suffix:
        if not destination.is_dir():
            raise NotADirectoryError(f"Path {destination} is neither a directory nor a epub.")
        destination = destination / filename

    if destination.is_dir():
        raise IsADirectoryError(f"Path {destination} is a directory.")

    if destination.exists():
        raise FileExistsError(f"File {destination} already exists.")

    if not destination.parent.exists():
        destination.parent.mkdir(parents=True)

    return destination
