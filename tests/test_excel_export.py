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
        self.calculation = calculate_draft(self.draft)

    def _workbook(self):
        content = build_foundation_workbook(
            object_name=self.draft.object_name,
            data=self.calculation.data,
            result=self.calculation.result,
            lines=self.calculation.lines,
            demo_summary=self.calculation.demo_summary,
            price_candidates=self.calculation.price_candidates,
            created_at=datetime(2026, 11, 2),
        )
        return load_workbook(BytesIO(content), data_only=False)

    def test_workbook_contains_four_expected_sheets(self) -> None:
        workbook = self._workbook()
        self.assertEqual(
            workbook.sheetnames,
            ["Сводка", "Исходные данные", "Смета", "Источники цен"],
        )
        self.assertEqual(workbook["Сводка"]["B13"].value, 26.5)
        self.assertEqual(
            workbook["Сводка"]["B7"].value,
            "='Смета'!C36",
        )
        self.assertEqual(workbook["Сводка"]["B5"].value, "02.11.2026")
        self.assertEqual(workbook["Смета"].max_row, 37)
        self.assertEqual(workbook["Смета"]["C36"].value, "=SUM(J6:J33)")

    def test_concrete_line_keeps_formula_quantity_and_demo_price(self) -> None:
        workbook = self._workbook()
        ws = workbook["Смета"]
        concrete_row = next(
            row
            for row in range(6, ws.max_row + 1)
            if ws.cell(row=row, column=2).value == "MAT-CONCRETE"
        )
        self.assertEqual(ws.cell(row=concrete_row, column=5).value, 26.5)
        self.assertTrue(ws.cell(row=concrete_row, column=7).value.startswith("=IF("))
        self.assertEqual(ws.cell(row=concrete_row, column=9).value, 6900)
        self.assertEqual(
            ws.cell(row=concrete_row, column=13).value,
            "DEMO_UNVERIFIED",
        )

    def test_price_sources_keep_provenance_and_alternatives(self) -> None:
        workbook = self._workbook()
        ws = workbook["Источники цен"]
        concrete_rows = [
            row
            for row in range(6, ws.max_row + 1)
            if ws.cell(row=row, column=2).value == "MAT-CONCRETE"
        ]
        self.assertEqual(len(concrete_rows), 8)
        active_row = next(
            row
            for row in concrete_rows
            if ws.cell(row=row, column=8).value == "Да"
        )
        self.assertEqual(ws.cell(row=active_row, column=7).value, 6900)
        self.assertEqual(ws.cell(row=active_row, column=13).value, "U27")


if __name__ == "__main__":
    unittest.main()
