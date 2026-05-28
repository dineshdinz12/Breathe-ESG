from django.contrib import admin
from .models import (
    Tenant, EmissionFactor, PlantCodeLookup, AirportLookup,
    IngestionBatch, EmissionRecord, EmissionRecordEdit
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ["category_code", "co2e_per_unit", "unit", "source_name", "source_year", "version"]
    list_filter = ["source_name", "source_year"]
    search_fields = ["category_code"]


@admin.register(PlantCodeLookup)
class PlantCodeAdmin(admin.ModelAdmin):
    list_display = ["tenant", "code", "facility_name", "country", "grid_region"]
    list_filter = ["tenant", "country"]


@admin.register(AirportLookup)
class AirportAdmin(admin.ModelAdmin):
    list_display = ["iata_code", "name", "city", "country", "lat", "lon"]
    search_fields = ["iata_code", "name", "city"]


class EmissionRecordEditInline(admin.TabularInline):
    model = EmissionRecordEdit
    extra = 0
    readonly_fields = ["edited_by", "edited_at", "field_changed", "old_value", "new_value", "reason"]
    can_delete = False


@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = [
        "id", "source_type", "category_code", "scope", "activity_date",
        "quantity_normalized", "unit_canonical", "co2e_kg", "status", "is_locked"
    ]
    list_filter = ["source_type", "scope", "status", "is_locked", "tenant"]
    search_fields = ["raw_id", "category_code", "facility_or_cc"]
    readonly_fields = ["source_row_json", "created_at", "updated_at"]
    inlines = [EmissionRecordEditInline]


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ["id", "tenant", "source_type", "filename", "uploaded_by", "uploaded_at", "status", "row_count", "error_count"]
    list_filter = ["source_type", "status", "tenant"]
