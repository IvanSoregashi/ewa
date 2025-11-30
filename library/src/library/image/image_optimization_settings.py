from dataclasses import dataclass

from packages.ewa import ImageData


@dataclass
class ImageFilter:
    """Filter for images.
    Filters images based on size and suffix.
    upper and lower thresholds are int file size values in bytes.
    suffixes are tuple of lower case suffixes.
    """

    size_lower_threshold: int = 50 * 1024
    size_upper_threshold: int = 0
    suffixes: tuple[str, ...] = (".jpg", ".jpeg", ".png")

    def __call__(self, imaged: ImageData) -> bool:
        """Returns True if image is eligible for processing, False otherwise."""
        if self.size_lower_threshold and imaged.size < self.size_lower_threshold:
            return False
        if self.size_upper_threshold and imaged.size > self.size_upper_threshold:
            return False
        if self.suffixes and imaged.suffix.lower() not in self.suffixes:
            return False
        return True


@dataclass
class ImageConverter:
    """
    Converter for images.
    Converts images to the new mode and dimensions.
    max_width and max_height are int values in pixels.
    quality is int value in 0-100 (for jpg images).
    """

    max_width: int = 1080
    max_height: int = 0
    convert_rgb_to_jpg: bool = True
    quality: int | None = None

    def new_dimensions(self, imaged: ImageData) -> tuple[int, int]:
        width, height = imaged.dimensions
        new_width, new_height = width, height
        if self.max_width and width > self.max_width:
            ratio = self.max_width / width
            new_width = self.max_width
            new_height = int(height * ratio)
        if self.max_height and new_height > self.max_height:
            ratio = self.max_height / new_height
            new_width = int(width * ratio)
            new_height = self.max_height
        return (new_width, new_height)

    def new_mode(self, imaged: ImageData) -> str:
        if imaged.mode == "RGBA":
            extrema = imaged.image.getextrema()  # LOADS PIXEL DATA
            no_transparency = len(extrema) == 4 and extrema[3][0] == 255
            new_mode = "RGB" if no_transparency else "RGBA"
        else:
            new_mode = imaged.mode
        return new_mode

    def new_suffix(self, imaged: ImageData) -> str:
        pass

    def __call__(self, imaged: ImageData) -> ImageData:
        """Converts image to the new mode and dimensions."""
        new_dimensions = self.new_dimensions(imaged)
        new_mode = self.new_mode(imaged)
        new_suffix = self.new_suffix(imaged)
        return ImageData(
            path=imaged.path,
            _dimensions=new_dimensions,
            _mode=new_mode,
            _suffix=new_suffix,
            _image=imaged.image,
        )


class ImageSettings:
    def __init__(
        self,
        filter: ImageFilter = ImageFilter(50 * 1024, 0, (".jpg", ".jpeg", ".png")),
        converter: ImageConverter = ImageConverter(1080, 0, quality=80),
    ):
        self.filter = filter
        self.converter = converter

    def construct_new_image(self, image: ImageData) -> ImageData:
        """
        Constructs new image data object.
        image object from original image data object.
        mode and dimensions are configured by settings.
        """
        new_dimensions = self.converter.new_dimensions(image)
        new_mode = self.converter.new_mode(image)
        if new_mode == "RGB" and image.path.suffix.lower() == ".png":
            new_path = image.path.with_suffix(".jpg")
        else:
            new_path = image.path
        new_image = ImageData(
            path=new_path,
            _mode=new_mode,
            _dimensions=new_dimensions,
            _image=image.image,
        )
        return new_image
