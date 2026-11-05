from io import BytesIO
import unittest

from PIL import Image

from smeta_estimator.ai import PlanRecognition
from smeta_estimator.telegram_bot.ai_service import (
    HourlyRateLimiter,
    ImagePreparationError,
    apply_recognition_to_draft,
    prepare_image,
    recognition_summary,
)
from smeta_estimator.telegram_bot.service import FoundationDraft


def recognition(**overrides) -> PlanRecognition:
    values = {
        "shape": "rectangular",
        "length_m": 10.0,
        "width_m": 12.0,
        "area_m2": 120.0,
        "outer_perimeter_m": 44.0,
        "inner_bearing_wall_length_m": 21.5,
        "storeys": 2,
        "wall_material": "Porotherm 44",
        "missing_fields": [],
        "warnings": [],
    }
    values.update(overrides)
    return PlanRecognition(**values)


class TelegramAIServiceTests(unittest.TestCase):
    def test_prepare_image_resizes_and_converts_to_jpeg(self) -> None:
        source = BytesIO()
        Image.new("RGBA", (3000, 1500), (0, 0, 0, 0)).save(source, format="PNG")
        result = prepare_image(
            source.getvalue(), max_file_bytes=10_000_000, max_dimension=2200
        )
        self.assertEqual((result.width, result.height), (2200, 1100))
        self.assertEqual(result.mime_type, "image/jpeg")
        with Image.open(BytesIO(result.content)) as prepared:
            self.assertEqual(prepared.format, "JPEG")
            self.assertEqual(prepared.mode, "RGB")

    def test_prepare_image_rejects_invalid_content(self) -> None:
        with self.assertRaisesRegex(ImagePreparationError, "Не удалось прочитать"):
            prepare_image(b"not-an-image", max_file_bytes=1000, max_dimension=2200)

    def test_rate_limiter_is_per_user_and_expires(self) -> None:
        limiter = HourlyRateLimiter(max_requests=2, window_seconds=10)
        self.assertTrue(limiter.allow(1, now=0))
        self.assertTrue(limiter.allow(1, now=1))
        self.assertFalse(limiter.allow(1, now=2))
        self.assertTrue(limiter.allow(2, now=2))
        self.assertTrue(limiter.allow(1, now=11))

    def test_apply_rectangular_recognition_uses_deterministic_geometry(self) -> None:
        draft = FoundationDraft()
        apply_recognition_to_draft(recognition(outer_perimeter_m=999), draft)
        self.assertEqual(str(draft.house_length_m), "10.0")
        self.assertEqual(str(draft.house_width_m), "12.0")
        self.assertEqual(str(draft.area_m2), "120.00")
        self.assertEqual(str(draft.outer_wall_length_m), "44.0")
        self.assertEqual(str(draft.inner_wall_length_m), "21.5")
        self.assertEqual(draft.storeys, 2)
        self.assertEqual(draft.wall_material, "Porotherm")

    def test_unknown_shape_does_not_infer_geometry_from_dimensions(self) -> None:
        draft = FoundationDraft()
        apply_recognition_to_draft(recognition(shape="unknown"), draft)
        self.assertEqual(draft.shape, "")
        self.assertIsNone(draft.house_length_m)
        self.assertEqual(str(draft.outer_wall_length_m), "44.0")

    def test_summary_includes_warning_and_human_check(self) -> None:
        summary = recognition_summary(
            recognition(warnings=["Периметр вычислен из размеров."])
        )
        self.assertIn("Периметр вычислен", summary)
        self.assertIn("Проверьте значения", summary)


if __name__ == "__main__":
    unittest.main()
