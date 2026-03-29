import base64
import json
from pathlib import Path

from library.chapter.model import Chapter, ChapterMetadata
from library.chapter.media import MediaResource


class Base64Storage:
    """Storage backend for saving/loading Chapters as a single JSON file.
    
    Media assets are embedded as Base64-encoded strings.
    """

    def save(self, chapter: Chapter, path: str | Path) -> None:
        path = Path(path)

        # Prepare metadata
        metadata_dict = chapter.metadata.to_dict()

        # Build combined data
        media_data = [
            {
                "filename": m.filename,
                "media_type": str(m.media_type),
                "content": base64.b64encode(m.content).decode("utf-8"),
            }
            for m in chapter.media
        ]

        data = {
            "metadata": metadata_dict,
            "content": chapter.content,
            "content_type": chapter.content_type,
            "media": media_data,
        }

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def load(self, path: str | Path) -> Chapter:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        
        # Load metadata
        metadata_dict = data.get("metadata", {})
        known_fields = set(ChapterMetadata.model_fields.keys())
        extra = {k: v for k, v in metadata_dict.items() if k not in known_fields}
        
        # Clean up metadata_dict to only contain known fields
        metadata_args = {k: v for k, v in metadata_dict.items() if k in known_fields}
        metadata_args["extra"] = extra
        
        metadata = ChapterMetadata(**metadata_args)
        
        # Load media
        media = []
        for m in data.get("media", []):
            media.append(
                MediaResource.from_bytes(
                    filename=m["filename"],
                    media_type=m["media_type"],
                    content=base64.b64decode(m["content"]),
                )
            )
            
        return Chapter(
            metadata=metadata,
            content=data["content"],
            content_type=data["content_type"],
            media=media,
        )
