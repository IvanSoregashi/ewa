"""Inspect image resources without applying optimization policy or changing bytes."""

import io
from PIL import Image
from library.epub.resources import Resource
from library.image.constants import ImageMode
from library.image.models import ImageInfo


def get_image_info(resource: Resource) -> ImageInfo:
    with resource.stream() as stream:
        with Image.open(stream) as image:
            return ImageInfo.from_image(image, resource.info.file_size)


def get_image_info_with_extrema(resource: Resource) -> ImageInfo:
    image_info = get_image_info(resource)
    if image_info.mode is ImageMode.RGBA:
        with Image.open(io.BytesIO(resource.content)) as image:
            image_info.extrema = image.getextrema()
    return image_info
