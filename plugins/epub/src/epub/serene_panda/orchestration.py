import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from epub.serene_panda.font import process_font
from ewa.cli.progress import DisplayProgress, track_unknown, track_sized
from ewa.main import settings
from ewa.ui import print_success, print_error
from library.image.ocr import recognize_letter


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
            #print_success(str(letter))
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
