import string

from collections import Counter


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
