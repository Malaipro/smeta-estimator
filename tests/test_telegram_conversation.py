from types import SimpleNamespace
import unittest

from telegram.ext import ConversationHandler

from smeta_estimator.ai import PlanRecognition
from smeta_estimator.telegram_bot.app import (
    BUTTON_CALCULATE,
    DEMO_PARAMETERS,
    SHAPE,
    SHAPE_RECTANGULAR,
    SOIL,
    accept_ai_result,
    confirm_action,
    new_estimate,
    receive_house_length,
    receive_house_width,
    receive_inner_length,
    receive_object,
    receive_parameters_mode,
    receive_shape,
    receive_soil,
    receive_storeys,
    receive_wall_material,
)
from smeta_estimator.telegram_bot.config import BotConfig


class FakeMessage:
    def __init__(self) -> None:
        self.text = ""
        self.replies: list[str] = []
        self.documents: list[object] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)

    async def reply_document(self, document, **kwargs) -> None:
        self.documents.append(document)


class TelegramConversationTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self):
        return SimpleNamespace(
            user_data={},
            application=SimpleNamespace(
                bot_data={
                    "config": BotConfig(
                        token="123456:ABCdef",
                        allowed_user_ids=frozenset(),
                        startup_delay_seconds=0,
                    )
                }
            ),
        )

    async def test_rectangular_demo_flow_builds_excel(self) -> None:
        message = FakeMessage()
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        context = self.make_context()

        await new_estimate(update, context)
        message.text = "Контрольный дом"
        await receive_object(update, context)
        message.text = SHAPE_RECTANGULAR
        await receive_shape(update, context)
        message.text = "10"
        await receive_house_length(update, context)
        message.text = "10"
        await receive_house_width(update, context)
        message.text = "21,5"
        await receive_inner_length(update, context)
        message.text = "2 этажа"
        await receive_storeys(update, context)
        message.text = "Porotherm"
        await receive_wall_material(update, context)
        message.text = "Неизвестен"
        await receive_soil(update, context)
        message.text = DEMO_PARAMETERS
        await receive_parameters_mode(update, context)

        draft = context.user_data["draft"]
        self.assertEqual(str(draft.area_m2), "100")
        self.assertEqual(str(draft.outer_wall_length_m), "40")
        self.assertTrue(any("Наружный периметр: 40 м" in item for item in message.replies))

        message.text = BUTTON_CALCULATE
        state = await confirm_action(update, context)
        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(len(message.documents), 1)
        self.assertTrue(any("Свай: 41 шт" in item for item in message.replies))
        self.assertTrue(any("295 100 ₽" in item for item in message.replies))
        self.assertIn("last_draft", context.user_data)

    async def test_confirmed_ai_geometry_prefills_draft_and_asks_missing_soil(self) -> None:
        message = FakeMessage()
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        context = self.make_context()
        context.user_data["ai_recognition"] = PlanRecognition(
            shape="rectangular",
            length_m=10,
            width_m=12,
            area_m2=120,
            outer_perimeter_m=44,
            inner_bearing_wall_length_m=21.5,
            storeys=2,
            wall_material="Porotherm",
            missing_fields=[],
            warnings=[],
        )

        state = await accept_ai_result(update, context)
        self.assertNotEqual(state, ConversationHandler.END)
        message.text = "Дом по плану"
        state = await receive_object(update, context)

        self.assertEqual(state, SOIL)
        draft = context.user_data["draft"]
        self.assertEqual(str(draft.outer_wall_length_m), "44")
        self.assertEqual(str(draft.inner_wall_length_m), "21.5")
        self.assertEqual(draft.storeys, 2)
        self.assertEqual(draft.wall_material, "Porotherm")

    async def test_unknown_ai_photo_returns_to_manual_shape_question(self) -> None:
        message = FakeMessage()
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        context = self.make_context()
        context.user_data["ai_recognition"] = PlanRecognition(
            shape="unknown",
            length_m=None,
            width_m=None,
            area_m2=None,
            outer_perimeter_m=None,
            inner_bearing_wall_length_m=None,
            storeys=None,
            wall_material=None,
            missing_fields=["length_m"],
            warnings=["Нет размеров"],
        )

        await accept_ai_result(update, context)
        message.text = "Фото дома"
        state = await receive_object(update, context)
        self.assertEqual(state, SHAPE)


if __name__ == "__main__":
    unittest.main()
