from pydantic_xml import BaseXmlModel, attr, element
from library.epub.epub_namespaces import NamespacePrefix, OPF_NSMAP


class ManifestItem(BaseXmlModel, tag="item", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    id: str = attr()
    href: str = attr()
    media_type: str = attr(name="media-type")
    properties: str | None = attr(default=None)
    fallback: str | None = attr(default=None)
    overlay: str | None = attr(default=None)


class Manifest(BaseXmlModel, tag="manifest", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    items: list[ManifestItem] = element(tag="item", default=[])

    def add_item(self, id: str, href: str, media_type: str, **kwargs) -> ManifestItem:
        new_item = ManifestItem(id=id, href=href, media_type=media_type, **kwargs)
        self.items.append(new_item)
        return new_item

    def remove_item(self, item: ManifestItem | None = None, _id: str | None = None, path: str | None = None):
        """Remove a manifest item by its id or object reference."""
        if item is not None:
            self.items = [i for i in self.items if i is not item]
        elif _id is not None:
            self.items = [i for i in self.items if i.id != _id]
        elif path is not None:
            self.items = [i for i in self.items if i.href != path]


class SpineItemRef(BaseXmlModel, tag="itemref", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    idref: str = attr()
    linear: str | None = attr(default=None)
    properties: str | None = attr(default=None)
    id: str | None = attr(default=None)


class Spine(BaseXmlModel, tag="spine", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    toc: str | None = attr(default=None)
    page_progression_direction: str | None = attr(name="page-progression-direction", default=None)
    page_map: str | None = attr(name="page-map", default=None)
    itemrefs: list[SpineItemRef] = element(tag="itemref", default=[])

    def add_itemref(self, idref: str, linear: str | None = None, **kwargs) -> SpineItemRef:
        new_ref = SpineItemRef(idref=idref, linear=linear, **kwargs)
        self.itemrefs.append(new_ref)
        return new_ref

    def remove_itemref(self, itemref: SpineItemRef | None = None, idref: str | None = None):
        """Remove a spine itemref by its idref or object reference."""
        if itemref is not None:
            self.itemrefs = [r for r in self.itemrefs if r is not itemref]
        elif idref is not None:
            self.itemrefs = [r for r in self.itemrefs if r.idref != idref]


class GuideReference(BaseXmlModel, tag="reference", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    type: str = attr()
    title: str | None = attr(default=None)
    href: str = attr()


class Guide(BaseXmlModel, tag="guide", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    references: list[GuideReference] = element(tag="reference", default=[])

    def add_reference(self, type: str, href: str, title: str | None = None, **kwargs) -> GuideReference:
        new_ref = GuideReference(type=type, href=href, title=title, **kwargs)
        self.references.append(new_ref)
        return new_ref

    def remove_reference(self, reference: GuideReference | None = None, type: str | None = None):
        """Remove a guide reference by its type or object reference."""
        if reference is not None:
            self.references = [r for r in self.references if r is not reference]
        elif type is not None:
            self.references = [r for r in self.references if r.type != type]


class Tour(BaseXmlModel, tag="tour", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    title: str = attr()


class Tours(BaseXmlModel, tag="tours", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    tours: list[Tour] = element(tag="tour", default=[])

    def add_tour(self, id: str, title: str, **kwargs) -> Tour:
        new_tour = Tour(id=id, title=title, **kwargs)
        self.tours.append(new_tour)
        return new_tour

    def remove_tour(self, tour: Tour | None = None, id: str | None = None):
        """Remove a tour by its id or object reference."""
        if tour is not None:
            self.tours = [t for t in self.tours if t is not tour]
        elif id is not None:
            self.tours = [t for t in self.tours if t.id != id]
