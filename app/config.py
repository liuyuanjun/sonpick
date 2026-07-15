from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-production"
    admin_password: str = "admin"
    storage_path: str = str(Path(__file__).resolve().parent.parent / "downloads")
    database_path: str = str(Path(__file__).resolve().parent.parent / "data" / "music.db")
    data_dir: str = str(Path(__file__).resolve().parent.parent / "data")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
