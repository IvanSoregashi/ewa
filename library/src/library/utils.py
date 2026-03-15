import fnmatch
import string

from collections import Counter
from collections.abc import Callable
from pathlib import Path


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
