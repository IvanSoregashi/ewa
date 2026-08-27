from library.epub.resources import Resource
from PIL import Image

from library.image.models import ImageInfo


def get_image_header(resource: Resource):
    with resource.stream() as stream:
        with Image.open(stream) as image:
            return ImageInfo.from_image(image, resource.info.file_size)

def get_image_no_transparency(resource: Resource):
    with resource.stream() as stream:
        with Image.open(stream) as image:
            extrema = image.getextrema()
            return len(extrema) == 4 and extrema[3][0] == 255

