from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q
from decimal import Decimal

from core.models import EmissionRecord, EmissionRecordEdit, IngestionBatch
from .serializers import EmissionRecordSerializer, EmissionRecordEditableSerializer


def get_tenant():
    from core.models import Tenant
    return Tenant.objects.first()


class EmissionRecordListView(generics.ListAPIView):
    """
    GET /api/records/
    Filterable by: batch, status, scope, source_type, search
    """
    serializer_class = EmissionRecordSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["raw_id", "category_code", "facility_or_cc", "flag_reason"]
    ordering_fields = ["activity_date", "co2e_kg", "created_at", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        tenant = get_tenant()
        qs = EmissionRecord.objects.filter(tenant=tenant).select_related(
            "emission_factor", "reviewed_by", "batch"
        ).prefetch_related("edits")

        batch = self.request.query_params.get("batch")
        if batch:
            qs = qs.filter(batch_id=batch)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status__in=status_filter.upper().split(","))

        scope = self.request.query_params.get("scope")
        if scope:
            qs = qs.filter(scope__in=[int(s) for s in scope.split(",")])

        source_type = self.request.query_params.get("source_type")
        if source_type:
            qs = qs.filter(source_type=source_type.upper())

        flagged_only = self.request.query_params.get("flagged")
        if flagged_only == "true":
            qs = qs.filter(is_flagged_auto=True)

        return qs


class EmissionRecordDetailView(APIView):
    """
    GET  /api/records/{id}/  — retrieve record
    PATCH /api/records/{id}/ — edit editable fields, creates audit log entry
    """
    def get_object(self, pk):
        tenant = get_tenant()
        return get_object_or_404(EmissionRecord, pk=pk, tenant=tenant)

    def get(self, request, pk):
        record = self.get_object(pk)
        return Response(EmissionRecordSerializer(record).data)

    def patch(self, request, pk):
        record = self.get_object(pk)

        if record.is_locked:
            return Response(
                {"error": "Record is locked — cannot edit after audit lock"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = EmissionRecordEditableSerializer(record, data=request.data, partial=True)
        if serializer.is_valid():
            # Record each changed field in audit log
            for field, new_value in serializer.validated_data.items():
                old_value = getattr(record, field)
                if str(old_value) != str(new_value):
                    EmissionRecordEdit.objects.create(
                        record=record,
                        edited_by=request.user,
                        field_changed=field,
                        old_value=str(old_value),
                        new_value=str(new_value),
                        reason=request.data.get("reason", ""),
                    )
            serializer.save()
            return Response(EmissionRecordSerializer(record).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ApproveView(APIView):
    """POST /api/records/{id}/approve/"""
    def post(self, request, pk):
        tenant = get_tenant()
        record = get_object_or_404(EmissionRecord, pk=pk, tenant=tenant)
        try:
            record.approve(request.user)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EmissionRecordSerializer(record).data)


class FlagView(APIView):
    """POST /api/records/{id}/flag/"""
    def post(self, request, pk):
        tenant = get_tenant()
        record = get_object_or_404(EmissionRecord, pk=pk, tenant=tenant)
        reason = request.data.get("reason", "")
        try:
            record.flag(request.user, reason)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EmissionRecordSerializer(record).data)


class RejectView(APIView):
    """POST /api/records/{id}/reject/"""
    def post(self, request, pk):
        tenant = get_tenant()
        record = get_object_or_404(EmissionRecord, pk=pk, tenant=tenant)
        reason = request.data.get("reason", "")
        try:
            record.reject(request.user, reason)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EmissionRecordSerializer(record).data)


class DashboardView(APIView):
    """
    GET /api/dashboard/
    Returns aggregate stats for the analyst dashboard KPI cards.
    """
    def get(self, request):
        tenant = get_tenant()
        qs = EmissionRecord.objects.filter(tenant=tenant)

        def scope_co2e(scope):
            result = qs.filter(scope=scope).aggregate(total=Sum("co2e_kg"))["total"]
            return float(result or 0)

        def scope_count(scope):
            return qs.filter(scope=scope).count()

        total_co2e = float(qs.aggregate(total=Sum("co2e_kg"))["total"] or 0)

        # By source
        source_breakdown = []
        for src in ["SAP", "UTILITY", "TRAVEL"]:
            co2e = float(qs.filter(source_type=src).aggregate(t=Sum("co2e_kg"))["t"] or 0)
            count = qs.filter(source_type=src).count()
            source_breakdown.append({"source": src, "co2e_kg": co2e, "count": count})

        # By month (last 12 months)
        from django.db.models.functions import TruncMonth
        monthly = (
            qs.filter(activity_date__isnull=False)
            .annotate(month=TruncMonth("activity_date"))
            .values("month", "scope")
            .annotate(co2e=Sum("co2e_kg"))
            .order_by("month", "scope")
        )

        # Recent batches
        recent_batches = IngestionBatch.objects.filter(tenant=tenant)[:5]
        from ingestion.serializers import IngestionBatchSerializer as BS
        batches_data = BS(recent_batches, many=True).data

        return Response({
            "total_co2e_kg": total_co2e,
            "total_co2e_t": total_co2e / 1000,
            "scope_1_co2e_kg": scope_co2e(1),
            "scope_2_co2e_kg": scope_co2e(2),
            "scope_3_co2e_kg": scope_co2e(3),
            "scope_1_count":   scope_count(1),
            "scope_2_count":   scope_count(2),
            "scope_3_count":   scope_count(3),
            "pending_count":   qs.filter(status="PENDING").count(),
            "approved_count":  qs.filter(status="APPROVED").count(),
            "flagged_count":   qs.filter(status="FLAGGED").count(),
            "rejected_count":  qs.filter(status="REJECTED").count(),
            "locked_count":    qs.filter(is_locked=True).count(),
            "source_breakdown": source_breakdown,
            "monthly_trend": list(monthly.values("month", "scope", "co2e")),
            "recent_batches": batches_data,
        })
