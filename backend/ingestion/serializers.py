from rest_framework import serializers
from core.models import IngestionBatch
from django.db.models import Sum


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField()
    total_co2e_kg = serializers.SerializerMethodField()
    approved_count = serializers.SerializerMethodField()
    flagged_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = IngestionBatch
        fields = [
            "id", "source_type", "filename", "uploaded_by", "uploaded_at",
            "status", "row_count", "error_count",
            "total_co2e_kg", "approved_count", "flagged_count", "pending_count",
        ]

    def get_total_co2e_kg(self, obj):
        result = obj.records.aggregate(t=Sum("co2e_kg"))["t"]
        return float(result or 0)

    def get_approved_count(self, obj):
        return obj.records.filter(status="APPROVED").count()

    def get_flagged_count(self, obj):
        return obj.records.filter(status="FLAGGED").count()

    def get_pending_count(self, obj):
        return obj.records.filter(status="PENDING").count()
