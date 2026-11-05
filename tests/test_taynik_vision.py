import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from smeta_estimator.ai.taynik_vision import (
    PlanRecognition,
    TaynikVisionConfig,
    TaynikVisionError,
    build_chat_payload,
    check_gateway_access,
    parse_recognition_content,
    recognize_plan,
)


VALID_DATA = {
    "shape": "rectangular",
    "length_m": 10,
    "width_m": 12,
    "area_m2": 120,
    "outer_perimeter_m": 44,
    "inner_bearing_wall_length_m": None,
    "storeys": None,
    "wall_material": None,
    "missing_fields": ["inner_bearing_wall_length_m", "storeys", "wall_material"],
    "warnings": ["Периметр вычислен из наружных размеров."],
}


class FakeResponse:
    status = 200

    def __init__(self, data: dict) -> None:
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.data


class TaynikVisionTests(unittest.TestCase):
    def test_config_requires_key(self) -> None:
        with self.assertRaisesRegex(TaynikVisionError, "AI_API_KEY"):
            TaynikVisionConfig.from_env({})

    def test_config_rejects_non_ascii_key_without_exposing_it(self) -> None:
        with self.assertRaisesRegex(TaynikVisionError, "не-ASCII") as context:
            TaynikVisionConfig.from_env({"AI_API_KEY": "tk_ai_секрет"})
        self.assertNotIn("секрет", str(context.exception))

    def test_config_rejects_key_with_internal_whitespace(self) -> None:
        with self.assertRaisesRegex(TaynikVisionError, "пробел"):
            TaynikVisionConfig.from_env({"AI_API_KEY": "tk_ai_part one"})

    def test_payload_contains_text_image_and_json_mode(self) -> None:
        payload = build_chat_payload(b"image-bytes", "image/png", "gpt-6-luna")
        content = payload["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_gateway_preflight_confirms_requested_model(self) -> None:
        def opener(request, timeout):
            self.assertEqual(request.full_url, "https://taynik.store/v1/models")
            return FakeResponse({"data": [{"id": "gpt-6-luna"}]})

        diagnostics = check_gateway_access(
            TaynikVisionConfig(api_key="secret"), opener=opener
        )
        self.assertTrue(diagnostics["requested_model_available"])

    def test_gateway_preflight_rejects_missing_model(self) -> None:
        def opener(request, timeout):
            return FakeResponse({"data": [{"id": "gpt-6.1-sol"}]})

        with self.assertRaisesRegex(TaynikVisionError, "отсутствует"):
            check_gateway_access(TaynikVisionConfig(api_key="secret"), opener=opener)

    def test_parser_accepts_plain_json(self) -> None:
        result = parse_recognition_content(json.dumps(VALID_DATA))
        self.assertIsInstance(result, PlanRecognition)
        self.assertEqual(result.outer_perimeter_m, 44.0)

    def test_parser_accepts_fenced_json(self) -> None:
        content = "```json\n" + json.dumps(VALID_DATA) + "\n```"
        result = parse_recognition_content(content)
        self.assertEqual(result.shape, "rectangular")

    def test_parser_rejects_extra_field(self) -> None:
        data = {**VALID_DATA, "foundation_type": "pile"}
        with self.assertRaisesRegex(TaynikVisionError, "лишние"):
            parse_recognition_content(json.dumps(data))

    def test_parser_rejects_non_positive_measurement(self) -> None:
        data = {**VALID_DATA, "length_m": 0}
        with self.assertRaisesRegex(TaynikVisionError, "length_m"):
            parse_recognition_content(json.dumps(data))

    def test_parser_rejects_non_finite_measurement(self) -> None:
        data = {**VALID_DATA, "length_m": float("nan")}
        with self.assertRaisesRegex(TaynikVisionError, "length_m"):
            parse_recognition_content(json.dumps(data))

    def test_recognize_plan_sends_request_and_parses_response(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["authorization"] = request.get_header("Authorization")
            captured["payload"] = json.loads(request.data)
            response = {
                "model": "gpt-6-luna",
                "choices": [{"message": {"content": json.dumps(VALID_DATA)}}],
            }
            return FakeResponse(response)

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "plan.png"
            image.write_bytes(b"not-a-real-image-but-the-api-is-mocked")
            config = TaynikVisionConfig(api_key="secret-test-key")
            result, diagnostics = recognize_plan(image, config, opener=opener)

        self.assertEqual(result.area_m2, 120.0)
        self.assertEqual(captured["url"], "https://taynik.store/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer secret-test-key")
        self.assertEqual(diagnostics["http_status"], 200)

    def test_recognize_plan_rejects_unsupported_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "plan.pdf"
            image.write_bytes(b"pdf")
            with self.assertRaisesRegex(TaynikVisionError, "JPG и PNG"):
                recognize_plan(image, TaynikVisionConfig(api_key="secret"))

    def test_recognize_plan_rejects_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "plan.jpg"
            image.write_bytes(b"1234")
            config = TaynikVisionConfig(api_key="secret", max_image_bytes=3)
            with self.assertRaisesRegex(TaynikVisionError, "лимита"):
                recognize_plan(image, config)

    def test_http_error_exposes_safe_provider_message_and_redacts_key(self) -> None:
        def opener(request, timeout):
            body = json.dumps(
                {"error": {"message": "Invalid key tk_ai_secret-value"}}
            ).encode("utf-8")
            raise HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(body))

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "plan.png"
            image.write_bytes(b"image")
            with self.assertRaises(TaynikVisionError) as context:
                recognize_plan(
                    image,
                    TaynikVisionConfig(api_key="tk_ai_secret-value"),
                    opener=opener,
                )

        message = str(context.exception)
        self.assertIn("HTTP 403", message)
        self.assertIn("распознавание изображения", message)
        self.assertIn("Invalid key", message)
        self.assertNotIn("tk_ai_secret-value", message)


if __name__ == "__main__":
    unittest.main()
