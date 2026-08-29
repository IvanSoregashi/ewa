from library.asserts import require
from library.epub.epub import EPUB


def replace_links(epub: EPUB, replace_links: dict) -> None:
    manifest = epub.core.manifest
    for old_link, new_link in replace_links.items():
        require(manifest.by_path(old_link), f"Manifest({old_link})").item.href = new_link
