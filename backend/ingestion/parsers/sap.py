"""
SAP Flat-File Parser

Format: Tab-delimited export from SAP SE16N/SQVI joining EKKO, EKPO, MARA.
This is what a sustainability lead actually receives — not an IDoc (those are
middleware-to-middleware). The SE16N export is the path of least resistance for
most clients: filter by material type, export to spreadsheet.

Real-world headaches handled here:
1. Date formats: SAP uses YYYYMMDD internally but German-locale exports show DD.MM.YYYY
2. Units: MEINS can be L, LTR, LT, KG, G, M3, GAL, GLN — we normalize all
3. Plant codes: WERKS is a 4-char code (DE01, UK03) — looked up against PlantCodeLookup
4. Material mapping: MAKTX (description) is used to infer fuel type when no explicit code
5. Zero quantities: SAP sometimes exports cancelled PO lines with MENGE=0 — flagged
6. German thousand separators: 1.234,56 vs 1,234.56

Scope assignment: All SAP fuel/procurement records are Scope 1 (direct combustion
from company-owned/controlled sources — the GHG Protocol definition).

Units normalized to litres (L) for liquid fuels, kg for gas.
"""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from core.models import (
    EmissionFactor, EmissionRecord, IngestionBatch, PlantCodeLookup
)


# ---------------------------------------------------------------------------
# Unit normalization mappings
# SAP MEINS codes → canonical unit + conversion factor to canonical
# ---------------------------------------------------------------------------
UNIT_MAP = {
    # Litres
    "L":   ("L", Decimal("1")),
    "LTR": ("L", Decimal("1")),
    "LT":  ("L", Decimal("1")),
    "ML":  ("L", Decimal("0.001")),
    # Kilograms (gas)
    "KG":  ("kg", Decimal("1")),
    "G":   ("kg", Decimal("0.001")),
    "T":   ("kg", Decimal("1000")),
    # Volume (gas — m³, converted to kg via density approx)
    "M3":  ("kg", Decimal("0.717")),    # natural gas: ~0.717 kg/m³ at STP
    "NM3": ("kg", Decimal("0.717")),
    # Imperial (some SAP configs)
    "GAL": ("L", Decimal("3.78541")),   # US gallon
    "GLN": ("L", Decimal("3.78541")),
    "IGL": ("L", Decimal("4.54609")),   # Imperial gallon
}

# ---------------------------------------------------------------------------
# Material description → fuel category code
# We check MAKTX (material description) with simple keyword matching.
# In a real deployment, MARA-MTART and a material group mapping would be used.
# ---------------------------------------------------------------------------
FUEL_KEYWORDS = {
    "diesel":       ["diesel", "gasoil", "gas oil", "hvgo", "automotive diesel"],
    "petrol":       ["petrol", "gasoline", "unleaded", "super", "e10", "e5"],
    "natural_gas":  ["natural gas", "lng", "cng", "compressed gas", "erdgas", "flüssiggas"],
    "lpg":          ["lpg", "liquid petroleum", "autogas", "propane", "butane"],
    "fuel_oil":     ["fuel oil", "heavy fuel", "bunker", "hfo", "mazut"],
    "jet_fuel":     ["jet fuel", "aviation fuel", "kerosene", "kerosin", "avtur"],
}

SCOPE1_CATEGORY_SCOPE = {k: 1 for k in FUEL_KEYWORDS}


def _infer_fuel_type(description: str) -> Optional[str]:
    desc_lower = description.lower()
    for category, keywords in FUEL_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return None


# ---------------------------------------------------------------------------
# Date parsing — SAP exports in at least 3 formats
# ---------------------------------------------------------------------------
def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    if not raw or raw in ("00000000", "0000-00-00"):
        return None
    # YYYYMMDD
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # DD.MM.YYYY (German locale)
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    # YYYY-MM-DD (ISO, some configs)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_quantity(raw: str) -> Optional[Decimal]:
    """Handle German number format (1.234,56) and standard (1,234.56)."""
    raw = raw.strip()
    if not raw:
        return None
    # German format: dot as thousands separator, comma as decimal
    if re.match(r"^\d{1,3}(\.\d{3})*,\d+$", raw):
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")  # strip thousand separators
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _get_emission_factor(category_code: str, unit: str) -> Optional[EmissionFactor]:
    """Fetch latest valid emission factor for this category+unit."""
    return (
        EmissionFactor.objects
        .filter(category_code=category_code, unit=unit)
        .order_by("-source_year", "-valid_from")
        .first()
    )


def _get_plant(tenant, werks: str):
    try:
        return PlantCodeLookup.objects.get(tenant=tenant, code=werks.strip())
    except PlantCodeLookup.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Column name aliases — SAP exports have inconsistent header names depending
# on the transaction and locale. We try multiple aliases per field.
# ---------------------------------------------------------------------------
COLUMN_ALIASES = {
    "po_number":    ["EBELN", "PO_NUMBER", "Purchasing Document", "Purchasing Document Number"],
    "po_item":      ["EBELP", "PO_ITEM", "Item"],
    "material":     ["MATNR", "MATERIAL", "Material"],
    "description":  ["MAKTX", "DESCRIPTION", "Material Description", "Kurztext"],
    "plant":        ["WERKS", "PLANT", "Plant"],
    "doc_date":     ["BEDAT", "DOC_DATE", "Document Date", "Belegdatum"],
    "quantity":     ["MENGE", "QUANTITY", "Order Quantity", "Menge"],
    "unit":         ["MEINS", "UNIT", "Order Unit", "Mengeneinheit", "UOM"],
    "net_price":    ["NETPR", "NET_PRICE", "Net Price"],
    "currency":     ["WAERS", "CURRENCY", "Currency"],
    "cost_center":  ["KOSTL", "COST_CENTER", "Cost Center", "Kostenstelle"],
    "vendor":       ["LIFNR", "VENDOR", "Vendor"],
}


def _resolve_headers(header_row: list) -> dict:
    """Map actual CSV headers to canonical field names."""
    header_upper = {h.strip().upper(): h.strip() for h in header_row}
    resolved = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias.upper() in header_upper:
                resolved[field] = header_upper[alias.upper()]
                break
    return resolved


def parse_sap_file(file_content: bytes, batch: IngestionBatch) -> tuple[int, int, list]:
    """
    Parse a SAP flat file export and create EmissionRecord objects.

    Returns: (rows_created, error_count, error_log)
    """
    tenant = batch.tenant
    rows_created = 0
    errors = []

    # Detect delimiter — SAP exports are usually tab-delimited
    sample = file_content[:4096].decode("utf-8", errors="replace")
    dialect = csv.Sniffer().sniff(sample, delimiters="\t,;|")

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

        raw_qty_str  = get(row, "quantity")
        raw_unit_str = get(row, "unit").upper()
        raw_date_str = get(row, "doc_date")
        raw_desc     = get(row, "description")
        raw_plant    = get(row, "plant")
        raw_po       = get(row, "po_number")
        raw_item     = get(row, "po_item")

        # --- Parse quantity ---
        quantity = _parse_quantity(raw_qty_str)
        if quantity is None:
            errors.append({"line": i, "error": f"Cannot parse quantity '{raw_qty_str}'", "row": dict(row)})
            continue

        # --- Normalize unit ---
        unit_entry = UNIT_MAP.get(raw_unit_str)
        if unit_entry is None:
            errors.append({"line": i, "error": f"Unknown unit '{raw_unit_str}'", "row": dict(row)})
            continue
        canonical_unit, conversion = unit_entry
        quantity_normalized = quantity * conversion

        # --- Parse date ---
        activity_date = _parse_date(raw_date_str)

        # --- Infer fuel type ---
        category_code = _infer_fuel_type(raw_desc)
        if category_code is None:
            line_errors.append(f"Cannot infer fuel type from description '{raw_desc}'")

        # --- Resolve plant code ---
        plant = _get_plant(tenant, raw_plant)
        facility_name = plant.facility_name if plant else raw_plant
        if not plant and raw_plant:
            line_errors.append(f"Plant code '{raw_plant}' not in lookup table")

        # --- Fetch emission factor ---
        ef = None
        co2e_kg = Decimal("0")
        if category_code:
            ef = _get_emission_factor(category_code, canonical_unit)
            if ef:
                co2e_kg = quantity_normalized * ef.co2e_per_unit
            else:
                line_errors.append(f"No emission factor for {category_code}/{canonical_unit}")

        # --- Auto-flag conditions ---
        is_flagged = bool(line_errors) or quantity_normalized == 0
        flag_reason = "; ".join(line_errors) if line_errors else ("Zero quantity" if quantity_normalized == 0 else "")

        EmissionRecord.objects.create(
            tenant=tenant,
            batch=batch,
            source_type="SAP",
            source_row_json=dict(row),
            raw_id=f"{raw_po}-{raw_item}",
            raw_date_str=raw_date_str,
            raw_unit=raw_unit_str,
            raw_quantity_str=raw_qty_str,
            activity_date=activity_date,
            category_code=category_code or "unknown",
            scope=1,
            facility_or_cc=facility_name,
            quantity_normalized=quantity_normalized,
            unit_canonical=canonical_unit,
            co2e_kg=co2e_kg,
            emission_factor=ef,
            status="FLAGGED" if is_flagged else "PENDING",
            is_flagged_auto=is_flagged,
            flag_reason=flag_reason,
        )
        rows_created += 1

    return rows_created, len(errors), errors
