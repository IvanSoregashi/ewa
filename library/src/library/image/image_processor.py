import logging
import time

from dataclasses import dataclass
from packages.ewa import ImageData

logger = logging.getLogger(__name__)


@dataclass
class ImageProcessingResult:
    ori_image: ImageData
    new_image: ImageData | None = None

    success: bool = False
    error: str = ""
    time_taken: float = 0

    def not_eligible_result(self, start_time: float) -> "ImageProcessingResult":
        self.success = True
        self.time_taken = time.time() - start_time
        self.error = "Image is not eligible for processing"
        return self

    def success_result(
        self, start_time: float, new_image: ImageData
    ) -> "ImageProcessingResult":
        self.success = True
        self.time_taken = time.time() - start_time
        self.new_image = new_image
        return self

    def failure_result(self, start_time: float, error: str) -> "ImageProcessingResult":
        self.ori_image.collect_garbage()
        if self.new_image:
            self.new_image.collect_garbage()
        self.success = False
        self.time_taken = time.time() - start_time
        self.error = error
        return self

    @property
    def name(self) -> str:
        return self.ori_image.path.name

    @property
    def resize_percent(self) -> float:
        o_dim = self.ori_image.dimensions
        n_dim = self.new_image.dimensions if self.new_image else None
        if o_dim and n_dim:
            return round((n_dim[0] * n_dim[1]) / (o_dim[0] * o_dim[1]) * 100, 2)
        return 100

    @property
    def compressed_to(self) -> float:
        if self.new_image.size is None or self.ori_image.size is None:
            return 100
        return round(self.new_image.size / self.ori_image.size * 100, 2)

    @property
    def savings(self) -> int:
        return self.ori_image.size - self.new_image.size

    @property
    def resized(self) -> bool:
        return self.ori_image.dimensions != self.new_image.dimensions

    @property
    def converted(self) -> bool:
        return self.new_image.mode == "RGB"

    @property
    def renamed(self) -> bool:
        return self.new_image and self.ori_image.path.name != self.new_image.path.name

    def detailed_report(self) -> dict:
        return {
            "name": self.name,
            "original_mode": self.ori_image.mode,
            "new_mode": self.new_image.mode,
            "old_size": self.ori_image.size,
            "new_size": self.new_image.size,
            "resize": self.resize_percent,
            "compressed_to": self.compressed_to,
            "savings": self.savings,
            "error": self.error,
        }


# @dataclass
# class ImageProcessor:
#     settings: "ImageSettings"
#
#     def optimize_image(self, path: Path) -> ImageProcessingResult:
#         start_time = time.time()
#         ori_image = ImageData(path)
#         eligible = self.settings.evaluate(ori_image)
#         result = ImageProcessingResult(ori_image=ori_image)
#         if not eligible:
#             return result.not_eligible_result(start_time)
#         try:
#             new_image = self.settings.construct_new_image(ori_image)
#             new_image.optimize_and_save(self.settings.quality)
#             ori_image.delete_file_if_size_is_same()
#             return result.success_result(start_time, new_image)
#         except Exception as e:
#             return result.failure_result(start_time, str(e))
