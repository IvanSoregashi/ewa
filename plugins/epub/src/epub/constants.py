from pathlib import Path

epub_dir = Path(r"D:\EPUB")
duplicates_dir = epub_dir / "_duplicates"
duplicates_dir.mkdir(parents=True, exist_ok=True)
quarantine_dir = epub_dir / "_quarantine"
quarantine_dir.mkdir(parents=True, exist_ok=True)
