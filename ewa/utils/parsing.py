import logging
from typing import Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


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