import yaml
from pathlib import Path

from library.chapter.model import Chapter, ChapterMetadata
from library.chapter.media import MediaResource


class MarkdownStorage:
    """Storage backend for saving/loading Chapters as Markdown with YAML frontmatter.

    Media files are stored in a [filename].assets/ directory.
    """

    def save(self, chapter: Chapter, path: str | Path) -> None:
        path = Path(path)
        assets_dir = path.parent / f"{path.stem}.assets"

        # Prepare metadata
        metadata_dict = chapter.metadata.to_dict()

        frontmatter = yaml.dump(metadata_dict, sort_keys=False, allow_unicode=True)

        # Save main file
        content = f"---\n{frontmatter}---\n\n{chapter.to_markdown()}"
        path.write_text(content, encoding="utf-8")

        # Save assets
        if chapter.media:
            assets_dir.mkdir(parents=True, exist_ok=True)
            for media in chapter.media:
                media_path = assets_dir / media.filename
                media_path.write_bytes(media.content)

    def load(self, path: str | Path) -> Chapter:
        path = Path(path)
        assets_dir = path.parent / f"{path.stem}.assets"

        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            # Minimalistic fallback if no frontmatter
            return Chapter(metadata=ChapterMetadata(title=path.stem), content=content, content_type="text/markdown")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid markdown frontmatter in {path}")

        metadata_dict = yaml.safe_load(parts[1])
        print(f"DEBUG: metadata_dict={metadata_dict}")
        markdown_content = parts[2].strip()

        # Extract extra fields
        known_fields = set(ChapterMetadata.model_fields.keys())
        extra = {k: v for k, v in metadata_dict.items() if k not in known_fields}

        # Clean up metadata_dict to only contain known fields
        metadata_args = {k: v for k, v in metadata_dict.items() if k in known_fields}
        metadata_args["extra"] = extra

        metadata = ChapterMetadata(**metadata_args)

        # Load assets
        media = []
        if assets_dir.is_dir():
            for asset_path in assets_dir.iterdir():
                if asset_path.is_file():
                    media.append(MediaResource.from_file(asset_path))

        return Chapter(metadata=metadata, content=markdown_content, content_type="text/markdown", media=media)
