from pathlib import Path
from ewa.main import settings

epub_dir = Path(r"D:\EPUB")
duplicates_directory = epub_dir / "_duplicates"
duplicates_directory.mkdir(parents=True, exist_ok=True)
quarantine_directory = epub_dir / "_quarantine"
quarantine_directory.mkdir(parents=True, exist_ok=True)
translated_directory = epub_dir / "_translated"
translated_directory.mkdir(parents=True, exist_ok=True)
untranslated_directory = epub_dir / "_untranslated"
untranslated_directory.mkdir(parents=True, exist_ok=True)

epub_settings_dir = settings.profile_dir / "epub"
serene_panda_docs_dir = epub_settings_dir / "serene_panda"
serene_panda_fonts_dir = serene_panda_docs_dir / "fonts"

translated_r_directory = epub_dir / "_translated" / "for removal"
translated_r_directory.mkdir(parents=True, exist_ok=True)
