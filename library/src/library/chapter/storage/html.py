import json
from pathlib import Path
from lxml import html

from library.chapter.model import Chapter, ChapterMetadata
from library.chapter.media import MediaResource


class HtmlStorage:
    """Storage backend for saving/loading Chapters as HTML/XHTML.
    
    Metadata is stored in a JSON-LD or custom <script> block in the <head>.
    Media files are stored in a [filename].assets/ directory.
    """

    def save(self, chapter: Chapter, path: str | Path) -> None:
        path = Path(path)
        assets_dir = path.parent / f"{path.stem}.assets"

        # Prepare metadata
        metadata_dict = chapter.metadata.to_dict()

        # Build full HTML document
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

    def load(self, path: str | Path) -> Chapter:
        path = Path(path)
        assets_dir = path.parent / f"{path.stem}.assets"
        
        content_bytes = path.read_bytes()
        tree = html.fromstring(content_bytes)
        
        # Load metadata
        metadata_script = tree.find(".//head/script[@id='chapter-metadata']")
        if metadata_script is not None and metadata_script.text_content():
            metadata_dict = json.loads(metadata_script.text_content())
            print(f"DEBUG HTML: metadata_dict={metadata_dict}")
            
            # Extract extra fields
            known_fields = set(ChapterMetadata.model_fields.keys())
            extra = {k: v for k, v in metadata_dict.items() if k not in known_fields}
            metadata_dict["extra"] = extra
            
            # Clean up metadata_dict to only contain known fields for the constructor
            # (Pydantic will handle extra fields via model_extra if allowed, but we use an explicit dict)
            metadata_args = {k: v for k, v in metadata_dict.items() if k in known_fields}
            metadata_args["extra"] = extra
            
            metadata = ChapterMetadata(**metadata_args)
        else:
            # Minimalistic fallback
            title = tree.find(".//title")
            metadata = ChapterMetadata(title=title.text if title is not None else path.stem)

        # Load assets
        media = []
        if assets_dir.is_dir():
            for asset_path in assets_dir.iterdir():
                if asset_path.is_file():
                    media.append(MediaResource.from_file(asset_path))
        
        return Chapter(
            metadata=metadata,
            content=html.tostring(tree, encoding="utf-8", method="html", pretty_print=True).decode("utf-8"),
            content_type="text/html",
            media=media
        )
