import logging
import re
from pathlib import Path
from ebooklib import epub

logger = logging.getLogger(__name__)

class EPUB:
    def __init__(self, path: Path):
        self.set_path(path)
        self.book = None

    def set_path(self, path: Path):
        if not path.is_file() or path.suffix.lower() != ".epub":
            raise ValueError("Path is not a valid EPUB file")
        self.path = path

    def to_dict(self,
                size: bool=False,
                chapters: bool=False,
                name: bool=False) -> dict:
        dictionary = {"Filename": self.path.name}
        if name:
            dictionary["Name"] = self.name()
        if chapters:
            dictionary["Chapters"] = re.search(r"(\d+\s*-\s*\d+)", self.path.name).group(1)
        if size:
            dictionary["Size"] = f"{self.path.stat().st_size / 1024 / 1024:.2f} Mb"
        return dictionary

    def read_epub(self):
        self.book = epub.read_epub(self.path)

    def get_metadata(self):
        if self.book is None:
            self.read_epub()
        logger.info(f"Getting metadata for {self.path}, {self.book.metadata}")
        return {
            "identifier": self.book.get_metadata('DC', 'identifier'),
            "title": self.book.get_metadata('DC', 'title'),
            "language": self.book.get_metadata('DC', 'language'),
            "creator": self.book.get_metadata('DC', 'creator'),
            "contributor": self.book.get_metadata('DC', 'contributor'),
            "publisher": self.book.get_metadata('DC', 'publisher'),
            "rights": self.book.get_metadata('DC', 'rights'),
            "coverage": self.book.get_metadata('DC', 'coverage'),
            "date": self.book.get_metadata('DC', 'date'),
            "description": self.book.get_metadata('DC', 'description')
        }


class EPUBUseCase:
    def __init__(self, path: Path) -> None:
        self.set_path(path)
        self.epubs = None

    def set_path(self, path: Path) -> None:
        path = Path(path)
        if not path.is_dir():
            raise ValueError("Path is not a directory")
        self.path = path

    def collect_epubs(self, recursive: bool = False) -> None:
        self.epubs = [file
                for file in self.path.glob(f"{'**/' if recursive else ''}*.epub",
                                           case_sensitive=False)]
    
    def form_table(self, size: bool=False, chapters: bool=False) -> list[dict]:
        return [EPUB(epub).to_dict(size, chapters) for epub in self.epubs]

