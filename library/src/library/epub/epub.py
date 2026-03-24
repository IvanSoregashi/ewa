import logging
import tempfile
from collections.abc import Generator, Iterable, Callable
from contextlib import contextmanager
from pathlib import Path
from posixpath import join as posix_join, dirname as posix_dirname
from typing import Self
from zipfile import is_zipfile, ZipFile, ZIP_STORED, ZIP_DEFLATED, ZipInfo

from library.epub.media_type import MediaType, Category
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol
from library.epub.utils import strip_fragment
from library.epub.xml_literals import CONTAINER_PATH
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NCXDocument, NavPoint
from library.epub.xml_models.nav_model import NavDocument, NavListItem
from library.epub.xml_models.opf_model import PackageDocument

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
        self._core: EpubCore | None = None

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
        if self._confirmed_epub:
            return True
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

    @property
    def core(self) -> 'EpubCore':
        """Lazily initialize and return the EpubCore for this EPUB."""
        if self._core is None:
            self.confirm_mimetype()
            resources = self.scan_resources()
            self._core = EpubCore(resources)
        return self._core


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


class EpubCore:
    """Manages the structural core of an EPUB archive.

    Initialized with a ResourceIndex (from EPUB.scan_resources()), it parses
    the container, OPF, NCX, and NAV documents to enrich resources with
    metadata and provide convenient access to core files.
    """

    def __init__(self, resources: ResourceIndex) -> None:
        self.resources = resources

        # Core documents (populated during parsing)
        self._opf_path: str | None = None
        self._opf: PackageDocument | None = None
        self._ncx: NCXDocument | None = None
        self._nav: NavDocument | None = None

        # Core resource references (populated during enrichment)
        self.mimetype_resource: EPUBResource | None = None
        self.container_resource: EPUBResource | None = None
        self.opf_resource: EPUBResource | None = None
        self.ncx_resource: EPUBResource | None = None
        self.nav_resource: EPUBResource | None = None
        self.cover_resource: EPUBResource | None = None

        # Run the parsing pipeline
        self._parse_container()
        self._parse_opf()
        self._enrich_from_opf()
        self._enrich_from_ncx()
        self._enrich_from_nav()

    # -----------------------------------------------------------------------
    # Parsing pipeline
    # -----------------------------------------------------------------------

    def _parse_container(self) -> None:
        """Parse META-INF/container.xml to find the OPF path."""
        self.mimetype_resource = self.resources.by_path("mimetype")
        self.container_resource = self.resources.by_path(CONTAINER_PATH)
        if self.container_resource is None:
            raise ValueError(f"EPUB is missing '{CONTAINER_PATH}'.")

        container = ContainerDocument.from_xml(self.container_resource.content)
        self._opf_path = container.opf_path
        if self._opf_path is None:
            raise ValueError("container.xml does not specify an OPF rootfile.")

    def _parse_opf(self) -> None:
        """Parse the OPF package document."""
        if self._opf_path is None:
            raise ValueError("OPF path not set. Call _parse_container first.")

        self.opf_resource = self.resources.by_path(self._opf_path)
        if self.opf_resource is None:
            raise ValueError(f"OPF file '{self._opf_path}' not found in resources.")

        self._opf = PackageDocument.from_xml(self.opf_resource.content)

    def _resolve_href(self, href: str) -> str:
        """Resolve a manifest href (relative to OPF) to an absolute EPUB path."""
        href = strip_fragment(href)
        opf_dir = posix_dirname(self._opf_path)
        if opf_dir:
            return posix_join(opf_dir, href)
        return href

    # -----------------------------------------------------------------------
    # OPF enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_opf(self) -> None:
        """Enrich resources with manifest, spine, and guide data from the OPF."""
        if self._opf is None:
            return

        # --- Manifest ---
        for item in self._opf.manifest.items:
            abs_path = self._resolve_href(item.href)
            resource = self.resources.by_path(abs_path)
            if resource is None:
                logger.warning(f"Manifest item '{item.id}' references missing file: {abs_path}")
                continue

            resource.id = item.id
            resource.href = item.href
            resource.fallback = item.fallback
            resource.media_overlay = getattr(item, 'overlay', None)

            if item.properties:
                resource.properties = item.properties.split()
            else:
                resource.properties = []

            # Override media type from manifest if present
            if item.media_type:
                resource.media_type = MediaType(item.media_type)

        # Rebuild ID index now that IDs are populated
        self.resources.rebuild_id_index()

        # --- Spine ---
        for idx, itemref in enumerate(self._opf.spine.itemrefs):
            resource = self.resources.by_id(itemref.idref)
            if resource is None:
                logger.warning(f"Spine itemref '{itemref.idref}' references unknown manifest ID.")
                continue
            resource.spine_index = idx
            resource.linear = itemref.linear

        # --- Guide ---
        if self._opf.guide:
            for ref in self._opf.guide.references:
                abs_path = self._resolve_href(ref.href)
                resource = self.resources.by_path(abs_path)
                if resource is None:
                    logger.warning(f"Guide reference '{ref.type}' references missing file: {abs_path}")
                    continue
                resource.guide_type = ref.type
                resource.guide_title = ref.title

        # --- Identify core resources from manifest data ---
        self._identify_core_resources()

    def _identify_core_resources(self) -> None:
        """Identify NCX, NAV, and cover resources from enriched manifest data."""
        # NCX: found via spine@toc attribute or by media type
        if self._opf.spine.toc:
            self.ncx_resource = self.resources.by_id(self._opf.spine.toc)
        if self.ncx_resource is None:
            for r in self.resources:
                if r.media_type == MediaType.NCX:
                    self.ncx_resource = r
                    break

        # NAV: found via manifest properties="nav"
        for r in self.resources:
            if r.properties and "nav" in r.properties:
                self.nav_resource = r
                break

        # Cover image: EPUB 3 properties="cover-image" or EPUB 2 meta
        for r in self.resources:
            if r.properties and "cover-image" in r.properties:
                self.cover_resource = r
                break
        if self.cover_resource is None and self._opf:
            for meta in self._opf.metadata.metas:
                name = getattr(meta, 'name', None)
                content = getattr(meta, 'content_attr', None)
                if name == "cover" and content:
                    self.cover_resource = self.resources.by_id(content)
                    break

    # -----------------------------------------------------------------------
    # NCX enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_ncx(self) -> None:
        """Enrich resources with toc_label from the NCX document."""
        if self.ncx_resource is None:
            return

        self._ncx = NCXDocument.from_xml(self.ncx_resource.content)
        if self._ncx.nav_map is None:
            return

        self._walk_ncx_navpoints(self._ncx.nav_map.nav_points)

    def _walk_ncx_navpoints(self, navpoints: list[NavPoint]) -> None:
        """Recursively walk NCX navPoints and set toc_label on resources."""
        for point in navpoints:
            if point.content and point.content.src:
                abs_path = self._resolve_href(strip_fragment(point.content.src))
                resource = self.resources.by_path(abs_path)
                if resource and resource.toc_label is None:
                    label = None
                    if point.nav_label and point.nav_label.text:
                        label = point.nav_label.text
                    resource.toc_label = label

            if point.nav_points:
                self._walk_ncx_navpoints(point.nav_points)

    # -----------------------------------------------------------------------
    # NAV enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_nav(self) -> None:
        """Enrich resources with toc_label from the NAV document."""
        if self.nav_resource is None:
            return

        self._nav = NavDocument.from_xml(self.nav_resource.content)

        for nav_elem in self._nav.body.navs:
            if nav_elem.epub_type and "toc" in nav_elem.epub_type:
                if nav_elem.ol:
                    self._walk_nav_items(nav_elem.ol.items)
                return

    def _walk_nav_items(self, items: list[NavListItem]) -> None:
        """Recursively walk NAV list items and set toc_label on resources."""
        for item in items:
            if item.link and item.link.href:
                abs_path = self._resolve_href(strip_fragment(item.link.href))
                resource = self.resources.by_path(abs_path)
                if resource and resource.toc_label is None:
                    resource.toc_label = item.link.text

            if item.ol:
                self._walk_nav_items(item.ol.items)

    # -----------------------------------------------------------------------
    # Convenience properties
    # -----------------------------------------------------------------------

    @property
    def opf(self) -> PackageDocument | None:
        return self._opf

    @property
    def ncx(self) -> NCXDocument | None:
        return self._ncx

    @property
    def nav(self) -> NavDocument | None:
        return self._nav

    @property
    def opf_path(self) -> str | None:
        return self._opf_path

    @property
    def styles(self) -> list[EPUBResource]:
        """All CSS stylesheets in the EPUB."""
        return [r for r in self.resources if r.media_type.category == Category.STYLE]

    @property
    def fonts(self) -> list[EPUBResource]:
        """All font files in the EPUB."""
        return [r for r in self.resources if r.media_type.category == Category.FONT]

    @property
    def images(self) -> list[EPUBResource]:
        """All image files in the EPUB."""
        return [r for r in self.resources if r.media_type.category == Category.IMAGE]

    @property
    def spine(self) -> list[EPUBResource]:
        """Resources in spine order."""
        return sorted(
            [r for r in self.resources if r.is_spine_item],
            key=lambda r: r.spine_index,
        )
