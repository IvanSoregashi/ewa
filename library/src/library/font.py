"""
Module for working with epubs encoded via TrueType Font
Requires: PIL, ... (Image extra)
"""

import logging
import hashlib
import json

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

logger = logging.getLogger(__name__)

HANGUL_START = 0xAC00
HANGUL_END = 0xD7AF
HANGUL_CHARS = map(chr, range(HANGUL_START, HANGUL_END + 1))
RENDER_SIZE = 24
ALPHABET_PATH = Path("~/.ewa/epub/serene_panda/alpha").expanduser().absolute()


def render_letter(ch: str, font: FreeTypeFont, canvas_size: int) -> Image.Image:
    """
    receive character, font and size
    returns rendered Image.Image of the character
    """
    img = Image.new("L", (canvas_size, canvas_size), 255)
    ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=0)
    return img


def render_centered_letter(ch: str, font: FreeTypeFont, canvas_size: int) -> Image.Image:
    """
    receive character, font and size
    returns rendered centered Image.Image of the character
    """
    img = Image.new("L", (canvas_size, canvas_size), 255)

    draw = ImageDraw.Draw(img)
    left, top, right, bottom = draw.textbbox((0, 0), ch, font=font)
    w, h = right - left, bottom - top
    x = (canvas_size - w) / 2 - left
    y = (canvas_size - h) / 2 - top
    draw.text((x, y), ch, font=font, fill=0)

    # bbox = img.getbbox()
    # if bbox:
    #     img = img.crop(bbox).resize((32, 32))

    return img


def render_hangul_in_font(font_path: Path, size: int = RENDER_SIZE) -> tuple[dict[str, list[str]], dict[str, Image.Image]]:
    font = ImageFont.truetype(font_path, size)
    images = {}
    characters = {}
    for char in HANGUL_CHARS:
        img = render_centered_letter(char, font, size)
        _hash = hashlib.md5(img.tobytes()).hexdigest()
        characters.setdefault(_hash, []).append(char)
        images.setdefault(_hash, img)
    return characters, images


def process_font(font_path: Path, alphabet_path: Path = ALPHABET_PATH):
    json_path = font_path.with_suffix(".json")
    if json_path.exists():
        return
    characters, images = render_hangul_in_font(font_path)
    json_path.write_text(json.dumps(characters, ensure_ascii=False), encoding="utf-8")
    for h, img in images.items():
        filepath = alphabet_path / f"{h}.png"
        if not filepath.exists():
            img.save(filepath)


def process_all_fonts_sync(fonts: str = "fonts"):
    """
    receive path to a folder
    process all fonts in the folder synchronously
    """
    fonts_dir = Path(fonts)
    return list(map(process_font, fonts_dir.glob("*.ttf")))


def process_all_fonts_mproc(fonts: str = "fonts"):
    """
    receive path to a folder
    process all fonts in the folder in multiple processes
    """
    fonts_dir = Path(fonts)
    with ProcessPoolExecutor() as executor:
        return list(executor.map(process_font, fonts_dir.glob("*.ttf")))


def get_hash_to_letter():
    """
    return hash: letter dictionary
    """
    # TODO:
    text = Path("hash_to_letter.json").read_text(encoding="utf-8")
    hash_to_letter = json.loads(text)
    # Path("glyphs").mkdir(parents=True, exist_ok=True)
    return hash_to_letter


def form_translation():
    """
    return glyph: letter translation dictionary
    """
    list_of_dicts = process_all_fonts_mproc()
    hash_to_letter = get_hash_to_letter()

    translation = {}

    for groups in list_of_dicts:
        for h, glyph_lst in groups.items():
            for glyph in glyph_lst:
                letter = hash_to_letter[h]
                if letter not in ["#", " ", ""]:
                    translation.setdefault(glyph, set()).add(letter)

    for glyph, letters in (translation.copy()).items():
        if len(letters) == 1:
            translation[glyph] = list(letters)[0]
        else:
            translation[glyph] = glyph

    return translation
