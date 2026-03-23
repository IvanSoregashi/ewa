import mimetypes
from pathlib import Path
from library.filetypes.mimetypes_utils import parse_mime_types, write_mime_types

# Explicitly load our standard mime.types file
# so it is correctly instantiated upon package import.
_mime_types_file = Path(__file__).parent / "mime.types"
if _mime_types_file.exists():
    mimetypes.init(files=[str(_mime_types_file)])


def guess_file_type(path: str | Path) -> str | None:
    """
    Guess the media type of a file based on its filename or path.

    Args:
        path: The file path or name to guess file type from.

    Returns:
        The guessed media type as a string, or None if it cannot be determined.
    """
    path = Path(path)

    if path.name == "mimetype":
        return "text/plain"

    return mimetypes.guess_file_type(path)[0]
