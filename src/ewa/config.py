import logging
import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import DirectoryPath, FilePath
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    profile_dir: Path = Path("~/.ewa").expanduser().absolute()
    current_dir: DirectoryPath = Path(".").absolute()
    database_filename: str = "database.db"
    database_path: FilePath = Path("~/.ewa").expanduser().absolute()
    database_url: str = f"sqlite:///{Path('~/.ewa').expanduser().absolute() / 'database.db'}"
    log_level_name: str = "INFO"
    log_level: int = 10
    is_windows: bool = os.name == "nt"

    def model_post_init(self, context: Any, /) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.profile_dir / self.database_filename
        self.database_url = f"sqlite:///{self.database_path}"
        self.log_level = logging.getLevelName(self.log_level_name)


settings = Settings()
