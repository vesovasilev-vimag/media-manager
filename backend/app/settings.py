from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIMAG_", extra="ignore")
    environment: str = "production"
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "vimag"
    db_user: str = "vimag"
    db_password_file: Path = Path("/run/secrets/db_password")
    setup_token_file: Path = Path("/run/secrets/setup_token")
    qbt_url: str = "http://qbittorrent:8080"
    qbt_api_key_file: Path = Path("/run/secrets/qbt_api_key")
    qbt_username_file: Path = Path("/run/secrets/qbt_username")
    qbt_password_file: Path = Path("/run/secrets/qbt_password")
    jellyfin_url: str = "http://jellyfin:8096"
    jellyfin_library_root: str = "/library"
    jellyfin_api_key_file: Path = Path("/run/secrets/jellyfin_api_key")
    tmdb_api_key_file: Path = Path("/run/secrets/tmdb_api_key")
    subtitle_api_key_file: Path = Path("/run/secrets/subtitle_api_key")
    write_enabled: bool = False
    automatic_intake: bool = False
    cookie_secure: bool = True
    allowed_host: str = "manager.vimag.app"
    origin: str = "https://manager.vimag.app"
    session_hours: int = 8
    lease_seconds: int = 90
    poll_seconds: int = 20
    retry_budget: int = 3
    nas_root: Path = Path("/nas-movies")
    staging_root: Path = Path("/downloads/complete")
    nas_mount_source: str = ""
    min_free_bytes: int = 100 * 1024**3
    min_free_percent: float = 5
    adapters: str = "real"

    def secret(self, path: Path) -> SecretStr:
        return SecretStr(path.read_text(encoding="utf-8").strip() if path.is_file() else "")

    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.secret(self.db_password_file).get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    def validate_runtime(self) -> None:
        if self.environment == "production" and (
            self.adapters != "real"
            or not self.cookie_secure
            or not self.origin.startswith("https://")
        ):
            raise ValueError("Unsafe production configuration")
