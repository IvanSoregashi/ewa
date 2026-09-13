from urllib.parse import urlsplit

from library.asserts import require
from library.epub.media_type import EpubRole, FileName
from library.epub.resources import Resource, ResourceIndex
from library.epub.utils_href import posix_absolute_href, posix_relative_href
from library.epub.xml_models.package_document import PackageDocument
from library.epub.xml_models.container_model import ContainerDocument


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
        container_resource: Resource | None = None,
    ) -> None:
        self.resource = resource
        self.resources = resources
        self._document: PackageDocument | None = None
        self.container_resource = container_resource
        self._container: ContainerDocument | None = None

    def __repr__(self) -> str:
        return f"EpubPackage({self.resource.filename!r})"

    @property
    def document(self) -> PackageDocument:
        if self._document is None:
            self._document = PackageDocument.from_xml_bytes(self.resource.content)
        return self._document

    @property
    def container(self) -> ContainerDocument | None:
        if self._container is None and self.container_resource is not None:
            self._container = ContainerDocument.from_xml_bytes(self.container_resource.content)
        return self._container

    @classmethod
    def from_resources(cls, resources: ResourceIndex) -> EpubPackage:
        """Discover a single package, preferring the container's explicit reference."""
        container_resource = resources.by_path(FileName.CONTAINER)
        container = None
        if container_resource is not None:
            container = ContainerDocument.from_xml_bytes(container_resource.content)
            if len(container.opf_paths) != 1:
                raise NotImplementedError("Expected a single package document in the container")
            path = require(container.opf_path, "container's opf_path")
            resource = require(resources.by_path(path), f"package resource {path!r}")
        else:
            # Retain support for incomplete inputs with one OPF and no container.
            candidates = resources.by_role(EpubRole.OPF)
            if len(candidates) != 1:
                raise ValueError("Cannot locate a unique OPF without container.xml")
            resource = candidates[0]
        package = cls(resource, resources, container_resource=container_resource)
        package._container = container
        return package

    def resolve_href(self, href: str) -> str:
        """Resolve a local OPF-relative href to an archive path (with fragment).

        Uses the resource's current location; no duplicate package path is kept.
        This prototype retains the existing local POSIX href handling.
        """
        return posix_absolute_href(self.resource.filename, href)

    def relative_href(self, archive_path: str) -> str:
        """Express an archive path relative to this OPF's current location."""
        return posix_relative_href(self.resource.filename, archive_path)

    def resource_for_href(self, href: str) -> Resource | None:
        """Look up a local manifest href; missing resources remain inspectable."""
        return self.resources.by_path(self.resolve_href(href))

    def relocate(self, new_path: str) -> bool:
        """Move the OPF in the output inventory, updating local hrefs and container.

        Content resources stay in place. A container is required for relocation;
        discovering a container-less input does not implicitly create one.
        """
        old_path = self.resource.filename
        if old_path == new_path:
            return False
        container = require(self.container, "container document")
        container_resource = require(self.container_resource, "container resource")
        rootfiles = [root for root in container.rootfiles if root.full_path == old_path]
        if not rootfiles:
            raise ValueError(f"Container does not reference {old_path!r}")
        document = self.document
        references = list(document.manifest.items)
        if document.guide is not None:
            references.extend(document.guide.references)

        def rebased(href: str) -> str:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                return href
            return posix_relative_href(new_path, posix_absolute_href(old_path, href))

        hrefs = [rebased(reference.href) for reference in references]
        # Prepare serialization before modifying the live objects or the index.
        updated_document = document.model_copy(deep=True)
        updated_references = list(updated_document.manifest.items)
        if updated_document.guide is not None:
            updated_references.extend(updated_document.guide.references)
        for reference, href in zip(updated_references, hrefs):
            reference.href = href
        updated_container = container.model_copy(deep=True)
        for root in updated_container.rootfiles:
            if root.full_path == old_path:
                root.full_path = new_path
        opf_bytes = updated_document.to_xml_bytes()
        container_bytes = updated_container.to_xml_bytes()

        self.resources.rename(self.resource, new_path)
        for reference, href in zip(references, hrefs):
            reference.href = href
        for root in rootfiles:
            root.full_path = new_path
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
