import json
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from library.chapter.model import Chapter, ChapterMetadata
from library.chapter.media import MediaResource


class MhtmlStorage:
    """Storage backend for saving/loading Chapters as MHTML (MIME encapsulation of aggregate HTML documents).

    All resources (HTML, images, etc.) are bundled into a single file.
    Metadata is stored in custom X-Metadata headers.
    """

    def save(self, chapter: Chapter, path: str | Path) -> None:
        path = Path(path)

        msg = EmailMessage()
        msg["From"] = "uwa-chapter-export@local"
        msg["Subject"] = chapter.metadata.title
        msg["Date"] = formatdate(localtime=True)
        msg["MIME-Version"] = "1.0"

        # Store metadata in a single JSON header to avoid issues with individual fields
        metadata_dict = chapter.metadata.to_dict()
        msg["X-Chapter-Metadata"] = json.dumps(metadata_dict, default=str)

        # Main HTML content
        msg.set_content(chapter.to_html(), subtype="html", charset="utf-8")

        # Add media resources as related parts
        for media in chapter.media:
            maintype, subtype = str(media.media_type).split("/", 1)
            msg.add_related(
                media.content,
                maintype=maintype,
                subtype=subtype,
                filename=media.filename,
                cid=media.filename,
            )

        path.write_bytes(msg.as_bytes())

    def load(self, path: str | Path) -> Chapter:
        import email
        from email.policy import default

        path = Path(path)
        with path.open("rb") as f:
            msg = email.message_from_bytes(f.read(), policy=default)

        # Extract metadata from X-Chapter-Metadata header
        metadata_json = msg.get("X-Chapter-Metadata")
        if metadata_json:
            metadata_dict = json.loads(str(metadata_json))

            # Extract extra fields
            known_fields = set(ChapterMetadata.model_fields.keys())
            extra = {k: v for k, v in metadata_dict.items() if k not in known_fields}

            # Clean up metadata_dict to only contain known fields
            metadata_args = {k: v for k, v in metadata_dict.items() if k in known_fields}
            metadata_args["extra"] = extra

            metadata = ChapterMetadata(**metadata_args)
        else:
            # Fallback to individual headers if JSON one is missing (backwards compatibility)
            metadata_dict = {}
            for header, value in msg.items():
                if header.startswith("X-Chapter-"):
                    key = header[10:].lower().replace("-", "_")
                    metadata_dict[key] = value

            known_fields = set(ChapterMetadata.model_fields.keys())
            extra = {k: v for k, v in metadata_dict.items() if k not in known_fields}
            metadata_args = {k: v for k, v in metadata_dict.items() if k in known_fields}
            metadata_args["extra"] = extra
            metadata = ChapterMetadata(**metadata_args)

        # Extract HTML content
        content = ""
        media = []

        # In multipart/related, the first part is usually the HTML if it's the root
        # or the root contains parts. msg.get_body() can be used for simpler email,
        # but for MHTML we iterate.
        for part in msg.walk():
            ct = part.get_content_type()

            if ct == "text/html":
                # Only take the first one or prioritize the one with correct charset
                if not content:
                    payload = part.get_payload(decode=True)
                    content = payload.decode(part.get_content_charset() or "utf-8")
            elif "multipart" not in ct:
                filename = part.get_filename()
                cid = part.get("Content-ID")

                # Use filename or CID (removing < >) as the resource name
                resource_name = filename or cid
                if resource_name and resource_name.startswith("<") and resource_name.endswith(">"):
                    resource_name = resource_name[1:-1]

                if not resource_name:
                    resource_name = f"unknown_{len(media)}"

                payload = part.get_payload(decode=True)
                if payload:
                    media.append(
                        MediaResource.from_bytes(
                            filename=resource_name,
                            media_type=ct,
                            content=payload,
                        )
                    )

        return Chapter(
            metadata=metadata,
            content=content,
            content_type="text/html",
            media=media,
        )
