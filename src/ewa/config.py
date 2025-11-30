from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import DirectoryPath, FilePath
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    profile_dir: DirectoryPath = Path("~/.ewa").expanduser().absolute()
    current_dir: DirectoryPath = Path(".").absolute()
    database_file: FilePath | None = None
    database_url: str | None = None

    def model_post_init(self, context: Any, /) -> None:
        if self.database_file is None:
            self.database_file = self.profile_dir / "database.db"
        if self.database_url is None:
            self.database_url = f"sqlite:///{self.database_file}"
