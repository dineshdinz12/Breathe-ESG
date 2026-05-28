"""
Management command: seed_demo
Creates demo users, loads fixtures, and ingests sample data files.
Run once after initial migration.
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User
import os


class Command(BaseCommand):
    help = "Seed the database with demo data: users, fixtures, and sample ingestion files"

    def handle(self, *args, **options):
        self.stdout.write("Loading emission factor fixtures...")
        call_command("loaddata", "fixtures/emission_factors.json")
        call_command("loaddata", "fixtures/plant_codes.json")
        call_command("loaddata", "fixtures/airports.json")
        self.stdout.write(self.style.SUCCESS("Fixtures loaded."))

        # Create demo users
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@breathe-esg.demo", "admin123")
            self.stdout.write(self.style.SUCCESS("Created superuser: admin / admin123"))

        if not User.objects.filter(username="analyst").exists():
            User.objects.create_user("analyst", "analyst@breathe-esg.demo", "analyst123",
                                     first_name="Sarah", last_name="Chen")
            self.stdout.write(self.style.SUCCESS("Created analyst: analyst / analyst123"))

        # Ingest sample files
        self.stdout.write("Ingesting sample data files...")
        self._ingest_sample("sap_fuel_procurement.tsv", "SAP")
        self._ingest_sample("utility_electricity.csv", "UTILITY")
        self._ingest_sample("travel_concur_export.csv", "TRAVEL")
        self.stdout.write(self.style.SUCCESS("Demo seed complete!"))

    def _ingest_sample(self, filename, source_type):
        from core.models import Tenant, IngestionBatch
        from ingestion.parsers.sap import parse_sap_file
        from ingestion.parsers.utility import parse_utility_file
        from ingestion.parsers.travel import parse_travel_file

        sample_dir = os.path.join(os.path.dirname(__file__), "../../../../sample_data")
        filepath = os.path.join(sample_dir, filename)
        filepath = os.path.normpath(filepath)

        if not os.path.exists(filepath):
            self.stdout.write(self.style.WARNING(f"  Skipping {filename} — file not found at {filepath}"))
            return

        tenant = Tenant.objects.get(slug="acme-industries")
        admin_user = User.objects.get(username="admin")

        batch = IngestionBatch.objects.create(
            tenant=tenant,
            source_type=source_type,
            filename=filename,
            uploaded_by=admin_user,
            status="PROCESSING",
        )

        with open(filepath, "rb") as f:
            content = f.read()

        parsers = {"SAP": parse_sap_file, "UTILITY": parse_utility_file, "TRAVEL": parse_travel_file}
        rows, errors, error_log = parsers[source_type](content, batch)

        batch.status = "COMPLETE"
        batch.row_count = rows
        batch.error_count = errors
        batch.error_log = error_log[:20]
        batch.save()

        self.stdout.write(f"  {filename}: {rows} rows ingested, {errors} errors")
