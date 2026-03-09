import datetime
import json
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from itertools import repeat, combinations
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from epub.epub_classes import EPUB, ScanEpubsInDirectory
from epub.file_parsing import parse_container_xml, parse_content_opf
from epub.serene_panda.font import process_font
from epub.tables import EpubFileModel, EpubBookTable, EpubContentsTable
from epub.utils import string_to_int_hash64, to_hex_hash
from epub.constants import (
    translated_directory,
    translated_r_directory,
    untranslated_directory,
    epub_dir,
    quarantine_directory,
)
from ewa.cli.progress import DisplayProgress, track_unknown, track_sized, track_batch_queue, track_batch_sized
from ewa.main import settings
from ewa.ui import print_success, print_error
from library.database.sqlite_model_table import TERMINATOR
from library.epub.xml_models.opf_model import Metadata, PackageDocument
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


def translate_epub(
    epub: EPUB,
    dictionary: dict,
    translated_dir: Path = translated_directory,
    untranslated_dir: Path = untranslated_directory,
) -> EPUB:
    new_name = new_decoded_name(epub.path)
    new_epub = None
    # add
    # unminify html
    # remove ttf font from contents.opf
    #
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


def search_duplicates(table: EpubBookTable):
    results = table.get_most_common(["filesize"], more_then=1)
    rows = table.get_many(table.model.filesize.in_(results))
    print(*[(row.filepath, row.filesize) for row in rows], sep="\n")
    pairs = []
    for row in rows:
        path = Path(row.filepath)
        h = string_to_int_hash64(path.read_bytes())
        pairs.append((path, h, row.filesize))
    for pair in combinations(pairs, 2):
        (p1, h1, s1), (p2, h2, s2) = pair
        if s1 == s2 and h1 == h2:
            print_success(f"{p1} and {p2} are identical")
            if p1.stem == p2.stem + "+":
                p1.unlink()
                print_success(f"deleting {p1}")
            if p2.stem == p1.stem + "+":
                p2.unlink()
                print_success(f"deleting {p2}")
            if p2.stem == p1.stem:
                p2.unlink()
                print_success(f"deleting {p2}")
        elif s1 == s2:
            print_success(f"same size {s1} ({h1} vs {h2}) {p1} and {p2}")
            if p1.stem == p2.stem + "+":
                result = find_differences(p1, p2)
                if result:
                    print_success(f"\tdiff success {p1, p2}")
                    p1.unlink()
                    print_success(f"deleting {p1}")
                    continue
            if p2.stem == p1.stem + "+":
                result = find_differences(p1, p2)
                if result:
                    print_success(f"\tdiff success {p1, p2}")
                    p2.unlink()
                    print_success(f"deleting {p2}")
                    continue
            if p2.stem == p1.stem:
                result = find_differences(p1, p2)
                if result:
                    print_success(f"\tdiff success {p1, p2}")
                    p2.unlink()
                    print_success(f"deleting {p2}")
                    continue
            result = find_differences(p1, p2)
            if result:
                print_success(f"\tdiff success {p1, p2}")
                print_error(f"\t\tnot deleting - different names {p1, p2}")


def find_differences(epub1: Path, epub2: Path) -> bool:
    dict1 = EPUB(epub1).file_identities_dict()
    dict2 = EPUB(epub2).file_identities_dict()
    if list(sorted(dict1.keys())) != list(sorted(dict2.keys())):
        set_list = set(dict1.keys()) ^ set(dict2.keys())
        print_error(f"\t\tdiff fail, different files {list(set_list)[:10]}")
        return False
    diffs = []
    for (f1, h1), (f2, h2) in zip(sorted(dict1.items()), sorted(dict2.items())):
        if f1 != f2 or h1 != h2:
            diffs.append((f1, h1, h2))
    if diffs:
        print_error(f"\t\tdiff fail, different hashes {diffs}")
        return False
    return True


def find_differences_in_sizes(epub1: Path, epub2: Path) -> bool:
    dict1 = EPUB(epub1).file_identities_and_sizes_dict()
    dict2 = EPUB(epub2).file_identities_and_sizes_dict()
    folders = {
        "fonts/",
        "EPUB/chapters/",
        "fonts/SerenePanda.ttf",
        "META-INF/",
        "EPUB/",
        "EPUB/images/",
        "EPUB/Images/",
    }
    if list(sorted(dict1.keys())) != list(sorted(dict2.keys())):
        set_list = (set(dict1.keys()) ^ set(dict2.keys())) - folders
        if set_list:
            print_error(f"\t\tdiff fail, different files {list(set_list)[:10]}")
            return False
    diffs = []
    i1 = ((f, s, h) for f, (s, h) in sorted(dict1.items()) if f not in folders)
    i2 = ((f, s, h) for f, (s, h) in sorted(dict2.items()) if f not in folders)

    ratios = []
    for (f1, s1, h1), (f2, s2, h2) in zip(i1, i2):
        if f1 == f2 and f1.endswith("html"):
            ratios.append((s2 / s1) * 100)
            continue
        if f1 == f2 and s1 != s2:
            diffs.append((f1, s1, s2))
            continue
        if f1 == f2 and h1 != h2:
            diffs.append((f1, h1, h2))
            continue
        if f1 != f2:
            print_error(f"paths are not equal for {epub1} and {epub2}")
            break

    if diffs:
        print_error(f"\t\tdiff fail, different hashes: \n{'\n'.join(str(diff) for diff in diffs[:10])}")
        return False
    if not diffs:
        avg_ratio = int(sum(ratios) / len(ratios)) if len(ratios) else 0
        print_success(f"\t\tdiff success (avg html ratio {avg_ratio}), total files ({len(dict1)}) for {epub1}")
    return True


def scan_folder(path: Path | None = None):
    path = path or epub_dir
    print_success(f"Scanning {path}...")
    with DisplayProgress(), EpubContentsTable() as contents_table, EpubBookTable() as book_table:
        scanning = ScanEpubsInDirectory(path, workers=4)
        contents_table.write_from_queue_in_thread(track_batch_queue(scanning.queue, TERMINATOR))
        book_list = scanning.do_scan_with_progress()
        contents_table.await_write_completion()
        book_table.upsert_many_dicts(track_batch_sized([row.model_dump() for row in book_list]))


def compare_epubs():
    translated_paths = [path for path in translated_directory.glob("*.epub")]

    for path in untranslated_directory.glob("*.epub"):
        new_name = new_decoded_name(path)
        expected_path = translated_directory / new_name
        if not expected_path.exists():
            print_error(f"\tno double for {path.name}, {expected_path.name} does not exist")
            continue
        if expected_path in translated_paths:
            translated_paths.remove(expected_path)
        else:
            print_error(f"existence: {expected_path} exists but not in translated_directory")
        ratio = (expected_path.stat().st_size / path.stat().st_size) * 100
        if ratio < 25:
            print_success(
                f"weight: {int(ratio)}% of the {path.stat().st_size / 1024 / 1024:.2f} MB original, the {expected_path} is"
            )
            result = find_differences_in_sizes(path, expected_path)

    if translated_paths:
        print_error(f"\t{translated_paths}")


def return_untranslated_back(table: EpubBookTable):
    moved = 0
    error = 0
    skipped = 0
    for epub in track_sized(table.get_encrypted_epubs()):
        table_path = Path(epub.filepath)
        path1 = untranslated_directory / table_path.name

        tr_path = translated_directory / new_decoded_name(table_path)
        new_tr_path = translated_r_directory / tr_path.name
        if path1 == table_path:
            skipped += 1
            continue
        if path1.exists():
            try:
                path1.rename(table_path)
                moved += 1
                if tr_path.exists() and not new_tr_path.exists():
                    tr_path.rename(new_tr_path)
                continue
            except Exception as e:
                print_error(f"{e}")
                error += 1
    print_success(f"{moved=} {skipped=}")
    print_error(f"\t{error=}")


def move_remains():
    for epub in untranslated_directory.glob("*.epub"):
        dtfrom = datetime.datetime.strptime("2026-01-21 00:00:00", "%Y-%m-%d %H:%M:%S")
        dtto = datetime.datetime.strptime("2026-01-21 01:00:00", "%Y-%m-%d %H:%M:%S")
        dt = datetime.datetime.fromtimestamp(epub.stat().st_ctime)
        if dtfrom < dt < dtto:
            print(dt, epub.stem)
            try:
                epub.rename(epub_dir / "21.01.26 f h" / epub.name)
                tr_path = translated_directory / new_decoded_name(epub)
                if tr_path.exists():
                    tr_path.rename(translated_r_directory / tr_path.name)
            except Exception as e:
                print_error(f"epub {epub.stem} error: {e}")


def extract_opf_to_destination(epub_path: Path, opf_path: str | None = None) -> bool:
    if quarantine_directory in epub_path.parents:
        print_error(f"skipping {epub_path}")
        return True
    with ZipFile(epub_path) as epub_zip:
        try:
            if opf_path is None:
                opf_path = parse_container_xml(epub_zip)
            opf_bytes = epub_zip.read(opf_path)
            opf_hash = to_hex_hash(opf_bytes)
            new_filepath = settings.profile_dir / "epub" / "opf" / f"{opf_hash}_{Path(opf_path).name}"
            if not new_filepath.exists():
                new_filepath.write_bytes(opf_bytes)
        except Exception as e:
            logger.error(f"extract_opf_to_destination: {e}")
            return True
        return False


def extract_package_files():
    destination = settings.profile_dir / "epub" / "opf"
    destination.mkdir(parents=True, exist_ok=True)
    epub_paths = list(epub_dir.rglob("*.epub"))
    with DisplayProgress(), ThreadPoolExecutor(max_workers=12) as executor:
        errs = list(track_unknown(executor.map(extract_opf_to_destination, epub_paths), total=len(epub_paths)))
        print_error(str(sum(errs)))
        print_success(str(len(errs)))


def extract_nav_to_destination(epub_path: Path) -> bool:
    if quarantine_directory in epub_path.parents:
        print_error(f"skipping {epub_path}")
        return True
    with ZipFile(epub_path) as epub_zip:
        try:
            opf_path = parse_container_xml(epub_zip)
            navs = parse_content_opf(epub_zip, opf_path)["navs"]
            if not navs:
                return False
            for nav in navs:
                f_bytes = epub_zip.read(nav)
                f_hash = to_hex_hash(f_bytes)
                new_filepath = settings.profile_dir / "epub" / "nav" / f"{f_hash}_{Path(nav).name}"
                if not new_filepath.exists():
                    new_filepath.write_bytes(f_bytes)
        except Exception as e:
            logger.error(f"extract_nav_to_destination: {e}")
            return True
        return False


def extract_nav_files():
    destination = settings.profile_dir / "epub" / "nav"
    destination.mkdir(parents=True, exist_ok=True)
    epub_paths = list(epub_dir.rglob("*.epub"))
    with DisplayProgress(), ThreadPoolExecutor(max_workers=12) as executor:
        errs = list(track_unknown(executor.map(extract_nav_to_destination, epub_paths), total=len(epub_paths)))
        print_error(str(sum(errs)))
        print_success(str(len(errs)))


def extract_ncx_to_destination(epub_path: Path) -> bool:
    if quarantine_directory in epub_path.parents:
        print_error(f"skipping {epub_path}")
        return True
    with ZipFile(epub_path) as epub_zip:
        try:
            for filename in epub_zip.namelist():
                if not filename.endswith(".ncx"):
                    continue
                f_bytes = epub_zip.read(filename)
                f_hash = to_hex_hash(f_bytes)
                new_filepath = settings.profile_dir / "epub" / "ncx" / f"{f_hash}_{Path(filename).name}"
                if not new_filepath.exists():
                    new_filepath.write_bytes(f_bytes)
        except Exception as e:
            logger.error(f"extract_nav_to_destination: {e}")
            return True
        return False


def extract_ncx_files():
    destination = settings.profile_dir / "epub" / "ncx"
    destination.mkdir(parents=True, exist_ok=True)
    epub_paths = list(epub_dir.rglob("*.epub"))
    with DisplayProgress(), ThreadPoolExecutor(max_workers=12) as executor:
        errs = list(track_unknown(executor.map(extract_ncx_to_destination, epub_paths), total=len(epub_paths)))
        print_error(str(sum(errs)))
        print_success(str(len(errs)))




def analyze_metadata(metadata: Metadata):
    lengths = {
        "titles": len(metadata.titles),
        "creators": len(metadata.creators),
        "subjects": len(metadata.subjects),
        "descriptions": len(metadata.descriptions),
        "publishers": len(metadata.publishers),
        "contributors": len(metadata.contributors),
        "dates": len(metadata.dates),
        "types": len(metadata.types),
        "formats": len(metadata.formats),
        "identifiers": len(metadata.identifiers),
        "sources": len(metadata.sources),
        "languages": len(metadata.languages),
        "relations": len(metadata.relations),
        "coverages": len(metadata.coverages),
        "rights": len(metadata.rights),
        "metas": len(metadata.metas),
        "dc_metas": len(metadata.dc_metas),
    }

    contents = {
        "titles": [i.text for i in metadata.titles],
        "creators": [i.text for i in metadata.creators],
        "subjects": [i.text for i in metadata.subjects],
        "descriptions": [i.text for i in metadata.descriptions],
        "publishers": [i.text for i in metadata.publishers],
        "contributors": [i.text for i in metadata.contributors],
        "dates": [i.text for i in metadata.dates],
        "types": [i.text for i in metadata.types],
        "formats": [i.text for i in metadata.formats],
        "identifiers": [i.text for i in metadata.identifiers],
        "sources": [i.text for i in metadata.sources],
        "languages": [i.text for i in metadata.languages],
        "relations": [i.text for i in metadata.relations],
        "coverages": [i.text for i in metadata.coverages],
        "rights": [i.text for i in metadata.rights],
        "metas": [i.text for i in metadata.metas],
        "dc_metas": [i.text for i in metadata.dc_metas],
    }

    return lengths, contents

all_length = []
all_contents = []
def analize_opf_metadata(path: Path):
    doc = PackageDocument.from_path(path)
    lengths, contents = analyze_metadata(doc.metadata)
    lengths["file"] = path.name
    contents["file"] = path.name
    all_length.append(lengths)
    all_contents.append(contents)

def parse_opf_metadata():
    source = settings.profile_dir / "epub" / "opf"
    opf_paths = list(source.glob("*.opf"))
    with DisplayProgress(), ThreadPoolExecutor(max_workers=12) as executor:
        list(track_unknown(executor.map(analize_opf_metadata, opf_paths), total=len(opf_paths)))
    lengths_df = pd.DataFrame(all_length)
    contents_df = pd.DataFrame(all_contents)
    lengths_df.to_csv(settings.profile_dir / "opf_metadata_l.csv")
    contents_df.to_csv(settings.profile_dir / "opf_metadata_c.csv")
