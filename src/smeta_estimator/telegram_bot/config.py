"""Environment configuration for the Telegram demo."""

from dataclasses import dataclass
import os
from typing import Mapping


class BotConfigError(ValueError):
    """Raised when a required bot setting is missing or invalid."""


@dataclass(frozen=True, slots=True)
class BotConfig:
    token: str
    allowed_user_ids: frozenset[int]
    startup_delay_seconds: float = 5.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "BotConfig":
        values = os.environ if env is None else env
        token = values.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise BotConfigError("TELEGRAM_BOT_TOKEN is required")

        raw_ids = values.get("ALLOWED_TELEGRAM_IDS", "").strip()
        try:
            allowed = frozenset(int(item.strip()) for item in raw_ids.split(",") if item.strip())
        except ValueError as exc:
            raise BotConfigError("ALLOWED_TELEGRAM_IDS must contain integers separated by commas") from exc

        try:
            delay = float(values.get("BOT_STARTUP_DELAY_SECONDS", "5"))
        except ValueError as exc:
            raise BotConfigError("BOT_STARTUP_DELAY_SECONDS must be a number") from exc
        if delay < 0 or delay > 30:
            raise BotConfigError("BOT_STARTUP_DELAY_SECONDS must be between 0 and 30")

        return cls(token=token, allowed_user_ids=allowed, startup_delay_seconds=delay)
