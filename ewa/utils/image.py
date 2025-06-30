import json
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def resize_image(image_path: Path, max_width: int = 1080, max_height: int | None = None, quality: int = 80) -> tuple[dict, dict]:
    """
    Resize image.
    Returns a tuple of old metrics and new metrics.
    """
    new_path = None
    try:
        with Image.open(image_path) as image:
            old_metrics = image_metrics(image, image_path)
            old_dimensions, new_dimensions = calculate_dimensions(image, max_width, max_height)
            resize = old_dimensions != new_dimensions
            convert = is_convert_needed(image)

            if resize:
                image = image.resize(new_dimensions, Image.Resampling.LANCZOS)
            
            if convert:
                image = image.convert('RGB')

            if resize or convert:
                new_path = save_image(image, image_path, quality)                
            else:
                new_path = image_path

            new_metrics = image_metrics(image, new_path)
            return old_metrics, new_metrics
    except Exception as e:
        logger.error(f"Error resizing image {image_path}: {str(e)[:100]}")
        if new_path and new_path.exists():
            new_path.unlink()
        return {
            'success': False,
            'error': e,
            'path': image_path
        }, {
            'success': False,
            'error': e,
            'path': image_path
        }


def calculate_dimensions(image: Image.Image, max_width: int = 1080, max_height: int | None = None) -> tuple[tuple[int, int], tuple[int, int]]:
    width, height = image.size
    new_width, new_height = width, height
    if width > max_width:
        ratio = max_width / width
        new_width = max_width
        new_height = int(height * ratio)
    if max_height is not None and new_height > max_height:
        ratio = max_height / new_height
        new_width = int(width * ratio)
        new_height = max_height
    return (width, height), (new_width, new_height)


def is_convert_needed(image: Image.Image) -> bool:
    if image.mode == 'RGBA':
        extrema = image.getextrema()
        if len(extrema) != 4:
            return False
        no_transparency = extrema[3][0] == 255
        return no_transparency
    if image.mode == 'RGB':
        return True
    return False


def save_image(image: Image.Image, path: Path, quality) -> Path:
    if path.suffix.lower() in ('.jpg', '.jpeg'):
        image.save(path, optimize=True, quality=quality)
        return path
    if image.mode == 'RGB':
        new_path = path.with_stem(path.stem).with_suffix('.jpg')
        image.save(new_path, optimize=True, quality=quality)
        return new_path
    if path.suffix.lower() == '.png':
        image.save(path, optimize=True)
        return path
    raise ValueError(f"Unsupported image format: {path.suffix}, mode: {image.mode}, path: {path}")


def image_metrics(image: Image.Image, path: Path) -> dict:
    size = path.stat().st_size
    return {
        'path': path,
        'file_size': size,
        'size': image.size,
        'mode': image.mode,
        'format': path.suffix.lower(), 
        'success': True
    }
