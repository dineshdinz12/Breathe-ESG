"""
Corporate Travel Parser (Concur-style CSV Export)

Format: CSV export from Concur or similar corporate travel platform.
We use CSV export rather than the live API because:
- Live Concur API requires OAuth2 client credentials registered with the client's IT team
- That's a weeks-long procurement process that blocks onboarding
- Every Concur user can export reports as CSV today with no IT involvement
- The CSV format is stable and well-documented

Expense types handled:
  AIR   — Flights (distance computed from IATA codes via haversine + 8% uplift)
  HOTEL — Hotel nights (nights × per-night emission factor)
  CAR   — Rental car / company car (distance × car emission factor)
  TAXI  — Taxi, rideshare, Uber, Lyft (distance × taxi factor)
  RAIL  — Train (distance × rail factor)

Scope: All business travel is Scope 3, Category 6 (GHG Protocol Corporate Standard).

Flight emission methodology (DEFRA 2023 distance-based):
  1. Look up origin/destination IATA codes → lat/lon
  2. Calculate great circle distance (haversine)
  3. Apply 8% distance uplift (aircraft rarely fly straight lines)
  4. Apply radiative forcing multiplier (RF = 1.891 per DEFRA 2023) for
     non-CO2 climate effects (NOx, contrails, water vapour at altitude)
  5. Apply cabin class weighting:
     Economy: 1.0×, Premium Economy: 1.6×, Business: 2.9×, First: 4.0×

Why radiative forcing matters: CO2 alone understates aviation's climate impact
by roughly 2×. DEFRA includes RF; EPA does not. We default to including it and
flag it so analysts can see which methodology was used.
"""

import csv
import io
import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from core.models import AirportLookup, EmissionFactor, EmissionRecord, IngestionBatch


# ---------------------------------------------------------------------------
# Cabin class multipliers (DEFRA 2023, relative to economy seat)
# ---------------------------------------------------------------------------
CABIN_MULTIPLIERS = {
    "economy":          Decimal("1.0"),
    "economy class":    Decimal("1.0"),
    "coach":            Decimal("1.0"),
    "premium economy":  Decimal("1.6"),
    "premium":          Decimal("1.6"),
    "business":         Decimal("2.9"),
    "business class":   Decimal("2.9"),
    "first":            Decimal("4.0"),
    "first class":      Decimal("4.0"),
}

DISTANCE_UPLIFT = Decimal("1.08")   # 8% for actual routing vs great circle
RF_MULTIPLIER   = Decimal("1.891")  # DEFRA 2023 radiative forcing

# ---------------------------------------------------------------------------
# Expense type → (category_code, canonical_unit, scope)
# ---------------------------------------------------------------------------
EXPENSE_TYPE_MAP = {
    "AIR":    ("flight_economy", "pkm", 3),
    "FLIGHT": ("flight_economy", "pkm", 3),
    "HOTEL":  ("hotel_uk",       "night", 3),
    "ACCOMMODATION": ("hotel_uk", "night", 3),
    "CAR":    ("car_rental",     "km",    3),
    "RENTAL": ("car_rental",     "km",    3),
    "TAXI":   ("taxi_rideshare", "km",    3),
    "RIDE":   ("taxi_rideshare", "km",    3),
    "UBER":   ("taxi_rideshare", "km",    3),
    "LYFT":   ("taxi_rideshare", "km",    3),
    "RAIL":   ("rail_national",  "km",    3),
    "TRAIN":  ("rail_national",  "km",    3),
    "METRO":  ("rail_national",  "km",    3),
}

COLUMN_ALIASES = {
    "expense_id":     ["EXPENSE_ID", "ExpenseId", "EntryKey", "ID"],
    "report_id":      ["REPORT_ID", "ReportId", "ReportKey"],
    "employee_id":    ["EMPLOYEE_ID", "EmployeeId", "LoginId", "Username"],
    "transaction_date": ["TRANSACTION_DATE", "TransactionDate", "Date", "Datum"],
    "expense_type":   ["EXPENSE_TYPE", "ExpenseType", "Type", "Category", "MccCode"],
    "origin":         ["ORIGIN", "DepartureCity", "From", "FromAirport", "Departure"],
    "destination":    ["DESTINATION", "ArrivalCity", "To", "ToAirport", "Arrival"],
    "departure_date": ["DEPARTURE_DATE", "DepartureDate", "CheckIn", "StartDate"],
    "return_date":    ["RETURN_DATE", "ReturnDate", "CheckOut", "EndDate"],
    "nights":         ["NIGHTS", "Nights", "NumberOfNights", "Duration"],
    "distance_km":    ["DISTANCE_KM", "Distance", "Miles", "DistanceMiles", "Kilometers"],
    "distance_unit":  ["DISTANCE_UNIT", "DistanceUnit", "DistUnit"],
    "cabin_class":    ["CABIN_CLASS", "CabinClass", "ClassOfService", "Class", "SeatClass"],
    "amount":         ["AMOUNT", "TransactionAmount", "Amount", "Betrag"],
    "currency":       ["CURRENCY", "CurrencyCode", "Währung"],
    "description":    ["DESCRIPTION", "Comment", "BusinessPurpose", "Vendor"],
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
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y%m%d", "%m-%d-%Y"):
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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance between two lat/lon points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_airport(iata: str) -> Optional[AirportLookup]:
    iata = iata.strip().upper()
    if len(iata) != 3:
        return None
    try:
        return AirportLookup.objects.get(iata_code=iata)
    except AirportLookup.DoesNotExist:
        return None


def _flight_distance_km(origin_iata: str, dest_iata: str) -> tuple[Optional[Decimal], list]:
    """Compute flight distance with uplift. Returns (km, errors)."""
    errors = []
    origin_ap = _get_airport(origin_iata)
    dest_ap   = _get_airport(dest_iata)
    if not origin_ap:
        errors.append(f"Unknown origin airport code '{origin_iata}'")
    if not dest_ap:
        errors.append(f"Unknown destination airport code '{dest_iata}'")
    if origin_ap and dest_ap:
        gc_km = _haversine_km(
            float(origin_ap.lat), float(origin_ap.lon),
            float(dest_ap.lat),   float(dest_ap.lon)
        )
        return Decimal(str(round(gc_km * float(DISTANCE_UPLIFT), 1))), errors
    return None, errors


def _classify_flight(distance_km: float) -> str:
    """Classify flight as domestic/short/long haul per DEFRA bands."""
    if distance_km < 483:
        return "flight_economy_domestic"
    elif distance_km < 3700:
        return "flight_economy_short"
    else:
        return "flight_economy_long"


def _get_ef(category_code: str, unit: str) -> Optional[EmissionFactor]:
    return (
        EmissionFactor.objects
        .filter(category_code=category_code, unit=unit)
        .order_by("-source_year", "-valid_from")
        .first()
    )


def parse_travel_file(file_content: bytes, batch: IngestionBatch) -> tuple[int, int, list]:
    """
    Parse a Concur-style travel CSV export and create EmissionRecord objects.
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

        raw_expense_type = get(row, "expense_type").upper()
        raw_date         = get(row, "transaction_date") or get(row, "departure_date")
        raw_origin       = get(row, "origin").upper()
        raw_dest         = get(row, "destination").upper()
        raw_nights       = get(row, "nights")
        raw_distance     = get(row, "distance_km")
        raw_dist_unit    = get(row, "distance_unit").upper() or "KM"
        raw_cabin        = get(row, "cabin_class").lower()
        raw_expense_id   = get(row, "expense_id") or get(row, "report_id")

        # Match expense type
        expense_entry = None
        for key, val in EXPENSE_TYPE_MAP.items():
            if key in raw_expense_type:
                expense_entry = val
                break
        if expense_entry is None:
            errors.append({
                "line": i,
                "error": f"Unknown expense type '{raw_expense_type}'",
                "row": dict(row)
            })
            continue

        category_code, canonical_unit, scope = expense_entry
        activity_date = _parse_date(raw_date)
        co2e_kg = Decimal("0")
        quantity_normalized = Decimal("0")
        origin_iata = ""
        dest_iata   = ""
        distance_km_val = None

        # ----------------------------------------------------------------
        # FLIGHTS
        # ----------------------------------------------------------------
        if canonical_unit == "pkm":
            origin_iata = raw_origin
            dest_iata   = raw_dest

            distance_km_val, dist_errors = _flight_distance_km(raw_origin, raw_dest)
            line_errors.extend(dist_errors)

            if distance_km_val is not None:
                category_code = _classify_flight(float(distance_km_val))
                ef = _get_ef(category_code, "pkm")
                if ef:
                    # Apply cabin class multiplier
                    cabin_mult = CABIN_MULTIPLIERS.get(raw_cabin, Decimal("1.0"))
                    if raw_cabin and raw_cabin not in CABIN_MULTIPLIERS:
                        line_errors.append(f"Unknown cabin class '{raw_cabin}', assuming economy")
                    # pkm = distance × cabin multiplier; then × RF
                    pkm = distance_km_val * cabin_mult
                    co2e_kg = pkm * ef.co2e_per_unit * RF_MULTIPLIER
                    quantity_normalized = distance_km_val  # store raw km
                else:
                    line_errors.append(f"No emission factor for {category_code}/pkm")
            else:
                line_errors.append("Could not compute flight distance — need valid IATA codes")

        # ----------------------------------------------------------------
        # HOTELS
        # ----------------------------------------------------------------
        elif canonical_unit == "night":
            nights = _parse_decimal(raw_nights)
            if nights is None or nights <= 0:
                line_errors.append(f"Invalid nights value '{raw_nights}'")
                nights = Decimal("1")
            ef = _get_ef("hotel_uk", "night")
            if ef:
                co2e_kg = nights * ef.co2e_per_unit
            else:
                line_errors.append("No emission factor for hotel_uk/night")
            quantity_normalized = nights

        # ----------------------------------------------------------------
        # GROUND TRANSPORT (car, taxi, rail)
        # ----------------------------------------------------------------
        else:
            distance = _parse_decimal(raw_distance)
            if distance is None or distance <= 0:
                line_errors.append(f"Missing or invalid distance '{raw_distance}'")
                distance = Decimal("0")
            # Convert miles if needed
            if "MI" in raw_dist_unit or "MILE" in raw_dist_unit:
                distance = distance * Decimal("1.60934")
                line_errors.append("Distance converted from miles to km")
            quantity_normalized = distance
            ef = _get_ef(category_code, "km")
            if ef and distance > 0:
                co2e_kg = distance * ef.co2e_per_unit
            elif not ef:
                line_errors.append(f"No emission factor for {category_code}/km")

        is_flagged = bool(line_errors)
        flag_reason = "; ".join(line_errors)

        EmissionRecord.objects.create(
            tenant=tenant,
            batch=batch,
            source_type="TRAVEL",
            source_row_json=dict(row),
            raw_id=raw_expense_id,
            raw_date_str=raw_date,
            raw_unit=raw_dist_unit or canonical_unit,
            raw_quantity_str=raw_distance or raw_nights,
            activity_date=activity_date,
            category_code=category_code,
            scope=scope,
            facility_or_cc=get(row, "employee_id"),
            quantity_normalized=quantity_normalized,
            unit_canonical=canonical_unit,
            co2e_kg=co2e_kg,
            emission_factor=_get_ef(category_code, canonical_unit),
            origin_iata=origin_iata,
            destination_iata=dest_iata,
            cabin_class=raw_cabin,
            distance_km=distance_km_val,
            status="FLAGGED" if is_flagged else "PENDING",
            is_flagged_auto=is_flagged,
            flag_reason=flag_reason,
        )
        rows_created += 1

    return rows_created, len(errors), errors
