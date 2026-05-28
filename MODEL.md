# Data Model — Breathe ESG

## Overview

Every ingested row — regardless of source — is normalised into a single canonical table: **EmissionRecord**. The original source data is always preserved verbatim. Edits never mutate records in place; they append to an immutable audit log.

---

## Entity Relationship

```
Tenant
  └── IngestionBatch (many)
        └── EmissionRecord (many)
              ├── EmissionFactor (FK, protected)
              ├── EmissionRecordEdit (audit log, many)
              └── reviewed_by → User

PlantCodeLookup  (tenant-scoped lookup for SAP plant codes)
AirportLookup    (global IATA code → lat/lon for haversine distance)
```

---

## Table: Tenant

Multi-tenancy is **row-level** — every important table carries a `tenant` FK. This was chosen over schema-per-tenant because:

- SQLite (dev) and PostgreSQL (prod) both support it simply.
- Simpler ORM queries — no dynamic `SET search_path`.
- Sufficient isolation for an analyst-facing prototype; a true SaaS product with strict data isolation needs would reconsider.

| Field | Type | Notes |
|-------|------|-------|
| name | CharField | Human name, e.g. "Acme Industries Ltd" |
| slug | SlugField (unique) | URL/identifier safe key |

---

## Table: EmissionFactor

Published emission conversion factors, **versioned**. A factor row is never deleted or updated — when DEFRA releases a new edition, a new row is inserted. This means we can always re-derive the CO2e figure that was used at ingestion time, or re-compute with a newer factor.

| Field | Type | Notes |
|-------|------|-------|
| category_code | CharField | e.g. `diesel`, `electricity_uk_grid`, `flight_economy_long` |
| unit | CharField | The denominator unit: L, kg, kWh, km, pkm, night |
| co2e_per_unit | Decimal(12,6) | kg CO2e per unit |
| source_name | CharField | e.g. "DEFRA 2023" |
| source_year | PositiveSmallInteger | For ordering/selection |
| version | CharField | e.g. "2023-v1" |
| valid_from / valid_to | DateField | For time-bounded factor selection |

**Why not embed factors directly on EmissionRecord?**  
Factors change annually. Embedding would make historical re-derivation impossible. With a FK we can re-run `quantity × factor.co2e_per_unit` at any time.

---

## Table: IngestionBatch

One upload session. Groups N EmissionRecords together. Preserves who uploaded, when, what file, and the final outcome including any parse errors.

Batches support a **lock** operation: once all records in a batch are approved, an analyst can lock the batch. Locking sets `is_locked=True` on every approved EmissionRecord, making them read-only for audit submission.

---

## Table: EmissionRecord

The canonical normalised emission row. Every source ends up here.

### Source preservation
- `source_row_json` — verbatim copy of the incoming row, never modified. Analysts can always verify what the system actually received.
- `raw_id`, `raw_date_str`, `raw_unit`, `raw_quantity_str` — key raw fields extracted separately for easy display without parsing JSON.

### Normalised fields
- `activity_date` — parsed and normalised to a Python `date`.
- `quantity_normalized` — converted to the canonical unit for that category (L for liquid fuels, kWh for electricity, km for ground transport, pkm for flights, nights for hotels).
- `unit_canonical` — one of: L, kg, kWh, km, pkm, night.
- `co2e_kg` — `quantity_normalized × emission_factor.co2e_per_unit`. Always in kg CO2e.

### Scope assignment
| Source | Scope | GHG Protocol basis |
|--------|-------|---------------------|
| SAP fuel/procurement | 1 | Direct combustion from company-controlled sources |
| Utility electricity | 2 | Purchased electricity (location-based) |
| Corporate travel | 3 | Category 6 — business travel |

### Review workflow
```
PENDING → APPROVED → (locked)
        ↘ FLAGGED  → PENDING (after analyst edits)
        ↘ REJECTED
```

`is_locked` is a one-way transition. Once locked, the record cannot be edited or re-approved — it is audit-ready.

### Auto-flagging
The parser sets `is_flagged_auto=True` and writes a `flag_reason` string when it encounters:
- Unknown plant codes, unknown fuel types, unknown airports
- Zero quantities, negative consumption
- Very high values (statistical outliers)
- Missing dates
- Unknown cabin classes, unit ambiguities

Auto-flagged records start in `FLAGGED` status so analysts see them immediately.

---

## Table: EmissionRecordEdit (Audit Log)

Every field change on an EmissionRecord is recorded here — **never in-place**. Fields:

| Field | Notes |
|-------|-------|
| record | FK to EmissionRecord |
| edited_by | FK to User |
| edited_at | auto timestamp |
| field_changed | e.g. "quantity_normalized" |
| old_value / new_value | stored as text |
| reason | analyst's free-text explanation |

This means a full edit history is available for any record. Auditors can see exactly what was changed, by whom, and why.

---

## Lookup Tables

### PlantCodeLookup
SAP plant codes (`WERKS`) are opaque 4-character identifiers. Without this table, SAP rows cannot be attributed to a real facility. The lookup is tenant-scoped (each client has different codes) and includes `country`, `region`, and `grid_region` for electricity factor selection.

### AirportLookup
IATA 3-letter airport codes → lat/lon. Used to compute great-circle distances for flights when only the route (e.g. `LHR → JFK`) is given. Distances are then used to select the appropriate DEFRA flight category (domestic / short-haul / long-haul).

---

## Design Decisions

1. **Single canonical table over source-specific tables.** One table means one Review Queue, one audit trail, and one API. The cost is nullable fields for travel-specific columns (origin_iata, cabin_class, distance_km) that don't apply to SAP rows.

2. **Decimal not Float for all CO2e values.** Carbon accounting is financial-adjacent. Float rounding errors are unacceptable in an audit context.

3. **JSONField for source_row_json.** We never lose what came in. If our parser had a bug, the raw data is there to re-process.

4. **Immutable audit log over versioned records.** A versioning system (row per version) is more complex and harder to query. An append-only edit log is simpler and sufficient for an analyst audit trail.
