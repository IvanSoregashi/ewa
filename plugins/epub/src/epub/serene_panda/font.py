"""
Module for working with epubs encoded via TrueType Font
Requires: PIL, ... (Image extra)
"""

import logging
import hashlib
import json

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

from ewa.ui import print_error

logger = logging.getLogger(__name__)

HANGUL_START = 0xAC00
HANGUL_END = 0xD7AF
HANGUL_CHARS = list(map(chr, range(HANGUL_START, HANGUL_END + 1)))
RENDER_SIZE = 24
ALPHABET_PATH = Path("~/.ewa/epub/serene_panda/alpha").expanduser().absolute()
ALPHABET_PATH.mkdir(parents=True, exist_ok=True)


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


def render_hangul_in_font(
    font_path: Path, size: int = RENDER_SIZE
) -> tuple[dict[str, list[str]], dict[str, Image.Image]]:
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
    try:
        characters, images = render_hangul_in_font(font_path)
        json_path.write_text(json.dumps(characters, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print_error(f"{e}")
        return
    for h, img in images.items():
        filepath = alphabet_path / f"{h}.png"
        if not filepath.exists():
            img.save(filepath)
