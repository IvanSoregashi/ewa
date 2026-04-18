import logging
from enum import StrEnum
from posixpath import join as posix_join, dirname as posix_dirname
from typing import Protocol

from library.epub.media_type import MediaType, Category, ResourceType
from library.epub.resources import ResourceIndex, EPUBResource
from library.epub.utils import strip_fragment
from library.epub.xml_literals import FileName
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NCXDocument, NavPoint
from library.epub.xml_models.nav_model import NavDocument, NavListItem
from library.epub.xml_models.package_document import PackageDocument
from tests.test_opf_document import opf_path

logger = logging.getLogger("epub_core")

# os.path.relpath - relative path including the walkback os.path.relpath(target, start)

class EpubSpecification(StrEnum):
    UNKNOWN = "UNKNOWN"
    SERENE_PANDA_ENCRYPTED = "SERENE_PANDA_ENCRYPTED"
    SERENE_PANDA_UNENCRYPTED = "SERENE_PANDA_UNENCRYPTED"
    ASIA_NOVEL = "ASIA_NOVEL"
    CALIBRE = "CALIBRE"
    WEB_TO_EPUB = "WEB_TO_EPUB"
    EPUB_PRESS = "EPUB_PRESS"
    EWA_ONE = "EWA_ONE"


class EpubCore:
    """Manages the structural core of an EPUB archive.

    Initialized with a ResourceIndex (from EPUB.scan_resources()), it parses
    the container, OPF, NCX, and NAV documents to enrich resources with
    metadata and provide convenient access to core files.
    """

    def __init__(self, resources: ResourceIndex) -> None:
        logger.debug(f"Initializing epub_core with {len(resources)} resources.")
        self.resources = resources

        # Core documents (populated during parsing)
        self._opf_path: str | None = None
        self.package: PackageDocument | None = None
        self.ncx: NCXDocument | None = None
        self.nav: NavDocument | None = None

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

        # --- Identify core resources from manifest data ---
        self._identify_core_resources()

        self._enrich_from_ncx()
        self._enrich_from_nav()

    def sync(self) -> None:
        """Serialize all core models (package, ncx, nav) back to their respective resources."""
        if self.package and self.opf_resource:
            self.opf_resource.content = self.package.to_xml_bytes()
        if self.ncx and self.ncx_resource:
            self.ncx_resource.content = self.ncx.to_xml_bytes()
        if self.nav and self.nav_resource:
            self.nav_resource.content = self.nav.to_xml_bytes()

    # -----------------------------------------------------------------------
    # Parsing pipeline
    # -----------------------------------------------------------------------

    def _parse_container(self) -> None:
        """Parse META-INF/container.xml to find the OPF path."""
        logger.debug(f"parsing {FileName.CONTAINER!s} file.")
        self.mimetype_resource = self.resources.by_path(FileName.MIMETYPE)
        self.container_resource = self.resources.by_path(FileName.CONTAINER)
        if self.container_resource is None:
            raise ValueError(f"EPUB is missing '{FileName.CONTAINER!s}'.")

        container = ContainerDocument.from_xml_bytes(self.container_resource.content)
        if len(container.rootfiles) > 1:
            logger.warning(f"{self} has {len(container.rootfiles)} rootfiles. Using the first one.")
        logger.debug(f"found {container.opf_paths!r} paths, assigning the {container.opf_path!r}.")
        self._opf_path = container.opf_path
        if self._opf_path is None:
            raise ValueError("container.xml does not specify an OPF rootfile.")

    def _parse_opf(self) -> None:
        """Parse the OPF package document."""
        logger.debug(f"parsing OPF({self._opf_path}) file.")
        if self._opf_path is None:
            raise ValueError("OPF path not set. Call _parse_container first.")

        self.opf_resource = self.resources.by_path(self._opf_path)
        if self.opf_resource is None:
            raise ValueError(f"OPF file '{self._opf_path}' not found in resources.")

        self.package = PackageDocument.from_xml_bytes(self.opf_resource.content)

    def __absolute_from_relative_href(self, href: str, source_file: str) -> str:
        """Resolve a manifest href (relative to OPF by default) to an absolute EPUB path."""
        href = strip_fragment(href)
        source_dir = posix_dirname(source_file)
        if source_dir:
            href = posix_join(source_dir, href)
        return href

    # -----------------------------------------------------------------------
    # OPF enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_opf(self) -> None:
        """Enrich resources with manifest, spine, and guide data from the OPF."""
        logger.debug(f"enriching resources from opf data")
        opf_path = self._opf_path
        if self.package is None:
            raise

        # --- Manifest ---
        logger.debug(f"processing {len(self.package.manifest.items)} manifest items")
        for item in self.package.manifest.items:
            abs_path = self.__absolute_from_relative_href(item.href, opf_path)
            resource = self.resources.by_path(abs_path)
            if resource is None:
                logger.warning(f"Manifest item '{item.id}' references missing file: {abs_path}")
                continue

            resource.manifest_item = item

            if item.properties and "nav" in item.properties:
                resource.resource_type = ResourceType.CORE
                logger.debug(f"found nav file: {resource}")
                if self.nav_resource is not None:
                    logger.warning(f"Found second nav file old: {self.nav_resource.filename}, new: {resource.filename}")
                self.nav_resource = resource

            if resource.media_type != item.media_type:
                logger.warning(f"Media type mismatch {abs_path}, {resource.media_type}, {item.media_type}")
            # Override media type from manifest if present
            # if item.media_type:
            #     resource.media_type = MediaType(item.media_type)

        # Rebuild ID index now that IDs are populated
        self.resources.rebuild_id_index()

        # --- Spine ---
        logger.debug(f"processing {len(self.package.spine.itemrefs)} spine items")
        for itemref in self.package.spine.itemrefs:
            resource = self.resources.by_id(itemref.idref)
            if resource is None:
                logger.warning(f"Spine itemref '{itemref.idref}' references unknown manifest ID.")
                continue
            resource.spine_item_ref = itemref

        # --- Guide ---
        if self.package.guide:
            logger.debug(f"processing {len(self.package.guide.references)} guide references")
            for ref in self.package.guide.references:
                abs_path = self.__absolute_from_relative_href(ref.href, opf_path)
                resource = self.resources.by_path(abs_path)
                if resource is None:
                    logger.warning(f"Guide reference '{ref.type}' references missing file: {abs_path}")
                    continue
                resource.guide_reference = ref

    def _identify_core_resources(self) -> None:
        """Identify NCX, NAV, and cover resources from enriched manifest data."""
        logger.debug("identifying NCX, NAV, and cover resources")
        # TODO: dissolve this func
        # NCX: found via spine@toc attribute or by media type
        logger.debug("looking for NCX file")
        if self.package.spine.toc:
            self.ncx_resource = self.resources.by_id(self.package.spine.toc)
        if self.ncx_resource is None:
            for resource in self.resources:
                if self.ncx_resource is None and resource.media_type == MediaType.NCX:
                    self.ncx_resource = resource
                    break
        logger.debug(f"ncx_resource: {self.ncx_resource}")

        logger.debug(f"looking for cover file EPUB 3 style")
        # TODO: Cover logic - make either a chapter, or core.
        # Cover image: EPUB 3 properties="cover-image" or EPUB 2 meta
        for resource in self.resources:
            if resource.manifest_item and resource.manifest_item.properties and "cover-image" in resource.manifest_item.properties:
                self.cover_resource = resource
                break
        if self.cover_resource is None and self.package:
            logger.debug(f"looking for cover file EPUB 2 style")
            for meta in self.package.metadata.metas:
                name = getattr(meta, "name", None)
                content = getattr(meta, "content", None)
                if name == "cover" and content:
                    self.cover_resource = self.resources.by_id(content)
                    break
        logger.debug(f"cover_resource: {self.cover_resource}")

    # -----------------------------------------------------------------------
    # NCX enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_ncx(self) -> None:
        """Enrich resources with toc_label from the NCX document."""
        logger.debug("enriching resources from NCX document")
        if self.ncx_resource is None:
            logger.warning(f"NCX document not found, skipping NCX enrichment")
            return

        self.ncx = NCXDocument.from_xml_bytes(self.ncx_resource.content)
        if self.ncx.nav_map is None:
            logger.warning(f"NavMap not found in NCX document, skipping NCX enrichment")
            return

        self._walk_ncx_navpoints(self.ncx.nav_map.nav_points)

    def _walk_ncx_navpoints(self, nav_points: list[NavPoint]) -> None:
        """Recursively walk NCX navPoints and set toc_label on resources."""
        ncx_path = self.ncx_resource.filename
        logger.debug(f"walking NCX navPoints ({len(nav_points)})")
        for nav_point in nav_points:
            if nav_point.content and nav_point.content.src:
                rel_path = strip_fragment(nav_point.content.src)
                abs_path = self.__absolute_from_relative_href(rel_path, ncx_path)
                resource = self.resources.by_path(abs_path)
                if resource is not None:
                    if resource.ncx_nav_point is None:
                        resource.ncx_nav_point = nav_point
                    else:
                        logger.warning(f"NCX Path {nav_point.content.src} found several times"
                                       f" ({resource.ncx_nav_point.nav_label.text}, {nav_point.nav_label.text})")
                else:
                    logger.warning(f"NCX Path {nav_point.content.src} not found in NCX")

            if nav_point.nav_points:
                self._walk_ncx_navpoints(nav_point.nav_points)

    # -----------------------------------------------------------------------
    # NAV enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_nav(self) -> None:
        """Enrich resources from the NAV document."""
        logger.debug(f"enriching resources from NAV document")
        if self.nav_resource is None:
            logger.warning(f"NAV document not found, skipping NAV enrichment")
            return

        self.nav = NavDocument.from_xml_bytes(self.nav_resource.content)

        for nav_elem in self.nav.body.navs:
            self._walk_nav_items(nav_elem.epub_type, nav_elem.ol.items)

    def _walk_nav_items(self, epub_type: str, items: list[NavListItem]) -> None:
        """Recursively walk NAV list items and set toc_label on resources."""
        nav_path = self.nav_resource.filename
        logger.debug(f"walking NAV items ({len(items)}) of {epub_type} type")
        for item in items:
            if item.link and item.link.href:
                rel_path = strip_fragment(item.link.href)
                abs_path = self.__absolute_from_relative_href(rel_path, nav_path)
                resource = self.resources.by_path(abs_path)
                if epub_type not in resource.navs:
                    resource.navs[epub_type] = item

            if item.ol:
                self._walk_nav_items(epub_type, item.ol.items)

    # -----------------------------------------------------------------------
    # Convenience properties
    # -----------------------------------------------------------------------

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
