import mimetypes
from pathlib import Path

# Explicitly load our standard mime.types file
# so it is correctly instantiated upon package import.
_mime_types_file = Path(__file__).parent / "mime.types"
if _mime_types_file.exists():
    mimetypes.init(files=[str(_mime_types_file)])

# Enforce some explicit modern standards for common files that might be missing
# from local registries or older mimeData.
mimetypes.add_type("application/toml", ".toml")
mimetypes.add_type("application/yaml", ".yaml")
mimetypes.add_type("application/x-ipynb+json", ".ipynb")
mimetypes.add_type("text/plain", ".ini")
mimetypes.add_type("font/sfnt", ".sfnt")
mimetypes.add_type("image/heic", ".heic")
mimetypes.add_type("image/heif", ".heif")
mimetypes.add_type("application/vnd.ms-fontobject", ".eot")

def guess_file_type(path: str | Path) -> str | None:
    """
    Guess the media type of a file based on its filename or path.

    Args:
        path: The file path or name to guess file type from.

    Returns:
        The guessed media type as a string, or None if it cannot be determined.
    """
    path = Path(path)

    if path.suffix.lower() == ".ncx":
        return "application/x-dtbncx+xml"
    if path.suffix.lower() == ".opf":
        return "application/oebps-package+xml"
    if path.name == "mimetype":
        return "text/plain"

    guessed = mimetypes.guess_file_type(path)[0]

    # Coerce legacy or system-specific types to the modern standard
    if guessed:
        if guessed in ("image/pjpeg", "image/x-citrix-jpeg"):
            return "image/jpeg"
        if guessed in ("application/zip-compressed", "application/x-zip-compressed"):
            return "application/zip"
        if guessed in ("application/x-rar-compressed",):
            return "application/vnd.rar"
        if guessed in ("application/x-msdownload",):
            return "application/vnd.microsoft.portable-executable"
        if guessed in ("text/xml",):
            return "application/xml"
        if guessed in ("application/javascript",):
            return "text/javascript"

    return guessed
