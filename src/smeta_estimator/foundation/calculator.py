"""Pure foundation geometry and concrete calculations."""

from decimal import Decimal, ROUND_CEILING

from .errors import FoundationValidationError, ValidationIssue
from .models import FoundationInput, FoundationResult, QuantitySource, RebarConfig


PI = Decimal("3.141592653589793")
ENGINEERING_WARNING = (
    "Расчёт предварительный: тип фундамента и несущая способность не проверены."
)
OPEN_REBAR_WARNING = (
    "Параметры поперечной арматуры свай не подтверждены и не рассчитаны автоматически."
)


def _greater_than_zero(issues: list[ValidationIssue], field: str, value: Decimal) -> None:
    if value <= 0:
        issues.append(ValidationIssue(field, "значение должно быть больше нуля"))


def _not_negative(issues: list[ValidationIssue], field: str, value: Decimal) -> None:
    if value < 0:
        issues.append(ValidationIssue(field, "значение не может быть отрицательным"))


def _validate_rebar(
    issues: list[ValidationIssue],
    prefix: str,
    config: RebarConfig,
    *,
    allow_open_transverse: bool = False,
) -> None:
    if not config.longitudinal_grade or not config.longitudinal_grade.strip():
        issues.append(
            ValidationIssue(f"{prefix}.longitudinal_grade", "класс не заполнен")
        )
    _greater_than_zero(
        issues, f"{prefix}.longitudinal_diameter_mm", config.longitudinal_diameter_mm
    )
    if config.longitudinal_count <= 0:
        issues.append(
            ValidationIssue(
                f"{prefix}.longitudinal_count", "значение должно быть целым больше нуля"
            )
        )
    _greater_than_zero(
        issues, f"{prefix}.transverse_spacing_m", config.transverse_spacing_m
    )
    _not_negative(issues, f"{prefix}.concrete_cover_m", config.concrete_cover_m)
    if not allow_open_transverse:
        if not config.transverse_grade or not config.transverse_grade.strip():
            issues.append(
                ValidationIssue(f"{prefix}.transverse_grade", "класс не заполнен")
            )
        if config.transverse_diameter_mm is None:
            issues.append(
                ValidationIssue(f"{prefix}.transverse_diameter_mm", "диаметр не заполнен")
            )
        else:
            _greater_than_zero(
                issues,
                f"{prefix}.transverse_diameter_mm",
                config.transverse_diameter_mm,
            )


def validate_foundation_input(data: FoundationInput) -> None:
    issues: list[ValidationIssue] = []

    _greater_than_zero(issues, "outer_wall_length_m", data.outer_wall_length_m)
    _not_negative(issues, "inner_wall_length_m", data.inner_wall_length_m)
    _greater_than_zero(issues, "outer_grillage_width_m", data.outer_grillage_width_m)
    _greater_than_zero(issues, "outer_grillage_height_m", data.outer_grillage_height_m)
    if data.inner_wall_length_m > 0:
        _greater_than_zero(issues, "inner_grillage_width_m", data.inner_grillage_width_m)
        _greater_than_zero(issues, "inner_grillage_height_m", data.inner_grillage_height_m)
    _greater_than_zero(issues, "pile_spacing_m", data.pile_spacing_m)
    _greater_than_zero(issues, "pile_diameter_m", data.pile_diameter_m)
    _greater_than_zero(issues, "pile_length_m", data.pile_length_m)
    _greater_than_zero(
        issues, "concrete_rounding_step_m3", data.concrete_rounding_step_m3
    )

    for field_name in ("grillage_waste_ratio", "pile_waste_ratio"):
        value = getattr(data, field_name)
        if value < 0 or value > Decimal("0.5"):
            issues.append(
                ValidationIssue(field_name, "коэффициент должен быть от 0 до 0,5")
            )

    for field_name in (
        "outer_sand_thickness_m",
        "inner_sand_thickness_m",
        "pile_base_sand_thickness_m",
    ):
        _not_negative(issues, field_name, getattr(data, field_name))

    if (
        not isinstance(data.grillage_concrete_grade, str)
        or not data.grillage_concrete_grade.strip()
    ):
        issues.append(ValidationIssue("grillage_concrete_grade", "класс не заполнен"))
    if (
        not isinstance(data.pile_concrete_grade, str)
        or not data.pile_concrete_grade.strip()
    ):
        issues.append(ValidationIssue("pile_concrete_grade", "класс не заполнен"))

    if data.pile_count_override is not None:
        if isinstance(data.pile_count_override, bool) or not isinstance(
            data.pile_count_override, int
        ):
            issues.append(
                ValidationIssue("pile_count_override", "значение должно быть целым")
            )
        elif data.pile_count_override <= 0:
            issues.append(
                ValidationIssue(
                    "pile_count_override", "значение должно быть больше нуля"
                )
            )

    _validate_rebar(issues, "outer_rebar", data.outer_rebar)
    if data.inner_wall_length_m > 0:
        _validate_rebar(issues, "inner_rebar", data.inner_rebar)
    _validate_rebar(issues, "pile_rebar", data.pile_rebar, allow_open_transverse=True)

    if issues:
        raise FoundationValidationError(issues)


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _round_up_to_step(value: Decimal, step: Decimal) -> Decimal:
    multiplier = (value / step).to_integral_value(rounding=ROUND_CEILING)
    return multiplier * step


def calculate_foundation(data: FoundationInput) -> FoundationResult:
    """Calculate preliminary foundation geometry without choosing a design."""

    validate_foundation_input(data)

    total_length = data.outer_wall_length_m + data.inner_wall_length_m
    calculated_piles = _ceil_decimal(total_length / data.pile_spacing_m)
    effective_piles = data.pile_count_override or calculated_piles

    if (
        data.pile_count_override is not None
        and data.pile_count_override != calculated_piles
        and not (data.pile_count_override_reason or "").strip()
    ):
        raise FoundationValidationError(
            [
                ValidationIssue(
                    "pile_count_override_reason",
                    "укажите причину изменения рассчитанного количества свай",
                )
            ]
        )

    outer_volume = (
        data.outer_wall_length_m
        * data.outer_grillage_width_m
        * data.outer_grillage_height_m
    )
    inner_volume = (
        data.inner_wall_length_m
        * data.inner_grillage_width_m
        * data.inner_grillage_height_m
        if data.inner_wall_length_m > 0
        else Decimal("0")
    )
    one_pile_volume = PI * (data.pile_diameter_m / 2) ** 2 * data.pile_length_m
    all_piles_volume = Decimal(effective_piles) * one_pile_volume

    grillage_with_waste = (outer_volume + inner_volume) * (
        Decimal("1") + data.grillage_waste_ratio
    )
    piles_with_waste = all_piles_volume * (Decimal("1") + data.pile_waste_ratio)
    concrete_before_rounding = grillage_with_waste + piles_with_waste
    concrete_calculated = _round_up_to_step(
        concrete_before_rounding, data.concrete_rounding_step_m3
    )

    warnings = [ENGINEERING_WARNING]
    if (
        data.pile_rebar.transverse_grade is None
        or data.pile_rebar.transverse_diameter_mm is None
    ):
        warnings.append(OPEN_REBAR_WARNING)

    return FoundationResult(
        total_grillage_length_m=total_length,
        pile_count_calculated=calculated_piles,
        pile_count_effective=effective_piles,
        pile_count_source=(
            QuantitySource.MANUAL
            if data.pile_count_override is not None
            else QuantitySource.FORMULA
        ),
        outer_grillage_volume_m3=outer_volume,
        inner_grillage_volume_m3=inner_volume,
        one_pile_volume_m3=one_pile_volume,
        all_piles_volume_m3=all_piles_volume,
        grillage_concrete_with_waste_m3=grillage_with_waste,
        pile_concrete_with_waste_m3=piles_with_waste,
        concrete_before_rounding_m3=concrete_before_rounding,
        concrete_calculated_m3=concrete_calculated,
        warnings=tuple(warnings),
    )
