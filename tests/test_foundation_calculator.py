from dataclasses import replace
from decimal import Decimal
import unittest

from smeta_estimator.foundation import (
    FoundationInput,
    FoundationValidationError,
    QuantitySource,
    calculate_foundation,
)


def control_input(**changes: object) -> FoundationInput:
    data = FoundationInput(
        outer_wall_length_m="40",
        inner_wall_length_m="21.5",
        outer_grillage_width_m="0.5",
        outer_grillage_height_m="0.6",
        inner_grillage_width_m="0.4",
        inner_grillage_height_m="0.6",
        pile_spacing_m="1.5",
        pile_diameter_m="0.35",
        pile_length_m="2",
        grillage_waste_ratio="0.05",
        pile_waste_ratio="0.05",
        concrete_rounding_step_m3="0.5",
    )
    return replace(data, **changes) if changes else data


class FoundationCalculatorTests(unittest.TestCase):
    def test_control_scenario_matches_source_workbook(self) -> None:
        result = calculate_foundation(control_input())

        self.assertEqual(result.total_grillage_length_m, Decimal("61.5"))
        self.assertEqual(result.pile_count_calculated, 41)
        self.assertEqual(result.pile_count_effective, 41)
        self.assertEqual(result.pile_count_source, QuantitySource.FORMULA)
        self.assertEqual(result.outer_grillage_volume_m3, Decimal("12.000"))
        self.assertEqual(result.inner_grillage_volume_m3, Decimal("5.160"))
        self.assertAlmostEqual(result.all_piles_volume_m3, Decimal("7.889324551327366"))
        self.assertEqual(result.concrete_calculated_m3, Decimal("26.5"))

    def test_ten_percent_pile_waste_rounds_to_27(self) -> None:
        result = calculate_foundation(control_input(pile_waste_ratio="0.10"))
        self.assertEqual(result.concrete_calculated_m3, Decimal("27.0"))

    def test_zero_inner_wall_length_does_not_require_inner_dimensions(self) -> None:
        result = calculate_foundation(
            control_input(
                inner_wall_length_m="0",
                inner_grillage_width_m="0",
                inner_grillage_height_m="0",
            )
        )
        self.assertEqual(result.inner_grillage_volume_m3, Decimal("0"))
        self.assertEqual(result.pile_count_calculated, 27)

    def test_manual_pile_count_is_preserved_with_source(self) -> None:
        result = calculate_foundation(
            control_input(
                pile_count_override=45,
                pile_count_override_reason="По проекту конструктора",
            )
        )
        self.assertEqual(result.pile_count_calculated, 41)
        self.assertEqual(result.pile_count_effective, 45)
        self.assertEqual(result.pile_count_source, QuantitySource.MANUAL)

    def test_changed_override_requires_reason(self) -> None:
        with self.assertRaises(FoundationValidationError) as context:
            calculate_foundation(control_input(pile_count_override=45))
        self.assertIn("pile_count_override_reason", str(context.exception))

    def test_diameter_and_length_change_concrete_volume(self) -> None:
        baseline = calculate_foundation(control_input())
        changed = calculate_foundation(
            control_input(pile_diameter_m="0.30", pile_length_m="1.8")
        )
        self.assertLess(changed.all_piles_volume_m3, baseline.all_piles_volume_m3)
        self.assertNotEqual(
            changed.concrete_calculated_m3, baseline.concrete_calculated_m3
        )

    def test_engineering_warning_is_always_present(self) -> None:
        result = calculate_foundation(control_input())
        self.assertTrue(any("несущая способность" in item for item in result.warnings))


if __name__ == "__main__":
    unittest.main()
