"""
EpubCore — manages the structural ("core") components of an EPUB.

Responsible for:
    1. Parsing container.xml to locate the OPF.
    2. Enriching EPUBResource objects from the OPF manifest, spine, and guide.
    3. Enriching EPUBResource objects from the NCX and NAV documents.
    4. Providing convenient access to core resources (OPF, NCX, NAV, cover, styles, fonts).
"""

import logging
from posixpath import join as posix_join, dirname as posix_dirname

from library.epub.epub import EPUBResource, ResourceIndex
from library.epub.media_type import MediaType, Category
from library.epub.utils import strip_fragment
from library.epub.xml_literals import CONTAINER_PATH
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NCXDocument, NavPoint
from library.epub.xml_models.nav_model import NavDocument, NavListItem
from library.epub.xml_models.opf_model import PackageDocument

logger = logging.getLogger(__name__)


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
            # Fallback: find by media type
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
            # EPUB 2 fallback: <meta name="cover" content="image-id"/>
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

            # Recurse into nested navPoints
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

        # Find the <nav epub:type="toc"> element
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

            # Recurse into nested lists
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
