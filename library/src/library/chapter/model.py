from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Self, TypedDict, NotRequired
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from library.chapter.media import MediaResource
from library.utils_xhtml import parse_html_content
from library.filetypes import guess_file_type


class ChapterType(StrEnum):
    UNKNOWN = "UNKNOWN"
    MARKDOWN = "MARKDOWN"
    MHTML = "MHTML"
    XHTML = "XHTML"
    TEXT = "PLAINTEXT"


class ContentType(StrEnum):
    UNKNOWN = "application/unknown"
    MARKDOWN = "text/markdown"
    MHTML = "message/rfc822"
    XHTML = "application/xhtml+xml"
    TEXT = "text/plain"

    @classmethod
    def from_filename(cls, value: str | Path) -> Self | None:
        guessed = guess_file_type(value)
        if not guessed:
            return cls("application/unknown")
        instance = cls(guessed)
        return instance


class ChapterMetadataDict(TypedDict):
    source_title: str
    source_id: NotRequired[str]
    source_sequence: NotRequired[str]

    title: str
    author: NotRequired[str]
    url: NotRequired[str]
    date_published: NotRequired[str]
    date_acquired: NotRequired[str]

    tags: NotRequired[list[str]]
    rating: NotRequired[int]


class ChapterMetadata(BaseModel):
    """Metadata for a Chapter, following pydantic model for validation."""

    model_config = ConfigDict(extra="allow")

    # Source related info
    source_title: str = Field(description="Title of the Book / Source.")
    source_id: str = Field(default_factory=lambda: str(uuid4()), repr=False, description="Id (uuid_id) of the Source.")
    source_sequence: str | None = Field(default=None, repr=False, description="Number of chapter in the source.")

    # Content related info
    title: str = Field(description="Title of the chapter.")
    author: str = Field(default="Unknown", repr=False, description="Author of the chapter.")
    url: str | None = Field(default=None, repr=False, description="Url of chapter on the internet.")
    date_published: str | None = Field(default=None, repr=False, description="Datetime in format YYYY-MM-DD.")
    date_acquired: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"),
        repr=False,
        description="Datetime in format YYYY-MM-DD.",
    )

    tags: list[str] = Field(default_factory=list, repr=False, description="Tags associated with the chapter content.")
    rating: int | None = Field(None, ge=0, le=5, repr=False, description="User rating for this chapter.")

    def to_dict(self) -> dict[str, Any]:
        """Returns a dict with all metadata, including extra fields, and dates serialized to ISO format."""
        data = self.model_dump()
        if self.__pydantic_extra__:
            data.update(self.__pydantic_extra__)
        return data


class Chapter(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    chapter_type: ChapterType
    metadata: ChapterMetadata
    content: str
    content_type: ContentType
    media: list[MediaResource] = Field(
        default_factory=list, repr=False, description="List of media resources associated with the chapter."
    )

    source_href: str | None = None

    def __repr__(self) -> str:
        return f"Chapter({self.metadata.title!r}, content_type={self.content_type})"

    @property
    def tags(self) -> list[str]:
        """Convenience property for accessing tags from metadata."""
        return self.metadata.tags

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self.metadata.tags = value

    # ----------------------------------------------------------------------------------------------------
    @classmethod
    def from_epub(
        cls,
        chapter_path: str | Path,
        read_source_bytes: Callable[str, bytes],
        metadata: ChapterMetadataDict | None = None,
    ) -> Self:
        content_type = ContentType.from_filename(chapter_path)
        chapter_bytes = read_source_bytes(chapter_path)

        assert content_type == ContentType.XHTML, "Content type is not XHTML"

        parsed_metadata, head_attach, body_attach = parse_html_content(chapter_bytes)

        if metadata is None:
            metadata = ChapterMetadata.model_validate(parsed_metadata)

        # parse html / xhtml chapter
        # enrich ChapterMetadata?
        # find all references to media resources in the chapter
        # load all resources into memory (?) initialize MediaResource classes
        media: list = []
        return cls(metadata=metadata, content=chapter_bytes, media=media)

    @classmethod
    def from_filesystem(cls, path: str) -> Self:
        content_type = ContentType.from_filename(path)
        match content_type:
            case ContentType.XHTML:
                return cls()
            case ContentType.MARKDOWN:
                return cls()
            case ContentType.MHTML:
                return cls()
            case _:
                raise ValueError(f"Unknown media type {content_type}")

    @classmethod
    def from_url(cls, url: str) -> Self:
        pass

    def to_markdown(self) -> str:
        """Stub for HTML -> Markdown conversion."""
        if "markdown" in self.content_type.lower():
            return self.content
        # TODO: Implement markdownify calling logic here
        return self.content

    def to_html(self) -> str:
        """Stub for Markdown -> HTML conversion."""
        if "html" in self.content_type.lower() or "xhtml" in self.content_type.lower():
            return self.content
        # TODO: Implement markdown-it-py calling logic here
        return self.content
