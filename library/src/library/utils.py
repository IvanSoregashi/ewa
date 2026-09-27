from collections import Counter


def is_sublist(sublist, superlist):
    """This does consider duplicates"""

    subcount = Counter(sublist)
    supercount = Counter(superlist)

    for item, count in subcount.items():
        if count > supercount[item]:
            return False

    return True


def remove_none_values(items: dict) -> dict:
    return {
        key: remove_none_values(value) if isinstance(value, dict) else value
        for key, value in items.items()
        if value is not None
    }
