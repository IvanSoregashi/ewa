"""Image-operation evidence attached to one book-processing run."""

from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from library.database.typed_json import TypedJSON
from library.image.models import ImageInfo, ImageOptimizationResult


class ImageOptimizationRecord(SQLModel, table=True):
    __tablename__ = "epub_image_optimizations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="epub_processing_runs.id", index=True)
    success: bool = False
    skip: int | None = None
    error: int | None = None
    original_image: ImageInfo = Field(sa_column=Column(TypedJSON(ImageInfo), nullable=False))
    new_image: ImageInfo | None = Field(default=None, sa_column=Column(TypedJSON(ImageInfo), nullable=True))

    @classmethod
    def from_result(cls, run_id: UUID, result: ImageOptimizationResult) -> ImageOptimizationRecord:
        return cls(
            run_id=run_id,
            success=result.success,
            skip=result.skip,
            error=result.error,
            original_image=result.original_image,
            new_image=result.new_image,
        )
