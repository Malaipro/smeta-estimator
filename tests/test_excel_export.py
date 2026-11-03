from datetime import datetime
from decimal import Decimal
from io import BytesIO
import unittest

from openpyxl import load_workbook

from smeta_estimator.excel import build_foundation_workbook
from smeta_estimator.telegram_bot.service import FoundationDraft, calculate_draft


class ExcelExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.draft = FoundationDraft(
            object_name="Тестовый дом",
            outer_wall_length_m=Decimal("40"),
            inner_wall_length_m=Decimal("21.5"),
        )
        self.data, self.result, self.lines = calculate_draft(self.draft)

    def test_workbook_contains_three_expected_sheets(self) -> None:
        content = build_foundation_workbook(
            object_name=self.draft.object_name,
            data=self.data,
            result=self.result,
            lines=self.lines,
            created_at=datetime(2026, 11, 2),
        )
        workbook = load_workbook(BytesIO(content), data_only=False)
        self.assertEqual(workbook.sheetnames, ["Сводка", "Исходные данные", "Смета"])
        self.assertEqual(workbook["Сводка"]["B13"].value, 26.5)
        self.assertEqual(workbook["Смета"].max_row, 35)

    def test_concrete_line_keeps_formula_quantity_and_editable_price(self) -> None:
        content = build_foundation_workbook(
            object_name=self.draft.object_name,
            data=self.data,
            result=self.result,
            lines=self.lines,
        )
        workbook = load_workbook(BytesIO(content), data_only=False)
        ws = workbook["Смета"]
        concrete_row = next(
            row for row in range(6, ws.max_row + 1) if ws.cell(row=row, column=2).value == "MAT-CONCRETE"
        )
        self.assertEqual(ws.cell(row=concrete_row, column=5).value, 26.5)
        self.assertTrue(ws.cell(row=concrete_row, column=7).value.startswith("=IF("))
        self.assertIsNone(ws.cell(row=concrete_row, column=9).value)


if __name__ == "__main__":
    unittest.main()
