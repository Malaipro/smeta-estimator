from decimal import Decimal
import unittest

from smeta_estimator.telegram_bot import build_application
from smeta_estimator.ai import TaynikVisionConfig
from smeta_estimator.telegram_bot.app import BUTTON_AI, _main_keyboard
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
        calculation = calculate_draft(draft)
        self.assertEqual(calculation.result.pile_count_effective, 41)
        self.assertEqual(calculation.result.concrete_calculated_m3, Decimal("26.5"))
        self.assertEqual(len(calculation.lines), 28)
        self.assertEqual(calculation.demo_summary.known_subtotal, Decimal("295100.0"))

    def test_rectangular_geometry_calculates_area_and_perimeter(self) -> None:
        draft = FoundationDraft()
        draft.set_rectangular_geometry(Decimal("10"), Decimal("12"))
        self.assertEqual(draft.area_m2, Decimal("120"))
        self.assertEqual(draft.outer_wall_length_m, Decimal("44"))
        self.assertEqual(draft.shape, "Прямоугольный дом")

    def test_project_info_keeps_non_engineering_answers(self) -> None:
        draft = FoundationDraft(
            shape="Сложная форма",
            area_m2=Decimal("135.5"),
            storeys=2,
            wall_material="Porotherm",
            soil_condition="Неизвестен",
        )
        info = draft.to_project_info()
        self.assertEqual(info.area_m2, Decimal("135.5"))
        self.assertEqual(info.storeys, 2)
        self.assertEqual(info.wall_material, "Porotherm")
        self.assertEqual(info.soil_condition, "Неизвестен")

    def test_decimal_parser_accepts_comma(self) -> None:
        self.assertEqual(parse_decimal("21,5"), Decimal("21.5"))

    def test_percent_parser_converts_to_ratio(self) -> None:
        self.assertEqual(parse_percent("5"), Decimal("0.05"))

    def test_config_is_public_by_default(self) -> None:
        config = BotConfig.from_env({"TELEGRAM_BOT_TOKEN": "token"})
        self.assertEqual(config.allowed_user_ids, frozenset())
        self.assertFalse(config.ai_enabled)
        self.assertEqual(config.ai_max_requests_per_hour, 3)

    def test_config_parses_public_ai_limits(self) -> None:
        config = BotConfig.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "token",
                "AI_ENABLED": "true",
                "AI_MAX_REQUESTS_PER_HOUR": "4",
                "AI_MAX_CONCURRENT_REQUESTS": "1",
            }
        )
        self.assertTrue(config.ai_enabled)
        self.assertEqual(config.ai_max_requests_per_hour, 4)
        self.assertEqual(config.ai_max_concurrent_requests, 1)

    def test_config_rejects_invalid_allowed_ids(self) -> None:
        with self.assertRaises(BotConfigError):
            BotConfig.from_env(
                {
                    "TELEGRAM_BOT_TOKEN": "token",
                    "ALLOWED_TELEGRAM_IDS": "123,not-an-id",
                }
            )

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

    def test_ai_button_is_hidden_until_feature_is_enabled(self) -> None:
        disabled = BotConfig(token="token", allowed_user_ids=frozenset())
        enabled = BotConfig(
            token="token", allowed_user_ids=frozenset(), ai_enabled=True
        )
        disabled_labels = [
            button.text for row in _main_keyboard(disabled).keyboard for button in row
        ]
        enabled_labels = [
            button.text for row in _main_keyboard(enabled).keyboard for button in row
        ]
        self.assertNotIn(BUTTON_AI, disabled_labels)
        self.assertIn(BUTTON_AI, enabled_labels)

        application = build_application(
            enabled,
            ai_config=TaynikVisionConfig(api_key="tk_ai_test"),
        )
        self.assertIsNotNone(application.bot_data["ai_config"])


if __name__ == "__main__":
    unittest.main()
