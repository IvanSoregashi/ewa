import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def check_references(chapter_paths: list[Path], metrics_tuples: list[tuple[dict, dict]]) -> bool:
    update_metrics = [
        (old_metrics, new_metrics)
        for old_metrics, new_metrics in metrics_tuples
        if new_metrics['path'] and old_metrics['path'] != new_metrics['path']
    ]

    with ThreadPoolExecutor() as executor:
        for chapter_path in chapter_paths:
            references = executor.submit(update_image_references_in_file, chapter_path, update_metrics)
            references.add_done_callback(lambda future: future.result())





def update_image_references_in_file(filename: Path, update_metrics: tuple[Path, Path]) -> bool:
    parser = "html.parser" if filename.suffix.lower().endswith("html") else "lxml"
    soup = BeautifulSoup(filename.read_text(encoding="utf-8"), parser)
    new_unlink = []
    old_unlink = []
    references = 0
    if not len(soup.find_all('img')):
        return True, {"references": references, "old_unlink": old_unlink, "new_unlink": new_unlink}
    logger.warning(f"Updating image references in {filename} with total of {len(soup.find_all('img'))} images")
    for img in soup.find_all("img"):
        for old_path, new_path in path_pairs:
            old_name = old_path.name
            new_name = new_path.name
            if old_name in img.get("src"):
                img["src"] = img["src"].replace(old_name, new_name)
                new_unlink.append(new_path)
                old_unlink.append(old_path)
                references += 1
    logger.warning(f"Updated {references} image references in {filename}")
    if references:
        assert len(new_unlink) == references, "Number of paths for unlinking does not match number of references"
        try:
            filename.write_bytes(soup.prettify(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error writing {filename}: {e}")
            for path in new_unlink:
                path.unlink()
            return False
        try:
            for path in old_unlink:
                path.unlink()
            return True, {"references": references}
        except Exception as e:
            logger.error(f"Error deleting {old_unlink}: {e}")
            return False
    return True, {"references": references}


def list_image_references(filename: Path) -> list[str]:
    parser = "html.parser" if filename.suffix.lower().endswith("html") else "lxml"
    soup = BeautifulSoup(filename.read_text(encoding="utf-8"), parser)
    return [img.get("src") for img in soup.find_all("img")]


def count_image_references(filename: Path) -> int:
    return len(list_image_references(filename))