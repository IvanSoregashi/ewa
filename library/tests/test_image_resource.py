from pathlib import Path
from zipfile import ZipInfo

from library.epub.media_type import type_and_role_from_filename
from library.epub.resources import EpubImageResource


def test_image_info():
    image_path = Path(r"samples\images\Book_01.png")
    images_dir = Path(r"samples\images")
    for file in images_dir.iterdir():
        if file.suffix == ".HEIC":
            continue

        image_resource = EpubImageResource.from_filesystem_path(file)
        print()
        print(image_resource.info.file_size, image_resource.info.filename, file.suffix)

        with image_resource.stream_image() as image:
            for k, v in image.info.items():
                print(k, v)
        print(
            f"{image.format=}\n{image.format_description=}\n{image.mode=}\n{image.size=}\n{image.has_transparency_data=}\n{image.palette=}\n"
        )
        print(f"{image=}\n")
