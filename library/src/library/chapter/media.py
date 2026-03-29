from collections.abc import Callable
from pathlib import Path
from typing import Self

from library.epub.media_type import MediaType


class MediaResource:
    """Represents a related media file (image, font, etc.) for a Chapter.
    
    Supports lazy loading of content bytes via a provided callback function.
    """

    def __init__(
        self,
        filename: str,
        media_type: MediaType | str,
        read_bytes_func: Callable[[], bytes] | None = None,
        content: bytes | None = None,
    ) -> None:
        self.filename = filename
        self.media_type = (
            media_type if isinstance(media_type, MediaType) else MediaType(media_type)
        )
        self._content = content
        self._read_bytes_func = read_bytes_func

    def __repr__(self) -> str:
        return f"MediaResource({self.filename!r}, media_type={str(self.media_type)})"

    @property
    def loaded(self) -> bool:
        """Returns True if the content bytes are already in memory."""
        return self._content is not None

    @property
    def content(self) -> bytes:
        """Returns the content bytes, loading them if necessary."""
        if self._content is None:
            if self._read_bytes_func is None:
                raise ValueError(f"MediaResource {self.filename!r} has no content and no read_bytes_func.")
            self._content = self._read_bytes_func()
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        self._content = value

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        """Create a MediaResource from a local file path (lazy loaded)."""
        path = Path(path)
        media_type = MediaType.from_filename(path) or "application/octet-stream"
        
        def read_file() -> bytes:
            return path.read_bytes()
            
        return cls(path.name, media_type, read_bytes_func=read_file)

    @classmethod
    def from_bytes(cls, filename: str, content: bytes, media_type: MediaType | str | None = None) -> Self:
        """Create a MediaResource from bytes in memory."""
        if media_type is None:
            media_type = MediaType.from_filename(filename) or "application/octet-stream"
        return cls(filename, media_type, content=content)
