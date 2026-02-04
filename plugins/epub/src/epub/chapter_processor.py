import warnings
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Generator
import time

from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup, Tag
from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)


class EpubChapter:
    def __init__(self, path: Path):
        self.path: Path = path
        self._text: str | None = None
        self._soup: BeautifulSoup | None = None
        self.references_updated: int = 0

        self.warnings: list[str] = []
        self.error: str | None = None

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, EpubChapter):
            return False
        return self.path == other.path

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.path.read_text(encoding="utf-8")
        return self._text

    @text.setter
    def text(self, text: str) -> None:
        self._text = text
        self._soup = None
        self.path.write_text(text, encoding="utf-8")

    @property
    def soup(self) -> BeautifulSoup:
        if self._soup is None:
            self._soup = BeautifulSoup(self.text, "lxml")
        return self._soup

    def translate(self, table: dict) -> None:
        self.text = self.text.translate(table)

    def image_tags(self) -> Generator[Tag, None, None]:
        yield from self.soup.find_all("img")

    def get_linked_image_names(self) -> list[str]:
        list_of_refs = []
        for img in self.image_tags():
            src = str(img.get("src"))
            expected_folder = "../Images/"
            if not src.startswith(expected_folder):
                self.warnings.append(
                    f"Chapter {self.path.name} has image reference {src} that is not in the Images directory"
                )
                continue
            list_of_refs.append(src.replace(expected_folder, ""))
        return list_of_refs

    def update_image_references(self, replacers: dict[str, str]) -> bool:
        try:
            for img in self.image_tags():
                src = img.get("src")
                img_name = src.split("/")[-1]
                if img_name in replacers:
                    img["src"] = src.replace(img_name, replacers[img_name])
                    self.references_updated += 1

            if self.references_updated > 0:
                self.path.write_bytes(self._soup.prettify(encoding="utf-8"))
            return True
        except Exception as e:
            self.error = f"{self.path.name}: {e}"
            self.references_updated = 0
            logger.error(self.error)
            return False
        finally:
            self._soup = None

    def to_dict(self) -> dict:
        return {
            "name": str(self.path.name),
            "references": self.references_updated,
            "error": self.error[:20] if self.error else "",
        }


class EpubChapters:
    def __init__(self, unpacked_epub_dir: Path):
        self.unpacked_epub_dir = unpacked_epub_dir
        self.chapters_dir = unpacked_epub_dir / "EPUB" / "chapters"
        self.chapters: list[EpubChapter] = list(map(EpubChapter, self.iter_chapter_paths()))
        self.image_references: dict[int, list[str]] | None = None

        self.update_time: float = 0

    def __len__(self) -> int:
        return len(self.chapters)

    def __iter__(self):
        return iter(self.chapters)

    def iter_chapter_paths(self) -> Generator[Path, None, None]:
        for path in self.chapters_dir.glob("*.*html"):
            yield path

    def apply(self, method: Callable, *args, **kwargs):
        results = []
        for chapter in self.chapters:
            result = method(chapter, *args, **kwargs)
            results.append(result)
        return results

    def map_image_references(self, update: bool = False) -> dict[int, list[str]]:
        if not update and self.image_references is not None:
            return self.image_references
        result = {}
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            refs = executor.map(EpubChapter.get_linked_image_names, self.chapters)
        for i, refs in enumerate(refs):
            if refs:
                result[i] = refs
        self.image_references = result
        return result

    @property
    def with_images(self) -> list[EpubChapter]:
        return [self.chapters[i] for i in self.map_image_references()]

    @property
    def errors(self) -> list[str] | None:
        return [ch.error for ch in self.with_images if ch.error is not None]

    @property
    def updated(self) -> int:
        return len([ch for ch in self.chapters if ch.references_updated > 0])

    def cross_reference_images(self, images: list[str]) -> tuple[bool, list[tuple[int, list[str]]], list[str]]:
        """
        Cross reference images
        Args:
            images: The images to cross reference.
        Returns:
            True if the images were cross referenced successfully, False otherwise.
            List of chapters with orphan images.
            List of images without references.
        """
        all_refs = [value for sublist in self.map_image_references().values() for value in sublist]
        if set(all_refs) != set(images):
            ch_with_orphans = [
                (i, [ref for ref in refs if ref not in images])
                for i, refs in self.map_image_references().items()
                if not all(ref in images for ref in refs)
            ]
            imgs_without_refs = [img for img in images if img not in all_refs]
            return False, ch_with_orphans, imgs_without_refs
        return True, [], []

    def update_image_references(self, replacers: dict[str, str]) -> bool:
        """
        Update image references in a chapter
        Args:
            replacers: The replacers to update.
        Returns:
            True if the image references were updated successfully, False otherwise.
        """
        start_time = time.time()
        chapters_with_images = self.with_images
        list_of_replacers = [replacers] * len(chapters_with_images)
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            results = executor.map(
                EpubChapter.update_image_references,
                chapters_with_images,
                list_of_replacers,
            )
        self.update_time = time.time() - start_time
        return all(results)

    def short_report(self) -> dict:
        return {
            "chapters t/u/e": f"{len(self)} / {self.updated} / {len(self.errors)}",
            "time": f"{self.update_time:.2f} s",
        }

    def detailed_report(self) -> list[dict]:
        return [ch.to_dict() for ch in self.chapters if ch.error is not None or ch.references_updated > 0]
