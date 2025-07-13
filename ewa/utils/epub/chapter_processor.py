import warnings
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from bs4 import BeautifulSoup, Tag
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)


@dataclass
class ChapterProcessor:
    path: Path
    soup: BeautifulSoup | None = None
    error: str | None = None

    def read_chapter(self) -> None:
        """Read the chapter from the file into the soup"""
        self.soup = BeautifulSoup(self.path.read_text(encoding="utf-8"), "lxml")

    def write_chapter(self) -> None:
        self.path.write_bytes(self.soup.prettify(encoding="utf-8"))

    def image_tags(self) -> Generator[Tag, None, None]:
        if self.soup is None:
            self.read_chapter()
        yield from self.soup.find_all("img")

    def update_image_references(self, image_processors: list) -> bool:
        """
        Update image references in a chapter
        Args:
            image_processors: The image processors to update.
        Returns:
            True if the image references were updated successfully, False otherwise.
        """
        old_name = None
        pending_updates = defaultdict(int)
        images = {}
        try:
            for img in self.image_tags():
                src = img.get("src")
                for processor in image_processors:
                    old_name = processor.original_path.name
                    if old_name in src:
                        processor.threadsafe_increment_total_references()
                        if not processor.renamed or not processor.success:
                            images[src] = "not renamed"
                            break
                        new_name = processor.new_path.name
                        img["src"] = src.replace(old_name, new_name)
                        pending_updates[processor] += 1
                        images[src] = "renamed"
                        break
                else:
                    images[src] = "not found"

            self.write_chapter()
            for processor, count in pending_updates.items():
                processor.threadsafe_increment_updated_references(count)
            return {"chapter": self.path.name, "images": images, "success": True, "error": None}
        except Exception as e:
            self.error = f"Error updating image references in chapter {self.path}, old name value: {old_name}, failure was recorded: {e}"
            logger.error(self.error)
            return {"chapter": self.path.name, "images": images, "success": False, "error": self.error}

