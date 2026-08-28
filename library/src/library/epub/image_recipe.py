import io
from pathlib import PosixPath

from library.epub.resources import Resource
from PIL import Image

from library.image.constants import ImageMode, ImageFormat
from library.image.models import ImageInfo, OptimizationResult
from library.image.optimization import optimization_machine


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


def perform_image_optimization(resource: Resource) -> OptimizationResult:
    with Image.open(io.BytesIO(resource.content)) as image:
        buffer = io.BytesIO()
        result = optimization_machine(image=image, buffer=buffer, filesize=resource.info.file_size)

    if result.success:
        resource.content = buffer.getvalue()
        if result.new_image.format is ImageFormat.JPEG and result.original_image.format is ImageFormat.PNG:
            resource.filename = str(PosixPath(resource.filename).with_suffix(f".jpg"))

    return result
