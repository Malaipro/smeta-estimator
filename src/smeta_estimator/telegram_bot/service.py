"""Pure service layer shared by Telegram handlers and tests."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from smeta_estimator.demo import (
    DemoEstimateSummary,
    DemoPriceCandidate,
    build_demo_foundation_estimate,
    load_demo_price_candidates,
)
from smeta_estimator.foundation import (
    EstimateLine,
    FoundationInput,
    FoundationResult,
    calculate_foundation,
)


@dataclass(slots=True)
class FoundationDraft:
    object_name: str = ""
    outer_wall_length_m: Decimal | None = None
    inner_wall_length_m: Decimal | None = None
    outer_grillage_width_m: Decimal = Decimal("0.5")
    outer_grillage_height_m: Decimal = Decimal("0.6")
    inner_grillage_width_m: Decimal = Decimal("0.4")
    inner_grillage_height_m: Decimal = Decimal("0.6")
    pile_spacing_m: Decimal = Decimal("1.5")
    pile_diameter_m: Decimal = Decimal("0.35")
    pile_length_m: Decimal = Decimal("2.0")
    grillage_waste_ratio: Decimal = Decimal("0.05")
    pile_waste_ratio: Decimal = Decimal("0.05")
    concrete_rounding_step_m3: Decimal = Decimal("0.5")

    def to_input(self) -> FoundationInput:
        if self.outer_wall_length_m is None or self.inner_wall_length_m is None:
            raise ValueError("Wall lengths are required")
        return FoundationInput(
            outer_wall_length_m=self.outer_wall_length_m,
            inner_wall_length_m=self.inner_wall_length_m,
            outer_grillage_width_m=self.outer_grillage_width_m,
            outer_grillage_height_m=self.outer_grillage_height_m,
            inner_grillage_width_m=self.inner_grillage_width_m,
            inner_grillage_height_m=self.inner_grillage_height_m,
            pile_spacing_m=self.pile_spacing_m,
            pile_diameter_m=self.pile_diameter_m,
            pile_length_m=self.pile_length_m,
            grillage_waste_ratio=self.grillage_waste_ratio,
            pile_waste_ratio=self.pile_waste_ratio,
            concrete_rounding_step_m3=self.concrete_rounding_step_m3,
        )


@dataclass(frozen=True, slots=True)
class EditField:
    name: str
    label: str
    unit: str
    kind: str = "positive"


@dataclass(frozen=True, slots=True)
class DraftCalculation:
    data: FoundationInput
    result: FoundationResult
    lines: tuple[EstimateLine, ...]
    price_candidates: tuple[DemoPriceCandidate, ...]
    demo_summary: DemoEstimateSummary


EDIT_FIELDS: tuple[EditField, ...] = (
    EditField("outer_grillage_width_m", "Ширина наружного ростверка", "м"),
    EditField("outer_grillage_height_m", "Высота наружного ростверка", "м"),
    EditField("inner_grillage_width_m", "Ширина внутреннего ростверка", "м"),
    EditField("inner_grillage_height_m", "Высота внутреннего ростверка", "м"),
    EditField("pile_spacing_m", "Шаг свай", "м"),
    EditField("pile_diameter_m", "Диаметр свай", "м"),
    EditField("pile_length_m", "Длина свай", "м"),
    EditField("grillage_waste_ratio", "Запас бетона ростверка", "%", "percent"),
    EditField("pile_waste_ratio", "Запас бетона свай", "%", "percent"),
)


def parse_decimal(text: str, *, allow_zero: bool = False) -> Decimal:
    normalized = text.strip().replace(" ", "").replace(",", ".")
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Введите число, например 40 или 21,5") from exc
    if value < 0 or (value == 0 and not allow_zero):
        condition = "неотрицательным" if allow_zero else "больше нуля"
        raise ValueError(f"Значение должно быть {condition}")
    return value


def parse_percent(text: str) -> Decimal:
    value = parse_decimal(text, allow_zero=True)
    if value > 50:
        raise ValueError("Запас должен быть от 0 до 50 процентов")
    return value / Decimal("100")


def calculate_draft(
    draft: FoundationDraft,
) -> DraftCalculation:
    data = draft.to_input()
    result = calculate_foundation(data)
    candidates = load_demo_price_candidates()
    lines, summary = build_demo_foundation_estimate(data, result, candidates)
    return DraftCalculation(
        data=data,
        result=result,
        lines=lines,
        price_candidates=candidates,
        demo_summary=summary,
    )


def draft_summary(draft: FoundationDraft) -> str:
    return (
        f"Объект: {draft.object_name}\n"
        f"Наружные стены: {draft.outer_wall_length_m} м\n"
        f"Внутренние несущие стены: {draft.inner_wall_length_m} м\n\n"
        "Тестовые параметры:\n"
        f"• наружный ростверк: {draft.outer_grillage_width_m} × {draft.outer_grillage_height_m} м\n"
        f"• внутренний ростверк: {draft.inner_grillage_width_m} × {draft.inner_grillage_height_m} м\n"
        f"• сваи: шаг {draft.pile_spacing_m} м, диаметр {draft.pile_diameter_m} м, длина {draft.pile_length_m} м\n"
        f"• запас бетона: ростверк {draft.grillage_waste_ratio * 100}%, сваи {draft.pile_waste_ratio * 100}%\n\n"
        "Параметры предварительные и не заменяют проект конструктора."
    )
