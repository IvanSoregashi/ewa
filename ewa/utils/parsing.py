import logging
from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def update_image_references_in_directory(directory: Path, old_path: Path, new_path: Path):
    references = 0
    old_name = old_path.name
    new_name = new_path.name
    for filename in directory.glob("EPUB/chapters/*.*html"):
        try:
            parser = "html.parser" if filename.suffix.lower().endswith("html") else "lxml"
            soup = BeautifulSoup(filename.read_text(encoding="utf-8"), parser)
            for img in soup.find_all("img"):
                if old_name in img.get("src"):
                    img["src"] = img["src"].replace(old_name, new_name)
                    references += 1
            filename.write_bytes(soup.prettify(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error updating image references in {filename}: {e}")
    if references:
        logger.warning(f"Updated {references} image references, {old_name} -> {new_name}, deleting")
        try:
            old_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Error deleting old path: {e}")
    else:
        logger.warning(f"No image references found, {old_name} -> {new_name}, deleting new path")
        try:
            new_path.unlink()
        except Exception as e:
            logger.error(f"Error deleting new path: {e}")
    return False


def update_image_references_in_file(filename: Path, path_pairs: tuple[Path, Path]) -> bool:
    parser = "html.parser" if filename.suffix.lower().endswith("html") else "lxml"
    soup = BeautifulSoup(filename.read_text(encoding="utf-8"), parser)
    new_unlink = []
    old_unlink = []
    references = 0
    if not len(soup.find_all('img')):
        return True
    logger.warning(f"Updating image references in {filename} with total of {len(soup.find_all('img'))} images")
    for img in soup.find_all("img"):
        for old_path, new_path in path_pairs:
            old_name = old_path.name
            new_name = new_path.name
            if old_name in img.get("src"):
                img["src"] = img["src"].replace(old_name, new_name)
                old_unlink.append(old_path)
                new_unlink.append(new_path)
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
            return True
        except Exception as e:
            logger.error(f"Error deleting {old_unlink}: {e}")
            return False
    return True


def list_image_references(filename: Path) -> list[str]:
    parser = "html.parser" if filename.suffix.lower().endswith("html") else "lxml"
    soup = BeautifulSoup(filename.read_text(encoding="utf-8"), parser)
    return [img.get("src") for img in soup.find_all("img")]


def count_image_references(filename: Path) -> int:
    return len(list_image_references(filename))