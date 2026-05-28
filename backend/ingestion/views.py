from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from django.shortcuts import get_object_or_404

from core.models import IngestionBatch, EmissionRecord
from review.serializers import IngestionBatchSerializer
from ingestion.parsers.sap import parse_sap_file
from ingestion.parsers.utility import parse_utility_file
from ingestion.parsers.travel import parse_travel_file


PARSER_MAP = {
    "SAP":     parse_sap_file,
    "UTILITY": parse_utility_file,
    "TRAVEL":  parse_travel_file,
}


class IngestUploadView(APIView):
    """
    POST /api/ingest/
    Accepts a file upload + source_type and runs the appropriate parser.
    Creates an IngestionBatch and N EmissionRecords.
    """
    parser_classes = [MultiPartParser]

    def post(self, request):
        source_type = request.data.get("source_type", "").upper()
        if source_type not in PARSER_MAP:
            return Response(
                {"error": f"source_type must be one of {list(PARSER_MAP.keys())}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        # For prototype: use first tenant, or tenant from header
        from core.models import Tenant
        tenant = Tenant.objects.first()
        if not tenant:
            return Response({"error": "No tenant configured"}, status=status.HTTP_400_BAD_REQUEST)

        batch = IngestionBatch.objects.create(
            tenant=tenant,
            source_type=source_type,
            filename=uploaded_file.name,
            uploaded_by=request.user,
            status="PROCESSING",
        )

        try:
            file_content = uploaded_file.read()
            parser = PARSER_MAP[source_type]
            rows_created, error_count, error_log = parser(file_content, batch)

            batch.status = "COMPLETE"
            batch.row_count = rows_created
            batch.error_count = error_count
            batch.error_log = error_log[:50]  # store first 50 errors max
            batch.save()

            return Response(
                IngestionBatchSerializer(batch).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            batch.status = "FAILED"
            batch.error_log = [{"error": str(e)}]
            batch.save()
            return Response(
                {"error": str(e), "batch_id": batch.id},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BatchListView(generics.ListAPIView):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        from core.models import Tenant
        tenant = Tenant.objects.first()
        return IngestionBatch.objects.filter(tenant=tenant)


class BatchDetailView(generics.RetrieveAPIView):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        from core.models import Tenant
        tenant = Tenant.objects.first()
        return IngestionBatch.objects.filter(tenant=tenant)


class BatchLockView(APIView):
    """
    POST /api/batches/{id}/lock/
    Locks all APPROVED records in a batch — final step before audit submission.
    Once locked, records cannot be edited or re-approved.
    """
    def post(self, request, pk):
        from core.models import Tenant
        tenant = Tenant.objects.first()
        batch = get_object_or_404(IngestionBatch, pk=pk, tenant=tenant)

        pending = batch.records.filter(status="PENDING").count()
        flagged = batch.records.filter(status="FLAGGED").count()
        if pending > 0 or flagged > 0:
            return Response(
                {
                    "error": "Cannot lock batch with pending or flagged records",
                    "pending": pending,
                    "flagged": flagged,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        locked = batch.records.filter(status="APPROVED").update(is_locked=True)
        return Response({"locked": locked, "batch_id": pk})
