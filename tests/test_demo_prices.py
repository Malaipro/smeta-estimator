from decimal import Decimal
import unittest

from smeta_estimator.demo import (
    DemoPriceStatus,
    build_demo_foundation_estimate,
    load_demo_price_candidates,
)
from smeta_estimator.foundation import FoundationInput, calculate_foundation


def control_input(**overrides) -> FoundationInput:
    values = {
        "outer_wall_length_m": "40",
        "inner_wall_length_m": "21.5",
        "outer_grillage_width_m": "0.5",
        "outer_grillage_height_m": "0.6",
        "inner_grillage_width_m": "0.4",
        "inner_grillage_height_m": "0.6",
        "pile_spacing_m": "1.5",
        "pile_diameter_m": "0.35",
        "pile_length_m": "2",
        "grillage_waste_ratio": "0.05",
        "pile_waste_ratio": "0.05",
        "concrete_rounding_step_m3": "0.5",
    }
    values.update(overrides)
    return FoundationInput(**values)


class DemoPriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = load_demo_price_candidates()

    def test_active_prices_match_algorithm_workbook(self) -> None:
        active = {
            candidate.item_code: candidate.unit_price_rub
            for candidate in self.candidates
            if candidate.is_active
        }
        self.assertEqual(len(active), 22)
        self.assertEqual(active["MAT-CONCRETE"], Decimal("6900"))
        self.assertEqual(active["MAT-REBAR-12"], Decimal("65"))
        self.assertEqual(active["MAT-REBAR-6"], Decimal("37"))

    def test_alternatives_and_unit_mismatch_are_not_active(self) -> None:
        concrete_alternatives = [
            candidate
            for candidate in self.candidates
            if candidate.item_code == "MAT-CONCRETE" and not candidate.is_active
        ]
        self.assertIn(
            Decimal("4350"),
            [item.unit_price_rub for item in concrete_alternatives],
        )
        auger = next(
            item
            for item in self.candidates
            if item.variant_id == "algorithm-auger"
        )
        self.assertFalse(auger.is_active)
        self.assertEqual(auger.status, DemoPriceStatus.DEMO_UNIT_MISMATCH)

    def test_control_estimate_returns_partial_295100_without_zero_filling(self) -> None:
        data = control_input()
        lines, summary = build_demo_foundation_estimate(
            data, calculate_foundation(data), self.candidates
        )
        self.assertEqual(summary.known_subtotal, Decimal("295100.0"))
        self.assertIsNone(summary.complete_total)
        self.assertEqual(len(summary.calculated_line_codes), 9)
        self.assertEqual(len(summary.missing_quantity_codes), 19)
        self.assertEqual(len(summary.missing_price_codes), 6)
        nail_90 = next(
            line for line in lines if line.item_code == "MAT-NAIL-90"
        )
        self.assertIsNone(nail_90.effective_quantity)
        self.assertEqual(nail_90.unit_price, Decimal("130"))
        self.assertIsNone(nail_90.line_total)

    def test_formula_quantities_change_with_geometry(self) -> None:
        data = control_input(outer_wall_length_m="50", inner_wall_length_m="10")
        lines, _ = build_demo_foundation_estimate(
            data, calculate_foundation(data), self.candidates
        )
        quantities = {
            line.item_code: line.effective_quantity for line in lines
        }
        self.assertEqual(quantities["MAT-FORMWORK"], Decimal("60"))
        self.assertEqual(quantities["MAT-RUBEROID"], Decimal("4"))
        self.assertEqual(quantities["MAT-NAIL-70"], Decimal("9"))
        self.assertEqual(quantities["MAT-SAND"], Decimal("12"))


if __name__ == "__main__":
    unittest.main()
