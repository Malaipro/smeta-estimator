"""Demo-only quantities and partial-cost aggregation for the foundation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from smeta_estimator.foundation import (
    EstimateLine,
    FoundationInput,
    FoundationResult,
    QuantitySource,
    build_foundation_estimate,
)

from .prices import DemoPriceCandidate, active_demo_prices


@dataclass(frozen=True, slots=True)
class DemoEstimateSummary:
    known_subtotal: Decimal
    complete_total: Decimal | None
    calculated_line_codes: tuple[str, ...]
    missing_quantity_codes: tuple[str, ...]
    missing_price_codes: tuple[str, ...]


def _floor(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_FLOOR)


def _ceil(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)


def build_demo_foundation_estimate(
    data: FoundationInput,
    result: FoundationResult,
    candidates: tuple[DemoPriceCandidate, ...],
) -> tuple[tuple[EstimateLine, ...], DemoEstimateSummary]:
    """Apply only source-backed demo quantities and prices; never fill gaps with zero."""

    lines = build_foundation_estimate(
        result,
        unit_prices=active_demo_prices(candidates),
    )
    total_length = result.total_grillage_length_m
    formwork_length = _floor(total_length)
    quantities: dict[str, tuple[Decimal, QuantitySource, str]] = {
        "MAT-FORMWORK": (
            formwork_length,
            QuantitySource.FORMULA,
            "Демо-формула: округление общей длины ростверка вниз; источник W10",
        ),
        "MAT-RUBEROID": (
            _ceil(total_length / Decimal("15")),
            QuantitySource.FORMULA,
            "Демо-формула: округление вверх (длина ростверка / 15); источник W11",
        ),
        "MAT-NAIL-70": (
            _ceil(formwork_length * Decimal("0.15")),
            QuantitySource.FORMULA,
            "Демо-формула: округление вверх (опалубка × 0,15); источник W12",
        ),
        "MAT-SAND": (
            _ceil(total_length * data.outer_sand_thickness_m * Decimal("2")),
            QuantitySource.FORMULA,
            "Демо-формула источника: округление вверх (длина × толщина × 2); W14",
        ),
        "MAT-BUCKET": (
            Decimal("6"),
            QuantitySource.SPECIFICATION,
            "Фиксированное демо-количество из исходной таблицы",
        ),
        "MAT-SHOVEL": (
            Decimal("4"),
            QuantitySource.SPECIFICATION,
            "Фиксированное демо-количество из исходной таблицы",
        ),
        "MAT-SCREW-76": (
            Decimal("500"),
            QuantitySource.SPECIFICATION,
            "Фиксированное демо-количество из исходной таблицы",
        ),
        "MAT-SCREW-51": (
            Decimal("500"),
            QuantitySource.SPECIFICATION,
            "Фиксированное демо-количество из исходной таблицы",
        ),
    }

    enriched: list[EstimateLine] = []
    for line in lines:
        if line.item_code in quantities:
            quantity, source, comment = quantities[line.item_code]
            line = replace(
                line,
                calculated_quantity=quantity,
                base_quantity_source=source,
                comment=comment,
            )
        enriched.append(line)

    final_lines = tuple(enriched)
    calculated = tuple(
        line.item_code for line in final_lines if line.line_total is not None
    )
    missing_quantity = tuple(
        line.item_code for line in final_lines if line.effective_quantity is None
    )
    missing_price = tuple(
        line.item_code for line in final_lines if line.unit_price is None
    )
    known_subtotal = sum(
        (line.line_total for line in final_lines if line.line_total is not None),
        Decimal("0"),
    )
    complete_total = known_subtotal if len(calculated) == len(final_lines) else None
    summary = DemoEstimateSummary(
        known_subtotal=known_subtotal,
        complete_total=complete_total,
        calculated_line_codes=calculated,
        missing_quantity_codes=missing_quantity,
        missing_price_codes=missing_price,
    )
    return final_lines, summary
