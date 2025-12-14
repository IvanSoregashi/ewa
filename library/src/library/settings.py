from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class EpubSettings:
    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self.epub_dir = Path("~").expanduser().absolute() / "Books"
        self.epub_dir.mkdir(parents=True, exist_ok=True)
        self.epubs_db = self.epub_dir / "epub.sqlite"
        self.epubs_table: str = "epubs"
        self.files_table: str = "files"


class Config(Settings):
    PROFILE: Path = Path("~/.ewa").expanduser().absolute()

    # epub: EpubSettings = EpubSettings(profile_dir=PROFILE)

    def model_post_init(self, context: Any, /) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)


config = Config()
print(config.profile_dir)
print(config.epub.epub_dir)
