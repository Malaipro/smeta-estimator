from decimal import Decimal
import unittest

from smeta_estimator.telegram_bot import build_application
from smeta_estimator.telegram_bot.config import BotConfig, BotConfigError
from smeta_estimator.telegram_bot.service import (
    FoundationDraft,
    calculate_draft,
    parse_decimal,
    parse_percent,
)


class TelegramServiceTests(unittest.TestCase):
    def test_control_draft_uses_foundation_engine(self) -> None:
        draft = FoundationDraft(
            object_name="Тестовый дом",
            outer_wall_length_m=Decimal("40"),
            inner_wall_length_m=Decimal("21.5"),
        )
        _, result, lines = calculate_draft(draft)
        self.assertEqual(result.pile_count_effective, 41)
        self.assertEqual(result.concrete_calculated_m3, Decimal("26.5"))
        self.assertEqual(len(lines), 28)

    def test_decimal_parser_accepts_comma(self) -> None:
        self.assertEqual(parse_decimal("21,5"), Decimal("21.5"))

    def test_percent_parser_converts_to_ratio(self) -> None:
        self.assertEqual(parse_percent("5"), Decimal("0.05"))

    def test_config_is_closed_by_default(self) -> None:
        with self.assertRaises(BotConfigError):
            BotConfig.from_env({"TELEGRAM_BOT_TOKEN": "token"})

    def test_config_parses_allowed_ids(self) -> None:
        config = BotConfig.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "token",
                "ALLOWED_TELEGRAM_IDS": "123, 456",
                "BOT_STARTUP_DELAY_SECONDS": "0",
            }
        )
        self.assertEqual(config.allowed_user_ids, frozenset({123, 456}))
        self.assertEqual(config.startup_delay_seconds, 0)

    def test_application_uses_sequential_updates_for_conversation(self) -> None:
        application = build_application(
            BotConfig(
                token="123456:ABCdef",
                allowed_user_ids=frozenset({123}),
                startup_delay_seconds=0,
            )
        )
        self.assertEqual(application.update_processor.max_concurrent_updates, 1)
        self.assertGreaterEqual(len(application.handlers[0]), 4)


if __name__ == "__main__":
    unittest.main()
