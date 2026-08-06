import logging
import re
from collections.abc import Iterator
from enum import StrEnum


from library.epub.epub_link import EPUBLink
from library.epub.media_type import MediaType, EpubRole, FileName
from library.epub.resources import (
    EpubHtmlResource,
    EpubContainerResource,
    EpubPackageResource,
    EpubDefaultResource,
    EpubNcxResource,
    AnyResource,
)
from library.epub.resource_index import ResourceIndex
from library.epub.utils_href import posix_absolute_href
from library.epub.xml_models.ncx_model import NCXDocument, NavPoint
from library.epub.xml_models.nav_model import NavDocument, NavListItem
from library.epub.xml_models.package_document import PackageDocument
from library.asserts import require

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

        self.mimetype_resource = require(self.resources.by_path(FileName.MIMETYPE), "MIMETYPE")
        self.container_resource: EpubContainerResource = self.resources.by_path(FileName.CONTAINER)
        self.container_document = require(self.container_resource, "CONTAINER").document
        assert len(self.container_document.opf_paths) == 1, "EPUB's with several package documents are not supported"

        opf_path = require(self.container_document.opf_path, "opf_path")
        self.package_resource: EpubPackageResource = require(self.resources.by_path(opf_path), "package_resource")
        self.package_document = PackageDocument.from_xml_bytes(self.package_resource.content)

        self.ncx_resource: EpubNcxResource | None = None
        self._ncx_document: NCXDocument | None = None
        self.nav_resource: EpubHtmlResource | None = None
        self._nav_document: NavDocument | None = None

        self.cover_resource: EpubDefaultResource | None = None

        logger.debug(f"{self} initializing")

        self._enrich_from_opf()
        self._enrich_from_ncx()
        self._iterlinks_navs()

        logger.debug(f"{self} initialized")

    def __repr__(self):
        return f"EpubCore({len(self.resources)})"

    @property
    def ncx_document(self) -> NCXDocument:
        if self._ncx_document is None:
            resource = require(self.ncx_resource, "ncx_resource")
            self._ncx_document = NCXDocument.from_xml_bytes(resource.content)
        return require(self._ncx_document)

    @property
    def nav_document(self) -> NavDocument:
        if self._nav_document is None:
            resource = require(self.nav_resource, "nav_resource")
            self._nav_document = NavDocument.from_xml_bytes(resource.content)
        return require(self._nav_document)

    def sync(self) -> None:
        """Serialize all core models (package, ncx, nav) back to their respective resources."""
        logger.debug(f"{self} sync core documents")
        if self.package_resource and self.package_resource.is_modified:
            self.package_resource.content = self.package_document.to_xml_bytes()
        if self.ncx_resource and self.ncx_resource.is_modified:
            self.ncx_resource.content = self.ncx_document.to_xml_bytes()
        if self.nav_resource and self.nav_resource.is_modified:
            self.nav_resource.content = self.nav_document.to_xml_bytes()

    # -----------------------------------------------------------------------
    # OPF enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_opf(self) -> None:
        """Enrich resources with manifest, spine, and guide data from the OPF."""
        logger.debug(f"{self} enriching resources from opf data")
        opf_path = self.package_resource.info.filename

        # --- Manifest ---
        logger.debug(f"{self} processing {len(self.package_document.manifest.items)} manifest items")
        for item in self.package_document.manifest.items:
            abs_path = posix_absolute_href(opf_path, item.href)
            resource = self.resources.by_path(abs_path)

            if resource is None:
                logger.error(f"{self} manifest item {item.id!r} references missing file: {abs_path!r}")
                continue

            resource.manifest_item = item

            if item.properties and "cover-image" in item.properties:
                logger.debug(f"{self} EPUB 3 style cover image found {item.href}")
                self.cover_resource = resource

            if item.properties and "nav" in item.properties:
                resource.role = EpubRole.NAV
                logger.debug(f"{self} found nav file: {resource.info.filename!r}")
                if self.nav_resource is not None:
                    logger.warning(f"{self} found second nav file {resource.info.filename!r}")
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
                    # logger.debug(f"{self} switching type of {resource.filename!r} from {rmt!r} to {imt!r}")
                    pass

        # Rebuild ID index now that IDs are populated
        self.resources.rebuild_id_index()

        # --- Spine ---
        logger.debug(f"{self} processing {len(self.package_document.spine.itemrefs)} spine items")
        for index, itemref in enumerate(self.package_document.spine.itemrefs):
            resource = self.resources.by_id(itemref.idref)
            if resource is None:
                logger.warning(f"{self} spine itemref {itemref.idref!r} references unknown manifest ID.")
                continue

            chapter_match = re.fullmatch(r"^chapter_(\d+)$", itemref.idref)
            chapter_number = int(chapter_match.group(1)) if chapter_match else None
            if chapter_number is None:
                logger.debug(f"{self} chapter_number not found for {itemref.idref}")
            # number_match = re.search(r"(\d+)", itemref.idref)
            # number_number = int(number_match.group(1)) if number_match else None

            # logger.info(f"{self} spine {itemref.idref=}, {index=}, {chapter_number=}, {number_number=}")

            resource.source_sequence = chapter_number
            resource.spine_item_ref = itemref

        # --- Guide ---
        if self.package_document.guide:
            logger.debug(f"{self} processing {len(self.package_document.guide.references)} guide references")
            for ref in self.package_document.guide.references:
                abs_path = posix_absolute_href(opf_path, ref.href)
                resource = self.resources.by_path(abs_path)
                if resource is None:
                    logger.warning(f"{self} guide reference {ref.type!r} references missing file: {abs_path!r}")
                    continue
                resource.guide_reference = ref

        # --- Cover ---
        if self.cover_resource is None:
            logger.debug(f"{self} looking for cover file EPUB 2 style")
            for meta in self.package_document.metadata.metas:
                name = getattr(meta, "name", None)
                content = getattr(meta, "content", None)
                if name and name == "cover" and content:
                    self.cover_resource = self.resources.by_id(content)
                    break
        logger.debug(f"{self} cover_resource: {self.cover_resource}")

    # -----------------------------------------------------------------------
    # NCX enrichment
    # -----------------------------------------------------------------------

    def _enrich_from_ncx(self) -> None:
        """Enrich resources with toc_label from the NCX document."""
        logger.debug(f"{self} looking for NCX file")
        if self.package_document.spine.toc:
            self.ncx_resource = self.resources.by_id(self.package_document.spine.toc)

        if self.ncx_resource is None:
            for resource in self.resources:
                if resource.media_type == MediaType.NCX:
                    self.ncx_resource = resource
                    break

        if self.ncx_resource is None:
            logger.warning("NCX document not found, skipping NCX enrichment")
            return

        if self.ncx_document.nav_map is None:
            logger.warning("NavMap not found in NCX document, skipping NCX enrichment")
            return

        self._walk_ncx_nav_points(self.ncx_document.nav_map.nav_points)

    def _walk_ncx_nav_points(self, nav_points: list[NavPoint]) -> None:
        """Recursively walk NCX navPoints and set toc_label on resources."""
        ncx_path = self.ncx_resource.info.filename
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
            logger.debug(f"{self} NAV document not found, skipping NAV enrichment")
            return

        # TODO REDO considering 6bfb89338d0e7deef8bfddc973dc531c_toc.xhtml
        for nav_elem in self.nav_document.body.navs:
            self._walk_nav_items(nav_elem.epub_type, nav_elem.ol.items)

    def _walk_nav_items(self, epub_type: str, items: list[NavListItem]) -> None:
        """Recursively walk NAV list items and set toc_label on resources."""
        nav_path = self.nav_resource.info.filename
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

    def _iterlinks_navs(self):
        logger.debug(f"{self} _iterlinks_navs")
        nav_res = self.nav_resource
        if nav_res is None:
            logger.debug(f"{self} NAV document not found, skipping")
            return

        for link_data in nav_res.html.iterlinks():
            epub_link = EPUBLink.from_iterlinks(nav_res.info.filename, link_data)
            nav_res.linked_to.append(epub_link)
            if epub_link.absolute_path is not None:
                linked_resource = self.resources.by_path(epub_link.absolute_path)
                assert linked_resource is not None, f"not found {epub_link.absolute_path}({epub_link.link})"
                assert linked_resource.role is EpubRole.HTML, (
                    f"Nav document links NON-HTML resource ({epub_link.absolute_path})"
                )
                linked_resource.linked_by.append(epub_link)

    # -----------------------------------------------------------------------
    # Convenience properties
    # -----------------------------------------------------------------------

    @property
    def spine(self) -> list[EpubHtmlResource]:
        """Resources in spine order."""
        return sorted(
            [r for r in self.resources if r.is_spine_item()],
            key=lambda r: r.source_sequence or 9999,
        )

    def writing_sequence(self) -> Iterator[AnyResource]:
        # yield self.mimetype_resource
        yield self.container_resource
        yield self.package_resource
        if self.ncx_resource and not self.ncx_resource.is_deleted:
            yield self.ncx_resource
        if self.nav_resource and not self.nav_resource.is_deleted:
            yield self.nav_resource
        yielded = [
            self.mimetype_resource,
            self.container_resource,
            self.package_resource,
            self.ncx_resource,
            self.nav_resource,
        ]
        for resource in self.resources.core_items():
            if resource not in yielded and not resource.is_deleted:
                yield resource
                yielded.append(resource)
        for resource in self.resources.common_items():
            if resource not in yielded and not resource.is_deleted:
                yield resource
                yielded.append(resource)
        for resource in self.spine:
            if resource not in yielded and not resource.is_deleted:
                yield resource
                yielded.append(resource)
        for resource in self.resources:
            if resource not in yielded and not resource.is_deleted:
                yield resource
                yielded.append(resource)

    # -----------------------------------------------------------------------
    #
    # -----------------------------------------------------------------------

    def remove_resource(self, resource) -> None:
        resource.is_deleted = True
        if resource.manifest_item is not None:
            self.package_document.manifest.remove_item(resource.manifest_item)
            self.package_resource.is_modified = True
        if resource.spine_item_ref is not None:
            self.package_document.spine.remove_itemref(resource.spine_item_ref)
            self.package_resource.is_modified = True
        if resource.guide_reference is not None:
            self.package_document.guide.remove_reference(resource.guide_reference)
            self.package_resource.is_modified = True
        if self.package_resource.is_modified:
            logger.info("package_resource was modified")
            self.package_resource.content = self.package_document.to_xml_bytes()
        if resource.ncx_nav_point is not None:
            self.ncx_document.nav_map.remove_nav_point(point=resource.ncx_nav_point)
            self.ncx_resource.is_modified = True
        if resource.navs:
            raise NotImplementedError("Nav removal not implemented yet.")
            self.nav_resource.is_modified = True
        if resource.linked_by:
            for link in resource.linked_by:
                logger.debug(f"{self} removing link {link!r}")
                link.element.getparent().remove(link.element)
                link.resource.linked_to.remove(link)
                link.resource.is_modified = True

    def remove_garbage(self):
        ibook_resource = self.resources.by_path(FileName.IBOOKS_OPTIONS)
        if ibook_resource is not None:
            ibook_resource.is_deleted = True
