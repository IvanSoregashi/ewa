import logging
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from io import BytesIO
from types import TracebackType

from PIL import Image

from library.asserts import require
from library.image.constants import ImageMode, ImageFormat
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult, ImageSkipReason

logger = logging.getLogger(__name__)


class _ImageSkipped(Exception):
    pass


class ImageProcessingContext:
    def __init__(
        self,
        *,
        min_filesize: int = 50 * 1024,
        compression: int = 100,
        max_dimensions: tuple[int, int] | None = None,
        target_quality: int | None = 85,
    ):
        self.compression = compression
        self.min_filesize = min_filesize
        self.max_dimensions = max_dimensions
        self.target_quality = target_quality

        self.original_image_info = ImageInfo.failed()
        self.current_image_info = ImageInfo.failed()
        self.target_image_info = ImageInfo.failed()

        self.candidate: bytes | None = None
        self.result: ImageOptimizationResult | None = None

        self._image: Image.Image | None = None
        self.exit_stack = ExitStack()

    @property
    def image(self) -> Image.Image:
        return require(self._image, "self._image")

    def __enter__(self) -> ImageProcessingContext:
        return self

    def open_bytes_as_image(self, content: bytes) -> None:
        self.original_image_info = ImageInfo.failed(filesize=len(content))
        source = self.exit_stack.enter_context(BytesIO(content))
        image = Image.open(source)
        self.replace_image(image)
        self.original_image_info = ImageInfo.from_image(image, len(content))
        self.current_image_info = replace(self.original_image_info)
        self.target_image_info = replace(self.original_image_info)

    def replace_image(self, image: Image.Image) -> None:
        """Take ownership of an opened or transformed image until the block exits."""
        if image is not self._image:
            self.exit_stack.callback(image.close)
            if self._image is not None:
                self._image.close()
            self._image = image
        self.current_image_info.size = image.size
        self.current_image_info.mode = ImageMode(image.mode)
        self.current_image_info.format = ImageFormat(image.format)

    def verify(self, *checks: Callable[[ImageProcessingContext], ImageSkipReason | None]) -> None:
        for check in checks:
            reason = check(self)
            if reason is not None:
                self.skip(reason)

    def skip(self, reason: ImageSkipReason) -> None:
        self.result = ImageOptimizationResult(
            skip=reason,
            original_image=self.original_image_info,
            new_image=self.current_image_info if self.candidate is not None else None,
        )
        raise _ImageSkipped

    def succeed(self) -> None:
        """Mark encoded, size-accepted candidate bytes as successful."""
        if self.candidate is None:
            raise RuntimeError("Image processing completed without an encoded candidate")
        self.result = ImageOptimizationResult(
            success=True,
            original_image=self.original_image_info,
            new_image=self.current_image_info,
        )

    def outcome(self) -> tuple[ImageOptimizationResult, bytes | None]:
        if self.result is None:
            raise RuntimeError("Image processing has not completed")
        return self.result, self.candidate if self.result.success else None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        processing_exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        outcome_error: Exception | None = None
        interrupt: BaseException | None = None
        if isinstance(processing_exception, _ImageSkipped):
            # Skip outcome already recorded.
            pass
        elif isinstance(processing_exception, Exception):
            # Record processing errors after cleanup.
            outcome_error = processing_exception
        else:
            # Retain interrupts; None means normal exit.
            interrupt = processing_exception

        # Attempt every cleanup callback.
        try:
            self.exit_stack.close()
        except Exception as cleanup_error:
            # Cleanup errors override success/skip, not earlier failures.
            if outcome_error is None and interrupt is None:
                outcome_error = cleanup_error
            else:
                # Log the secondary error.
                logger.warning("Image cleanup failed: %s", cleanup_error)
        except BaseException as cleanup_interrupt:
            # Interrupts take precedence; keep the first.
            if interrupt is None:
                interrupt = cleanup_interrupt
            else:
                logger.warning("Image cleanup failed: %s", cleanup_interrupt)
        finally:
            # Drop the working image reference.
            self._image = None

        # Discard output before propagating interrupts.
        if interrupt is not None:
            self.candidate = None
            self.result = None
            if interrupt is processing_exception:
                # Preserve the original traceback.
                return False
            # Re-raise the cleanup interrupt.
            raise interrupt

        # Require explicit success or skip.
        if outcome_error is None and self.result is None:
            outcome_error = RuntimeError("Image processing exited without completion")

        # Record the error, retaining metadata.
        if outcome_error is not None:
            reason = ImageErrorReason.from_error(outcome_error)
            logger.warning("Image processing failed (%s): %s", reason.name, outcome_error)
            self.result = ImageOptimizationResult(
                error=reason,
                original_image=self.original_image_info,
                new_image=self.current_image_info if self.candidate is not None else None,
            )

        # Discard unaccepted bytes.
        if self.result is not None and not self.result.success:
            self.candidate = None

        # Suppress recorded skips/errors.
        return True
