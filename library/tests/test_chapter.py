import pytest
from library.chapter import (
    Chapter,
    ChapterMetadata,
    MediaResource,
    MarkdownStorage,
    HtmlStorage,
    MhtmlStorage,
    Base64Storage,
)


@pytest.fixture
def sample_chapter():
    metadata = ChapterMetadata(
        source_title="Source Title",
        title="Chapter Title",
        author="Author Name",
        tags=["tag1", "tag2"],
        extra={"custom": "value"},
    )
    content = "<h1>Chapter Content</h1><p>Hello world.</p>"
    media = [MediaResource.from_bytes("test.png", b"fake-png-data", "image/png")]
    return Chapter(metadata=metadata, content=content, content_type="text/html", media=media)


@pytest.mark.parametrize(
    "storage_class, ext",
    [
        (MarkdownStorage, ".md"),
        (HtmlStorage, ".html"),
        (MhtmlStorage, ".mhtml"),
        (Base64Storage, ".json"),
    ],
)
def test_storage_roundtrip(storage_class, ext, sample_chapter, tmp_path):
    storage = storage_class()
    file_path = tmp_path / f"test_chapter{ext}"

    # Save
    storage.save(sample_chapter, file_path)

    # Check media organization for file-based storages
    if storage_class in [MarkdownStorage, HtmlStorage]:
        assets_dir = tmp_path / "test_chapter.assets"
        assert assets_dir.is_dir()
        assert (assets_dir / "test.png").is_file()
        assert (assets_dir / "test.png").read_bytes() == b"fake-png-data"

    # Load
    loaded = storage.load(file_path)

    # Verify metadata
    assert loaded.metadata.title == sample_chapter.metadata.title
    assert loaded.metadata.author == sample_chapter.metadata.author
    assert loaded.metadata.source_title == sample_chapter.metadata.source_title
    assert set(loaded.metadata.tags) == set(sample_chapter.metadata.tags)
    assert loaded.metadata.extra.get("custom") == "value"

    # Verify content
    # Note: HTML serialization might change tags or whitespace, so we check for inclusion
    if "html" in loaded.content_type:
        assert "Chapter Content" in loaded.content
    else:
        assert loaded.content.strip() == sample_chapter.content.strip() or "Chapter Content" in loaded.content

    # Verify media
    assert len(loaded.media) == 1
    assert loaded.media[0].filename == "test.png"
    assert loaded.media[0].content == b"fake-png-data"


def test_chapter_metadata_validation():
    with pytest.raises(Exception):  # Pydantic validation error
        ChapterMetadata(title=None)  # Title is required


def test_media_resource_lazy_loading(tmp_path):
    media_file = tmp_path / "lazy.txt"
    media_file.write_bytes(b"lazy content")

    res = MediaResource.from_file(media_file)
    assert not res.loaded
    assert res.content == b"lazy content"
    assert res.loaded
