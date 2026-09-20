import posixpath

from library.asserts import require
from library.epub.media_type import EpubRole, FileName
from library.epub.metadata import MetadataType
from library.epub.resources import Resource, ResourceIndex, ResourceSelection
from library.epub.package_urls import archive_path, local_target, path_url, rebase_href
from library.epub.utils_href import posix_absolute_href, posix_relative_href
from library.epub.xml_models.package_document import PackageDocument
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.package_sequences import ManifestItem, GuideReference


class EpubPackage:
    """An OPF document bound to its resource and the EPUB's resource inventory.

    Edit the parsed document through ``document``; ``flush`` writes those edits
    back to the resource. EPUB export calls flush automatically. Once parsed,
    the document is the editing authority: do not independently replace its
    resource bytes. Relocating the OPF also updates its container reference.
    """

    def __init__(
        self,
        resource: Resource,
        resources: ResourceIndex,
        *,
        container_resource: Resource,
        document: PackageDocument | None = None,
        container_document: ContainerDocument | None = None,
    ) -> None:
        self.resource = resource
        self.resources = resources
        self._document = document
        self.container_resource = container_resource
        self._container = container_document

    def __repr__(self) -> str:
        return f"EpubPackage({self.resource.filename!r})"

    @property
    def document(self) -> PackageDocument:
        if self._document is None:
            self._document = PackageDocument.from_xml_bytes(self.resource.content)
        return self._document

    @property
    def container(self) -> ContainerDocument:
        if self._container is None:
            if self.container_resource is None:
                raise ValueError("Container resource is missing")
            self._container = ContainerDocument.from_xml_bytes(self.container_resource.content)
        return self._container

    @classmethod
    def from_resources(cls, resources: ResourceIndex) -> EpubPackage:
        """Discover a single package, creating a missing container for a unique OPF."""
        container_resource = resources.by_path(FileName.CONTAINER)

        if container_resource is not None:
            container = ContainerDocument.from_xml_bytes(container_resource.content)

            if len(container.opf_paths) != 1:
                raise NotImplementedError("Expected a single package document in the container")

            href = require(container.opf_path, "container's opf_path")
            path, suffix = require(local_target("", href), "local container package URL")

            if suffix:
                raise ValueError("Container package URL must not contain a query or fragment")

            resource = require(resources.by_path(path), f"package resource {path!r}")

        else:
            # Repair only an absent container, after unambiguous OPF discovery.
            candidates = resources.by_role(EpubRole.OPF)

            if len(candidates) != 1:
                raise ValueError("Cannot locate a unique OPF without container.xml")

            resource = candidates[0]
            container = ContainerDocument.standard(path_url(resource.filename))
            container_resource = Resource.from_bytes(FileName.CONTAINER, container.to_xml_bytes())
            resources.add(container_resource)

        package = cls(resource, resources, container_resource=container_resource, container_document=container)

        return package

    def resolve_href(self, href: str) -> str:
        """Resolve a local OPF-relative href to an archive path (with fragment).

        Uses the resource's current location; no duplicate package path is kept.
        This prototype retains the existing local POSIX href handling.
        """
        return posix_absolute_href(self.resource.filename, href)

    def relative_href(self, root_path: str) -> str:
        """Express an archive path relative to this OPF's current location."""
        return posix_relative_href(self.resource.filename, root_path)

    def resource_for_href(self, href: str) -> Resource | None:
        """Look up a local manifest href; missing resources remain inspectable."""
        target = local_target(self.resource.filename, href)
        return self.resources.by_path(target[0]) if target is not None else None

    def manifest_item_by_path(self, path: str) -> ManifestItem | None:
        """Look up a declaration by decoded archive path, without cached indexes."""
        return next((item for item in self.document.manifest.items if self._item_path(item) == path), None)

    def _item_path(self, item: ManifestItem) -> str | None:
        target = local_target(self.resource.filename, item.href)
        return target[0] if target is not None else None

    @property
    def undeclared_resources(self) -> ResourceSelection:
        """Inventory files missing from the manifest, excluding archive infrastructure.

        NCX, navigation, and other content XML still need declarations; is_core()
        is not an infrastructure test. META-INF files and this OPF are excluded.
        """
        declared_paths = {self._item_path(item) for item in self.document.manifest.items}
        return ResourceSelection(
            resource
            for resource in self.resources
            if resource is not self.resource
            and resource is not self.container_resource
            and resource.filename != FileName.MIMETYPE
            and not resource.filename.startswith("META-INF/")
            and not resource.info.is_dir()
            and resource.filename not in declared_paths
        )

    @property
    def manifest_resources(self) -> ResourceSelection:
        """Snapshot of declared local resources; remote entries have no archive bytes."""
        return ResourceSelection(
            require(self.resources.by_path(path), f"manifest resource {path!r}")
            for item in self.document.manifest.items
            if (path := self._item_path(item)) is not None
        )

    def add_resource(
        self,
        resource: Resource,
        *,
        item_id: str,
        media_type: str | None = None,
        properties: str | None = None,
    ) -> ManifestItem:
        """Add archive content and an OPF declaration, or declare an already-owned resource.

        Does not insert a spine entry or create navigation links. Export flushes
        the edited OPF; the returned item is the actual XML model entry.
        """
        path = archive_path(resource.filename)

        if path != resource.filename or resource.info.is_dir():
            raise ValueError("Resource must have a normalized archive file path")
        if (
            resource is self.resource
            or resource is self.container_resource
            or path == FileName.MIMETYPE
            or path.startswith("META-INF/")
        ):
            raise ValueError("Archive infrastructure cannot be registered in the manifest")

        document = self.document

        if item_id in document.ids:
            raise ValueError(f"Package ID already exists: {item_id!r}")

        if self.manifest_item_by_path(path) is not None:
            raise ValueError(f"Resource already declared: {path!r}")

        existing = self.resources.by_path(path)

        if existing is not None and existing is not resource:
            raise ValueError(f"Resource already exists: {path!r}")

        for other in self.resources:
            if other is resource:
                continue
            if other.filename.startswith(path + "/") or (
                path.startswith(other.filename.rstrip("/") + "/") and not other.info.is_dir()
            ):
                raise ValueError(f"Resource path conflicts with {other.filename!r}")

        href = path_url(posixpath.relpath(path, posixpath.dirname(self.resource.filename) or "."))
        item = document.manifest.add_item(
            id=item_id,
            href=href,
            media_type=str(resource.media_type) if media_type is None else media_type,
            properties=properties,
        )

        if existing is None:
            try:
                self.resources.add(resource)
            except Exception:
                document.manifest.remove_item(item=item)
                raise

        return item

    def remove_resource(self, resource: Resource, *, remove_references: bool = False) -> None:
        """Remove archive content and declarations; reject OPF dependents by default.

        remove_references=True also removes spine/guide entries, cover metadata
        and metadata refinements, and clears fallback/overlay/toc references.
        This is OPF cleanup only: XHTML/CSS and NCX/NAV links are not inspected
        or rewritten, and resulting publication validity is not guaranteed.
        """
        if (
            resource is self.resource
            or resource is self.container_resource
            or resource.filename == FileName.MIMETYPE
            or resource.filename.startswith("META-INF/")
        ):
            raise ValueError("Use an infrastructure-specific operation for this resource")

        if resource not in self.resources or self.resources.by_path(resource.filename) is not resource:
            raise ValueError("Resource is not owned by this package's inventory")

        document = self.document

        removed = [item for item in document.manifest.items if self._item_path(item) == resource.filename]
        removed_ids = {item.id for item in removed}

        itemrefs = [ref for ref in document.spine.itemrefs if ref.idref in removed_ids]
        removed_ids.update(ref.id for ref in itemrefs if ref.id)

        guide_refs = []
        if document.guide is not None:
            guide_refs = [ref for ref in document.guide.references if self.resource_for_href(ref.href) is resource]

        remaining = [item for item in document.manifest.items if item not in removed]
        dependent_items = [item for item in remaining if item.fallback in removed_ids or item.overlay in removed_ids]

        metadata_references = document.metadata.referencing(removed_ids)
        removed_ids.update(meta.id for meta in metadata_references if meta.id)

        toc = document.spine.toc in removed_ids

        if not remove_references and (itemrefs or guide_refs or dependent_items or metadata_references or toc):
            raise ValueError("Resource has OPF references; use remove_references=True to remove them")

        self.resources.remove(resource)

        for item in removed:
            document.manifest.remove_item(item=item)

        if remove_references:
            for ref in itemrefs:
                document.spine.remove_itemref(itemref=ref)

            if document.guide is not None:
                for ref in guide_refs:
                    document.guide.remove_reference(reference=ref)

            for item in dependent_items:
                if item.fallback in removed_ids:
                    item.fallback = None
                if item.overlay in removed_ids:
                    item.overlay = None

            if toc:
                document.spine.toc = None

            for meta in metadata_references:
                document.metadata.remove_metadata(MetadataType.META, dc=False, item=meta)

    def relocate(self, new_path: str) -> bool:
        """Move the OPF in the output inventory, updating local hrefs and container.

        Content resources stay in place. A container is required for relocation;
        from_resources creates one when discovering a unique container-less OPF.
        """
        new_path = archive_path(new_path)
        old_path = self.resource.filename

        if old_path == new_path:
            return False

        container = require(self.container, "container document")
        container_resource = require(self.container_resource, "container resource")
        rootfiles = [root for root in container.rootfiles if local_target("", root.full_path) == (old_path, "")]

        if not rootfiles:
            raise ValueError(f"Container does not reference {old_path!r}")

        for resource in self.resources:
            if resource is not self.resource and (
                resource.filename.rstrip("/") == new_path
                or resource.filename.startswith(new_path + "/")
                or new_path.startswith(resource.filename.rstrip("/") + "/")
                and not resource.info.is_dir()
            ):
                raise ValueError(f"Resource already exists at or conflicts with {new_path!r}")

        document = self.document

        references: list[ManifestItem | GuideReference] = list(document.manifest.items)

        if document.guide is not None:
            references.extend(document.guide.references)

        hrefs = [rebase_href(old_path, new_path, reference.href) for reference in references]
        # Prepare serialization before modifying the live objects or the index.
        updated_document = document.model_copy(deep=True)
        updated_references: list[ManifestItem | GuideReference] = list(updated_document.manifest.items)

        if updated_document.guide is not None:
            updated_references.extend(updated_document.guide.references)

        for reference, href in zip(updated_references, hrefs):
            reference.href = href

        updated_container = container.model_copy(deep=True)

        for root in updated_container.rootfiles:
            if local_target("", root.full_path) == (old_path, ""):
                root.full_path = path_url(new_path)

        opf_bytes = updated_document.to_xml_bytes()
        container_bytes = updated_container.to_xml_bytes()

        self.resources.rename(self.resource, new_path)

        for reference, href in zip(references, hrefs):
            reference.href = href

        for root in rootfiles:
            root.full_path = path_url(new_path)

        self.resource.content = opf_bytes
        container_resource.content = container_bytes

        return True

    def flush(self) -> bool:
        """Serialize loaded OPF/container documents; return whether anything was written.

        Does not parse an unopened document. Loaded documents are serialized
        every time, without tracking edits or preserving original formatting.
        """
        written = False

        if self._document is not None:
            self.resource.content = self._document.to_xml_bytes()
            written = True

        if self._container is not None and self.container_resource is not None:
            self.container_resource.content = self._container.to_xml_bytes()
            written = True

        return written
