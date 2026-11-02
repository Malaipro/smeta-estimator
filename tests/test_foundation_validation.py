from dataclasses import replace
import unittest

from smeta_estimator.foundation import FoundationInput, FoundationValidationError, calculate_foundation


def valid_input() -> FoundationInput:
    return FoundationInput(
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


class FoundationValidationTests(unittest.TestCase):
    def test_invalid_numeric_boundaries_are_rejected(self) -> None:
        cases = {
            "outer_wall_length_m": "0",
            "inner_wall_length_m": "-1",
            "outer_grillage_width_m": "0",
            "pile_spacing_m": "0",
            "pile_diameter_m": "0",
            "pile_length_m": "-2",
            "grillage_waste_ratio": "-0.01",
            "pile_waste_ratio": "0.51",
            "concrete_rounding_step_m3": "0",
            "pile_count_override": 0,
        }
        for field_name, invalid_value in cases.items():
            with self.subTest(field=field_name):
                with self.assertRaises(FoundationValidationError) as context:
                    calculate_foundation(replace(valid_input(), **{field_name: invalid_value}))
                self.assertIn(field_name, str(context.exception))

    def test_blank_required_value_is_not_converted_to_zero(self) -> None:
        with self.assertRaises(FoundationValidationError) as context:
            replace(valid_input(), pile_diameter_m="")
        self.assertIn("pile_diameter_m", str(context.exception))

    def test_non_integer_pile_override_is_rejected(self) -> None:
        with self.assertRaises(FoundationValidationError) as context:
            calculate_foundation(replace(valid_input(), pile_count_override=41.5))
        self.assertIn("pile_count_override", str(context.exception))


if __name__ == "__main__":
    unittest.main()
