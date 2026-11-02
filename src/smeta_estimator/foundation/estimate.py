"""Estimate aggregation that keeps incomplete totals visible."""

from decimal import Decimal

from .models import EstimateCategory, EstimateLine, EstimateTotals


def _category_total(
    lines: tuple[EstimateLine, ...], category: EstimateCategory
) -> tuple[Decimal | None, list[str]]:
    total = Decimal("0")
    missing: list[str] = []
    for line in lines:
        if not line.included or line.category is not category:
            continue
        line_total = line.line_total
        if line_total is None:
            missing.append(line.item_code)
        else:
            total += line_total
    return (None if missing else total), missing


def calculate_estimate_totals(lines: tuple[EstimateLine, ...]) -> EstimateTotals:
    """Return None for incomplete totals instead of understating them as zero."""

    materials, missing_materials = _category_total(lines, EstimateCategory.MATERIAL)
    machinery, missing_machinery = _category_total(lines, EstimateCategory.MACHINERY)
    work, missing_work = _category_total(lines, EstimateCategory.WORK)
    missing = tuple(missing_materials + missing_machinery + missing_work)
    subtotal = None
    if materials is not None and machinery is not None and work is not None:
        subtotal = materials + machinery + work
    return EstimateTotals(
        materials_total=materials,
        machinery_total=machinery,
        work_total=work,
        foundation_subtotal=subtotal,
        missing_item_codes=missing,
    )
