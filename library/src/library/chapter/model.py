from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Self, Optional
from pathlib import Path
from uuid import uuid4


from library.epub import media_type
from library.epub.media_type import MediaType
from pydantic import BaseModel, ConfigDict, Field
from pydantic.dataclasses import dataclass

from library.chapter.media import MediaResource


class ChapterType(StrEnum):
    MARKDOWN = "MARKDOWN"
    MHTML = "MHTML"
    XHTML = "XHTML"
    PLAINTEXT = "PLAINTEXT"


class ChapterMetadata(BaseModel):
    """Metadata for a Chapter, following pydantic model for validation."""
    model_config = ConfigDict(extra="allow")

    # Source related info
    source_title: str = Field(description="Title of the Book / Source.")
    source_id: str = Field(default_factory=lambda: str(uuid4()), repr=False, description="Id of the Book / Source.")

    # Content related info
    title: str = Field(description="Title of the chapter.")
    author: str = Field(default="Unknown", repr=False, description="Author of the chapter.")
    url: str | None = Field(default=None, repr=False, description="Url of chapter on the internet.")
    date_published: str | Noen = Field(default=None, repr=False, description="Datetime in format YYYY-MM-DD.")
    date_acquired: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), repr=False, description="Datetime in format YYYY-MM-DD.")
    
    tags: list[str] = Field(default_factory=list, repr=False, description="Tags associated with the chapter content.")
    rating: int | None = Field(None, ge=0, le=5, repr=False, description="User rating for this chapter.")
    
    def to_dict(self) -> dict[str, Any]:
        """Returns a dict with all metadata, including extra fields, and dates serialized to ISO format."""
        data = self.model_dump()
        if self.__pydantic_extra__:
            data.update(self.__pydantic_extra__)
        return data


class ChapterModel(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    chapter_type: ChapterType
    metadata: ChapterMetadata
    content: str
    content_type: str
    media: list[MediaResource] = Field(default_factory=list, repr=False, description="List of media resources associated with the chapter.")

    source_sequence: str | None = None
    source_href: str | None = None

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
    def from_epub(cls, metadata: ChapterMetadata, content: str, read_source_bytes: Callable[str, bytes]) -> Chapter:
        # instead of content we can pass in the relative path of the chapter
        # parse html / xhtml chapter
        # enrich ChapterMetadata?
        # find all references to media resources in the chapter
        # load all resources into memory (?) initialize MediaResource classes
        media: list
        return cls(metadata=metadata, content=content, media=media)

    @classmethod
    def from_filesystem(cls, path: str) -> Chapter:
        media_type = MediaType.from_filename(path)
        match media_type:
            case MediaType.XHTML:
                return cls()
            case MediaType.MARKDOWN:
                return cls()
            case MediaType.MHTML:
                return cls()

    @classmethod
    def from_url(cls, url: str) -> Chapter:
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


class XHTMLChapter(ChapterModel):
    chapter_type: ChapterType = ChapterType.XHTML

    def save(self, path: str | Path) -> None:
        assets_dir = path.parent / f"{path.stem}.assets"

        # Prepare metadata
        metadata_dict = chapter.metadata.to_dict()

        # Build full HTML document
        # is document already converted at this point?
        html_content = chapter.to_html()
        tree = html.document_fromstring(html_content)
        head = tree.find(".//head")
        if head is None:
            head = html.Element("head")
            tree.insert(0, head)

        # Add title
        title_tag = head.find("title")
        if title_tag is None:
            title_tag = html.Element("title")
            head.append(title_tag)
        title_tag.text = chapter.metadata.title

        # Add metadata script
        metadata_script = html.Element("script", type="application/json", id="chapter-metadata")
        metadata_script.text = json.dumps(metadata_dict, indent=2, ensure_ascii=False, default=str)
        head.append(metadata_script)

        # Save main file
        path.write_bytes(html.tostring(tree, encoding="utf-8", method="html", pretty_print=True))

        # Save assets
        if chapter.media:
            assets_dir.mkdir(parents=True, exist_ok=True)
            for media in chapter.media:
                media_path = assets_dir / media.filename
                media_path.write_bytes(media.content)





