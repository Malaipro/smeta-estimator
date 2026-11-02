from decimal import Decimal
import unittest

from smeta_estimator.foundation import (
    FOUNDATION_CATALOG,
    EstimateCategory,
    FoundationValidationError,
    QuantitySource,
    build_foundation_estimate,
    calculate_estimate_totals,
    calculate_foundation,
)

from test_foundation_calculator import control_input


class FoundationEstimateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = calculate_foundation(control_input())

    def test_catalog_contains_expected_category_counts(self) -> None:
        counts = {
            category: sum(item.category is category for item in FOUNDATION_CATALOG)
            for category in EstimateCategory
        }
        self.assertEqual(len(FOUNDATION_CATALOG), 28)
        self.assertEqual(counts[EstimateCategory.MATERIAL], 17)
        self.assertEqual(counts[EstimateCategory.MACHINERY], 7)
        self.assertEqual(counts[EstimateCategory.WORK], 4)

    def test_concrete_quantity_comes_from_formula(self) -> None:
        lines = build_foundation_estimate(self.result)
        concrete = next(line for line in lines if line.item_code == "MAT-CONCRETE")
        self.assertEqual(concrete.effective_quantity, Decimal("26.5"))
        self.assertEqual(concrete.quantity_source, QuantitySource.FORMULA)

    def test_zero_manual_quantity_is_preserved(self) -> None:
        lines = build_foundation_estimate(
            self.result,
            manual_quantities={"MAT-RUBEROID": "0"},
            unit_prices={"MAT-RUBEROID": "600"},
        )
        line = next(item for item in lines if item.item_code == "MAT-RUBEROID")
        self.assertEqual(line.effective_quantity, Decimal("0"))
        self.assertEqual(line.quantity_source, QuantitySource.MANUAL)
        self.assertEqual(line.line_total, Decimal("0"))

    def test_missing_price_keeps_line_and_totals_incomplete(self) -> None:
        lines = build_foundation_estimate(self.result)
        concrete = next(line for line in lines if line.item_code == "MAT-CONCRETE")
        totals = calculate_estimate_totals(lines)
        self.assertIsNone(concrete.line_total)
        self.assertIsNone(totals.materials_total)
        self.assertIsNone(totals.foundation_subtotal)
        self.assertIn("MAT-CONCRETE", totals.missing_item_codes)

    def test_complete_manual_catalog_produces_category_totals(self) -> None:
        quantities = {item.code: "1" for item in FOUNDATION_CATALOG}
        prices = {item.code: "100" for item in FOUNDATION_CATALOG}
        lines = build_foundation_estimate(
            self.result,
            manual_quantities=quantities,
            unit_prices=prices,
        )
        totals = calculate_estimate_totals(lines)
        self.assertEqual(totals.materials_total, Decimal("1700"))
        self.assertEqual(totals.machinery_total, Decimal("700"))
        self.assertEqual(totals.work_total, Decimal("400"))
        self.assertEqual(totals.foundation_subtotal, Decimal("2800"))
        self.assertEqual(totals.missing_item_codes, ())

    def test_excluded_incomplete_line_does_not_block_total(self) -> None:
        quantities = {item.code: "1" for item in FOUNDATION_CATALOG}
        prices = {item.code: "100" for item in FOUNDATION_CATALOG}
        prices.pop("MAT-OTHER")
        lines = build_foundation_estimate(
            self.result,
            manual_quantities=quantities,
            unit_prices=prices,
            excluded_codes={"MAT-OTHER"},
        )
        totals = calculate_estimate_totals(lines)
        self.assertEqual(totals.foundation_subtotal, Decimal("2700"))
        self.assertNotIn("MAT-OTHER", totals.missing_item_codes)

    def test_unknown_catalog_code_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            build_foundation_estimate(
                self.result, manual_quantities={"UNKNOWN": "1"}
            )

    def test_negative_manual_quantity_is_rejected(self) -> None:
        with self.assertRaises(FoundationValidationError):
            build_foundation_estimate(
                self.result, manual_quantities={"MAT-RUBEROID": "-1"}
            )

    def test_negative_price_is_rejected(self) -> None:
        with self.assertRaises(FoundationValidationError):
            build_foundation_estimate(
                self.result, unit_prices={"MAT-CONCRETE": "-6900"}
            )


if __name__ == "__main__":
    unittest.main()
