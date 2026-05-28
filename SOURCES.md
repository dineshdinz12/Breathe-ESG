# Sources — Breathe ESG

For each source: what real-world format was researched, what we learned, what the sample data looks like and why, and what would break in a real deployment.

---

## Source 1: SAP Fuel & Procurement

### What I researched

SAP's purchasing module (MM — Materials Management) stores procurement data across several tables:
- **EKKO** — Purchase Order Header (vendor, document date, company code)
- **EKPO** — Purchase Order Item (material, quantity, unit, plant, price)
- **MARA** — Material Master (material type, material group)
- **MAKT** — Material Description (short text in multiple languages)
- **LFA1** — Vendor Master

Real SAP export paths researched: IDoc (EDI messaging), SAP Gateway OData, BAPI RFC calls, and SE16N/SQVI flat file exports. I chose SE16N flat file — see DECISIONS.md.

Key learnings:
1. **MEINS (unit of measure)** uses SAP-internal codes: `L`, `LTR`, `LT` all mean litres; `GAL` and `GLN` are US and Imperial gallons respectively. German-locale SAP adds further variants.
2. **BEDAT (document date)** is stored as `YYYYMMDD` internally but German-locale exports show `DD.MM.YYYY`. Some SQVI exports show `YYYY-MM-DD`. The parser handles all three.
3. **WERKS (plant code)** is a 4-character opaque identifier (e.g. `DE01`, `UK03`). It means nothing without a lookup table — which SAP stores in table **T001W** (Plants). We replicate this as `PlantCodeLookup`.
4. **MAKTX (material description)** is the only reliable way to infer fuel type in a flat file export without access to MARA material groups. The parser uses keyword matching (diesel, petrol, natural gas, LPG, fuel oil, jet fuel).
5. **German number format:** Some SAP configs export quantities as `1.234,56` (dot=thousands, comma=decimal). The parser detects and handles this.
6. **Cancelled PO lines:** SAP sometimes includes reversed purchase orders with zero or negative quantities. These are flagged.

### What the sample data looks like

`sample_data/sap_fuel_procurement.tsv` — tab-delimited, 22 rows, columns:

```
EBELN    EBELP  MATNR       MAKTX                  WERKS  BEDAT     MENGE     MEINS  NETPR    WAERS
4500001  10     MAT-DSL-001 Diesel Fuel - Grade B   UK01   20240115  5000      L      0.85     GBP
4500002  10     MAT-PNG-001 Natural Gas - Pipeline   DE01   20240120  1200      M3     0.42     EUR
```

Dates are mixed (some YYYYMMDD, some DD.MM.YYYY) to test the parser's date handling. Plant codes map to the fixture lookup table. Material descriptions cover all six fuel categories. Two rows intentionally have unknown plant codes to exercise the flag path.

### What would break in a real deployment

1. **Material group mismatch:** If a client's MAKTX descriptions don't match our English keywords (e.g. "Kraftstoff Diesel" in German), the fuel type inference fails and the record is flagged. Fix: add German keywords or use MARA material group codes from a separate export.
2. **Non-fuel procurement in the same export:** Clients sometimes export all PO lines, not just fuel. Non-fuel materials fail fuel type inference and are flagged — the analyst must manually reject or categorise them.
3. **Plant codes not in our lookup:** New plants, JV plants, or temporary sites won't be in the lookup. Record is ingested with the raw plant code and flagged. Fix: maintain PlantCodeLookup as a living document.
4. **Large files:** A client with 50,000 PO lines per quarter would require async processing (see TRADEOFFS.md).
5. **Character encoding:** SAP can export in `SAP-1252` (a Windows variant). We assume UTF-8 with `errors='replace'` as a fallback.

---

## Source 2: Utility / Electricity

### What I researched

Utility data ingestion paths researched:
- **Green Button Connect (API):** US/Canada standard. OAuth2, requires registration with each utility. Most enterprise utilities support it.
- **Utility portal CSV export:** Every utility portal (EDF, National Grid, E.ON, etc.) offers a "download my data" CSV. Format varies but column semantics are consistent.
- **PDF bills:** Require OCR. No standard structure.
- **ESPM (Energy Star Portfolio Manager):** US EPA's benchmarking platform. Accepts bulk uploads and has an API. Relevant for US clients.

I chose portal CSV export — see DECISIONS.md.

Key learnings:
1. **Billing periods don't align to calendar months.** A typical UK meter reads on day 17 of each month. A billing period might run Dec 18 – Jan 17. We use `period_end` as `activity_date`.
2. **Peak/off-peak split.** Some portals export a row per tariff tier. Total consumption = peak + off-peak kWh. We accept both a `CONSUMPTION_KWH` total column and separate `PEAK_KWH`/`OFFPEAK_KWH` columns.
3. **Unit inconsistency.** Some portals export in MWh (especially large industrial accounts). Our parser normalises MWh → kWh with a 1000× factor.
4. **Negative consumption.** Credit/correction rows appear in the same export. These are flagged for analyst review.
5. **Green tariff flag.** If `TARIFF_CODE` contains keywords like "GREEN", "RENEW", "WIND", "SOLAR", we flag the record — the market-based emission factor may differ from location-based.
6. **Multi-meter accounts.** A site with 10 electricity meters may have 10 rows per billing period. Each row becomes one EmissionRecord (one meter = one measurement instrument = one record).

### What the sample data looks like

`sample_data/utility_electricity.csv` — comma-delimited, 20 rows:

```
ACCOUNT_ID,METER_ID,SERVICE_ADDRESS,BILLING_PERIOD_START,BILLING_PERIOD_END,CONSUMPTION_KWH,TARIFF_CODE,TOTAL_COST,CURRENCY,COUNTRY
ACC-001,MTR-UK-001,"123 Industrial Park, Manchester UK",2024-01-17,2024-02-17,45230,STANDARD,3847.55,GBP,GB
ACC-002,MTR-DE-001,"Industriestrasse 45, München",2024-01-20,2024-02-20,87500,ÖKOENERGIE GREEN,6125.00,EUR,DE
```

Includes: UK and German sites, one green tariff row (flagged), one very high consumption row (flagged), one negative consumption row (credit), mixed date formats.

### What would break in a real deployment

1. **Country inference from address:** Our heuristic (keyword matching on "London", "Manchester", etc.) fails for any address we haven't seen. Fix: require an explicit `COUNTRY` column or configure a default per-tenant.
2. **Market-based vs location-based:** We calculate location-based only. A client with PPAs or RECs needs a separate market-based calculation. Our flag directs the analyst to handle this manually.
3. **Sub-metering and allocation:** Large buildings often sub-meter by floor or department. The CSV export may not reflect this. We ingest at meter level; allocation to cost centres is a reporting concern outside this scope.
4. **Demand charges and reactive power:** Some exports include kVArh (reactive energy) columns. We ignore these — they don't contribute to Scope 2.
5. **BTU/therms (US gas):** US gas meters report in therms or BTU, not kWh. Our ELEC_UNIT_MAP includes BTU conversion but we don't have a natural gas Scope 1 overlap — if a US client has combined electricity and gas on one portal export, the gas rows would be mis-categorised as Scope 2.

---

## Source 3: Corporate Travel

### What I researched

Corporate travel platforms researched:
- **Concur Travel & Expense API:** Well-documented REST API with OAuth2. Provides expense reports, travel itineraries, and receipt data. Requires SAP Concur client ID — 3–6 week provisioning. Docs: developer.concur.com
- **Navan (TripActions) API:** Similar OAuth2 flow. Newer platform with better structured data. Same provisioning timeline.
- **Amex GBT / BCD Travel reports:** Travel Management Companies often provide monthly Excel/CSV extracts directly. Less structured but no API provisioning needed.
- **Manual expense spreadsheets:** The sustainability lead's fallback when no TMS exists.

I chose Concur CSV export — the "Standard Accounting Extract" report — see DECISIONS.md.

Key learnings about the Concur CSV format:
1. **Column names are configurable** — the report template determines headers. Our parser handles 15+ column name aliases per field.
2. **Expense types are client-configurable** in Concur. A client might use "AIRFARE" instead of "AIR". Our EXPENSE_TYPE_MAP handles common aliases.
3. **Distances are inconsistent.** Air travel entries sometimes include mileage (in miles, not km). Hotel entries have nights. Ground transport has km or miles. Our parser converts miles → km and handles absent distances.
4. **IATA codes aren't always 3 letters.** Train stations, cruise ports, and some regional airports use 4-letter ICAO codes. We validate for 3-letter codes only; non-standard codes are flagged.
5. **Return flights.** Concur sometimes logs a round trip as one row, sometimes as two. We treat every row as one leg and flag it if the analyst should verify this.
6. **Hotel nights vs dates.** Some exports give check-in/check-out dates (compute nights = difference); others give a `NIGHTS` column directly. We handle both.

**DEFRA 2023 flight methodology:**
- Great-circle distance via haversine formula
- 8% routing uplift (aircraft fly indirect routes)
- Distance bands: <483 km domestic, 483–3,700 km short-haul, >3,700 km long-haul
- Cabin class multipliers: Economy 1.0×, Premium Economy 1.6×, Business 2.9×, First 4.0×
- Radiative forcing multiplier: 1.891× (accounts for NOx, contrails, water vapour)

### What the sample data looks like

`sample_data/travel_concur_export.csv` — comma-delimited, 30 rows, covering:

```
EXPENSE_ID,EXPENSE_TYPE,ORIGIN,DESTINATION,DEPARTURE_DATE,NIGHTS,DISTANCE_KM,CABIN_CLASS,EMPLOYEE_ID
EXP-001,AIR,LHR,JFK,2024-01-10,,,"business",EMP-042
EXP-002,HOTEL,,,2024-01-10,3,,,"EMP-042"
EXP-003,TAXI,,,2024-01-10,,15,,"EMP-042"
```

Covers all five expense types (AIR, HOTEL, CAR, TAXI, RAIL). Includes: unknown IATA codes (flagged), unknown cabin class (flagged), missing nights (flagged), a domestic flight, a long-haul flight, and a business-class return.

### What would break in a real deployment

1. **Unknown IATA codes.** Our airport lookup has 30 common airports. A client flying to regional airports (e.g. `EXT` for Exeter) would have their flight distance unresolvable. Fix: extend the airport fixture or use an external IATA database API.
2. **Concur custom expense categories.** If a client's Concur instance uses "LUFTHANSA_BUSINESS" as an expense type rather than "AIR", our mapping misses it. Fix: add client-specific type mappings to the tenant config.
3. **Multi-currency amounts.** We store amounts as-is; no currency conversion. CO2e calculations don't use monetary amounts, but analysts might want to cross-reference spend.
4. **Travel data completeness.** Concur only captures expenses submitted for reimbursement. Personal card travel, executive travel booked outside the TMS, and travel by contractors are missing. This is the most significant real-world gap.
5. **Hotel emission factor granularity.** We use a single `hotel_uk` factor for all hotels. In reality, DEFRA provides factors by region and star rating. A UK budget hotel has a meaningfully different footprint than a US luxury hotel. Fix: add country and category-level hotel factors.
