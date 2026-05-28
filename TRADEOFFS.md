# Tradeoffs — Breathe ESG

Three things deliberately not built, and why.

---

## 1. Async / background ingestion (Celery + Redis)

**What it would be:** File uploads parsed in a background task queue. The API returns immediately with a batch ID; the client polls for completion. Prevents HTTP timeouts on large files.

**Why not built:**
- The sample files are small (< 1,000 rows). Synchronous parsing completes in under a second.
- Celery adds a non-trivial deployment dependency (Redis or RabbitMQ as broker, worker processes). For a 4-day prototype this doubles the infrastructure surface area.
- The `/api/ingest/` endpoint returns synchronously with success/error in one request, which is actually the right UX for an analyst uploading a file and wanting immediate feedback.

**When to build it:** When files exceed ~5,000 rows or when upload timeouts are reported. The parser interface (`parse_*_file → (rows, errors, log)`) is already designed to be dropped into a Celery task with no changes.

---

## 2. Role-based access control (RBAC)

**What it would be:** Separate permissions for "uploader", "analyst", "senior analyst" (can approve), "audit manager" (can lock batches). Currently any authenticated user can do everything.

**Why not built:**
- The assignment spec doesn't specify roles, and adding RBAC without a defined permission matrix would be speculative.
- Django's built-in `django.contrib.auth` permission system supports this exactly — `EmissionRecord | Can approve emission record` — and could be wired up in an afternoon.
- For a prototype being evaluated by analysts, friction from access control would obscure the core functionality being reviewed.

**When to build it:** The moment a second person joins who shouldn't be able to lock batches. The data model is already multi-user (every action records `reviewed_by` and `edited_by`). Adding `@permission_required` decorators is straightforward.

---

## 3. Re-computation of CO2e when emission factors are updated

**What it would be:** When DEFRA releases a new factor version (annually), a management command or admin action re-derives `co2e_kg` for all records pointing to the updated factor, creates audit log entries noting the re-computation, and flags them for analyst re-approval.

**Why not built:**
- The data model fully supports this: `EmissionRecord.emission_factor` is a FK, so querying all records using a specific factor is one ORM call.
- The re-computation logic itself is trivial (`quantity_normalized × new_factor.co2e_per_unit`).
- The full workflow (notify analysts, require re-approval, handle locked records) is a product decision that needs PM input: do locked/audited records get re-opened? That's not a technical question.

**When to build it:** When the first real DEFRA update cycle arrives and analysts ask "do our old figures need updating?" The scaffolding is there.

---

## Honourable mentions (also not built)

| Feature | Why excluded |
|---------|-------------|
| PDF utility bill parsing | OCR is a separate domain. Parsing structured CSV is achievable and accurate; OCR on PDFs is a 2-week project. |
| Live Concur / SAP API integration | Requires OAuth registration with client's IT. Weeks-long procurement. Out of scope for a 4-day prototype. |
| Monthly trend chart on dashboard | Data model supports it (`TruncMonth` annotated query is already in the dashboard view). Excluded for time; the scope/source breakdown is more useful for an analyst doing a spot check. |
| Email notifications on flag/approve | Requires SMTP config per deployment environment. Not asked for. Easy to add via Django signals. |
