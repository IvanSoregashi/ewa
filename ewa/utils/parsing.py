import logging
from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def update_image_references(directory: Path, old_path: Path, new_path: Path):
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
            filename.write_text(soup.prettify(encoding="utf-8"))
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