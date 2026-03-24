import logging
import tempfile
from collections.abc import Generator, Iterable, Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Self
from zipfile import is_zipfile, ZipFile, ZIP_STORED, ZIP_DEFLATED, ZipInfo

from library.epub.media_type import MediaType
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, path: str | Path) -> None:
        """Initialize an EPUB object with path to epub file or a directory."""
        self.path = Path(path)
        self.source: SourceProtocol | None = None
        if self.path.is_dir():
            self.source = DirectorySource(path, skip_dirs=True)
        elif is_zipfile(path):
            self.source = ZipFileSource(path, skip_dirs=True)
        else:
            raise ValueError("Path must be a directory or a zipfile.")
        if self.source is None:
            # TODO: None for creating new epub? or pass in the not yet existing path
            raise FileNotFoundError(f"Source {path} was not recognized as directory or epub(zipfile).")
        self._confirmed_epub: bool = False
        self.skip_dirs = True

    def confirm_mimetype(self) -> bool:
        """Confirm that this source is a valid EPUB by checking the mimetype file.

        Validates:
            1. A file named 'mimetype' exists at the archive root.
            2. Its content is exactly 'application/epub+zip'.
            3. For ZIP sources, it is stored uncompressed (ZIP_STORED).

        Returns:
            True if all checks pass.

        Raises:
            ValueError: If any check fails.
        """
        with self.source.open():
            try:
                mimetype_info = self.source.getinfo("mimetype")
            except KeyError:
                raise ValueError("EPUB is missing the 'mimetype' file.")

            # Check compression: must be ZIP_STORED (0) or None (directory source)
            if mimetype_info.compress_type not in (ZIP_STORED, None):
                raise ValueError(
                    f"EPUB 'mimetype' file must be stored uncompressed (ZIP_STORED), "
                    f"got compress_type={mimetype_info.compress_type}."
                )

            content = self.source.read_bytes(mimetype_info)
            if content.strip() != b"application/epub+zip":
                raise ValueError(
                    f"EPUB 'mimetype' file must contain 'application/epub+zip', "
                    f"got {content!r}."
                )

        self._confirmed_epub = True
        return True

    def extract_to(self, dest_dir: str | Path | None = None) -> EPUB:
        if dest_dir is None:
            dest_dir = Path(tempfile.mkdtemp())
        dest_dir.mkdir(parents=True, exist_ok=True)
        self.source.extract_all(destination=dest_dir)
        return EPUB(dest_dir)

    def package_into(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None):
        exclude_members = [m.filename if isinstance(m, ZipInfo) else m for m in (exclude_members or [])]
        destination = Path(destination)
        self.confirm_mimetype()
        if destination.suffix.lower() != ".epub":
            if destination.is_dir():
                destination = destination / self.path.name
            else:
                raise NotADirectoryError(f"Path {destination} is neither a directory nor a epub.")
        if destination.suffix.lower() == ".epub":
            if destination.exists():
                raise FileExistsError(f"File {destination} already exists.")
            if not destination.parent.exists():
                raise FileNotFoundError(f"Directory {destination.parent} does not exist.")

        try:
            with self.source.open(), ZipFile(destination, "w", compression=ZIP_DEFLATED) as zipf:
                mimetype_info = self.source.getinfo("mimetype")
                self.source.write_to_zipfile(zipf, mimetype_info, compress_type=ZIP_STORED)

                for zip_info in self.source.infolist():
                    # TODO: ZIP_STORED for images (already compressed)
                    # TODO: BUFFERED shutil.copyfileobj for big files
                    if zip_info.filename in exclude_members:
                        continue
                    if zip_info.filename == "mimetype":
                        continue
                    if self.skip_dirs and zip_info.is_dir():
                        continue
                    self.source.write_to_zipfile(zipf, zip_info)
        except Exception as e:
            logger.error(f"package_into: failed to compress into EPUB: {e}")
            raise e

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]:

        with self.source.open():
            yield self
        self.package_into(destination)

    def scan_resources(self) -> 'ResourceIndex':
        """Scan the EPUB source and build a ResourceIndex from all files."""
        with self.source.open():
            resources = [
                EPUBResource(info, self.source.read_bytes)
                for info in self.source.infolist()
            ]
        return ResourceIndex(resources)


class EPUBResource:
    """Represents a single file in an EPUB archive."""

    def __init__(self, info: ZipInfo, read_bytes_func: Callable[[str | ZipInfo], bytes]) -> None:
        self.info = info
        self.media_type = MediaType.from_filename(info.filename)
        self._content: bytes | None = None
        self._read_bytes_func = read_bytes_func

        # Manifest attributes (populated during OPF enrichment)
        self.id: str | None = None
        self.properties: list[str] | None = None
        self.href: str | None = None
        self.fallback: str | None = None
        self.media_overlay: str | None = None

        # Spine attributes (populated during OPF enrichment)
        self.spine_index: int | None = None
        self.linear: str | None = None

        # Guide attributes (populated during OPF enrichment)
        self.guide_type: str | None = None
        self.guide_title: str | None = None

        # Navigation label (populated during NCX/NAV enrichment)
        self.toc_label: str | None = None

    @property
    def loaded(self) -> bool:
        return self._content is not None

    @property
    def content(self) -> bytes:
        if self._content is None:
            self._content = self._read_bytes_func(self.info)
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        self._content = value

    @property
    def filename(self) -> str:
        return self.info.filename

    @filename.setter
    def filename(self, value: str) -> None:
        self.info.filename = value

    @property
    def is_spine_item(self) -> bool:
        return self.spine_index is not None

    def __repr__(self) -> str:
        return f"EPUBResource({self.filename!r}, media_type={str(self.media_type)})"


class ResourceIndex:
    """Auto-indexed collection of EPUBResource objects.

    Provides O(1) lookup by filename and by manifest ID,
    while maintaining a stable list for iteration.
    """

    def __init__(self, resources: list[EPUBResource] | None = None) -> None:
        self._items: list[EPUBResource] = []
        self._by_path: dict[str, EPUBResource] = {}
        self._by_id: dict[str, EPUBResource] = {}
        if resources:
            for r in resources:
                self.add(r)

    def add(self, resource: EPUBResource) -> None:
        """Add a resource to the index."""
        self._items.append(resource)
        self._by_path[resource.filename] = resource
        if resource.id is not None:
            self._by_id[resource.id] = resource

    def remove(self, resource: EPUBResource) -> None:
        """Remove a resource from the index."""
        self._items.remove(resource)
        self._by_path.pop(resource.filename, None)
        if resource.id is not None:
            self._by_id.pop(resource.id, None)

    def by_path(self, path: str) -> EPUBResource | None:
        """Look up a resource by its filename/path."""
        return self._by_path.get(path)

    def by_id(self, id: str) -> EPUBResource | None:
        """Look up a resource by its manifest ID."""
        return self._by_id.get(id)

    def rebuild_id_index(self) -> None:
        """Rebuild the ID index (call after OPF enrichment populates IDs)."""
        self._by_id = {r.id: r for r in self._items if r.id is not None}

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item: EPUBResource | str) -> bool:
        if isinstance(item, str):
            return item in self._by_path
        return item in self._items

    def __repr__(self) -> str:
        return f"ResourceIndex({len(self._items)} resources)"
