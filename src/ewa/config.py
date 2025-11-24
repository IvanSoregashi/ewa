from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import DirectoryPath
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    profile_dir: DirectoryPath = Path("~/.ewa").expanduser().absolute()
    current_dir: DirectoryPath = Path(".").absolute()
