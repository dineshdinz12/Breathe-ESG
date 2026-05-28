from rest_framework import serializers
from core.models import (
    EmissionRecord, EmissionRecordEdit, IngestionBatch, EmissionFactor
)


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = ["id", "category_code", "unit", "co2e_per_unit", "source_name", "source_year", "version"]


class EmissionRecordEditSerializer(serializers.ModelSerializer):
    edited_by = serializers.StringRelatedField()

    class Meta:
        model = EmissionRecordEdit
        fields = ["id", "edited_by", "edited_at", "field_changed", "old_value", "new_value", "reason"]


class EmissionRecordSerializer(serializers.ModelSerializer):
    emission_factor = EmissionFactorSerializer(read_only=True)
    edits = EmissionRecordEditSerializer(many=True, read_only=True)
    reviewed_by = serializers.StringRelatedField()

    class Meta:
        model = EmissionRecord
        fields = [
            "id", "source_type", "batch", "scope", "category_code",
            "activity_date", "facility_or_cc",
            "raw_id", "raw_date_str", "raw_unit", "raw_quantity_str",
            "quantity_normalized", "unit_canonical", "co2e_kg",
            "emission_factor",
            "origin_iata", "destination_iata", "cabin_class", "distance_km",
            "status", "reviewed_by", "reviewed_at", "is_locked",
            "review_note", "is_flagged_auto", "flag_reason",
            "source_row_json",
            "created_at", "updated_at",
            "edits",
        ]
        read_only_fields = [
            "id", "source_type", "batch", "scope", "category_code",
            "source_row_json", "raw_id", "raw_date_str", "raw_unit", "raw_quantity_str",
            "unit_canonical", "emission_factor", "origin_iata", "destination_iata",
            "distance_km", "is_flagged_auto", "reviewed_by", "reviewed_at",
            "is_locked", "created_at", "updated_at", "edits",
        ]


class EmissionRecordEditableSerializer(serializers.ModelSerializer):
    """Used for PATCH — only allows editing quantity and review_note."""
    class Meta:
        model = EmissionRecord
        fields = ["quantity_normalized", "co2e_kg", "review_note", "facility_or_cc"]


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField()
    record_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()
    approved_count = serializers.SerializerMethodField()
    flagged_count = serializers.SerializerMethodField()
    total_co2e_kg = serializers.SerializerMethodField()

    class Meta:
        model = IngestionBatch
        fields = [
            "id", "source_type", "filename", "uploaded_by", "uploaded_at",
            "status", "row_count", "error_count", "error_log",
            "record_count", "pending_count", "approved_count", "flagged_count",
            "total_co2e_kg",
        ]

    def get_record_count(self, obj):
        return obj.records.count()

    def get_pending_count(self, obj):
        return obj.records.filter(status="PENDING").count()

    def get_approved_count(self, obj):
        return obj.records.filter(status="APPROVED").count()

    def get_flagged_count(self, obj):
        return obj.records.filter(status="FLAGGED").count()

    def get_total_co2e_kg(self, obj):
        from django.db.models import Sum
        result = obj.records.aggregate(total=Sum("co2e_kg"))["total"]
        return float(result or 0)
