"""The book outcome returned by workers and persisted by the parent."""

from functools import cached_property
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from library.database.typed_json import TypedJSON
from library.epub.epub import EpubInfo


class ProcessingRun(SQLModel, table=True):
    __tablename__ = "epub_processing_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    input_path: str | None = None
    success: bool = False
    skip: int | None = None
    error: int | None = None
    details: str = ""
    original_epub: EpubInfo | None = Field(default=None, sa_column=Column(TypedJSON(EpubInfo), nullable=True))
    new_epub: EpubInfo | None = Field(default=None, sa_column=Column(TypedJSON(EpubInfo), nullable=True))

    @cached_property
    def analytics(self) -> list[SQLModel]:
        """Unsaved evidence carried from the worker; loaded rows start with an empty list."""
        return []

    def report(self) -> None:
        from epub.results import report

        report(self)

    def short_report(self) -> None:
        from epub.results import short_report

        short_report(self)
