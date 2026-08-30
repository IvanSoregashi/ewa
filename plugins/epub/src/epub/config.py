from pathlib import Path
from typing import Any

from pydantic import Field

from ewa.config import Settings


class EpubSettings(Settings):
    D_DISK: Path = Path(r"D:").absolute()
    epub_dir: Path = Path(r"D:\EPUB")
    encrypted_epub_dir: Path = Path(r"D:\ENCRYPTED_EPUBS")
    processed_epub_dir: Path = Path(r"D:\PROCESSED_EPUB")
    decrypted_epub_dir: Path = Path(r"D:\DECRYPTED_EPUB")
    quarantine_epub_dir: Path = Path(r"D:\QUARANTINE_EPUB")

    epub_settings_dir: Path = Field(init=False, default=Path())
    container_dir: Path = Field(init=False, default=Path())
    nav_dir: Path = Field(init=False, default=Path())
    ncx_dir: Path = Field(init=False, default=Path())
    opf_dir: Path = Field(init=False, default=Path())
    style_dir: Path = Field(init=False, default=Path())
    serene_panda_dir: Path = Field(init=False, default=Path())
    serene_panda_fonts_dir: Path = Field(init=False, default=Path())
    serene_panda_alpha_dir: Path = Field(init=False, default=Path())

    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        self.epub_settings_dir = self.profile_dir / "epub"

        self.container_dir = self.epub_settings_dir / "container"
        self.nav_dir = self.epub_settings_dir / "nav"
        self.ncx_dir = self.epub_settings_dir / "ncx"
        self.opf_dir = self.epub_settings_dir / "opf"
        self.style_dir = self.epub_settings_dir / "style"
        self.serene_panda_dir = self.epub_settings_dir / "serene_panda"

        self.serene_panda_fonts_dir = self.serene_panda_dir / "fonts"
        self.serene_panda_alpha_dir = self.serene_panda_dir / "alpha"

        for dir_path in (
            self.container_dir,
            self.nav_dir,
            self.ncx_dir,
            self.ncx_dir,
            self.opf_dir,
            self.serene_panda_fonts_dir,
            self.serene_panda_alpha_dir,
        ):
            dir_path.mkdir(parents=True, exist_ok=True)


settings = EpubSettings()
