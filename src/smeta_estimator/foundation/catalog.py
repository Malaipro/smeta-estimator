"""Foundation estimate catalog derived from the source workbook."""

from collections.abc import Mapping
from decimal import Decimal

from .models import (
    CatalogItem,
    DecimalLike,
    EstimateCategory,
    EstimateLine,
    FoundationResult,
    QuantitySource,
    to_decimal,
)


FOUNDATION_CATALOG: tuple[CatalogItem, ...] = (
    CatalogItem("MAT-FORMWORK", EstimateCategory.MATERIAL, "Аренда и амортизация опалубки", "м.пог."),
    CatalogItem("MAT-RUBEROID", EstimateCategory.MATERIAL, "Рубероид 15 м²", "рул."),
    CatalogItem("MAT-NAIL-70", EstimateCategory.MATERIAL, "Гвозди 70 мм", "кг"),
    CatalogItem("MAT-NAIL-90", EstimateCategory.MATERIAL, "Гвозди 90 мм", "кг"),
    CatalogItem("MAT-SAND", EstimateCategory.MATERIAL, "Песок строительный речной", "т"),
    CatalogItem("MAT-BUCKET", EstimateCategory.MATERIAL, "Ведро металлическое 10 л", "шт"),
    CatalogItem("MAT-SHOVEL", EstimateCategory.MATERIAL, "Лопата совковая и штыковая", "шт"),
    CatalogItem("MAT-SCREW-76", EstimateCategory.MATERIAL, "Саморезы 4,2 × 76 мм", "шт"),
    CatalogItem("MAT-SCREW-51", EstimateCategory.MATERIAL, "Саморезы 3,5 × 51 мм", "шт"),
    CatalogItem("MAT-WIRE", EstimateCategory.MATERIAL, "Проволока вязальная Ø1,2 мм", "кг"),
    CatalogItem("MAT-DISC-125", EstimateCategory.MATERIAL, "Диск по металлу 125 мм", "шт"),
    CatalogItem("MAT-DISC-230", EstimateCategory.MATERIAL, "Диск по металлу 230 мм", "шт"),
    CatalogItem("MAT-FILM", EstimateCategory.MATERIAL, "Плёнка полиэтиленовая", "рул."),
    CatalogItem("MAT-REBAR-12", EstimateCategory.MATERIAL, "Арматура Ø12", "п.м."),
    CatalogItem("MAT-REBAR-6", EstimateCategory.MATERIAL, "Арматура Ø6", "п.м."),
    CatalogItem(
        "MAT-CONCRETE",
        EstimateCategory.MATERIAL,
        "Бетон с доставкой",
        "м³",
        "concrete_calculated_m3",
    ),
    CatalogItem("MAT-OTHER", EstimateCategory.MATERIAL, "Прочие расходные материалы", "компл."),
    CatalogItem("MCH-TOOLS", EstimateCategory.MACHINERY, "Аренда и амортизация инструмента", "компл."),
    CatalogItem("MCH-TAMPER", EstimateCategory.MACHINERY, "Аренда трамбовки", "сут."),
    CatalogItem("MCH-AUGER", EstimateCategory.MACHINERY, "Аренда ямобура", "смена"),
    CatalogItem("MCH-EXCAVATOR", EstimateCategory.MACHINERY, "Экскаватор-погрузчик", "ч"),
    CatalogItem("MCH-EXCAVATOR-EXTRA", EstimateCategory.MACHINERY, "Дополнительное время экскаватора", "ч"),
    CatalogItem("MCH-PUMP", EstimateCategory.MACHINERY, "Аренда бетононасоса", "ч"),
    CatalogItem("MCH-DELIVERY", EstimateCategory.MACHINERY, "Доставка материалов", "рейс"),
    CatalogItem("WRK-GEODESY", EstimateCategory.WORK, "Геодезические работы", "компл."),
    CatalogItem("WRK-LOADING", EstimateCategory.WORK, "Погрузочно-разгрузочные работы", "компл."),
    CatalogItem("WRK-CONSUMABLES", EstimateCategory.WORK, "Расходные материалы плотников", "компл."),
    CatalogItem("WRK-FOUNDATION", EstimateCategory.WORK, "Устройство фундамента", "м³"),
)


def _convert_mapping(values: Mapping[str, DecimalLike] | None) -> dict[str, Decimal]:
    if not values:
        return {}
    return {key: to_decimal(value, key) for key, value in values.items()}


def build_foundation_estimate(
    result: FoundationResult,
    *,
    manual_quantities: Mapping[str, DecimalLike] | None = None,
    unit_prices: Mapping[str, DecimalLike] | None = None,
    excluded_codes: set[str] | frozenset[str] | None = None,
) -> tuple[EstimateLine, ...]:
    """Create the 28 transparent estimate lines without inventing missing values."""

    quantities = _convert_mapping(manual_quantities)
    prices = _convert_mapping(unit_prices)
    excluded = excluded_codes or set()
    known_codes = {item.code for item in FOUNDATION_CATALOG}
    unknown_codes = (set(quantities) | set(prices) | set(excluded)) - known_codes
    if unknown_codes:
        raise KeyError(f"Unknown estimate item codes: {', '.join(sorted(unknown_codes))}")

    lines: list[EstimateLine] = []
    for item in FOUNDATION_CATALOG:
        calculated_quantity = None
        source = QuantitySource.MANUAL
        if item.calculated_field:
            calculated_quantity = getattr(result, item.calculated_field)
            source = QuantitySource.FORMULA
        lines.append(
            EstimateLine(
                item_code=item.code,
                category=item.category,
                name=item.name,
                unit=item.unit,
                calculated_quantity=calculated_quantity,
                manual_quantity_override=quantities.get(item.code),
                unit_price=prices.get(item.code),
                base_quantity_source=source,
                included=item.code not in excluded,
            )
        )
    return tuple(lines)
