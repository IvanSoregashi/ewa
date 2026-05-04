from typing import TypeVar

T = TypeVar("T")


def require(value: T | None, description: str = "Object") -> T:
    """Ensures a value is not None, returning it for clean assignment."""
    if value is None:
        raise ValueError(f"{description} failed the existence check.")
    return value
