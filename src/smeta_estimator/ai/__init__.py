"""Изолированные интеграции ИИ для предварительного извлечения параметров."""

from .taynik_vision import (
    PlanRecognition,
    TaynikVisionConfig,
    TaynikVisionError,
    check_gateway_access,
    recognize_plan,
    recognize_plan_bytes,
)

__all__ = [
    "PlanRecognition",
    "TaynikVisionConfig",
    "TaynikVisionError",
    "check_gateway_access",
    "recognize_plan",
    "recognize_plan_bytes",
]
