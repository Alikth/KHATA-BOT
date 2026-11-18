from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    bot_token: str = ""
    bot_owner_id: int = Field(default=0, ge=0)
    admin_password_hash: str = ""
    database_url: str = ""
    log_level: str = "INFO"
    backup_dir: str = "./var/backups"
    statements_chat_id: int | None = None
    war_log_chat_id: int | None = None
    trade_log_chat_id: int | None = None
    world_start_paused: bool = True
    starting_gold: int = 1000
    starting_wood: int = 500
    starting_stone: int = 500
    starting_food: int = 1000
    admin_chat_id: int = 0
    admin_session_minutes: int = 20

@lru_cache
def get_settings() -> Settings:
    return Settings()
