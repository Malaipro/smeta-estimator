"""Чистые функции Telegram-сценария распознавания плана."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
import time
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from smeta_estimator.ai import PlanRecognition

from .service import FoundationDraft


Image.MAX_IMAGE_PIXELS = 40_000_000


class ImagePreparationError(ValueError):
    """Изображение нельзя безопасно подготовить для AI API."""


@dataclass(frozen=True, slots=True)
class PreparedImage:
    content: bytes
    mime_type: str
    width: int
    height: int


class HourlyRateLimiter:
    """Непостоянный лимит запросов на пользователя для публичного демо."""

    def __init__(self, max_requests: int, window_seconds: float = 3600) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int, *, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        history = self._requests[user_id]
        cutoff = timestamp - self.window_seconds
        while history and history[0] <= cutoff:
            history.popleft()
        if len(history) >= self.max_requests:
            return False
        history.append(timestamp)
        return True


def prepare_image(
    content: bytes,
    *,
    max_file_bytes: int,
    max_dimension: int,
) -> PreparedImage:
    if not content:
        raise ImagePreparationError("Файл изображения пуст.")
    if len(content) > max_file_bytes:
        raise ImagePreparationError(
            f"Файл превышает лимит {max_file_bytes // 1_000_000} МБ."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as opened:
                if opened.format not in {"JPEG", "PNG"}:
                    raise ImagePreparationError("Поддерживаются только JPG и PNG.")
                image = ImageOps.exif_transpose(opened)
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                if image.mode not in {"RGB", "L"}:
                    background = Image.new("RGB", image.size, "white")
                    if "A" in image.getbands():
                        background.paste(image, mask=image.getchannel("A"))
                    else:
                        background.paste(image)
                    image = background
                elif image.mode == "L":
                    image = image.convert("RGB")
                elif image.mode != "RGB":
                    image = image.convert("RGB")

                output = BytesIO()
                image.save(output, format="JPEG", quality=90, optimize=True)
                return PreparedImage(
                    content=output.getvalue(),
                    mime_type="image/jpeg",
                    width=image.width,
                    height=image.height,
                )
    except ImagePreparationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ImagePreparationError(
            "Не удалось прочитать изображение. Отправьте корректный JPG или PNG."
        ) from error


def recognition_summary(recognition: PlanRecognition) -> str:
    shape_labels = {
        "rectangular": "прямоугольная",
        "complex": "сложная",
        "unknown": "не определена",
    }

    def value(number: float | None, unit: str) -> str:
        return f"{number:g} {unit}" if number is not None else "не определено"

    storeys = str(recognition.storeys) if recognition.storeys is not None else "не определена"
    wall_material = recognition.wall_material or "не определён"
    lines = [
        "Результат распознавания:",
        "",
        f"Форма: {shape_labels[recognition.shape]}",
        f"Длина: {value(recognition.length_m, 'м')}",
        f"Ширина: {value(recognition.width_m, 'м')}",
        f"Площадь: {value(recognition.area_m2, 'м²')}",
        f"Наружный периметр: {value(recognition.outer_perimeter_m, 'м')}",
        "Внутренние несущие стены: "
        f"{value(recognition.inner_bearing_wall_length_m, 'м')}",
        f"Этажность: {storeys}",
        f"Материал стен: {wall_material}",
    ]
    if recognition.warnings:
        lines.extend(["", "Предупреждения:"])
        lines.extend(f"• {warning}" for warning in recognition.warnings[:8])
    lines.extend(
        [
            "",
            "Проверьте значения. ИИ не выбирает фундамент и не выполняет сметный расчёт.",
        ]
    )
    return "\n".join(lines)


def apply_recognition_to_draft(
    recognition: PlanRecognition,
    draft: FoundationDraft,
) -> None:
    """Перенести только допустимые подсказки AI в черновик сметчика."""
    if recognition.shape == "rectangular":
        draft.shape = "Прямоугольный дом"
        if recognition.length_m is not None:
            draft.house_length_m = Decimal(str(recognition.length_m))
        if recognition.width_m is not None:
            draft.house_width_m = Decimal(str(recognition.width_m))
        if draft.house_length_m is not None and draft.house_width_m is not None:
            draft.set_rectangular_geometry(draft.house_length_m, draft.house_width_m)
    elif recognition.shape == "complex":
        draft.shape = "Сложная форма"

    if draft.shape != "Прямоугольный дом":
        if recognition.outer_perimeter_m is not None:
            draft.outer_wall_length_m = Decimal(str(recognition.outer_perimeter_m))
        if recognition.area_m2 is not None:
            draft.area_m2 = Decimal(str(recognition.area_m2))

    if recognition.inner_bearing_wall_length_m is not None:
        draft.inner_wall_length_m = Decimal(
            str(recognition.inner_bearing_wall_length_m)
        )
    if recognition.storeys in {1, 2}:
        draft.storeys = recognition.storeys

    material = (recognition.wall_material or "").strip().lower()
    if "porotherm" in material or "поротерм" in material:
        draft.wall_material = "Porotherm"
    elif "кирпич" in material or material == "brick":
        draft.wall_material = "Кирпич"
