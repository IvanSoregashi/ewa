import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from epub.tables import EpubFileModel, EpubBookTable
from library.epub.utils import string_to_int_hash64

from ewa.cli.progress import track_unknown, track_sized
from ewa.main import settings
from ewa.ui import print_success, print_error

from library.epub.epub import EPUB

logger = logging.getLogger(__name__)


def translation_dictionary(
    translation_path: Path = settings.profile_dir / "epub" / "serene_panda" / "translator.json",
) -> dict:
    translation_dict = json.loads(translation_path.read_text(encoding="utf-8"))
    dictionary = str.maketrans(translation_dict)
    return dictionary


def new_decoded_name(path: Path):
    new_stem = (
        path.stem.replace("(Encrypted)", "")
        .replace("(Encoded)", "")
        .replace("(encoded)", "")
        .replace("+", "")
        .strip()
        .replace("  ", " ")
    )
    new_name = path.with_stem(new_stem).name
    return new_name


def translate_serene_panda(epub_path: Path, destination: Path):
    with EPUB(epub_path).stream_to(destination) as epub:
        if not epub.is_specification(EpubSpecification.SERENE_PANDA_ENCRYPTED):
            logger.error(f"{epub_path} is not a SERENE_PANDA_ENCRYPTED EPUB")
            return

        # 1. translate htmls
        # 2. remove font file
        # 3. remove font from opf
        # 4. remove font from css


def unpack_epub_by_chapters(epub_path: Path):
    pass

    #  epub core
    #  cover, titlepage, content.opf, toc.ncx
    #  common resources
    #  (styles, fonts) mimetype?, META-INF?,
    #


def move_file_preserving_hierarchy(path: Path, destination_dir: Path):
    for dirpath in list(Path("D:/").glob("*EPUB*")) + [Path(r"C:\Users\Ivan\Sync\Books")]:
        if path.is_relative_to(dirpath):
            if dirpath == destination_dir:
                logger.warning(f"SKIPPING MOVING: {str(dirpath)!r} == {str(path)!r}")
                return
            relative_path = path.relative_to(dirpath)
            break
    else:
        raise AssertionError(f"Relative root path not found {str(path)!r}")
    new_path = destination_dir / relative_path
    new_path.parent.mkdir(parents=True, exist_ok=True)
    while new_path.exists():
        if path.read_bytes() == new_path.read_bytes():
            path.unlink()
            logger.warning(f"EXISTS: {str(new_path)!r}\nDELETING: {str(path)!r}\nSUCCESS: {not path.exists()}")
            return
        else:
            new_path = new_path.with_stem(new_path.stem + "_copy")
    try:
        logger.info(f"MOVING: {str(path)!r} -> {str(new_path)!r}")
        shutil.move(str(path), str(new_path))
    except PermissionError:
        zone_stream = Path(f"{str(path)}:Zone.Identifier")
        if zone_stream.exists():
            logger.warning(f"PermissionError. Zone.Identifier exists in {str(zone_stream)!r}. removing.")
            try:
                zone_stream.unlink()
                shutil.move(str(path), str(new_path))
            except Exception as e:
                logger.warning(f"PermissionError. PermissionError. {e}.")
    except Exception as e:
        logger.error(f"MOVING: {str(path)!r} -> {str(new_path)!r}: {e}")
