from typing import Annotated, Any

import bs4

# Reproducing the behavior of typing.Required
type Required[T] = Annotated[T, "required"]


class EnforcingSoup(bs4.BeautifulSoup):
    def __init__(
        self,
        markup: str | bytes,
        features: str | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(
            markup,
            features,
            *args,
            **kwargs,
        )

        required = (
            field for field, annotation in self.__class__.__annotations__.items() if annotation.__origin__ is Required
        )

        for tag in required:
            if not getattr(self, tag):
                raise AttributeError(f"Package document missing {tag}")


class PackageDocumentSoup(EnforcingSoup):
    """A BeautifulSoup subclass for the package document."""

    manifest: Required[bs4.Tag]
    metadata: Required[bs4.Tag]
    spine: Required[bs4.Tag]


class PackageDocument(XMLResource[PackageDocumentSoup], SoupChanging):
    """
    The package document of the EPUB file, sometimes known as the 'content.opf' file.

    Typically used via an EPUB object:

    >>> from epublib import EPUB
    >>> with EPUB(sample) as book:
    ...     print(book.package_document)
    ...     print(book.package_document.metadata)
    ...     print(book.package_document.manifest)
    ...     print(book.package_document.spine)
    PackageDocument(content.opf)
    BookMetadata(... items)
    BookManifest(... items)
    BookSpine(... items)

    Args:
        file: The file-like object or bytes representing the package document.
        info: The ZipInfo, filename, or Path of the package document within the EPUB archive.
    """

    soup_class: type[PackageDocumentSoup] = PackageDocumentSoup

    def __init__(self, file: IO[bytes] | bytes, info: ZipInfo | str | Path) -> None:
        super().__init__(file, info)
        self._manifest: BookManifest | None = None
        self._metadata: BookMetadata | None = None
        self._spine: BookSpine | None = None
        self._guide: BookGuide | None = None

    @property
    def manifest(self) -> BookManifest:
        """
        The manifest in this package.
        """
        if self._manifest is None:
            self._manifest = BookManifest(
                self.soup,
                self.soup.manifest,
                own_filename=self.filename,
            )
        return self._manifest

    @property
    def metadata(self) -> BookMetadata:
        """
        The metadata in this package.
        """
        if self._metadata is None:
            self._metadata = BookMetadata(self.soup, self.soup.metadata)
        return self._metadata

    @property
    def spine(self) -> BookSpine:
        """
        The spine in this package.
        """
        if self._spine is None:
            self._spine = BookSpine(self.soup, self.soup.spine)
        return self._spine

    @property
    def guide(self) -> BookGuide | None:
        """
        The guide in this package, if any, else None.
        """
        if self._guide is None and self.soup.guide:
            self._guide = BookGuide(
                self.soup,
                self.soup.guide,
                own_filename=self.filename,
            )
        return self._guide

    def remove(self, resource: Resource | str | Path | EPUBId | ManifestItem | SpineItemRef) -> None:
        """
        Remove items referencing a resource from the manifest, spine and guide,
        if it exists. If the resource is marked as cover image in the manifest,
        remove the corresponding item in the metadata.

        Args:
            resource: The resource to remove, as a filename (str or Path), an
                identifier, a resource, a manifest item or a spine item.
        """

        if isinstance(resource, ManifestItem):
            item = resource
        else:
            item = self.manifest[resource]
        spine_item = self.spine.get(item.id)
        if spine_item:
            self.spine.remove_item(spine_item)
        if self.guide:
            guide_item = self.guide.get(item.filename)
            if guide_item:
                self.guide.remove_item(guide_item)
        self.manifest.remove_item(item)
        if item.has_property("cover-image"):
            metadata_item = self.metadata.get_valued("cover")
            if metadata_item and metadata_item.value == item.id:
                self.metadata.remove_item(metadata_item)

    @override
    def on_soup_change(self) -> None:
        del self._manifest
        del self._metadata
        del self._spine
        self._manifest = None
        self._metadata = None
        self._spine = None

    @override
    def on_content_change(self) -> None:
        super().on_content_change()
        self.on_soup_change()


def resource_to_manifest_item(
    resource: Resource,
    package: PackageDocument,
    identifier: EPUBId | str | None = None,
    media_type: MediaType | str | None = None,
    fallback: str | None = None,
    media_overlay: str | None = None,
    is_nav: bool = False,
    is_cover: bool = False,
    properties: list[str] | None = None,
    detect_properties: bool = True,
) -> ManifestItem:
    """
    Create a manifest item from a resource.

    Args:
        resource: The resource to create a manifest item for.
        package: The package document to create the manifest item in.
        identifier: The identifier to use for the manifest item. If None,
            a new identifier will be generated. Defaults to None.
        media_type: The media type to use for the manifest item. If None,
            the media type will be determined from the resource. Defaults to None.
        fallback: The fallback identifier to use for the manifest item. Defaults
            to None.
        media_overlay: The media overlay identifier to use for the manifest item.
            Defaults to None.
        is_nav: Whether the resource is a navigation document. Defaults to False.
        is_cover: Whether the resource is a cover image. Defaults to False.
        properties: List of properties to set on the manifest item. Defaults to
            None.
        detect_properties: Whether to detect properties from the resource.
            Defaults to True.

    Returns:
        The created manifest item.

    Raises:
        EPUBError: If any of the following occurr:
            - The identifier is already used in the manifest.
            - The media type cannot be determined from the resource.
            - is_nav is set to True, but the resource is not a content document.
            - is_cover is set to True, but the resource is not an image.
    """

    filename = resource.filename

    if identifier is None:
        identifier = package.manifest.get_new_id(resource.filename)
    elif package.manifest.get(identifier) is not None:
        raise EPUBError(f"Identifier '{identifier}' is already used in the manifest")

    if media_type is None:
        media_type = (
            resource.media_type
            if isinstance(resource, PublicationResource)
            else MediaType.from_filename(resource.filename)
        )

    if not media_type:
        raise EPUBError(f"Can't determine media type of file {resource.filename}")
    media_type = MediaType(media_type)

    if detect_properties or is_nav or is_cover:
        properties = properties if properties is not None else []

        if detect_properties and isinstance(resource, ContentDocument):
            properties += detect_manifest_properties(cast(ContentDocument[bs4.BeautifulSoup], resource).soup)

        if is_nav:
            if not isinstance(resource, ContentDocument):
                raise EPUBError("Only content documents can be navigation documents")
            properties.append("nav")

        if is_cover:
            if not media_type.category == Category.IMAGE:
                raise EPUBError("Only image resources can be cover images")
            properties.append("cover-image")

        properties = list(set(properties)) if properties else None

    return ManifestItem(
        soup=package.soup,
        filename=filename,
        id=EPUBId(identifier),
        media_type=str(media_type),
        media_overlay=media_overlay,
        fallback=fallback,
        properties=properties,
        own_filename=package.filename,
    )
