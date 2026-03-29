from __future__ import annotations
from datetime import datetime
from typing import Any, Self, Optional

from pydantic import BaseModel, ConfigDict, Field

from library.chapter.media import MediaResource


class ChapterMetadata(BaseModel):
    """Metadata for a Chapter, following pydantic model for validation."""
    model_config = ConfigDict(extra="allow")

    # Source related info
    source_title: Optional[str] = None
    source_id: Optional[str] = None
    source_sequence: Optional[int] = None
    source_href: Optional[str] = None

    # Content related info
    title: str = Field(..., description="Title of the chapter.")
    author: Optional[str] = None
    url: Optional[str] = None
    date_published: Optional[datetime] = None
    date_acquired: datetime = Field(default_factory=datetime.now)
    
    tags: list[str] = Field(default_factory=list, description="Tags associated with the chapter content.")
    rating: int | None = Field(None, ge=0, le=5, description="User rating for this chapter.")
    
    extra: dict[str, Any] = Field(default_factory=dict, description="Captures any additional metadata.")

    def to_dict(self) -> dict[str, Any]:
        """Returns a dict with all metadata, including extra fields, and dates serialized to ISO format."""
        data = self.model_dump(mode='json', exclude={"extra"})
        if self.extra:
            data.update(self.extra)
        return data


class Chapter:
    """The central data model for a single unit of content (Chapter).
    
    Each chapter contains metadata, text content, and related media.
    """

    def __init__(
        self,
        metadata: ChapterMetadata | dict[str, Any],
        content: str,
        content_type: str,
        media: list[MediaResource] | None = None,
    ) -> None:
        self.metadata = (
            metadata if isinstance(metadata, ChapterMetadata) else ChapterMetadata(**metadata)
        )
        self.content = content
        self.content_type = content_type
        self.media = media or []

    def __repr__(self) -> str:
        return f"Chapter({self.metadata.title!r}, content_type={self.content_type!r})"

    @property
    def tags(self) -> list[str]:
        """Convenience property for accessing tags from metadata."""
        return self.metadata.tags

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self.metadata.tags = value

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a Chapter instance from a dictionary representation."""
        media_data = data.pop("media", [])
        media = [MediaResource(**m) if isinstance(m, dict) else m for m in media_data]
        return cls(media=media, **data)

    def to_dict(self) -> dict[str, Any]:
        """Returns a dictionary representation of the Chapter."""
        return {
            "metadata": self.metadata.model_dump(),
            "content": self.content,
            "content_type": self.content_type,
            "media": [
                {
                    "filename": m.filename,
                    "media_type": str(m.media_type),
                    # Content is usually not serialized in the main dict for efficiency
                }
                for m in self.media
            ],
        }

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
