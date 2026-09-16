from pydantic_xml import BaseXmlModel, attr, element

from library.epub.metadata import DCMetadataType, MetadataType
from library.epub.epub_namespaces import NamespacePrefix, OPF_NSMAP


class DCElement(BaseXmlModel, ns=NamespacePrefix.DC, nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    text: str | None = None


class DCIdentifier(DCElement, tag=DCMetadataType.IDENTIFIER):
    scheme: str | None = attr(name="scheme", default=None)
    scheme_ns: str | None = attr(name="scheme", ns=NamespacePrefix.OPF, default=None)


class DCTitle(DCElement, tag=DCMetadataType.TITLE):
    file_as_ns: str | None = attr(name="file-as", ns=NamespacePrefix.OPF, default=None)


class DCLanguage(DCElement, tag=DCMetadataType.LANGUAGE):
    type: str | None = attr(name="type", ns=NamespacePrefix.XSI, default=None)
    file_as_ns: str | None = attr(name="file-as", ns=NamespacePrefix.OPF, default=None)


class DCCreator(DCElement):
    file_as: str | None = attr(name="file-as", default=None)
    file_as_ns: str | None = attr(name="file-as", ns=NamespacePrefix.OPF, default=None)
    role: str | None = attr(name="role", default=None)
    role_ns: str | None = attr(name="role", ns=NamespacePrefix.OPF, default=None)


class DCDate(DCElement, tag=DCMetadataType.DATE):
    event: str | None = attr(name="event", default=None)
    event_ns: str | None = attr(name="event", ns=NamespacePrefix.OPF, default=None)


class DCMeta(DCElement, tag=DCMetadataType.META):
    pass


class Meta(DCElement, tag=MetadataType.META, ns=NamespacePrefix.OPF):
    name: str | None = attr(default=None)
    content: str | None = attr(name="content", default=None)
    property: str | None = attr(default=None)
    refines: str | None = attr(default=None)
    scheme: str | None = attr(name="scheme", default=None)
    lang: str | None = attr(name="lang", ns=NamespacePrefix.XML, default=None)


class Metadata(BaseXmlModel, tag="metadata", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP, search_mode="unordered"):
    titles: list[DCTitle] = element(tag=DCMetadataType.TITLE, default=[])
    creators: list[DCCreator] = element(tag=DCMetadataType.CREATOR, default=[])
    identifiers: list[DCIdentifier] = element(tag=DCMetadataType.IDENTIFIER, default=[])
    languages: list[DCLanguage] = element(tag=DCMetadataType.LANGUAGE, default=[])
    descriptions: list[DCElement] = element(tag=DCMetadataType.DESCRIPTION, default=[])
    contributors: list[DCCreator] = element(tag=DCMetadataType.CONTRIBUTOR, default=[])
    publishers: list[DCElement] = element(tag=DCMetadataType.PUBLISHER, default=[])
    rights: list[DCElement] = element(tag=DCMetadataType.RIGHTS, default=[])
    sources: list[DCElement] = element(tag=DCMetadataType.SOURCE, default=[])
    dates: list[DCDate] = element(tag=DCMetadataType.DATE, default=[])
    subjects: list[DCElement] = element(tag=DCMetadataType.SUBJECT, default=[])
    types: list[DCElement] = element(tag=DCMetadataType.TYPE, default=[])
    formats: list[DCElement] = element(tag=DCMetadataType.FORMAT, default=[])
    coverages: list[DCElement] = element(tag=DCMetadataType.COVERAGE, default=[])
    relations: list[DCElement] = element(tag=DCMetadataType.RELATION, default=[])
    metas: list[Meta] = element(tag=MetadataType.META, default=[])
    dc_metas: list[DCMeta] = element(tag=DCMetadataType.META, default=[])

    @property
    def title(self) -> str | None:
        return self.titles[0].text if self.titles else None

    @property
    def language(self) -> str | None:
        return self.languages[0].text if self.languages else None

    @property
    def uuid_id_or_all_identifiers(self) -> str:
        for ident in self.identifiers:
            if ident.id == "uuid_id":
                return ident.text or "empty_text_uuid_id"
        return " | ".join([item.text or "empty_text" for item in self.identifiers])

    @property
    def aut_or_all_creators(self) -> str:
        for creator in self.creators:
            if creator.role_ns == "aut":
                return creator.text or "empty_text_opf:role"
        for creator in self.creators:
            if creator.role == "aut":
                return creator.text or "empty_text_role"
        return " | ".join([item.text or "empty_text" for item in self.creators])

    def add_metadata(self, tag: DCMetadataType | MetadataType, text: str, dc: bool = True, **kwargs):
        """Uniform helper to add metadata items."""
        new_item = None
        if tag is MetadataType.META:
            # EPUB 3 style <meta property="...">
            new_item = Meta(text=text, **kwargs)
            self.metas.append(new_item)
            return
        if tag == DCMetadataType.IDENTIFIER:
            new_item = DCIdentifier(text=text, **kwargs)
        if tag == DCMetadataType.TITLE:
            new_item = DCTitle(text=text, **kwargs)
        if tag == DCMetadataType.LANGUAGE:
            new_item = DCLanguage(text=text, **kwargs)
        if tag == DCMetadataType.CREATOR or tag == DCMetadataType.CONTRIBUTOR:
            new_item = DCCreator(text=text, **kwargs)
        if tag == DCMetadataType.DATE:
            new_item = DCDate(text=text, **kwargs)
        if tag == DCMetadataType.SUBJECT:
            new_item = DCElement(text=text, **kwargs)
        if new_item is None:
            new_item = DCElement(text=text, **kwargs)
        attr_name = f"{tag}s"  # Find matching list: titles, creators, etc.
        if tag is DCMetadataType.META:
            new_item = DCMeta(text=text, **kwargs)
            attr_name = "dc_metas"
        if hasattr(self, attr_name):
            getattr(self, attr_name).append(new_item)

    def add_tag(self, value: str, **kwargs):
        for subj in self.subjects:
            if subj.text == value:
                return
        self.add_metadata(tag=DCMetadataType.SUBJECT, text=value, **kwargs)

    def referencing(self, ids: set[str]) -> list[Meta]:
        """Return OPF meta entries that depend on the supplied element IDs.

        For {"cover-image"}, this includes <meta name="cover"
        content="cover-image"> and entries with refines="#cover-image".
        If a matching entry has id="r1", entries refining "#r1" are included
        too, continuing until no further dependents are found. An entry whose
        own ID matches is not selected unless it also references a target.

        Resource removal uses this list to reject deletion with dependents or
        explicitly remove them. The returned objects are the live entries in
        self.metas; neither metadata nor the supplied set is changed. Cycles
        terminate, and entries without IDs can still be returned. Other OPF
        sections and external documents are outside this search.
        """
        targets = set(ids)
        selected: list[Meta] = []
        pending = list(self.metas)
        while True:
            additions = [
                meta
                for meta in pending
                if (meta.name == "cover" and meta.content in targets)
                or (meta.refines is not None and meta.refines.startswith("#") and meta.refines[1:] in targets)
            ]
            if not additions:
                return selected
            selected.extend(additions)
            targets.update(meta.id for meta in additions if meta.id)
            added = {id(meta) for meta in additions}
            pending = [meta for meta in pending if id(meta) not in added]

    def remove_metadata(
        self,
        tag: DCMetadataType | MetadataType,
        text: str | None = None,
        id: str | None = None,
        dc: bool = True,
        *,
        item: DCElement | None = None,
    ):
        """Remove entries from the metadata collection selected by tag and dc.

        With dc=True, tag selects a Dublin Core collection (including dc_metas).
        With dc=False, search the OPF meta collection instead. Supplying item
        removes that exact object, taking precedence over text/id; this safely
        handles entries without IDs and preserves equal but distinct siblings.
        Otherwise all supplied text/id criteria must match. Omitting all three
        selectors removes every entry in the selected collection. Missing
        matches do nothing; dependent refinements are not removed automatically.
        """

        selected_item = item

        def should_remove(item) -> bool:
            if selected_item is not None:
                return item is selected_item
            if text is None and id is None:
                return True
            match_text = (text is None) or (getattr(item, "text", None) == text)
            match_id = (id is None) or (getattr(item, "id", None) == id)
            return match_text and match_id

        if dc:
            attr_name = f"{tag}s" if tag != DCMetadataType.META else "dc_metas"
            if hasattr(self, attr_name):
                current = getattr(self, attr_name)
                setattr(self, attr_name, [x for x in current if not should_remove(x)])
        else:
            self.metas = [x for x in self.metas if not should_remove(x)]
