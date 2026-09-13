from library.epub.resources import Resource, ResourceIndex
from library.epub.utils_href import posix_absolute_href, posix_relative_href
from library.epub.xml_models.package_document import PackageDocument


class EpubPackage:
    """An OPF document bound to its resource and the EPUB's resource inventory.

    Edit the parsed document through ``document``; ``flush`` writes those edits
    back to the resource. EPUB export calls flush automatically. Once parsed,
    the document is the editing authority: do not independently replace its
    resource bytes. Resource renames and container updates belong to the caller.
    """

    def __init__(self, resource: Resource, resources: ResourceIndex) -> None:
        self.resource = resource
        self.resources = resources
        self._document: PackageDocument | None = None

    def __repr__(self) -> str:
        return f"EpubPackage({self.resource.filename!r})"

    @property
    def document(self) -> PackageDocument:
        if self._document is None:
            self._document = PackageDocument.from_xml_bytes(self.resource.content)
        return self._document

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

    def flush(self) -> bool:
        """Serialize the loaded document to its resource; return whether written.

        Does not parse an unopened document. Loaded documents are serialized
        every time, without tracking edits or preserving original formatting.
        """
        if self._document is None:
            return False
        self.resource.content = self._document.to_xml_bytes()
        return True
