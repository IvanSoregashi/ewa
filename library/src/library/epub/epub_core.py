import logging
import re
from enum import StrEnum

from library.epub.media_type import MediaType, Category, ResourceType
from library.epub.resources import ResourceIndex, EPUBResource
from library.epub.utils_path import posix_absolute_href, strip_fragment
from library.epub.xml_literals import FileName
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NCXDocument, NavPoint
from library.epub.xml_models.nav_model import NavDocument, NavListItem
from library.epub.xml_models.package_document import PackageDocument

logger = logging.getLogger("epub_core")


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
        self.resources = resources

        # Core documents (populated during parsing)
        self._opf_path: str
        self.package: PackageDocument
        self.ncx: NCXDocument
        self.nav: NavDocument

        # Core resource references (populated during enrichment)
        self.mimetype_resource: EPUBResource | None = None
        self.container_resource: EPUBResource | None = None
        self.opf_resource: EPUBResource | None = None
        self.ncx_resource: EPUBResource | None = None
        self.nav_resource: EPUBResource | None = None
        self.cover_resource: EPUBResource | None = None

        logger.debug(f"{self} initializing")

        # Run the parsing pipeline
        self._parse_container()
        self._parse_opf()
        self._enrich_from_opf()

        # --- Identify core resources from manifest data ---
        self._identify_core_resources()

        self._enrich_from_ncx()
        self._enrich_from_nav()

        logger.debug(f"{self} initialized")

    def __repr__(self):
        return f"EpubCore({len(self.resources)})"

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
        logger.debug(f"{self} parsing '{FileName.CONTAINER!s}' file.")
        self.mimetype_resource = self.resources.by_path(FileName.MIMETYPE)
        self.container_resource = self.resources.by_path(FileName.CONTAINER)
        if self.container_resource is None:
            raise ValueError(f"{self} is missing '{FileName.CONTAINER!s}'.")

        container = ContainerDocument.from_xml_bytes(self.container_resource.content)
        if len(container.rootfiles) > 1:
            logger.warning(
                f"{self} has {len(container.rootfiles)} rootfiles. {container.opf_paths!r}, Using the first one."
            )
        self._opf_path = container.opf_path
        if self._opf_path is None:
            raise ValueError(f"{self} container.xml does not specify an OPF rootfile.")

    def _parse_opf(self) -> None:
        """Parse the OPF package document."""
        logger.debug(f"{self} parsing OPF({self._opf_path!r}) file.")
        if self._opf_path is None:
            raise ValueError(f"{self} OPF({self._opf_path!r}) path not set. Call _parse_container first.")

        self.opf_resource = self.resources.by_path(self._opf_path)
        if self.opf_resource is None:
            raise ValueError(f"{self} OPF({self._opf_path!r}) not found in resources.")

        self.package = PackageDocument.from_xml_bytes(self.opf_resource.content)

    # -----------------------------------------------------------------------
    # OPF enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_opf(self) -> None:
        """Enrich resources with manifest, spine, and guide data from the OPF."""
        logger.debug(f"{self} enriching resources from opf data")
        opf_path: str = self._opf_path
        if self.package is None:
            raise

        # --- Manifest ---
        logger.debug(f"{self} processing {len(self.package.manifest.items)} manifest items")
        for item in self.package.manifest.items:
            abs_path = posix_absolute_href(opf_path, item.href)
            resource = self.resources.by_path(abs_path)
            if resource is None:
                logger.warning(f"{self} manifest item {item.id!r} references missing file: {abs_path!r}")
                continue

            resource.manifest_item = item

            if item.properties and "nav" in item.properties:
                resource.resource_type = ResourceType.CORE
                logger.debug(f"{self} found nav file: {resource.filename!r}")
                if self.nav_resource is not None:
                    logger.warning(f"{self} found second nav file {resource.filename!r}")
                self.nav_resource = resource

            rmt = resource.media_type.value
            imt = item.media_type
            if rmt != imt:
                match (rmt, imt):
                    case ("text/html", "application/xhtml+xml"):
                        resource.media_type = MediaType(imt)
                    case ("font/ttf", "application/x-font-truetype"):
                        resource.media_type = MediaType(imt)
                    case _:
                        logger.warning(f"{self} type mismatch {abs_path!r}, {rmt!r}, {imt!r}")
                if resource.media_type.value == imt:
                    logger.debug(f"{self} switching type of {resource.filename!r} from {rmt!r} to {imt!r}")

        # Rebuild ID index now that IDs are populated
        self.resources.rebuild_id_index()

        # --- Spine ---
        logger.debug(f"{self} processing {len(self.package.spine.itemrefs)} spine items")
        for index, itemref in enumerate(self.package.spine.itemrefs):
            resource = self.resources.by_id(itemref.idref)
            if resource is None:
                logger.warning(f"{self} spine itemref {itemref.idref!r} references unknown manifest ID.")
                continue

            chapter_match = re.fullmatch(r"^chapter_(\d+)$", itemref.idref)
            chapter_number = int(chapter_match.group(1)) if chapter_match else None
            number_match = re.search(r"(\d+)", itemref.idref)
            number_number = int(number_match.group(1)) if number_match else None

            logger.info(f"{self} spine {itemref.idref=}, {index=}, {chapter_number=}, {number_number=}")

            resource.source_sequence = chapter_number
            resource.spine_item_ref = itemref

        # --- Guide ---
        if self.package.guide:
            logger.debug(f"{self} processing {len(self.package.guide.references)} guide references")
            for ref in self.package.guide.references:
                abs_path = posix_absolute_href(opf_path, ref.href)
                resource = self.resources.by_path(abs_path)
                if resource is None:
                    logger.warning(f"{self} guide reference {ref.type!r} references missing file: {abs_path!r}")
                    continue
                resource.guide_reference = ref

    def _identify_core_resources(self) -> None:
        """Identify NCX, NAV, and cover resources from enriched manifest data."""
        logger.debug(f"{self} identifying NCX, NAV, and cover resources")
        # TODO: dissolve this func
        # NCX: found via spine@toc attribute or by media type
        logger.debug(f"{self} looking for NCX file")
        if self.package.spine.toc:
            self.ncx_resource = self.resources.by_id(self.package.spine.toc)
        if self.ncx_resource is None:
            for resource in self.resources:
                if self.ncx_resource is None and resource.media_type == MediaType.NCX:
                    self.ncx_resource = resource
                    break
        logger.debug(f"{self} ncx_resource: {self.ncx_resource}")

        logger.debug(f"{self} looking for cover file EPUB 3 style")
        # TODO: Cover logic - make either a chapter, or core.
        # Cover image: EPUB 3 properties="cover-image" or EPUB 2 meta
        for resource in self.resources:
            if (
                resource.manifest_item
                and resource.manifest_item.properties
                and "cover-image" in resource.manifest_item.properties
            ):
                self.cover_resource = resource
                break
        if self.cover_resource is None and self.package:
            logger.debug(f"{self} looking for cover file EPUB 2 style")
            for meta in self.package.metadata.metas:
                name = getattr(meta, "name", None)
                content = getattr(meta, "content", None)
                if name == "cover" and content:
                    self.cover_resource = self.resources.by_id(content)
                    break
        logger.debug(f"{self} cover_resource: {self.cover_resource}")

    # -----------------------------------------------------------------------
    # NCX enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_ncx(self) -> None:
        """Enrich resources with toc_label from the NCX document."""
        logger.debug("enriching resources from NCX document")
        if self.ncx_resource is None:
            logger.warning("NCX document not found, skipping NCX enrichment")
            return

        self.ncx = NCXDocument.from_xml_bytes(self.ncx_resource.content)
        if self.ncx.nav_map is None:
            logger.warning("NavMap not found in NCX document, skipping NCX enrichment")
            return

        self._walk_ncx_nav_points(self.ncx.nav_map.nav_points)

    def _walk_ncx_nav_points(self, nav_points: list[NavPoint]) -> None:
        """Recursively walk NCX navPoints and set toc_label on resources."""
        ncx_path = self.ncx_resource.filename
        logger.debug(f"{self} walking NCX navPoints ({len(nav_points)})")
        for nav_point in nav_points:
            if nav_point.content and nav_point.content.src:
                abs_path = posix_absolute_href(ncx_path, nav_point.content.src)
                resource = self.resources.by_path(abs_path)
                if resource is not None:
                    if resource.ncx_nav_point is None:
                        resource.ncx_nav_point = nav_point
                    else:
                        logger.warning(
                            f"{self} NCX path {nav_point.content.src!r} found several times"
                            f" ({resource.ncx_nav_point.nav_label.text!r}, {nav_point.nav_label.text!r})."
                            " rewriting with the latest catch."
                        )
                        resource.ncx_nav_point = nav_point
                else:
                    logger.warning(f"{self} path {nav_point.content.src!r} not found in NCX")

            if nav_point.nav_points:
                self._walk_ncx_nav_points(nav_point.nav_points)

    # -----------------------------------------------------------------------
    # NAV enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_nav(self) -> None:
        """Enrich resources from the NAV document."""
        logger.debug(f"{self} enriching resources from NAV document")
        if self.nav_resource is None:
            logger.warning(f"{self} NAV document not found, skipping NAV enrichment")
            return

        self.nav = NavDocument.from_xml_bytes(self.nav_resource.content)

        for nav_elem in self.nav.body.navs:
            self._walk_nav_items(nav_elem.epub_type, nav_elem.ol.items)

    def _walk_nav_items(self, epub_type: str, items: list[NavListItem]) -> None:
        """Recursively walk NAV list items and set toc_label on resources."""
        nav_path = self.nav_resource.filename
        logger.debug(f"{self} walking NAV items ({len(items)}) of {epub_type!r} type")
        for item in items:
            if item.link and item.link.href:
                abs_path = posix_absolute_href(nav_path, item.link.href)
                resource = self.resources.by_path(abs_path)
                if resource is None:
                    logger.warning(f"{self} path {nav_path!r} not found")
                    continue
                if epub_type not in resource.navs:
                    resource.navs[epub_type] = item
                else:
                    logger.warning(f"{self} item {abs_path!r} already found in NAV, rewriting")
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
