import datetime
import json
import logging
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from itertools import repeat, combinations
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from epub.tables import EpubFileModel, EpubBookTable, EpubContentsTable
from library.epub.utils import string_to_int_hash64, to_hex_hash

from ewa.cli.progress import DisplayProgress, track_unknown, track_sized, track_batch_queue, track_batch_sized
from ewa.main import settings
from ewa.ui import print_success, print_error
from library.database.sqlite_model_table import TERMINATOR
from library.epub.epub_core import EpubSpecification
from library.epub.media_type import MediaType

from library.image.ocr import recognize_letter
from library.image.optimization import useless_transparency_mode
from library.epub.epub import EPUB

logger = logging.getLogger(__name__)


def extract_to_destination(book: EpubFileModel) -> bool:
    try:
        font_bytes = book.to_epub().get_file_bytes(book.serene_panda_ttf)
        hash_num = string_to_int_hash64(font_bytes)
        new_filename = f"{hash_num}_{Path(book.serene_panda_ttf).name}"
        new_filepath = settings.profile_dir / "epub" / "serene_panda" / "fonts" / new_filename
        if not new_filepath.exists():
            new_filepath.write_bytes(font_bytes)
    except Exception as e:
        logger.error(f"extract_to_destination: {e}")
        return True
    return False


def extract_font_files(table: EpubBookTable):
    path = settings.profile_dir / "epub" / "serene_panda" / "fonts"
    path.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=12) as executor:
        errs = list(track_unknown(executor.map(extract_to_destination, track_sized(table.get_encrypted_epubs()))))
        print_error(str(sum(errs)))
        print_success(str(len(errs)))


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
