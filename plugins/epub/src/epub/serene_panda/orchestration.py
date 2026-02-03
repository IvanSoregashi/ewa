import json
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from epub.chapter_processor import EpubChapter
from epub.epub_classes import EPUB
from epub.serene_panda.font import process_font
from epub.tables import EpubFileModel, EpubBookTable
from epub.utils import string_to_int_hash64
from ewa.cli.progress import DisplayProgress, track_unknown, track_sized
from ewa.main import settings
from ewa.ui import print_success, print_error
from library.image.ocr import recognize_letter

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


def process_all_fonts_sync(fonts: str = "fonts"):
    """
    receive path to a folder
    process all fonts in the folder synchronously
    """
    fonts = list(Path(fonts).glob("*.ttf"))
    with DisplayProgress():
        for p in track_sized(fonts):
            process_font(p)


def process_all_fonts_mproc(fonts: str = "fonts"):
    """
    receive path to a folder
    process all fonts in the folder in multiple processes
    """
    fonts = list(Path(fonts).glob("*.ttf"))
    with DisplayProgress(), ProcessPoolExecutor() as executor:
        return list(track_unknown(executor.map(process_font, fonts), total=len(fonts)))


def recognize_letters(letters_dir: str):
    """t"""
    letters = list(sorted(Path(letters_dir).glob("*.png"), key=lambda f: f.stat().st_size))
    letters_dict = {}
    with DisplayProgress():
        for letter in track_sized(letters):
            text = recognize_letter(letter)
            letters_dict[letter.stem] = text
    print(letters_dict)
    filepath = Path(letters_dir) / "letters.json"
    filepath.write_text(json.dumps(letters_dict, indent=4), encoding="utf-8")


def form_translation():
    """
    form glyph: letter translation dictionary
    """
    fonts_dir = settings.profile_dir / "epub" / "serene_panda" / "fonts"
    hash_to_letter_file = settings.profile_dir / "epub" / "serene_panda" / "alpha" / "letters_corrected.json"
    hash_to_letter_dict = json.loads(hash_to_letter_file.read_text(encoding="utf-8"))
    font_renders = list(fonts_dir.glob("*.json"))
    translation_path = settings.profile_dir / "epub" / "serene_panda" / "translator.json"

    translation = {}
    with DisplayProgress():
        for render in track_sized(font_renders):
            render = json.loads(render.read_text(encoding="utf-8"))
            for _hash, glyph_list in render.items():
                letter = hash_to_letter_dict[_hash]
                for glyph in glyph_list:
                    translation.setdefault(glyph, set()).add(letter)

    for glyph, letters in (translation.copy()).items():
        if len(letters - {' ', '□'}) == 1:
            translation[glyph] = next(iter(letters - {' ', '□'}))
        else:
            translation[glyph] = glyph

    translation_path.write_text(json.dumps(translation, indent=4, ensure_ascii=False), encoding="utf-8")


def translate_htmls(directory: Path):
    translation_path = settings.profile_dir / "epub" / "serene_panda" / "translator.json"
    translation_dict = json.loads(translation_path.read_text(encoding="utf-8"))
    dictionary = str.maketrans(translation_dict)
    for p in directory.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        html = html.translate(dictionary)
        p.with_stem(p.stem + "_tr").write_text(html, encoding="utf-8")


def translate_epub(path: Path):
    assert path.exists(), "path does not exist"
    print_success(str(path))
    translation_path = settings.profile_dir / "epub" / "serene_panda" / "translator.json"
    translation_dict = json.loads(translation_path.read_text(encoding="utf-8"))
    dictionary = str.maketrans(translation_dict)
    EPUB(path).extract().translate(dictionary).compress(settings.current_dir)


def translate_epubs_in_directory(directory: Path):
    assert directory.is_dir(), "directory does not exist"
    print_success(str(directory))
    translation_path = settings.profile_dir / "epub" / "serene_panda" / "translator.json"
    translation_dict = json.loads(translation_path.read_text(encoding="utf-8"))
    dictionary = str.maketrans(translation_dict)
    with DisplayProgress(), ThreadPoolExecutor() as executor:
        for path in directory.glob("*.epub"):
            EPUB(path).extract().translate(dictionary).compress(settings.current_dir)


def translate_all_encrypted(table: EpubBookTable):
    with DisplayProgress(), ThreadPoolExecutor() as executor:
        for epub in table.get_encrypted_epubs():
            pass
