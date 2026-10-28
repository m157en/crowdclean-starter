from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CrowdClean API"
    environment: str = "local"
    database_url: str = "sqlite:///./crowdclean.db"
    storage_dir: Path = Path("./storage")
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    allowed_audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
