import json
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from itertools import repeat
from pathlib import Path

from epub.epub_classes import EPUB
from epub.serene_panda.font import process_font
from epub.tables import EpubFileModel, EpubBookTable
from epub.utils import string_to_int_hash64
from epub.constants import translated_directory, untranslated_directory
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
        if len(letters - {" ", "□"}) == 1:
            translation[glyph] = next(iter(letters - {" ", "□"}))
        else:
            translation[glyph] = glyph

    translation_path.write_text(json.dumps(translation, indent=4, ensure_ascii=False), encoding="utf-8")


def translation_dictionary(
    translation_path: Path = settings.profile_dir / "epub" / "serene_panda" / "translator.json",
) -> dict:
    translation_dict = json.loads(translation_path.read_text(encoding="utf-8"))
    dictionary = str.maketrans(translation_dict)
    return dictionary


def translate_htmls(directory: Path):
    dictionary = translation_dictionary()
    for p in directory.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        html = html.translate(dictionary)
        p.with_stem(p.stem + "_tr").write_text(html, encoding="utf-8")


def translate_epub(
    epub: EPUB,
    dictionary: dict,
    translated_dir: Path = translated_directory,
    untranslated_dir: Path = untranslated_directory,
) -> EPUB:
    new_stem = (
        epub.path.stem.replace("(Encrypted)", "")
        .replace("(Encoded)", "")
        .replace("(encoded)", "")
        .replace("+", "")
        .strip()
        .replace("  ", " ")
    )
    new_name = epub.path.with_stem(new_stem).name
    new_epub = None
    try:
        new_epub = epub.extract().translate(dictionary).rename(new_name).compress(translated_dir)
    except Exception as e:
        print_error(str(e))
    epub.move_original_to(untranslated_dir)
    return new_epub


def translate_epub_path(
    path: Path,
    dictionary: dict,
    translated_dir: Path = translated_directory,
    untranslated_dir: Path = untranslated_directory,
) -> EPUB:
    return translate_epub(EPUB(path), dictionary, translated_dir, untranslated_dir)


def translate_epub_model(
    epub: EpubFileModel,
    dictionary: dict,
    translated_dir: Path = translated_directory,
    untranslated_dir: Path = untranslated_directory,
) -> EPUB:
    return translate_epub(epub.to_epub(), dictionary, translated_dir, untranslated_dir)


def translate_one_epub(path: Path):
    dictionary = translation_dictionary()
    return translate_epub_path(path, dictionary, translated_directory, untranslated_directory)


def translate_epubs_in_directory(
    directory: Path, translated_dir: Path = translated_directory, untranslated_dir: Path = untranslated_directory
):
    dictionary = translation_dictionary()
    paths = list(directory.glob("*(Encoded)*.epub"))
    with DisplayProgress(), ThreadPoolExecutor() as executor:
        list(
            track_unknown(
                executor.map(
                    translate_epub_path, paths, repeat(dictionary), repeat(translated_dir), repeat(untranslated_dir)
                ),
                total=len(paths),
            )
        )


def translate_all_encrypted(
    table: EpubBookTable, translated_dir: Path = translated_directory, untranslated_dir: Path = untranslated_directory
):
    dictionary = translation_dictionary()
    epubs = table.get_encrypted_epubs()
    with DisplayProgress(), ThreadPoolExecutor() as executor:
        list(
            track_unknown(
                executor.map(
                    translate_epub_model, epubs, repeat(dictionary), repeat(translated_dir), repeat(untranslated_dir)
                ),
                total=len(epubs),
            )
        )
