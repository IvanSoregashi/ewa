from library.asserts import require
from library.epub.media_type import MediaType, EpubRole
from library.epub.resources import ResourceIndex, Resource
from library.epub.xml_models.package_document import PackageDocument
from library.epub.xml_models.package_sequences import ManifestItem


class EpubManifestItem:
    def __init__(self, resource: Resource, item: ManifestItem) -> None:
        self.resource = resource
        self.item = item

        self.media_type = MediaType(item.media_type)
        self.role = EpubRole.from_id_media_and_path(
            _id=item.id,
            media_type=self.media_type,
            path=resource.info.filename,
        )

        if self.media_type != self.resource.media_type:
            pass


class EpubManifest:
    def __init__(self, resources: ResourceIndex) -> None:
        self.resources = resources

        self._items: list[EpubManifestItem] = []
        self._by_path: dict[str, EpubManifestItem] = {}
        self._by_id: dict[str, EpubManifestItem] = {}

    def __repr__(self) -> str:
        return f"EpubManifest({len(self._items)})"

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, item):
        return self._items[item]

    def __contains__(self, item: EpubManifestItem | str) -> bool:
        if isinstance(item, str):
            return item in self._by_path
        return item in self._items

    @classmethod
    def from_package(cls, package: PackageDocument, resources: ResourceIndex) -> EpubManifest:
        manifest = EpubManifest(resources)
        for opf_manifest_item in package.manifest.items:
            manifest.add_opf_item(opf_manifest_item)
        return manifest

    @classmethod
    def from_manifest_list(cls, manifests: list[EpubManifestItem], resources: ResourceIndex) -> EpubManifest:
        manifest = EpubManifest(resources)
        for manifest_item in manifests:
            manifest.add(manifest_item)
        return manifest

    def add_opf_item(self, opf_manifest_item: ManifestItem) -> None:
        resource = require(self.resources.by_path(opf_manifest_item.href), f"Resource matching {opf_manifest_item}")
        manifest_item = EpubManifestItem(resource=resource, item=opf_manifest_item)
        self.add(manifest_item)

    def add(self, manifest: EpubManifestItem) -> None:
        self._items.append(manifest)
        self._by_path[manifest.item.href] = manifest
        self._by_id[manifest.item.id] = manifest

    def remove(self, manifest: EpubManifestItem) -> None:
        self._items.remove(manifest)
        self._by_id.pop(manifest.item.id)
        self._by_path.pop(manifest.item.href)
        manifest.resource.is_deleted = True

    def remove_by_path(self, path: str) -> None:
        self.remove(require(self.by_path(path), f"manifest path={path}"))

    def remove_by_id(self, _id: str) -> None:
        self.remove(require(self.by_id(_id), f"manifest id={_id}"))

    def by_path(self, path: str) -> EpubManifestItem | None:
        return self._by_path.get(path)

    def by_id(self, _id: str) -> EpubManifestItem | None:
        return self._by_id.get(_id)

    def by_media_type(self, media_type: MediaType) -> EpubManifest:
        return EpubManifest.from_manifest_list(
            manifests=[m for m in self._items if m.media_type is media_type],
            resources=self.resources,
        )

    def by_role(self, role: EpubRole) -> EpubManifest:
        return EpubManifest.from_manifest_list(
            manifests=[m for m in self._items if m.role is role],
            resources=self.resources,
        )
