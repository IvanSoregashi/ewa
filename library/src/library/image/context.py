import logging
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import replace
from io import BytesIO
from types import TracebackType

from PIL import Image

from library.asserts import require
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult, ImageSkipReason
from library.utils import remove_none_values

logger = logging.getLogger(__name__)


class _ImageSkipped(Exception):
    def __init__(self, skip_reason: ImageSkipReason) -> None:
        self.skip_reason = skip_reason


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
        self.current_quality: int | None = None

        self.original_image_info = ImageInfo.failed()
        self.current_image_info = ImageInfo.failed()
        self.target_image_info = ImageInfo.failed()
        self.verifications: list[dict] = []
        self.operations: list[dict] = []

        self.candidate: bytes | None = None
        self.skip_reason: int | None = None
        self.error_reason: int | None = None

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
        self.exit_stack.callback(image.close)
        self._image = image
        self.original_image_info = ImageInfo.from_image(image, len(content))
        self.current_image_info = replace(self.original_image_info)
        self.target_image_info = replace(self.original_image_info)

    def replace_image(self, image: Image.Image) -> None:
        """Encode and retain the replacement only when it saves more than 5%."""
        current = self.image
        if image is not current:
            # Own the replacement before encoding or closing can fail.
            self.exit_stack.callback(image.close)

        options = remove_none_values({"quality": self.target_quality})
        operation = {"old_size": self.current_image_info.filesize} | options
        if image.size != current.size:
            operation["resize"] = image.size
        if image.mode != current.mode:
            operation["convert"] = image.mode
        if self.target_image_info.format != self.current_image_info.format:
            operation["reformat"] = self.target_image_info.format
        self.operations.append(operation)

        with BytesIO() as buffer:
            image.save(buffer, format=self.target_image_info.format, optimize=True, **options)
            candidate = buffer.getvalue()
        new_info = ImageInfo.from_image(image, len(candidate), format=self.target_image_info.format)
        worthwhile_change = new_info.filesize * 100 < self.current_image_info.filesize * 95
        operation.update({"accepted": worthwhile_change, "new_size": new_info.filesize})

        if worthwhile_change:
            self._image = image
            self.current_image_info = new_info
            self.current_quality = self.target_quality
            self.candidate = candidate
            if image is not current:
                current.close()
        elif image is not current:
            image.close()

        self.target_image_info = replace(self.current_image_info)
        self.target_quality = self.current_quality

    def verify(self, *checks: Callable[[ImageProcessingContext], ImageSkipReason | None]) -> None:
        for check in checks:
            reason = check(self)
            self.verifications.append({"check": check, "skip": reason and reason.name})
            if reason is not None:
                raise _ImageSkipped(reason)

    def outcome(self) -> tuple[ImageOptimizationResult, bytes | None]:
        success = self.candidate is not None and not self.skip_reason and not self.error_reason
        result = ImageOptimizationResult(
            success=success,
            skip=self.skip_reason,
            error=self.error_reason,
            original_image=self.original_image_info,
            new_image=(
                replace(self.current_image_info)
                if any(operation.get("accepted") for operation in self.operations)
                else None
            ),
            operations=self.operations,
        )
        return result, self.candidate if success else None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        processing_exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        outcome_error: Exception | None = None
        interrupt: BaseException | None = None
        if isinstance(processing_exception, _ImageSkipped):
            # Record the failed verification.
            self.skip_reason = processing_exception.skip_reason
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
            if interrupt is processing_exception:
                # Preserve the original traceback.
                return False
            # Re-raise the cleanup interrupt.
            raise interrupt

        # An unchanged image is a skip, not a processing failure.
        if outcome_error is None and self.candidate is None and self.skip_reason is None:
            self.skip_reason = ImageSkipReason.WORSE_CONVERSION if self.operations else ImageSkipReason.NOT_OPTIMIZED

        # Record the error, retaining metadata.
        if outcome_error is not None:
            reason = ImageErrorReason.from_error(outcome_error)
            logger.warning("Image processing failed (%s): %s", reason.name, outcome_error)
            self.error_reason = reason
            self.skip_reason = None

        # Discard unaccepted bytes.
        if self.error_reason or self.skip_reason:
            self.candidate = None

        # Suppress recorded skips/errors.
        return True
