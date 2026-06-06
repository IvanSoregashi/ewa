from pathlib import Path
from zipfile import ZipInfo

from ewa.cli.print_table import print_table, print_table_from_dicts
from library.epub.epub import EPUB
from library.epub.media_type import type_and_role_from_filename
from library.epub.resources import EpubImageResource
from library.image.utils import calculate_image_file_bpp


def test_image_info():
    images_dir = Path("samples") / "images"

    for file in images_dir.iterdir():
        if file.is_dir() or file.suffix == ".HEIC":
            continue

        image_resource = EpubImageResource.from_filesystem_path(file)
        print()
        print(image_resource.info.file_size, image_resource.info.filename, file.suffix)

        with image_resource.stream_image() as image:
            print(f"{image=}")
            for k, v in image.info.items():
                print(k, v)
            extrema = image.getextrema()
            no_transparency = len(extrema) == 4 and extrema[3][0] == 255
            print(extrema, no_transparency)
            print("is_animated", getattr(image, "is_animated", "Not found"))
            print("n_frames", getattr(image, "n_frames", "Not found"))
        print(f"{image.format=} {image.format_description=}")
        print(f"{image.mode=} {image.size=} {image.has_transparency_data=} {image.palette=}")
        print(f"{image=}")


def test_image_optimization():
    images_dir = Path("samples") / "images"
    for file in images_dir.iterdir():
        if file.is_dir() or file.suffix == ".HEIC":
            continue

        image_resource = EpubImageResource.from_filesystem_path(file)
        new_path = image_resource.optimize(max_width=1080, max_height=0, convert_rgb_to_jpg=True)
        output_path = images_dir / "output" / (new_path or file).name
        assert output_path.read_bytes() == image_resource.content
        #image_resource.write_to_filesystem(output_path)


def test_bpp():
    images_dir = Path("samples") / "images"
    for file in images_dir.rglob("*.*"):
        if file.is_dir() or file.suffix == ".HEIC":
            continue
        print(f"{file.name:<50}{calculate_image_file_bpp(file)}")


def test_analytics():
    images_dir = Path("samples")
    results = []
    for file in images_dir.glob("*.epub"):
        epub = EPUB(file)
        with epub.source.open():
            for image in epub.resources.images:
                info_dict = image.get_info()
                results.append(info_dict)
    print_table_from_dicts("Image Info", results)

