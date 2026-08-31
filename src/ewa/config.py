import logging
import os
from datetime import datetime
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import DirectoryPath
from pathlib import Path

default_db_name = "database.db"
profile_dir = Path("~/.ewa").expanduser().absolute()
current_dir = Path(".").absolute()
import_time_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
is_windows: bool = os.name == "nt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    profile_dir: Path = profile_dir
    current_dir: DirectoryPath = current_dir
    timestamp_db: bool = True
    log_level_name: str = "INFO"
    log_level: int = 10
    is_windows: bool = is_windows

    def model_post_init(self, context: Any, /) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.log_level = logging.getLevelName(self.log_level_name)

    @property
    def database_filename(self) -> str:
        return f"{import_time_stamp}_{default_db_name}" if self.timestamp_db else default_db_name

    @property
    def database_path(self) -> Path:
        return self.profile_dir / self.database_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


settings = Settings()
