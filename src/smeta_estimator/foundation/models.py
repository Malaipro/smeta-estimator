"""Data models shared by the foundation calculator and future interfaces."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Mapping

from .errors import FoundationValidationError, ValidationIssue


DecimalLike = Decimal | int | float | str


def to_decimal(value: DecimalLike | None, field_name: str) -> Decimal:
    """Convert external values without silently treating blanks as zero."""

    if value is None or (isinstance(value, str) and not value.strip()):
        raise FoundationValidationError(
            [ValidationIssue(field_name, "обязательное значение не заполнено")]
        )
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise FoundationValidationError(
            [ValidationIssue(field_name, "значение должно быть числом")]
        ) from exc


class EstimateCategory(StrEnum):
    MATERIAL = "material"
    MACHINERY = "machinery"
    WORK = "work"


class QuantitySource(StrEnum):
    FORMULA = "formula"
    MANUAL = "manual"
    PROJECT = "project"
    SPECIFICATION = "specification"


@dataclass(frozen=True, slots=True)
class RebarConfig:
    longitudinal_grade: str = "A500"
    longitudinal_diameter_mm: DecimalLike = Decimal("12")
    longitudinal_count: int = 0
    transverse_grade: str | None = "A500"
    transverse_diameter_mm: DecimalLike | None = Decimal("6")
    transverse_spacing_m: DecimalLike = Decimal("0.5")
    concrete_cover_m: DecimalLike = Decimal("0.05")

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "longitudinal_diameter_mm",
            to_decimal(self.longitudinal_diameter_mm, "longitudinal_diameter_mm"),
        )
        if self.transverse_diameter_mm is not None:
            object.__setattr__(
                self,
                "transverse_diameter_mm",
                to_decimal(self.transverse_diameter_mm, "transverse_diameter_mm"),
            )
        object.__setattr__(
            self,
            "transverse_spacing_m",
            to_decimal(self.transverse_spacing_m, "transverse_spacing_m"),
        )
        object.__setattr__(
            self,
            "concrete_cover_m",
            to_decimal(self.concrete_cover_m, "concrete_cover_m"),
        )


def _outer_rebar_default() -> RebarConfig:
    return RebarConfig(longitudinal_count=8)


def _inner_rebar_default() -> RebarConfig:
    return RebarConfig(longitudinal_count=6)


def _pile_rebar_default() -> RebarConfig:
    return RebarConfig(
        longitudinal_count=3,
        transverse_grade=None,
        transverse_diameter_mm=None,
    )


@dataclass(frozen=True, slots=True)
class FoundationInput:
    """Explicit inputs for one preliminary foundation calculation."""

    outer_wall_length_m: DecimalLike
    inner_wall_length_m: DecimalLike
    outer_grillage_width_m: DecimalLike
    outer_grillage_height_m: DecimalLike
    inner_grillage_width_m: DecimalLike
    inner_grillage_height_m: DecimalLike
    pile_spacing_m: DecimalLike
    pile_diameter_m: DecimalLike
    pile_length_m: DecimalLike
    grillage_waste_ratio: DecimalLike
    pile_waste_ratio: DecimalLike
    concrete_rounding_step_m3: DecimalLike
    outer_sand_thickness_m: DecimalLike = Decimal("0.1")
    inner_sand_thickness_m: DecimalLike = Decimal("0.1")
    pile_base_sand_thickness_m: DecimalLike = Decimal("0.1")
    grillage_concrete_grade: str = "B20 (М250)"
    pile_concrete_grade: str = "B20 (М250)"
    pile_count_override: int | None = None
    pile_count_override_reason: str | None = None
    outer_rebar: RebarConfig = field(default_factory=_outer_rebar_default)
    inner_rebar: RebarConfig = field(default_factory=_inner_rebar_default)
    pile_rebar: RebarConfig = field(default_factory=_pile_rebar_default)

    def __post_init__(self) -> None:
        decimal_fields = (
            "outer_wall_length_m",
            "inner_wall_length_m",
            "outer_grillage_width_m",
            "outer_grillage_height_m",
            "inner_grillage_width_m",
            "inner_grillage_height_m",
            "pile_spacing_m",
            "pile_diameter_m",
            "pile_length_m",
            "grillage_waste_ratio",
            "pile_waste_ratio",
            "concrete_rounding_step_m3",
            "outer_sand_thickness_m",
            "inner_sand_thickness_m",
            "pile_base_sand_thickness_m",
        )
        for field_name in decimal_fields:
            object.__setattr__(
                self,
                field_name,
                to_decimal(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class FoundationResult:
    total_grillage_length_m: Decimal
    pile_count_calculated: int
    pile_count_effective: int
    pile_count_source: QuantitySource
    outer_grillage_volume_m3: Decimal
    inner_grillage_volume_m3: Decimal
    one_pile_volume_m3: Decimal
    all_piles_volume_m3: Decimal
    grillage_concrete_with_waste_m3: Decimal
    pile_concrete_with_waste_m3: Decimal
    concrete_before_rounding_m3: Decimal
    concrete_calculated_m3: Decimal
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogItem:
    code: str
    category: EstimateCategory
    name: str
    unit: str
    calculated_field: str | None = None


@dataclass(frozen=True, slots=True)
class EstimateLine:
    item_code: str
    category: EstimateCategory
    name: str
    unit: str
    calculated_quantity: Decimal | None = None
    manual_quantity_override: Decimal | None = None
    unit_price: Decimal | None = None
    base_quantity_source: QuantitySource = QuantitySource.MANUAL
    included: bool = True
    comment: str | None = None

    def __post_init__(self) -> None:
        issues: list[ValidationIssue] = []
        for field_name in (
            "calculated_quantity",
            "manual_quantity_override",
            "unit_price",
        ):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                issues.append(
                    ValidationIssue(field_name, "значение не может быть отрицательным")
                )
        if issues:
            raise FoundationValidationError(issues)

    @property
    def effective_quantity(self) -> Decimal | None:
        if self.manual_quantity_override is not None:
            return self.manual_quantity_override
        return self.calculated_quantity

    @property
    def quantity_source(self) -> QuantitySource:
        if self.manual_quantity_override is not None:
            return QuantitySource.MANUAL
        return self.base_quantity_source

    @property
    def line_total(self) -> Decimal | None:
        quantity = self.effective_quantity
        if quantity is None or self.unit_price is None:
            return None
        return quantity * self.unit_price


@dataclass(frozen=True, slots=True)
class EstimateTotals:
    materials_total: Decimal | None
    machinery_total: Decimal | None
    work_total: Decimal | None
    foundation_subtotal: Decimal | None
    missing_item_codes: tuple[str, ...]


DecimalMapping = Mapping[str, DecimalLike]
