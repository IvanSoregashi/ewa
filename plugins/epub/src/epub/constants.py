from pathlib import Path

epub_dir = Path(r"D:\EPUB")
duplicates_directory = epub_dir / "_duplicates"
duplicates_directory.mkdir(parents=True, exist_ok=True)
quarantine_directory = epub_dir / "_quarantine"
quarantine_directory.mkdir(parents=True, exist_ok=True)
translated_directory = epub_dir / "_translated"
translated_directory.mkdir(parents=True, exist_ok=True)
untranslated_directory = epub_dir / "_untranslated"
untranslated_directory.mkdir(parents=True, exist_ok=True)
