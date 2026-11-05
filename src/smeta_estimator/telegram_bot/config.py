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
    ai_enabled: bool = False
    ai_max_file_bytes: int = 10_000_000
    ai_max_image_dimension: int = 2200
    ai_max_requests_per_hour: int = 3
    ai_max_concurrent_requests: int = 2

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

        raw_ai_enabled = values.get("AI_ENABLED", "false").strip().lower()
        if raw_ai_enabled not in {"true", "false"}:
            raise BotConfigError("AI_ENABLED must be true or false")

        try:
            ai_max_file_bytes = int(values.get("AI_MAX_FILE_BYTES", "10000000"))
            ai_max_image_dimension = int(values.get("AI_MAX_IMAGE_DIMENSION", "2200"))
            ai_max_requests_per_hour = int(
                values.get("AI_MAX_REQUESTS_PER_HOUR", "3")
            )
            ai_max_concurrent_requests = int(
                values.get("AI_MAX_CONCURRENT_REQUESTS", "2")
            )
        except ValueError as exc:
            raise BotConfigError("AI limits must be integers") from exc
        if not 100_000 <= ai_max_file_bytes <= 20_000_000:
            raise BotConfigError("AI_MAX_FILE_BYTES must be between 100000 and 20000000")
        if not 512 <= ai_max_image_dimension <= 4096:
            raise BotConfigError("AI_MAX_IMAGE_DIMENSION must be between 512 and 4096")
        if not 1 <= ai_max_requests_per_hour <= 100:
            raise BotConfigError("AI_MAX_REQUESTS_PER_HOUR must be between 1 and 100")
        if not 1 <= ai_max_concurrent_requests <= 10:
            raise BotConfigError("AI_MAX_CONCURRENT_REQUESTS must be between 1 and 10")

        return cls(
            token=token,
            allowed_user_ids=allowed,
            startup_delay_seconds=delay,
            ai_enabled=raw_ai_enabled == "true",
            ai_max_file_bytes=ai_max_file_bytes,
            ai_max_image_dimension=ai_max_image_dimension,
            ai_max_requests_per_hour=ai_max_requests_per_hour,
            ai_max_concurrent_requests=ai_max_concurrent_requests,
        )
