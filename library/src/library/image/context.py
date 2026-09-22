import logging
from collections.abc import Callable
from contextlib import ExitStack
from io import BytesIO
from types import TracebackType

from PIL import Image

from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult, ImageSkipReason

logger = logging.getLogger(__name__)


class _ImageSkipped(Exception):
    pass


class ImageProcessingContext:
    def __init__(
        self,
        *,
        compression: int = 100,
        convert_png_to_jpeg: bool = True,
        min_filesize: int = 50 * 1024,
        max_dimensions: tuple[int, int] | None = None,
    ):
        self.compression = compression
        self.convert_png_to_jpeg = convert_png_to_jpeg
        self.min_filesize = min_filesize
        self.max_dimensions = max_dimensions

        self.original_image_info = ImageInfo.failed()
        self.image: Image.Image | None = None
        self.candidate: bytes | None = None
        self.new_image_info: ImageInfo | None = None
        self.result: ImageOptimizationResult | None = None
        self.exit_stack = ExitStack()

    def __enter__(self) -> ImageProcessingContext:
        return self

    def open_bytes_as_image(self, content: bytes) -> None:
        self.original_image_info = ImageInfo.failed(filesize=len(content))
        source = self.exit_stack.enter_context(BytesIO(content))
        image = Image.open(source)
        self.replace_image(image)
        self.original_image_info = ImageInfo.from_image(image, len(content))

    def replace_image(self, image: Image.Image) -> None:
        """Take ownership of an opened or transformed image until the block exits."""
        if image is not self.image:
            self.exit_stack.callback(image.close)
            if self.image is not None:
                self.image.close()
            self.image = image

    def verify(self, *checks: Callable[[ImageProcessingContext], ImageSkipReason | None]) -> None:
        for check in checks:
            reason = check(self)
            if reason is not None:
                self.skip(reason)

    def skip(self, reason: ImageSkipReason) -> None:
        self.result = ImageOptimizationResult(
            skip=reason,
            original_image=self.original_image_info,
            new_image=self.new_image_info,
        )
        raise _ImageSkipped

    def succeed(self) -> None:
        """Mark encoded, size-accepted candidate bytes as successful."""
        if self.candidate is None or self.new_image_info is None:
            raise RuntimeError("Image processing completed without an encoded candidate and metadata")
        self.result = ImageOptimizationResult(
            success=True,
            original_image=self.original_image_info,
            new_image=self.new_image_info,
        )

    def outcome(self) -> tuple[ImageOptimizationResult, bytes | None]:
        if self.result is None:
            raise RuntimeError("Image processing has not completed")
        return self.result, self.candidate if self.result.success else None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        failure = None if isinstance(error, _ImageSkipped) else error
        try:
            self.exit_stack.close()
        except BaseException as cleanup_error:
            # Cleanup must not swallow an interrupt or replace the original processing failure.
            if failure is None or (isinstance(failure, Exception) and not isinstance(cleanup_error, Exception)):
                failure = cleanup_error
            else:
                logger.warning("Image cleanup failed: %s", cleanup_error)
        finally:
            self.image = None

        if failure is not None and not isinstance(failure, Exception):
            self.candidate = None
            self.result = None
            if failure is error:
                return False
            raise failure
        if failure is None and self.result is None:
            failure = RuntimeError("Image processing exited without completion")
        if failure is not None:
            reason = ImageErrorReason.from_error(failure)
            logger.warning("Image processing failed (%s): %s", reason.name, failure)
            self.result = ImageOptimizationResult(
                error=reason, original_image=self.original_image_info, new_image=self.new_image_info
            )
        if self.result is not None and not self.result.success:
            self.candidate = None
        return True
