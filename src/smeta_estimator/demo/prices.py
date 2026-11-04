"""Validated access to temporary, unverified demo-price candidates."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from importlib.resources import files

from smeta_estimator.foundation import FOUNDATION_CATALOG


class DemoPriceStatus(StrEnum):
    DEMO_UNVERIFIED = "DEMO_UNVERIFIED"
    DEMO_ALTERNATIVE = "DEMO_ALTERNATIVE"
    DEMO_UNIT_MISMATCH = "DEMO_UNIT_MISMATCH"


@dataclass(frozen=True, slots=True)
class DemoPriceCandidate:
    variant_id: str
    item_code: str
    name: str
    grade: str | None
    canonical_unit: str
    source_unit: str
    unit_price_rub: Decimal
    is_active: bool
    includes_delivery: bool | None
    status: DemoPriceStatus
    source_file: str
    source_sheet: str
    source_cell: str
    price_effective_date: str | None
    comment: str

    @property
    def source_reference(self) -> str:
        return f"{self.source_file} / {self.source_sheet}!{self.source_cell}"


def _parse_bool(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{field_name}: expected true or false, got {value!r}")


def _parse_delivery(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    if normalized == "unknown":
        return None
    raise ValueError(f"includes_delivery: unexpected value {value!r}")


def load_demo_price_candidates() -> tuple[DemoPriceCandidate, ...]:
    """Load and validate the structured extracts shipped with the demo."""

    catalog = {item.code: item for item in FOUNDATION_CATALOG}
    resource = files("smeta_estimator.demo.data").joinpath(
        "foundation_price_candidates.csv"
    )
    candidates: list[DemoPriceCandidate] = []
    with resource.open("r", encoding="utf-8", newline="") as stream:
        for row_number, row in enumerate(csv.DictReader(stream), start=2):
            item_code = row["item_code"].strip()
            if item_code not in catalog:
                raise ValueError(f"row {row_number}: unknown item code {item_code}")
            try:
                price = Decimal(row["unit_price_rub"].strip())
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"row {row_number}: invalid price") from exc
            if price <= 0:
                raise ValueError(f"row {row_number}: price must be positive")
            candidate = DemoPriceCandidate(
                variant_id=row["variant_id"].strip(),
                item_code=item_code,
                name=row["name"].strip(),
                grade=row["grade"].strip() or None,
                canonical_unit=row["canonical_unit"].strip(),
                source_unit=row["source_unit"].strip(),
                unit_price_rub=price,
                is_active=_parse_bool(row["is_active"], "is_active"),
                includes_delivery=_parse_delivery(row["includes_delivery"]),
                status=DemoPriceStatus(row["status"].strip()),
                source_file=row["source_file"].strip(),
                source_sheet=row["source_sheet"].strip(),
                source_cell=row["source_cell"].strip(),
                price_effective_date=row["price_effective_date"].strip() or None,
                comment=row["comment"].strip(),
            )
            if candidate.is_active:
                if candidate.status is not DemoPriceStatus.DEMO_UNVERIFIED:
                    raise ValueError(
                        f"row {row_number}: active price must be DEMO_UNVERIFIED"
                    )
                if candidate.canonical_unit != catalog[item_code].unit:
                    raise ValueError(
                        f"row {row_number}: canonical unit does not match catalog"
                    )
                if candidate.source_unit != candidate.canonical_unit:
                    raise ValueError(
                        f"row {row_number}: active source unit does not match catalog"
                    )
            candidates.append(candidate)

    active_codes = [candidate.item_code for candidate in candidates if candidate.is_active]
    duplicates = sorted({code for code in active_codes if active_codes.count(code) > 1})
    if duplicates:
        raise ValueError(f"multiple active prices: {', '.join(duplicates)}")
    return tuple(candidates)


def active_demo_prices(
    candidates: tuple[DemoPriceCandidate, ...] | None = None,
) -> dict[str, Decimal]:
    source = candidates if candidates is not None else load_demo_price_candidates()
    return {
        candidate.item_code: candidate.unit_price_rub
        for candidate in source
        if candidate.is_active
    }
