"""
Module for working with epubs encoded via TrueType Font
"""

import logging
import hashlib
import time
import json

from concurrent.futures import ProcessPoolExecutor
from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

logger = logging.getLogger(__name__)


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

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox).resize((32, 32))

    return img


def character_to_hash_and_img(char: str, font: FreeTypeFont, size: int) -> tuple[str, Image.Image]:
    """
    receive character, font and size
    render character in Image.Image, and take hash
    returns hash and image
    """
    img = render_letter(char, font, size)
    h = hashlib.md5(img.tobytes()).hexdigest()
    return h, img


def font_to_dict(characters: Iterator[str], font_path: Path, size: int = 24) -> dict[str, list[str]]:
    """
    receive collections of characters, path to a font file and size (of the font)
    iterate over collection,
    compose dictionary hash of render to a list of characters
    returns dictionary
    """
    start = time.time()
    font = ImageFont.truetype(font_path, size)
    groups = {}
    for char in characters:
        h, img = character_to_hash_and_img(char, font, size)
        groups.setdefault(h, []).append(char)
    logger.debug(f"Font {font_path} {font_path.stat().st_size / 1024 / 1024:.1f} mb collected dict in {time.time() - start:.1f} s")
    return groups


def render_glyphs(characters: Iterator[str], font_path: Path, size: int = 24) -> dict[str, Image.Image]:
    """
    receive collections of characters, path to a font file and size (of the font)
    iterate over collection,
    compose dictionary: hash of render to a rendered image
    returns dictionary
    """
    start = time.time()
    font = ImageFont.truetype(font_path, size)
    images = {}
    for char in characters:
        h, img = character_to_hash_and_img(char, font, size)
        if h not in images:
           images[h] = img
    logger.debug(f"Font {font_path} {font_path.stat().st_size / 1024 / 1024:.1f} mb rendered glyphs in {time.time() - start:.1f} s")
    return images


def font_to_hangul_dict(font_path: Path) -> dict[str, list[str]]:
    """
    receive path to a font
    run font_to_dict with collection of hangul characters
    """
    characters = map(chr, range(0xAC00, 0xD7AF + 1))
    return font_to_dict(characters, font_path, 24)


def render_and_save_hangul_glyphs(font_path: Path, image_dir: Path = Path("glyphs")) -> None:
    """
    receive font_path, and directory to save hangul glyphs
    render hangul characters in font, save in folder
    no return
    """
    characters = map(chr, range(0xAC00, 0xD7AF + 1))
    image_dir.mkdir(parents=True, exist_ok=True)
    images = render_glyphs(characters, font_path, 24)
    for h, img in images.items():
        image_path = image_dir / f"{h}.png"
        if not image_path.exists():
            img.save(image_path)


def process_all_fonts_sync(fonts: str = "fonts"):
    """
    receive path to a folder
    process all fonts in the folder synchronously
    """
    fonts_dir = Path(fonts)
    return list(map(font_to_hangul_dict, fonts_dir.glob("*.ttf")))


def process_all_fonts_mproc(fonts: str = "fonts"):
    """
    receive path to a folder
    process all fonts in the folder in multiple processes
    """
    fonts_dir = Path(fonts)
    with ProcessPoolExecutor() as exec:
        return list(exec.map(font_to_hangul_dict, fonts_dir.glob("*.ttf")))


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

