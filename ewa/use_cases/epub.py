import logging
import zipfile
import json
import re
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import ebooklib
from ebooklib.epub import EpubBook, read_epub
from ewa.utils.zip import Zip
from ewa.utils.image import resize_image
from ewa.utils.parsing import update_image_references

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, book_path: Path):
        self.set_path(book_path)
        self._book = None

    @property
    def book(self):
        if self._book is None:
            if self._epub_error is not None:
                raise self._epub_error
            else:
                try:
                    self.read_epub()
                except Exception as e:
                    self._epub_error = e
                    raise e
        return self._book
    
    @book.setter
    def book(self, book: EpubBook):
        self._book = book

    def set_path(self, book_path: Path):
        if not book_path.is_file() or book_path.suffix.lower() != ".epub":
            raise ValueError("Path does not lead to an EPUB file")
        self.book_path = book_path
        self._epub_error = None

    def to_dict(self,
                size: bool=False,
                chapters: bool=False,
                name: bool=False) -> dict:
        dictionary = {"Filename": self.book_path.name}
        if name:
            dictionary["Name"] = self.name()
        if chapters:
            dictionary["Chapters"] = re.search(r"(\d+\s*-\s*\d+)", self.book_path.name).group(1)
        if size:
            dictionary["Size"] = f"{self.book_path.stat().st_size / 1024 / 1024:.2f} Mb"
        return dictionary

    def read_epub(self):
        self.book: EpubBook = read_epub(self.book_path)

    def get_chapters(self):
        return [chapter.file_name for chapter in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT)]

    def get_chapters_zip(self):
        with zipfile.ZipFile(self.book_path) as zip_file:
            return [file for file in zip_file.namelist() if file.startswith("EPUB/chapters/")]

    def get_images(self):
        return [image.file_name for image in self.book.get_items_of_type(ebooklib.ITEM_IMAGE)]

    def get_images_zip(self):
        with zipfile.ZipFile(self.book_path) as zip_file:
            return [file for file in zip_file.namelist() if file.startswith(("EPUB/Images/", "EPUB/images/"))]
    
    def get_images_zip_info(self):
        images = []
        total_size = 0
        with zipfile.ZipFile(self.book_path) as zip_file:
            for file_info in zip_file.infolist():
                if file_info.filename.startswith(("EPUB/Images/", "EPUB/images/")):
                    size = f"{file_info.file_size / 1024 / 1024:.2f} Mb"
                    name = file_info.filename.split("/")[-1]
                    year, month, day, *_ = file_info.date_time
                    date = f"{year}-{month:02d}-{day:02d}"
                    total_size += file_info.file_size
                    images.append({"name": name, "size": size, "date": date})
        total_size = f"{total_size / 1024 / 1024:.2f} Mb"
        images.append({"name": "Total", "size": total_size})
        return images
    

    def zip_info(self):
        images = 0
        image_size = 0
        chapters = 0
        with zipfile.ZipFile(self.book_path) as zip_file:
            data = [(info.filename, info.file_size,) for info in zip_file.infolist()]
        for item in data:
            if item[0].startswith("EPUB/images/"):
                images += 1
                image_size += item[1]
            if item[0].startswith("EPUB/chapters/"):
                chapters += 1
        return {"images": images, "image_size": f"{image_size / 1024 / 1024:.2f} Mb", "chapters": chapters}

    def get_metadata(self, full: bool=False) -> dict | None:
        try:
            if self.book is None:
                self.read_epub()
            if full:
                metadata = self.book.metadata
            else:
                identifiers = [ident[0] for ident in self.book.get_metadata('DC', 'identifier')]
                title = self.book.get_metadata('DC', 'title')[0][0]
                metadata = {"identifier": identifiers, "title": title,}
            return metadata
        except Exception as e:
            logger.error(f"Error reading {self.book_path}: {e}\nTrying zipfile...")
        finally:
            logger.info(self.zip_info())
        



class EPUBUseCases:
    def __init__(self, path: Path = Path.cwd()) -> None:
        self.set_path(path)
        self.epubs = None
        self.table = None
        self.epub = None

    def set_path(self, path: Path) -> None:
        path = Path(path)
        if not path.is_dir():
            raise ValueError("Path is not a directory")
        self.path = path

    def find_epubs(self, recursive: bool = False) -> None:
        self.epubs = [file
                      for file in self.path.glob(f"{'**/' if recursive else ''}*.epub",
                                           case_sensitive=False)]
    
    def form_table(self, recursive: bool=False, size: bool=False, chapters: bool=False) -> list[dict]:
        if self.epubs is None:
            self.find_epubs(recursive)
        self.table = [EPUB(epub).to_dict(size, chapters) for epub in self.epubs]
        return self.table

    def select_epub(self, n: int) -> EPUB:
        if not self.table or not self.epubs:
            logger.warning("No table or epubs found, list files first")
            return None
        epub_path = [epub_path for epub_path in self.epubs if epub_path.name == self.table[n]["Filename"]][0]
        self.epub = EPUB(epub_path)
        self.zip = Zip(epub_path)
        logger.info(f"Selected {epub_path.name}")
        return self.epub
    
    def resize_images_in_epub(self, size_threshold: int = 50 * 1024) -> None:
        if self.epub is None:
            logger.warning("No epub selected, select one first")
            return
        with tempfile.TemporaryDirectory() as tdir:
            temp_dir = Path(tdir)
            self.zip.extract_all(temp_dir)
            with ThreadPoolExecutor() as executor:
                metrics_tuple_futures = [executor.submit(resize_image, args=(filename,))
                                         for filename in temp_dir.glob("EPUB/images/*")
                                         if filename.suffix.lower() in ('.jpg', '.jpeg', '.png')
                                         and filename.stat().st_size > size_threshold]
                for future in as_completed(metrics_tuple_futures):
                    try:
                        old_metrics, new_metrics = future.result()
                    except Exception as e:
                        logger.error(f"Error resizing image {path}: {str(e)[:100]}")
                        continue
                    old_path = old_metrics['path']
                    new_path = new_metrics['path']
                    if old_path == new_path or new_path is None:
                        continue
                    executor.submit(update_image_references, temp_dir, old_path, new_path)

            path = shutil.make_archive("archived_epub", "zip", temp_dir, verbose=True)


        
        
    def analyze_all_epubs(self):
        for epub in self.epubs:
            print(f"Analyzing {epub.name}, {epub.stat().st_size / 1024 / 1024:.2f} Mb")
            if epub.stat().st_size > 10000000:
                for info in Zip(epub).iterate():
                    if info.filename.endswith(".jpg") or info.filename.endswith(".png"):
                        if "cover" in info.filename.lower():
                            print(f"cover {info.filename} is too big with {info.file_size / 1024 / 1024:.2f} Mb")
                        elif info.file_size > 1000000:
                            print(f"file {info.filename} is too big with {info.file_size / 1024 / 1024:.2f} Mb")
    
