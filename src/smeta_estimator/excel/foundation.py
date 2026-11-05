"""Excel export for one preliminary foundation estimate."""

from __future__ import annotations

from copy import copy
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from smeta_estimator.demo import DemoEstimateSummary, DemoPriceCandidate
from smeta_estimator.foundation import (
    EstimateCategory,
    EstimateLine,
    FoundationInput,
    FoundationProjectInfo,
    FoundationResult,
)


NAVY = "1F4E78"
BLUE = "D9EAF7"
LIGHT_BLUE = "EDF4F9"
AMBER = "FFF2CC"
LIGHT_RED = "FCE8E6"
WHITE = "FFFFFF"
TEXT = "1F2937"
GRID = "D9E2F3"
FONT_NAME = "Arial"

CATEGORY_LABELS = {
    EstimateCategory.MATERIAL: "Материалы",
    EstimateCategory.MACHINERY: "Техника и доставка",
    EstimateCategory.WORK: "Работы",
}

SOURCE_LABELS = {
    "formula": "Формула",
    "manual": "Ручной ввод",
    "project": "Проект",
    "specification": "Спецификация",
}


def _number(value: Decimal | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return float(value)


def _safe_object_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "_", value.strip())
    return cleaned.strip("_")[:48] or "объект"


def foundation_workbook_filename(object_name: str, created_at: datetime | None = None) -> str:
    timestamp = created_at or datetime.now()
    return (
        f"Предварительная_смета_фундамент_"
        f"{_safe_object_name(object_name)}_{timestamp:%Y-%m-%d}.xlsx"
    )


def _style_title(ws, cell_range: str) -> None:
    ws.merge_cells(cell_range)
    cell = ws[cell_range.split(":", 1)[0]]
    cell.font = Font(name=FONT_NAME, size=15, bold=True, color=TEXT)
    cell.alignment = Alignment(horizontal="left", vertical="center")


def _style_header(cells: Iterable) -> None:
    for cell in cells:
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name=FONT_NAME, size=10, bold=True, color=WHITE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="thin", color=WHITE))


def _style_body(ws) -> None:
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None and cell.font == Font():
                cell.font = Font(name=FONT_NAME, size=10, color=TEXT)
            alignment = copy(cell.alignment)
            alignment.vertical = "center"
            cell.alignment = alignment
    ws.sheet_view.showGridLines = False


def _set_widths(ws, widths: dict[str, float]) -> None:
    for column, width in widths.items():
        ws.column_dimensions[column].width = width


def _add_summary_sheet(
    workbook: Workbook,
    object_name: str,
    created_at: datetime,
    data: FoundationInput,
    result: FoundationResult,
    demo_summary: DemoEstimateSummary,
) -> None:
    ws = workbook.active
    ws.title = "Сводка"
    ws.sheet_properties.tabColor = NAVY
    ws.sheet_view.showGridLines = False

    _style_title(ws, "A2:F2")
    ws["A2"] = "Предварительная смета: фундамент"
    ws["A4"] = "Объект"
    ws["B4"] = object_name
    ws["A5"] = "Дата расчёта"
    ws["B5"] = created_at.strftime("%d.%m.%Y")
    ws["A6"] = "Статус стоимости"
    ws["B6"] = "Частичный демо-итог; полная стоимость недоступна"
    ws.merge_cells("B6:F6")
    ws["B6"].alignment = Alignment(wrap_text=True, vertical="center")
    ws["B6"].fill = PatternFill("solid", fgColor=AMBER)
    ws.row_dimensions[6].height = 30
    ws["A7"] = "Стоимость рассчитанных позиций"
    ws["B7"] = "='Смета'!C36"
    ws["B7"].number_format = '#,##0.00 "₽"'
    ws["D7"] = (
        f"Рассчитано {len(demo_summary.calculated_line_codes)} из 28 строк; "
        f"без объёма: {len(demo_summary.missing_quantity_codes)}, "
        f"без активной цены: {len(demo_summary.missing_price_codes)}"
    )
    ws.merge_cells("D7:F7")
    ws["D7"].alignment = Alignment(wrap_text=True, vertical="top")

    ws["A8"] = "Основные результаты"
    ws["A8"].font = Font(name=FONT_NAME, size=11, bold=True, color=TEXT)
    ws["A9"] = "Суммарная длина ростверка"
    ws["B9"] = _number(result.total_grillage_length_m)
    ws["C9"] = "м"
    ws["A10"] = "Расчётное количество свай"
    ws["B10"] = result.pile_count_calculated
    ws["C10"] = "шт"
    ws["A11"] = "Количество свай в расчёте"
    ws["B11"] = result.pile_count_effective
    ws["C11"] = "шт"
    ws["A12"] = "Бетон до округления"
    ws["B12"] = _number(result.concrete_before_rounding_m3)
    ws["C12"] = "м³"
    ws["A13"] = "Бетон к заказу"
    ws["B13"] = _number(result.concrete_calculated_m3)
    ws["C13"] = "м³"
    for row_index in range(9, 14):
        ws.cell(row=row_index, column=2).number_format = "0.00"
    for row_index in (10, 11):
        ws.cell(row=row_index, column=2).number_format = "0"

    ws["A15"] = "Ограничения расчёта"
    ws["A15"].font = Font(name=FONT_NAME, size=11, bold=True, color=TEXT)
    row = 16
    price_warning = (
        "Цены взяты из тестовых таблиц: дата актуальности, регион, "
        "НДС и доставка не подтверждены, кроме явной пометки о доставке бетона."
    )
    for warning in (price_warning, *result.warnings):
        ws.cell(row=row, column=1, value=warning)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor=LIGHT_RED)
        ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        row += 1

    ws.cell(row=row + 1, column=1, value="Важно")
    ws.cell(row=row + 1, column=1).font = Font(name=FONT_NAME, bold=True, color=TEXT)
    ws.cell(
        row=row + 2,
        column=1,
        value=(
            "Документ предназначен для предварительной оценки. Тип фундамента, "
            "геология, нагрузки и несущая способность должны быть подтверждены проектом."
        ),
    )
    ws.merge_cells(start_row=row + 2, start_column=1, end_row=row + 3, end_column=6)
    ws.cell(row=row + 2, column=1).alignment = Alignment(wrap_text=True, vertical="top")

    _set_widths(ws, {"A": 39, "B": 22, "C": 10, "D": 12, "E": 12, "F": 12})
    for row in range(4, 7):
        ws.cell(row=row, column=1).font = Font(name=FONT_NAME, bold=True, color=TEXT)
    _style_body(ws)


def _add_inputs_sheet(
    workbook: Workbook,
    data: FoundationInput,
    project_info: FoundationProjectInfo | None,
) -> None:
    ws = workbook.create_sheet("Исходные данные")
    ws.sheet_properties.tabColor = "5B9BD5"
    ws.sheet_view.showGridLines = False
    _style_title(ws, "A2:E2")
    ws["A2"] = "Исходные данные и допущения"

    headers = ["Параметр", "Значение", "Ед.", "Источник", "Статус"]
    for column, value in enumerate(headers, start=1):
        ws.cell(row=4, column=column, value=value)
    _style_header(ws[4])

    info = project_info or FoundationProjectInfo()
    technical_source = info.parameters_source
    technical_status = (
        "Подтверждено сметчиком"
        if technical_source == "Ручной ввод"
        else "Требует проверки"
    )
    rows = [
        ("Форма дома", info.shape, "—", "Выбор сметчика", "Не влияет на формулу напрямую"),
        ("Длина дома", info.house_length_m, "м", "Ручной ввод", "Используется для расчёта периметра"),
        ("Ширина дома", info.house_width_m, "м", "Ручной ввод", "Используется для расчёта периметра"),
        ("Площадь дома", info.area_m2, "м²", "Расчёт/ручной ввод", "Пока не влияет на формулу"),
        ("Этажность", info.storeys, "эт.", "Выбор сметчика", "Пока не влияет на формулу"),
        ("Материал стен", info.wall_material, "—", "Выбор сметчика", "Пока не влияет на формулу"),
        ("Условие по грунту", info.soil_condition, "—", "Выбор сметчика", "Пока не влияет на формулу"),
        ("Периметр наружных несущих стен", data.outer_wall_length_m, "м", "Ручной ввод", "Подтверждено сметчиком"),
        ("Длина внутренних несущих стен", data.inner_wall_length_m, "м", "Ручной ввод", "Подтверждено сметчиком"),
        ("Источник технических параметров", technical_source, "—", technical_source, technical_status),
        ("Ширина наружного ростверка", data.outer_grillage_width_m, "м", technical_source, technical_status),
        ("Высота наружного ростверка", data.outer_grillage_height_m, "м", technical_source, technical_status),
        ("Ширина внутреннего ростверка", data.inner_grillage_width_m, "м", technical_source, technical_status),
        ("Высота внутреннего ростверка", data.inner_grillage_height_m, "м", technical_source, technical_status),
        ("Шаг свай", data.pile_spacing_m, "м", technical_source, technical_status),
        ("Диаметр свай", data.pile_diameter_m, "м", technical_source, technical_status),
        ("Длина свай", data.pile_length_m, "м", technical_source, technical_status),
        ("Запас бетона ростверка", data.grillage_waste_ratio, "доля", technical_source, technical_status),
        ("Запас бетона свай", data.pile_waste_ratio, "доля", technical_source, technical_status),
        ("Шаг округления бетона вверх", data.concrete_rounding_step_m3, "м³", "Формула источника", "Предварительно"),
        ("Класс бетона ростверка", data.grillage_concrete_grade, "—", "Тестовое значение", "Требует проекта"),
        ("Класс бетона свай", data.pile_concrete_grade, "—", "Тестовое значение", "Требует проекта"),
    ]
    for row_index, row_values in enumerate(rows, start=5):
        for column, value in enumerate(row_values, start=1):
            if isinstance(value, Decimal):
                value = float(value)
            ws.cell(row=row_index, column=column, value=value)
        ws.cell(row=row_index, column=2).number_format = "0.000"
        if row_values[3] == "Демонстрационные значения":
            ws.cell(row=row_index, column=2).fill = PatternFill("solid", fgColor=AMBER)

    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:E{4 + len(rows)}"
    _set_widths(ws, {"A": 42, "B": 25, "C": 10, "D": 31, "E": 36})
    for row_index in range(5, 5 + len(rows)):
        ws.row_dimensions[row_index].height = 32
        for column in (2, 4, 5):
            ws.cell(row=row_index, column=column).alignment = Alignment(
                wrap_text=True,
                vertical="center",
            )
    _style_body(ws)


def _add_estimate_sheet(
    workbook: Workbook,
    lines: tuple[EstimateLine, ...],
    price_candidates: tuple[DemoPriceCandidate, ...],
    demo_summary: DemoEstimateSummary,
) -> None:
    ws = workbook.create_sheet("Смета")
    ws.sheet_properties.tabColor = "70AD47"
    ws.sheet_view.showGridLines = False
    _style_title(ws, "A2:N2")
    ws["A2"] = "Предварительная ведомость объёмов и стоимости"
    ws["A3"] = (
        "Жёлтые ячейки можно корректировать. Показан только частичный демо-итог; "
        "пустые значения не заменяются нулями."
    )
    ws.merge_cells("A3:N3")
    ws["A3"].font = Font(name=FONT_NAME, size=9, italic=True, color=TEXT)

    headers = [
        "Категория",
        "Код",
        "Наименование",
        "Ед.",
        "Расчётное количество",
        "Ручная корректировка",
        "Количество в смете",
        "Источник",
        "Цена за единицу",
        "Стоимость",
        "Включено",
        "Комментарий",
        "Статус цены",
        "Источник цены",
    ]
    for column, value in enumerate(headers, start=1):
        ws.cell(row=5, column=column, value=value)
    _style_header(ws[5])

    active_candidates = {
        candidate.item_code: candidate
        for candidate in price_candidates
        if candidate.is_active
    }
    first_data_row = 6
    for row_index, line in enumerate(lines, start=first_data_row):
        candidate = active_candidates.get(line.item_code)
        values = [
            CATEGORY_LABELS[line.category],
            line.item_code,
            line.name,
            line.unit,
            _number(line.calculated_quantity),
            _number(line.manual_quantity_override),
            None,
            SOURCE_LABELS[line.quantity_source.value],
            _number(line.unit_price),
            None,
            "Да" if line.included else "Нет",
            line.comment,
            candidate.status.value if candidate else "Цена не заполнена",
            candidate.source_reference if candidate else None,
        ]
        for column, value in enumerate(values, start=1):
            ws.cell(row=row_index, column=column, value=value)
        ws.cell(
            row=row_index,
            column=7,
            value=(
                f'=IF(ISNUMBER(F{row_index}),F{row_index},'
                f'IF(ISNUMBER(E{row_index}),E{row_index},""))'
            ),
        )
        ws.cell(
            row=row_index,
            column=10,
            value=(
                f'=IF(AND(ISNUMBER(G{row_index}),ISNUMBER(I{row_index})),'
                f'G{row_index}*I{row_index},"")'
            ),
        )
        ws.cell(row=row_index, column=6).fill = PatternFill("solid", fgColor=AMBER)
        ws.cell(row=row_index, column=9).fill = PatternFill("solid", fgColor=AMBER)
        for column in (5, 6, 7, 9, 10):
            ws.cell(row=row_index, column=column).number_format = "#,##0.00"

    last_data_row = first_data_row + len(lines) - 1
    status_row = last_data_row + 2
    ws.cell(row=status_row, column=1, value="Статус итоговой стоимости")
    ws.cell(row=status_row, column=1).font = Font(name=FONT_NAME, bold=True, color=TEXT)
    ws.cell(row=status_row, column=3, value="Полный итог недоступен")
    ws.merge_cells(start_row=status_row, start_column=3, end_row=status_row, end_column=6)
    ws.cell(row=status_row, column=3).fill = PatternFill("solid", fgColor=AMBER)
    ws.cell(row=status_row + 1, column=1, value="Частичный демо-итог")
    ws.cell(
        row=status_row + 1,
        column=3,
        value=f"=SUM(J{first_data_row}:J{last_data_row})",
    )
    ws.cell(row=status_row + 1, column=3).number_format = '#,##0.00 "₽"'
    ws.cell(row=status_row + 2, column=1, value="Рассчитано строк")
    ws.cell(
        row=status_row + 2,
        column=3,
        value=f"{len(demo_summary.calculated_line_codes)} из {len(lines)}",
    )

    ws.freeze_panes = "A6"
    ws.auto_filter.ref = f"A5:L{last_data_row}"
    _set_widths(
        ws,
        {
            "A": 20,
            "B": 22,
            "C": 42,
            "D": 10,
            "E": 18,
            "F": 19,
            "G": 18,
            "H": 16,
            "I": 17,
            "J": 17,
            "K": 11,
            "L": 30,
            "M": 22,
            "N": 42,
        },
    )
    for row in range(6, last_data_row + 1):
        ws.row_dimensions[row].height = 34
        ws.cell(row=row, column=3).alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(row=row, column=12).alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(row=row, column=14).alignment = Alignment(wrap_text=True, vertical="center")
    _style_body(ws)


def _add_price_sources_sheet(
    workbook: Workbook,
    candidates: tuple[DemoPriceCandidate, ...],
) -> None:
    ws = workbook.create_sheet("Источники цен")
    ws.sheet_properties.tabColor = "A5A5A5"
    ws.sheet_view.showGridLines = False
    _style_title(ws, "A2:O2")
    ws["A2"] = "Тестовый каталог цен и происхождение значений"
    ws["A3"] = (
        "Дата актуальности цен не указана. Активные ставки нужны только для проверки схемы. "
        "Альтернативы в расчёт не входят."
    )
    ws.merge_cells("A3:O3")
    ws["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    headers = [
        "Вариант",
        "Код",
        "Наименование",
        "Класс/марка",
        "Ед. каталога",
        "Ед. источника",
        "Цена, ₽",
        "Активна",
        "Доставка",
        "Статус",
        "Файл",
        "Лист",
        "Ячейка",
        "Дата цены",
        "Комментарий",
    ]
    for column, value in enumerate(headers, start=1):
        ws.cell(row=5, column=column, value=value)
    _style_header(ws[5])
    delivery_labels = {True: "Да", False: "Нет", None: "Неизвестно"}
    for row_index, candidate in enumerate(candidates, start=6):
        values = [
            candidate.variant_id,
            candidate.item_code,
            candidate.name,
            candidate.grade,
            candidate.canonical_unit,
            candidate.source_unit,
            _number(candidate.unit_price_rub),
            "Да" if candidate.is_active else "Нет",
            delivery_labels[candidate.includes_delivery],
            candidate.status.value,
            candidate.source_file,
            candidate.source_sheet,
            candidate.source_cell,
            candidate.price_effective_date,
            candidate.comment,
        ]
        for column, value in enumerate(values, start=1):
            ws.cell(row=row_index, column=column, value=value)
        ws.cell(row=row_index, column=7).number_format = '#,##0.00 "₽"'
        if candidate.is_active:
            ws.cell(row=row_index, column=8).fill = PatternFill("solid", fgColor=BLUE)
        else:
            ws.cell(row=row_index, column=8).fill = PatternFill("solid", fgColor=AMBER)
        ws.row_dimensions[row_index].height = 34
        ws.cell(row=row_index, column=3).alignment = Alignment(
            wrap_text=True, vertical="center"
        )
        ws.cell(row=row_index, column=15).alignment = Alignment(wrap_text=True)
    last_row = 5 + len(candidates)
    ws.freeze_panes = "A6"
    ws.auto_filter.ref = f"A5:O{last_row}"
    _set_widths(
        ws,
        {
            "A": 24,
            "B": 22,
            "C": 36,
            "D": 16,
            "E": 15,
            "F": 15,
            "G": 14,
            "H": 11,
            "I": 14,
            "J": 22,
            "K": 22,
            "L": 12,
            "M": 10,
            "N": 15,
            "O": 46,
        },
    )
    _style_body(ws)


def build_foundation_workbook(
    *,
    object_name: str,
    data: FoundationInput,
    result: FoundationResult,
    lines: tuple[EstimateLine, ...],
    demo_summary: DemoEstimateSummary,
    price_candidates: tuple[DemoPriceCandidate, ...],
    project_info: FoundationProjectInfo | None = None,
    created_at: datetime | None = None,
) -> bytes:
    """Build a four-sheet XLSX in memory for Telegram delivery."""

    timestamp = created_at or datetime.now()
    workbook = Workbook()
    _add_summary_sheet(
        workbook, object_name, timestamp, data, result, demo_summary
    )
    _add_inputs_sheet(workbook, data, project_info)
    _add_estimate_sheet(workbook, lines, price_candidates, demo_summary)
    _add_price_sources_sheet(workbook, price_candidates)

    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
