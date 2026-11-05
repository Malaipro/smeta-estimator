"""Безопасный пробный клиент распознавания плана через OpenAI-compatible API.

Модуль не связан с Telegram-ботом и расчётным ядром. Его задача — проверить
совместимость шлюза с передачей изображения и получить только предложенные
параметры, которые затем должен подтвердить сметчик.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://taynik.store/v1"
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_MAX_IMAGE_BYTES = 10_000_000
SUPPORTED_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
CLIENT_HEADERS = {
    "Accept": "application/json",
    # Шлюз заявляет совместимость с OpenAI-клиентами; явный UA также исключает
    # блокировку стандартного Python-urllib как неизвестного робота.
    "User-Agent": "OpenAI/Python 2.20.0 smeta-estimator-demo/0.1",
}

EXPECTED_FIELDS = {
    "shape",
    "length_m",
    "width_m",
    "area_m2",
    "outer_perimeter_m",
    "inner_bearing_wall_length_m",
    "storeys",
    "wall_material",
    "missing_fields",
    "warnings",
}

EXTRACTION_PROMPT = """Ты извлекаешь параметры дома из обезличенного плана для сметчика.
Верни только один JSON-объект без Markdown и пояснений.

Правила:
1. Извлекай только явно видимые размеры и подписи. Ничего не угадывай.
2. shape: rectangular, complex или unknown.
3. Числовые значения указывай в метрах или квадратных метрах, без единиц.
4. outer_perimeter_m можно вычислить только из подтверждённых наружных размеров.
5. storeys и wall_material заполняй только если они явно написаны на изображении.
6. Не выбирай грунт, тип или размеры фундамента, сваи, бетон, цены и итог сметы.
7. Неуверенные или отсутствующие значения ставь null и перечисляй в missing_fields.
8. В warnings перечисли неоднозначности, плохую читаемость и сделанные вычисления.

Точная структура:
{
  "shape": "rectangular|complex|unknown",
  "length_m": number|null,
  "width_m": number|null,
  "area_m2": number|null,
  "outer_perimeter_m": number|null,
  "inner_bearing_wall_length_m": number|null,
  "storeys": integer|null,
  "wall_material": string|null,
  "missing_fields": [string],
  "warnings": [string]
}"""


class TaynikVisionError(RuntimeError):
    """Публичная безопасная ошибка теста API без секретов и base64."""


def _safe_api_error_detail(error: HTTPError) -> str | None:
    """Извлечь короткое сообщение провайдера, не печатая сырое тело ответа."""
    try:
        raw = error.read(32_768).decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    candidate: Any = None
    if isinstance(data, dict):
        api_error = data.get("error")
        if isinstance(api_error, dict):
            candidate = api_error.get("message") or api_error.get("code")
        elif isinstance(api_error, str):
            candidate = api_error
        if candidate is None:
            candidate = data.get("message") or data.get("detail")
    if not isinstance(candidate, str):
        return None

    # Даже если провайдер неожиданно вернул ключ в сообщении, он не попадёт в лог.
    detail = re.sub(r"tk_ai_[A-Za-z0-9._-]+", "[СКРЫТО]", candidate).strip()
    detail = " ".join(detail.split())
    return detail[:300] or None


@dataclass(frozen=True)
class TaynikVisionConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 180.0
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TaynikVisionConfig":
        source = os.environ if env is None else env
        api_key = source.get("AI_API_KEY", "").strip()
        if not api_key:
            raise TaynikVisionError("Не задан секрет AI_API_KEY.")
        if not api_key.isascii():
            raise TaynikVisionError(
                "AI_API_KEY содержит не-ASCII символы. Скопируйте только значение ключа "
                "Taynik без подписи, кавычек и постороннего текста."
            )
        if any(character.isspace() for character in api_key):
            raise TaynikVisionError(
                "AI_API_KEY содержит пробел или перенос строки. Скопируйте только "
                "непрерывное значение ключа Taynik."
            )

        base_url = source.get("AI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        model = source.get("AI_MODEL", DEFAULT_MODEL).strip()
        if not base_url.startswith("https://"):
            raise TaynikVisionError("AI_BASE_URL должен начинаться с https://.")
        if not model:
            raise TaynikVisionError("AI_MODEL не может быть пустым.")

        try:
            timeout = float(source.get("AI_TIMEOUT_SECONDS", "180"))
            max_bytes = int(source.get("AI_MAX_IMAGE_BYTES", str(DEFAULT_MAX_IMAGE_BYTES)))
        except ValueError as error:
            raise TaynikVisionError("Некорректная числовая настройка AI API.") from error
        if timeout <= 0 or max_bytes <= 0:
            raise TaynikVisionError("Лимиты AI API должны быть положительными.")

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout,
            max_image_bytes=max_bytes,
        )


@dataclass(frozen=True)
class PlanRecognition:
    shape: str
    length_m: float | None
    width_m: float | None
    area_m2: float | None
    outer_perimeter_m: float | None
    inner_bearing_wall_length_m: float | None
    storeys: int | None
    wall_material: str | None
    missing_fields: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_image(path: Path, max_bytes: int) -> tuple[bytes, str]:
    if not path.is_file():
        raise TaynikVisionError(f"Файл изображения не найден: {path}")
    mime_type = SUPPORTED_IMAGE_TYPES.get(path.suffix.lower())
    if mime_type is None:
        guessed, _ = mimetypes.guess_type(path.name)
        raise TaynikVisionError(
            f"Поддерживаются только JPG и PNG; получен {guessed or 'неизвестный формат'}."
        )
    size = path.stat().st_size
    if size <= 0:
        raise TaynikVisionError("Файл изображения пуст.")
    if size > max_bytes:
        raise TaynikVisionError(
            f"Изображение больше тестового лимита {max_bytes} байт."
        )
    return path.read_bytes(), mime_type


def build_chat_payload(image_bytes: bytes, mime_type: str, model: str) -> dict[str, Any]:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 1200,
    }


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def _optional_positive_number(data: Mapping[str, Any], field: str) -> float | None:
    value = data[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise TaynikVisionError(f"Поле {field} должно быть положительным числом или null.")
    return float(value)


def _string_list(data: Mapping[str, Any], field: str) -> list[str]:
    value = data[field]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TaynikVisionError(f"Поле {field} должно быть списком строк.")
    return value


def parse_recognition_content(content: str) -> PlanRecognition:
    try:
        data = json.loads(_strip_json_fence(content))
    except (json.JSONDecodeError, TypeError) as error:
        raise TaynikVisionError("Модель вернула невалидный JSON.") from error
    if not isinstance(data, dict):
        raise TaynikVisionError("Ответ модели должен быть JSON-объектом.")
    actual_fields = set(data)
    if actual_fields != EXPECTED_FIELDS:
        missing = sorted(EXPECTED_FIELDS - actual_fields)
        extra = sorted(actual_fields - EXPECTED_FIELDS)
        raise TaynikVisionError(
            f"JSON не соответствует схеме; отсутствуют {missing}, лишние {extra}."
        )

    shape = data["shape"]
    if shape not in {"rectangular", "complex", "unknown"}:
        raise TaynikVisionError("Поле shape содержит недопустимое значение.")

    storeys = data["storeys"]
    if storeys is not None and (
        isinstance(storeys, bool) or not isinstance(storeys, int) or storeys <= 0
    ):
        raise TaynikVisionError("Поле storeys должно быть положительным целым или null.")

    wall_material = data["wall_material"]
    if wall_material is not None and (
        not isinstance(wall_material, str) or not wall_material.strip()
    ):
        raise TaynikVisionError("Поле wall_material должно быть строкой или null.")

    return PlanRecognition(
        shape=shape,
        length_m=_optional_positive_number(data, "length_m"),
        width_m=_optional_positive_number(data, "width_m"),
        area_m2=_optional_positive_number(data, "area_m2"),
        outer_perimeter_m=_optional_positive_number(data, "outer_perimeter_m"),
        inner_bearing_wall_length_m=_optional_positive_number(
            data, "inner_bearing_wall_length_m"
        ),
        storeys=storeys,
        wall_material=wall_material.strip() if wall_material is not None else None,
        missing_fields=_string_list(data, "missing_fields"),
        warnings=_string_list(data, "warnings"),
    )


def _extract_message_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise TaynikVisionError("В ответе API нет choices[0].message.content.") from error
    if not isinstance(content, str):
        raise TaynikVisionError("API вернул content в неподдерживаемом формате.")
    return content


def _open_json_request(
    request: Request,
    *,
    timeout_seconds: float,
    opener=urlopen,
    phase: str,
) -> tuple[dict[str, Any], int, float]:
    started = time.monotonic()
    try:
        with opener(request, timeout=timeout_seconds) as http_response:
            status = getattr(http_response, "status", 200)
            response_body = http_response.read()
    except HTTPError as error:
        detail = _safe_api_error_detail(error)
        suffix = f" Причина провайдера: {detail}" if detail else ""
        raise TaynikVisionError(
            f"AI API вернул HTTP {error.code} на этапе «{phase}».{suffix}"
        ) from error
    except URLError as error:
        raise TaynikVisionError(
            f"Не удалось подключиться к AI API на этапе «{phase}»."
        ) from error
    except TimeoutError as error:
        raise TaynikVisionError(
            f"Истекло время ожидания AI API на этапе «{phase}»."
        ) from error
    except UnicodeEncodeError as error:
        raise TaynikVisionError(
            "Ключ или адрес API содержит символы, недопустимые в HTTP-заголовке."
        ) from error
    latency = round(time.monotonic() - started, 3)

    try:
        response = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TaynikVisionError(
            f"AI API вернул невалидный JSON на этапе «{phase}»."
        ) from error
    if not isinstance(response, dict):
        raise TaynikVisionError(
            f"AI API вернул неподдерживаемый ответ на этапе «{phase}»."
        )
    return response, status, latency


def check_gateway_access(
    config: TaynikVisionConfig,
    *,
    opener=urlopen,
) -> dict[str, Any]:
    """Проверить ключ и наличие модели без отправки изображения."""
    endpoint = f"{config.base_url.rstrip('/')}/models"
    request = Request(
        endpoint,
        method="GET",
        headers={
            **CLIENT_HEADERS,
            "Authorization": f"Bearer {config.api_key}",
        },
    )
    response, status, latency = _open_json_request(
        request,
        timeout_seconds=config.timeout_seconds,
        opener=opener,
        phase="проверка ключа и списка моделей",
    )
    models = response.get("data")
    if not isinstance(models, list):
        raise TaynikVisionError("Список моделей API имеет неподдерживаемый формат.")
    model_ids = {
        item.get("id")
        for item in models
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if config.model not in model_ids:
        raise TaynikVisionError(
            f"Модель {config.model} отсутствует в доступном для этого ключа списке."
        )
    return {
        "http_status": status,
        "latency_seconds": latency,
        "requested_model_available": True,
    }


def recognize_plan(
    image_path: str | Path,
    config: TaynikVisionConfig,
    *,
    opener=urlopen,
) -> tuple[PlanRecognition, dict[str, Any]]:
    image_bytes, mime_type = _read_image(Path(image_path), config.max_image_bytes)
    payload = build_chat_payload(image_bytes, mime_type, config.model)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            **CLIENT_HEADERS,
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    response, status, latency = _open_json_request(
        request,
        timeout_seconds=config.timeout_seconds,
        opener=opener,
        phase="распознавание изображения",
    )
    recognition = parse_recognition_content(_extract_message_content(response))
    diagnostics = {
        "http_status": status,
        "latency_seconds": latency,
        "requested_model": config.model,
        "response_model": response.get("model"),
    }
    return recognition, diagnostics
