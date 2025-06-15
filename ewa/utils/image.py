import json
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def resize_image(image_path: Path, max_width: int = 1080, max_height: int = None, quality: int = 80) -> Path:
    new_path = None
    try:
        with Image.open(image_path) as image:
            old_metrics = image_metrics(image, image_path)
            old_dimensions, new_dimensions = calculate_dimensions(image, max_width, max_height)
            resize = old_dimensions != new_dimensions
            convert = is_convert_needed(image)

            if resize:
                image = image.resize(new_dimensions, Image.LANCZOS)
            
            if convert:
                image = image.convert('RGB')

            if resize or convert:
                new_path = save_image(image, image_path, quality)                
            else:
                new_path = image_path

            new_metrics = image_metrics(image, new_path)
            #log_resizing(old_metrics, new_metrics)
            return old_metrics, new_metrics
    except Exception as e:
        logger.error(f"Error resizing image {image_path}: {str(e)[:100]}")
        raise
    


def calculate_dimensions(image: Image.Image, max_width: int = 1080, max_height: int = None) -> tuple[tuple[int, int], tuple[int, int]]:
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
        no_transparency = image.getextrema()[3][0] == 255
        logger.warning(f"Image {image.filename} is RGBA, transparency: {no_transparency}")
        return no_transparency
    if image.mode == 'RGB':
        logger.warning(f"Image {image.filename} is RGB, return True for Convert to JPG")
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
    filename = path
    size = path.stat().st_size
    return {
        'path': path,
        'file_size': size,
        'size': image.size,
        'mode': image.mode,
        'format': image.format,
    }


def log_resizing(old_metrics: dict, new_metrics: dict):
    changes_dict = {}
    for key in old_metrics:
        if old_metrics[key] != new_metrics[key]:
            changes_dict[key] = f"{old_metrics[key]} -> {new_metrics[key]}"
    if 'file_size' in changes_dict:
        changes_dict['file_size'] = f"{round(new_metrics['file_size'] / old_metrics['file_size'] * 100)} %"
    if 'size' in changes_dict:
        changes_dict['size'] = f"width {round(new_metrics['size'][0] / old_metrics['size'][0] * 100)} %"
    if changes_dict:
        logger.warning(f"Image {new_metrics['filename']} was resized")
        logger.warning(json.dumps(changes_dict, indent=4, ensure_ascii=False))
    else:
        logger.warning(f"Image {new_metrics['filename']} not resized")
        logger.warning(json.dumps(old_metrics, indent=4, ensure_ascii=False))


