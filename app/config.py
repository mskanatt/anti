"""Настройки приложения.

Все секреты (JWT, токен Telegram, ключи VAPID) читаются ТОЛЬКО из переменных
окружения / файла .env. В коде их нет и быть не должно.
Если JWT_SECRET или STAFF_INVITE_CODE не заданы — приложение не запустится.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

TRIGGERS: dict[str, str] = {
    "тупой": "insult",
    "идиот": "insult",
    "лох": "insult",
    "дурак": "insult",
    "дебил": "insult",
    "заткнись": "insult",
    "помощь": "help",
    "не бей": "violence",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    staff_invite_code: str = Field(min_length=8)

    database_url: str = "sqlite:///./antibullying.db"

    staff_token_minutes: int = 12 * 60
    device_token_minutes: int = 12 * 60

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_contact: str = "mailto:admin@example.com"

    min_confidence: float = Field(default=0.6, ge=0, le=1)
    alert_cooldown_seconds: int = 20
    device_online_seconds: int = 90
    pairing_code_hours: int = 24
    display_timezone: str = "UTC"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def push_enabled(self) -> bool:
        return bool(self.vapid_private_key and self.vapid_public_key)


settings = Settings()