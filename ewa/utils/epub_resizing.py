import json
import logging
import tempfile
import pandas as pd
from typing import Any
from pathlib import Path
from zipfile import ZipFile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger(__name__)


def setup_dirs() -> tuple[Path, Path, Path]:
    """
    return quarantine_dir, resized_dir, unchanged_dir
    """
    user_epub_dir = Path("~/Downloads/EPUB").expanduser().absolute()
    quarantine_dir = user_epub_dir / "Quarantine"
    resized_dir = user_epub_dir / "Resized"
    unchanged_dir = user_epub_dir / "Unchanged"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    resized_dir.mkdir(parents=True, exist_ok=True)
    unchanged_dir.mkdir(parents=True, exist_ok=True)
    return quarantine_dir, resized_dir, unchanged_dir


def directory_file_statistics(path: Path):
    return [
        {
            "path": filepath,
            "size": filepath.stat().st_size,
            "suffix": filepath.suffix.lower(),
            "name": filepath.stem,
            "directory": filepath.parent.relative_to(path)
        } 
        for filepath in path.rglob("*")
    ]


def analyze_file_statistic(path: Path | None = None, data: list[dict] | None = None):
    if not path and not not data:
        raise ValueError("analyze_file_statistic is called without argument")
    if path:
        data = directory_file_statistics(path)
    df = pd.DataFrame(data)
    total_size = df["size"].sum()


def resize_images_in_epub(epub_path: Path, size_threshold: int = 50 * 1024) -> None:
    """
    Resize images in an epub.
    Returns the path to the epub.
    """
    if not epub_path.exists() and epub_path.suffix.lower() != '.epub':
        raise FileNotFoundError(f"EPUB file not found: {epub_path}")

    quarantine_dir, resized_dir, unchanged_dir = setup_dirs()

    # check the path
    with tempfile.TemporaryDirectory() as tdir, ThreadPoolExecutor(max_workers=50) as executor:
        temp_dir = Path(tdir)
        with ZipFile(epub_path) as zip_file:
            zip_file.extractall(temp_dir)

        stats = directory_file_statistics(temp_dir, images={"glob": "EPUB/images/*", "suffix": ('.jpg', '.jpeg', '.png')}, chapters={"glob": "EPUB/chapters/*.*html"})
        print(json.dumps(stats, indent=4))
        
        # get the illustration paths
        illustration_paths = [
                filename
                for filename in temp_dir.glob("EPUB/images/*")
                if filename.suffix.lower() in ('.jpg', '.jpeg', '.png')
                and filename.stat().st_size > size_threshold
            ]

        # resize the images
        image_metric_pairs = list(executor.map(resize_image, illustration_paths))

        # format the image metrics
        formatted_image_metrics = format_image_metrics(image_metric_pairs)
        print(json.dumps(formatted_image_metrics, indent=4))

        # if no images were resized, move the epub to the unchanged directory
        if not formatted_image_metrics['changed']:
            return epub_path

        # get the update paths for the images
        update_paths = [
            (old_metrics['path'], new_metrics['path'])
            for old_metrics, new_metrics in image_metric_pairs
            if new_metrics['path']
            and old_metrics['success']
            and new_metrics['success']
            and old_metrics['file_size'] != new_metrics['file_size']
        ]

        chapter_paths = [
            (filename, update_paths)
            for filename in temp_dir.glob("EPUB/chapters/*.*html")
        ]
        
        chapter_metrics = list(executor.map(update_image_references_in_file, chapter_paths))

        #if all([metric['success'] for metric in chapter_metrics]):
        #    logger.warning("All image references updated")
        #    remove_unused_images(chapter_metrics)
        #    self._save_epub_to_resized_directory(temp_dir, original_path)
        #else:
        #    logger.error("Some image references were not updated")
        #    self._move_epub_to_quarantine(original_path)



def resize_image(image_path: Path, max_width: int = 1080, max_height: int | None = None, quality: int = 80) -> tuple[dict, dict]:
    """
    Resize image.
    Returns a tuple of old metrics and new metrics.
    """
    new_path = None
    try:
        with Image.open(image_path) as image:
            old_metrics = image_metrics(image, image_path)
            old_dimensions, new_dimensions = calculate_dimensions(image, max_width, max_height)
            resize = old_dimensions != new_dimensions
            convert = is_convert_needed(image)

            if resize:
                image = image.resize(new_dimensions, Image.Resampling.LANCZOS)
            
            if convert:
                image = image.convert('RGB')

            if resize or convert:
                new_path = save_image(image, image_path, quality)                
            else:
                new_path = image_path

            new_metrics = image_metrics(image, new_path)
            return old_metrics, new_metrics
    except Exception as e:
        logger.error(f"Error resizing image {image_path}: {str(e)[:100]}")
        if new_path and new_path.exists():
            new_path.unlink()
        return {
            'success': False,
            'error': e,
            'path': image_path
        }, {
            'success': False,
            'error': e,
            'path': image_path
        }



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

def calculate_dimensions(image: Image.Image, max_width: int = 1080, max_height: int | None = None) -> tuple[tuple[int, int], tuple[int, int]]:
    width, height = image.size
    new_width, new_height = width, height
    if width > max_width:
        ratio = max_width / width
        new_width = max_width
        new_height = int(height * ratio)
    if max_height is not None and new_height > max_height:
        ratio = max_height / new_height
        new_width = int(width * ratio)
        new_height = max_height
    return (width, height), (new_width, new_height)


def is_convert_needed(image: Image.Image) -> bool:
    if image.mode == 'RGBA':
        extrema = image.getextrema()
        if len(extrema) != 4:
            return False
        no_transparency = extrema[3][0] == 255
        return no_transparency
    if image.mode == 'RGB':
        return True
    return False


def save_image(image: Image.Image, path: Path, quality) -> Path:
    if path.suffix.lower() in ('.jpg', '.jpeg'):
        image.save(path, optimize=True, quality=quality)
        return path
    if image.mode == 'RGB':
        new_path = path.with_stem(path.stem).with_suffix('.jpg')
        image.save(new_path, optimize=True, quality=quality)
        return new_path
    if path.suffix.lower() == '.png':
        image.save(path, optimize=True)
        return path
    raise ValueError(f"Unsupported image format: {path.suffix}, mode: {image.mode}, path: {path}")


def image_metrics(image: Image.Image, path: Path) -> dict:
    size = path.stat().st_size
    return {
        'path': path,
        'file_size': size,
        'size': image.size,
        'mode': image.mode,
        'format': path.suffix.lower(), 
        'success': True
    }




def update_image_references_in_file(data: tuple[Path, list]) -> dict:
    filepath, update_paths = data
    soup = BeautifulSoup(filepath.read_text(encoding="utf-8"), "lxml")
    metric: dict[str, Any] = {}
    metric['filename'] = filepath
    metric['success'] = True
    metric['for_removal'] = []
    metric['old_images'] = [img.get("src").split("/")[-1] for img in soup.find_all("img")]

    for img in soup.find_all("img"):
        for old_path, new_path in update_paths:
            old_name = old_path.name
            new_name = new_path.name
            if old_name in img["src"]:
                img["src"] = img["src"].replace(old_name, new_name)
                metric['for_removal'].append(old_path)
    
    metric['new_images'] = [img.get("src").split("/")[-1] for img in soup.find_all("img")]
    
    try:
        filepath.write_bytes(soup.prettify(encoding="utf-8"))
        return metric
    except Exception as e:
        logger.error(f"Error writing chapter {filepath}, aborting epub: {e}")
        metric['success'] = False
        return metric


def list_image_references(filename: Path) -> list[str]:
    parser = "html.parser" if filename.suffix.lower().endswith("html") else "lxml"
    soup = BeautifulSoup(filename.read_text(encoding="utf-8"), parser)
    return [img.get("src") for img in soup.find_all("img")]


def count_image_references(filename: Path) -> int:
    return len(list_image_references(filename))