import logging
import zipfile
import json
import re
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import ebooklib
from ebooklib.epub import EpubBook, read_epub
from ewa.utils.zip import Zip
from ewa.utils.image import resize_image
from ewa.utils.parsing import update_image_references_in_file

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, book_path: Path):
        self.set_path(book_path)
        self._book = None

    @classmethod
    def archive_directory(cls, source_dir: Path, epub_path: Path, skip_list: list[str] = []) -> 'EPUB':
        with zipfile.ZipFile(epub_path, "w") as zipf:
            mimetype_file = source_dir / "mimetype"
            if mimetype_file.exists():
                zipf.write(mimetype_file, arcname="mimetype", compress_type=zipfile.ZIP_STORED)
            else:
                raise FileNotFoundError("Missing required 'mimetype' file for EPUB.")

            for file in source_dir.rglob("*"):
                if file.is_file() and file.name != "mimetype" and file.name not in skip_list:
                    arcname = file.relative_to(source_dir)
                    zipf.write(file, arcname=arcname, compress_type=zipfile.ZIP_DEFLATED)
        return cls(epub_path)

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
        #if name:
        #    dictionary["Name"] = self.name()
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
        self._setup_dirs()
        self.epubs = None
        self.table: list[dict] | None = None
        self.epub: EPUB | None = None
        self.zip: Zip | None = None

    def _setup_dirs(self):
        self.USER_EPUB_DIR = Path("~/Downloads/EPUB").expanduser().absolute()
        self.QUARANTINE_DIR = self.USER_EPUB_DIR / "Quarantine"
        self.RESIZED_DIR = self.USER_EPUB_DIR / "Resized"
        self.UNCHANGED_DIR = self.USER_EPUB_DIR / "Unchanged"

        self.QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
        self.RESIZED_DIR.mkdir(parents=True, exist_ok=True)
        self.UNCHANGED_DIR.mkdir(parents=True, exist_ok=True)

    def _move_epub_to_unchanged_directory(self, epub_path: Path):
        epub_path.rename(self.UNCHANGED_DIR / epub_path.name)

    def _move_epub_to_quarantine(self, epub_path: Path):
        epub_path.rename(self.QUARANTINE_DIR / epub_path.name)

    def _save_epub_to_resized_directory(self, temp_dir: Path, source_path: Path):
        target_path = self.RESIZED_DIR / source_path.name
        epub = EPUB.archive_directory(temp_dir, target_path)
        return target_path
    
    @staticmethod
    def _resize_images_in_epub_temp_dir(temp_dir: Path, size_threshold: int):
        illustration_paths = [
                filename
                for filename in temp_dir.glob("EPUB/images/*")
                if filename.suffix.lower() in ('.jpg', '.jpeg', '.png')
                and filename.stat().st_size > size_threshold
            ]
        
        with ThreadPoolExecutor() as executor:
            return list(executor.map(resize_image, illustration_paths))

    @staticmethod
    def _update_chapter_references(temp_dir: Path, metrics_tuples: list[tuple[dict, dict]]) -> list[dict]:
        """
        Check if image references are to be updated in chapter files.
        Returns a list of metrics for each chapter file.
        """

        update_paths = [
            (old_metrics['path'], new_metrics['path'])
            for old_metrics, new_metrics in metrics_tuples
            if new_metrics['path']
            and old_metrics['success']
            and new_metrics['success']
            and old_metrics['file_size'] != new_metrics['file_size']
        ]

        chapter_paths = [
            (filename, update_paths)
            for filename in temp_dir.glob("EPUB/chapters/*.*html")
        ]
        
        with ThreadPoolExecutor() as executor:
            return list(executor.map(update_image_references_in_file, chapter_paths))

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
    
    def resize_and_save_epub(self, original_path: Path = None, size_threshold: int = 50 * 1024) -> None:
        """
        Resize images in epub.
        If original_path is not provided, the current selected epub is used.
        If size_threshold is not provided, the default is 50 Mb.
        Resized epub is saved in RESIZED_DIR.
        Unused images are removed.
        If some image references were not updated, the epub is moved to QUARANTINE_DIR.
        """
        if self.epub is None and original_path is None:
            logger.error("No epub selected, select one first")
            return
        
        if original_path is None:
            original_path = self.epub.book_path
            zip = self.zip
        else:
            zip = Zip(original_path)

        with tempfile.TemporaryDirectory() as tdir:
            temp_dir = Path(tdir)
            zip.extract_all(temp_dir)

            image_metric_pairs = self._resize_images_in_epub_temp_dir(temp_dir, size_threshold)
            
            formatted_image_metrics = format_image_metrics(image_metric_pairs)

            print(json.dumps(formatted_image_metrics, indent=4))
            if not formatted_image_metrics['changed']:
                logger.warning(f"No images were resized, moving {original_path.name} to UNCHANGED_DIR")
                self._move_epub_to_unchanged_directory(original_path)
                return

            chapter_metrics = self._update_chapter_references(temp_dir, image_metric_pairs)

            if all([metric['success'] for metric in chapter_metrics]):
                logger.warning("All image references updated")
                remove_unused_images(chapter_metrics)
                self._save_epub_to_resized_directory(temp_dir, original_path)
            else:
                logger.error("Some image references were not updated")
                self._move_epub_to_quarantine(original_path)

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
    

def remove_unused_images(metrics: list[dict]) -> bool:
    logger.info(f"Removing unused images, {[metric['for_removal'] for metric in metrics]}")
    for metric in metrics:
        for path in metric['for_removal']:
            logger.info(f"Removing {path.name}")
            if path.exists():
                try:
                    path.unlink()
                except Exception as e:
                    logger.error(f"Error removing {path.name}: {e}")
                    return False
            else:
                logger.warning(f"File {path.name} does not exist")
    return True


def format_image_metrics(metric_pairs: list[tuple[dict, dict]]) -> dict:
    """
    Format image metrics.
    Returns a dictionary with the total old size, total new size, unchanged images, changed images, success, and error.
    """
    total_old_size = 0
    total_new_size = 0
    unchanged = []
    changed = []
    success = True
    error = []
    try:
        for old_metric, new_metric in metric_pairs:
            if old_metric == new_metric:
                if old_metric['success'] and new_metric['success']:
                    unchanged.append(f"{old_metric['path'].name:<20}: {old_metric['mode']} {new_metric['file_size'] / 1024 / 1024:.2f}")
                else:
                    error.append(f"ERROR {old_metric['path'].name:<20}: {old_metric['error']}")
                continue
            if old_metric['mode'] != new_metric['mode']:
                mode = f"{old_metric['mode']} -> {new_metric['mode']}"
            else:
                mode = f"{old_metric['mode']}"
            if old_metric['size'] != new_metric['size']:
                size = f"width {round(new_metric['size'][0] / old_metric['size'][0] * 100)} %"
            else:
                size = f"{old_metric['size'][0]}x{old_metric['size'][1]}"
            if old_metric['file_size'] != new_metric['file_size']:
                filesize = f"filesize {old_metric['file_size'] / 1024 / 1024:.2f} -> {new_metric['file_size'] / 1024 / 1024:.2f} Mb ({round(new_metric['file_size'] / old_metric['file_size'] * 100)} %)"
            else:
                filesize = f"filesize {old_metric['file_size'] / 1024 / 1024:.2f} Mb"
            changed.append(f"{old_metric['path'].name:<20}: {mode:<5} {size:<12} {filesize}")
            total_old_size += old_metric['file_size']
            total_new_size += new_metric['file_size']
    except Exception as e:
        logger.error(f"Error when reading image metric pairs: {e}")
        success = False
    return {
        "success": success,
        "total_old_size": total_old_size,
        "total_new_size": total_new_size,
        "unchanged": unchanged,
        "changed": changed,
        "error": error
    }


def format_chapter_metrics_success(metrics: list[dict]) -> dict:
    pass


def format_chapter_metrics_failure(metrics: list[dict]) -> dict:
    pass