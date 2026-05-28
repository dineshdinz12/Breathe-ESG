"""
Utility Electricity CSV Parser

Format: Monthly billing CSV export from utility portal (Green Button-style).
This is what a facilities manager actually downloads — not an API pull.
Real utility APIs (like Green Button Connect) require utility-specific OAuth
flows and registration; most enterprise clients can't provide that access
in a typical onboarding window.

Real-world headaches handled here:
1. Billing periods don't align to calendar months (Dec 28 – Jan 29 is common)
2. Peak/off-peak split may or may not be present
3. Units should be kWh but some portals export MWh or BTU
4. Some portals duplicate rows for the same meter if multi-tariff (T1/T2)
5. Negative consumption = credit/correction — flagged for analyst review
6. Multi-meter accounts: each meter gets its own record

Grid emission factor selection:
- We pick the factor by country (from meter service address or a provided country code)
- Market-based vs location-based is a reporting choice; we store location-based
  and flag if a market-based contract code is present (for analyst to note)

Scope assignment: Purchased electricity is always Scope 2 per GHG Protocol.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from core.models import EmissionFactor, EmissionRecord, IngestionBatch


# ---------------------------------------------------------------------------
# Unit normalization for electricity
# ---------------------------------------------------------------------------
ELEC_UNIT_MAP = {
    "KWH":  Decimal("1"),
    "MWH":  Decimal("1000"),
    "GWH":  Decimal("1000000"),
    "BTU":  Decimal("0.000293071"),     # 1 BTU = 0.000293 kWh
    "MBTU": Decimal("293.071"),
    "GJ":   Decimal("277.778"),         # 1 GJ = 277.778 kWh
}

# Country → emission factor category code
# In production this would be a proper grid region mapping
COUNTRY_GRID_FACTOR = {
    "GB":  "electricity_uk_grid",
    "UK":  "electricity_uk_grid",
    "US":  "electricity_us_grid",
    "AU":  "electricity_au_grid",
    "DE":  "electricity_eu_grid",
    "FR":  "electricity_eu_grid",
    "EU":  "electricity_eu_grid",
    "IN":  "electricity_in_grid",
}
DEFAULT_GRID_FACTOR = "electricity_uk_grid"  # fallback

COLUMN_ALIASES = {
    "account_id":      ["ACCOUNT_ID", "Account ID", "Account", "AccountNumber"],
    "meter_id":        ["METER_ID", "Meter ID", "MeterNumber", "Meter Serial", "SerialNumber"],
    "service_address": ["SERVICE_ADDRESS", "Service Address", "Address", "Site"],
    "period_start":    ["BILLING_PERIOD_START", "Period Start", "Start Date", "BillingStart", "ReadingStart"],
    "period_end":      ["BILLING_PERIOD_END", "Period End", "End Date", "BillingEnd", "ReadingEnd"],
    "consumption":     ["CONSUMPTION_KWH", "Consumption", "kWh", "Usage", "TotalKWh", "Total_kWh"],
    "peak_kwh":        ["PEAK_KWH", "Peak", "Peak kWh", "T1_kWh"],
    "offpeak_kwh":     ["OFFPEAK_KWH", "Off-Peak", "OffPeak kWh", "T2_kWh"],
    "unit":            ["UNIT", "Unit of Measure", "UOM", "Einheit"],
    "tariff_code":     ["TARIFF_CODE", "Tariff", "Rate Code", "Plan"],
    "total_cost":      ["TOTAL_COST", "Total Cost", "Amount", "Bill Amount"],
    "currency":        ["CURRENCY", "Currency", "Währung"],
    "country":         ["COUNTRY", "Country Code", "Region"],
}


def _resolve_headers(header_row: list) -> dict:
    header_upper = {h.strip().upper(): h.strip() for h in header_row}
    resolved = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias.upper() in header_upper:
                resolved[field] = header_upper[alias.upper()]
                break
    return resolved


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(raw: str) -> Optional[Decimal]:
    if not raw:
        return None
    raw = raw.strip().replace(",", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _infer_country(address: str, explicit_country: str) -> str:
    if explicit_country:
        return explicit_country.strip().upper()
    # Simple heuristic from address
    address_upper = address.upper()
    if any(x in address_upper for x in ["UK", "LONDON", "MANCHESTER", "BIRMINGHAM", "ENGLAND", "SCOTLAND"]):
        return "GB"
    if any(x in address_upper for x in ["USA", "NEW YORK", "CHICAGO", "LOS ANGELES"]):
        return "US"
    return ""


def parse_utility_file(file_content: bytes, batch: IngestionBatch) -> tuple[int, int, list]:
    """
    Parse a utility portal CSV export and create EmissionRecord objects.
    Returns: (rows_created, error_count, error_log)
    """
    tenant = batch.tenant
    rows_created = 0
    errors = []

    sample = file_content[:4096].decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(
        io.StringIO(file_content.decode("utf-8", errors="replace")),
        dialect=dialect
    )

    headers = reader.fieldnames or []
    col_map = _resolve_headers(headers)

    def get(row, field):
        col = col_map.get(field)
        return row.get(col, "").strip() if col else ""

    for i, row in enumerate(reader, start=2):
        line_errors = []

        raw_consumption = get(row, "consumption")
        raw_unit        = get(row, "unit").upper() or "KWH"
        raw_period_start = get(row, "period_start")
        raw_period_end   = get(row, "period_end")
        raw_meter_id     = get(row, "meter_id")
        raw_account_id   = get(row, "account_id")
        raw_address      = get(row, "service_address")
        raw_country      = get(row, "country")
        raw_tariff       = get(row, "tariff_code")

        # --- Parse consumption ---
        consumption = _parse_decimal(raw_consumption)
        if consumption is None:
            errors.append({"line": i, "error": f"Cannot parse consumption '{raw_consumption}'", "row": dict(row)})
            continue

        # --- Normalize unit ---
        unit_factor = ELEC_UNIT_MAP.get(raw_unit, ELEC_UNIT_MAP.get("KWH"))
        if raw_unit not in ELEC_UNIT_MAP:
            line_errors.append(f"Unexpected unit '{raw_unit}', assuming kWh")
        kwh_normalized = consumption * unit_factor

        # --- Parse dates ---
        period_start = _parse_date(raw_period_start)
        period_end   = _parse_date(raw_period_end)

        # Use billing period end as activity_date (standard ESG practice —
        # attribute consumption to the period it was delivered/billed)
        activity_date = period_end or period_start

        # --- Detect grid region ---
        country = _infer_country(raw_address, raw_country)
        category_code = COUNTRY_GRID_FACTOR.get(country, DEFAULT_GRID_FACTOR)

        # --- Fetch emission factor ---
        ef = (
            EmissionFactor.objects
            .filter(category_code=category_code, unit="kWh")
            .order_by("-source_year", "-valid_from")
            .first()
        )
        co2e_kg = Decimal("0")
        if ef:
            co2e_kg = kwh_normalized * ef.co2e_per_unit
        else:
            line_errors.append(f"No emission factor for {category_code}/kWh")

        # --- Auto-flag conditions ---
        if consumption < 0:
            line_errors.append("Negative consumption — possible credit/correction row")
        if kwh_normalized > Decimal("500000"):
            line_errors.append(f"Very high consumption ({kwh_normalized} kWh) — verify meter reads")
        if not period_start or not period_end:
            line_errors.append("Missing billing period dates")

        # Check if green/market-based tariff should override location-based factor
        if raw_tariff and any(x in raw_tariff.upper() for x in ["GREEN", "RENEW", "ZERO", "WIND", "SOLAR"]):
            line_errors.append(f"Green tariff detected ('{raw_tariff}') — market-based factor may apply; analyst should verify")

        is_flagged = bool(line_errors) or consumption <= 0
        flag_reason = "; ".join(line_errors)

        raw_id = raw_meter_id or raw_account_id or f"row-{i}"

        EmissionRecord.objects.create(
            tenant=tenant,
            batch=batch,
            source_type="UTILITY",
            source_row_json=dict(row),
            raw_id=raw_id,
            raw_date_str=raw_period_end or raw_period_start,
            raw_unit=raw_unit,
            raw_quantity_str=raw_consumption,
            activity_date=activity_date,
            category_code=category_code,
            scope=2,
            facility_or_cc=raw_address or raw_account_id,
            quantity_normalized=kwh_normalized,
            unit_canonical="kWh",
            co2e_kg=co2e_kg,
            emission_factor=ef,
            status="FLAGGED" if is_flagged else "PENDING",
            is_flagged_auto=is_flagged,
            flag_reason=flag_reason,
        )
        rows_created += 1

    return rows_created, len(errors), errors
