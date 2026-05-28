"""
Core data model for Breathe ESG ingestion platform.

Design principles:
- Every ingested row becomes an EmissionRecord (canonical form).
- Raw source data is always preserved in source_row_json (never lose what came in).
- Edits never mutate records in-place — they append to EmissionRecordEdit (audit log).
- Multi-tenancy is row-level (tenant FK on every important table).
- EmissionFactor is versioned so we can re-derive CO2e as factors update.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Tenant(models.Model):
    """A client company. All data is scoped to a tenant."""
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class EmissionFactor(models.Model):
    """
    Published emission conversion factors. Versioned so we know which
    version of e.g. DEFRA produced any given CO2e figure.

    category_code maps to the 'category_code' field on EmissionRecord.
    """
    UNIT_CHOICES = [
        ("L",    "Litres"),
        ("kg",   "Kilograms"),
        ("kWh",  "Kilowatt-hours"),
        ("km",   "Kilometres"),
        ("pkm",  "Passenger-kilometres"),
        ("night","Hotel nights"),
        ("t",    "Metric tonnes"),
    ]

    category_code   = models.CharField(max_length=60)   # e.g. "diesel", "electricity_uk_grid"
    unit            = models.CharField(max_length=10, choices=UNIT_CHOICES)
    co2e_per_unit   = models.DecimalField(max_digits=12, decimal_places=6)
    source_name     = models.CharField(max_length=120)  # e.g. "DEFRA 2023"
    source_year     = models.PositiveSmallIntegerField()
    version         = models.CharField(max_length=40)
    valid_from      = models.DateField()
    valid_to        = models.DateField(null=True, blank=True)
    notes           = models.TextField(blank=True)

    class Meta:
        unique_together = [("category_code", "version")]
        ordering = ["-source_year", "category_code"]

    def __str__(self):
        return f"{self.category_code} @ {self.co2e_per_unit} {self.unit} ({self.source_name})"


class PlantCodeLookup(models.Model):
    """
    SAP plant codes are opaque identifiers (e.g. 'DE01', 'UK03').
    This lookup table maps them to human-readable facility names.
    Without this, SAP rows can't be attributed to a real location.
    """
    tenant          = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    code            = models.CharField(max_length=20)
    facility_name   = models.CharField(max_length=200)
    country         = models.CharField(max_length=80)
    region          = models.CharField(max_length=80, blank=True)
    grid_region     = models.CharField(max_length=80, blank=True,
                        help_text="Grid region code for electricity emission factor lookup")

    class Meta:
        unique_together = [("tenant", "code")]

    def __str__(self):
        return f"{self.code} → {self.facility_name}"


class AirportLookup(models.Model):
    """
    IATA airport codes with lat/lon for haversine distance calculation.
    Travel data often gives only 'LHR' → 'JFK'; we compute the km.
    """
    iata_code   = models.CharField(max_length=4, unique=True)
    name        = models.CharField(max_length=200)
    city        = models.CharField(max_length=100)
    country     = models.CharField(max_length=80)
    lat         = models.DecimalField(max_digits=9, decimal_places=6)
    lon         = models.DecimalField(max_digits=9, decimal_places=6)

    def __str__(self):
        return f"{self.iata_code} ({self.city}, {self.country})"


class IngestionBatch(models.Model):
    """
    One upload session. A batch contains N EmissionRecords.
    Preserves: who uploaded what file, when, and final processing outcome.
    """
    SOURCE_CHOICES = [
        ("SAP",     "SAP Fuel & Procurement"),
        ("UTILITY", "Utility / Electricity"),
        ("TRAVEL",  "Corporate Travel"),
    ]
    STATUS_CHOICES = [
        ("PROCESSING", "Processing"),
        ("COMPLETE",   "Complete"),
        ("FAILED",     "Failed"),
    ]

    tenant          = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    source_type     = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    filename        = models.CharField(max_length=500)
    uploaded_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at     = models.DateTimeField(auto_now_add=True)
    status          = models.CharField(max_length=12, choices=STATUS_CHOICES, default="PROCESSING")
    row_count       = models.IntegerField(default=0)
    error_count     = models.IntegerField(default=0)
    error_log       = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.source_type} batch #{self.pk} ({self.status})"


class EmissionRecord(models.Model):
    """
    The canonical normalized emission row.

    Every row that comes through ingestion lands here after normalization.
    The original source row is preserved in source_row_json so we can always
    re-parse or audit what was actually received.

    Scope assignment:
      Scope 1 — direct combustion (SAP fuel: diesel, petrol, natural gas)
      Scope 2 — purchased electricity (utility data)
      Scope 3 — business travel (flights, hotels, ground transport)

    Unit normalization:
      SAP quantities are normalized to litres (L) or kg.
      Utility data is always kWh.
      Travel distances are normalized to km.
      co2e_kg is always in kilograms of CO2-equivalent.
    """
    SCOPE_CHOICES = [
        (1, "Scope 1 — Direct emissions"),
        (2, "Scope 2 — Purchased electricity"),
        (3, "Scope 3 — Value chain"),
    ]
    STATUS_CHOICES = [
        ("PENDING",   "Pending review"),
        ("APPROVED",  "Approved"),
        ("FLAGGED",   "Flagged for review"),
        ("REJECTED",  "Rejected"),
    ]
    UNIT_CHOICES = [
        ("L",     "Litres"),
        ("kg",    "Kilograms"),
        ("kWh",   "Kilowatt-hours"),
        ("km",    "Kilometres"),
        ("pkm",   "Passenger-km"),
        ("night", "Hotel nights"),
    ]

    # --- Provenance ---
    tenant          = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    batch           = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE,
                        related_name="records")
    source_type     = models.CharField(max_length=10)   # SAP / UTILITY / TRAVEL

    # --- Raw source preservation ---
    # We keep verbatim source field values so analysts can verify normalization.
    source_row_json = models.JSONField(help_text="Verbatim source row, never modified after ingest")
    raw_id          = models.CharField(max_length=200, blank=True)   # PO number, expense ID, meter ID
    raw_date_str    = models.CharField(max_length=50, blank=True)    # Date as it appeared in source
    raw_unit        = models.CharField(max_length=20, blank=True)    # Unit as it appeared in source
    raw_quantity_str= models.CharField(max_length=50, blank=True)    # Quantity as it appeared

    # --- Normalized fields ---
    activity_date       = models.DateField(null=True, blank=True)
    category_code       = models.CharField(max_length=60)  # diesel / electricity_uk_grid / flight_economy_long / etc.
    scope               = models.PositiveSmallIntegerField(choices=SCOPE_CHOICES)
    facility_or_cc      = models.CharField(max_length=200, blank=True,
                            help_text="Plant name, facility, or cost center")
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4,
                            help_text="Quantity in canonical unit (L, kWh, km, nights)")
    unit_canonical      = models.CharField(max_length=10, choices=UNIT_CHOICES)
    co2e_kg             = models.DecimalField(max_digits=18, decimal_places=4,
                            help_text="kg CO2e, computed from quantity × emission factor")

    # --- Emission factor used ---
    emission_factor     = models.ForeignKey(EmissionFactor, on_delete=models.PROTECT,
                            null=True, blank=True)

    # --- Travel-specific extras ---
    origin_iata         = models.CharField(max_length=4, blank=True)
    destination_iata    = models.CharField(max_length=4, blank=True)
    cabin_class         = models.CharField(max_length=20, blank=True)   # economy / business / first
    distance_km         = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # --- Review state ---
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    reviewed_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                        related_name="reviewed_records")
    reviewed_at     = models.DateTimeField(null=True, blank=True)
    is_locked       = models.BooleanField(default=False,
                        help_text="Locked after batch audit sign-off; no further edits allowed")
    review_note     = models.TextField(blank=True)

    # --- Suspicion flags (set by parser) ---
    is_flagged_auto = models.BooleanField(default=False,
                        help_text="Auto-flagged by parser for analyst attention")
    flag_reason     = models.CharField(max_length=500, blank=True)

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activity_date", "source_type"]

    def __str__(self):
        return f"{self.source_type} | {self.category_code} | {self.quantity_normalized} {self.unit_canonical} | {self.co2e_kg} kg CO2e"

    def approve(self, user):
        if self.is_locked:
            raise ValueError("Record is locked — cannot approve after audit lock.")
        self.status = "APPROVED"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    def flag(self, user, reason=""):
        if self.is_locked:
            raise ValueError("Record is locked.")
        self.status = "FLAGGED"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.flag_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "flag_reason"])

    def reject(self, user, reason=""):
        if self.is_locked:
            raise ValueError("Record is locked.")
        self.status = "REJECTED"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_note = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])


class EmissionRecordEdit(models.Model):
    """
    Immutable audit log of every field change on an EmissionRecord.
    Records are never updated in-place for audited fields; instead an
    Edit entry is appended here.
    """
    record      = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE,
                    related_name="edits")
    edited_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    edited_at   = models.DateTimeField(auto_now_add=True)
    field_changed = models.CharField(max_length=100)
    old_value   = models.TextField()
    new_value   = models.TextField()
    reason      = models.TextField(blank=True)

    class Meta:
        ordering = ["-edited_at"]

    def __str__(self):
        return f"Edit on record #{self.record_id}: {self.field_changed} by {self.edited_by}"
