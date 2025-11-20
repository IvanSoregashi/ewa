from pydantic_settings import BaseSettings

class EpubSettings(BaseSettings):
    enable_registration: bool = True
    min_password_length: int = 8
