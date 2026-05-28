# Decisions — Breathe ESG

Every ambiguity I resolved, what I chose, and why.

---

## 1. SAP ingestion mechanism: flat file export (SE16N/SQVI), not IDoc or OData

**The choice:** Tab-delimited flat file, exported from SAP SE16N or SQVI by a sustainability lead.

**Why:** I researched four real SAP integration paths:

| Method | What it is | Why rejected |
|--------|-----------|--------------|
| IDoc | SAP's native EDI message format | Requires SAP middleware (ALE/XI/PI). Weeks of SAP Basis involvement. Not realistic for a prototype onboarding. |
| OData (SAP Gateway) | REST-like API over SAP objects | Requires SAP Gateway configuration, client IT involvement, custom service activation. |
| BAPI | Remote function call | Requires RFC connection, credentials, SAP Basis. |
| SE16N flat file | GUI table browser → export to clipboard/file | Any SAP user with read access can do this today. No IT involvement. |

The SE16N export is the path of least resistance for nearly every enterprise client. Sustainability leads do this routinely. The cost is that column headers vary by locale and SAP version (English vs German), which the parser handles explicitly.

**What I'd ask the PM:** "Does the client have a dedicated SAP developer available? If so, we could set up a scheduled OData pull instead of manual exports. That would eliminate the upload step entirely."

---

## 2. Which SAP tables/fields to handle

**The choice:** EKKO (purchase order header) + EKPO (purchase order item) join, keyed on EBELN/EBELP. Fields: PO number, item, material description (MAKTX), plant (WERKS), document date (BEDAT), quantity (MENGE), unit (MEINS).

**Why:** Fuel and energy procurement lives in purchasing (MM module). The SE16N join on EKKO+EKPO gives exactly the procurement lines we need. I deliberately excluded:

- MARA (material master) — would give material group codes for more precise fuel classification, but requires a separate export. The parser falls back to keyword matching on MAKTX.
- MSEG (goods movements) — actual stock postings, more accurate than PO quantities but harder to export and align.

**What I ignored:** Procurement of non-energy materials (office supplies, raw materials). The parser infers fuel type from MAKTX description; rows that don't match known fuel keywords are flagged for analyst review rather than silently dropped.

---

## 3. Utility data: portal CSV export, not Green Button API or PDF

**The choice:** CSV export from a utility portal.

**Why:**
- **Green Button Connect (API):** Most enterprise utilities offer this, but it requires utility-specific OAuth2 registration, a client ID per utility, and often a 2–4 week provisioning process. Not feasible for a prototype.
- **PDF bills:** Require OCR or structured PDF parsing. High error rate, no standard format. Would dominate implementation time.
- **CSV export:** Every utility portal offers this. The facilities manager downloads it monthly. Format varies but column names are guessable. This is what actually lands in someone's inbox.

**What I'd ask the PM:** "Which utility providers does this client use? If they're all on a major platform (e.g. EDF, National Grid, SEFE), we could negotiate API access for v2. For now, CSV upload with a simple template is the right call."

---

## 4. Billing period vs calendar month for activity_date

**The choice:** Use `billing_period_end` as `activity_date`.

**Why:** Billing periods rarely align to calendar months (e.g. Dec 28 – Jan 29). ESG frameworks typically attribute consumption to the period it was delivered, not when the bill was issued. Using `period_end` is the standard practice. If only `period_start` is available, we fall back to that.

---

## 5. Corporate travel: Concur CSV export, not live API

**The choice:** CSV export from Concur (or Navan/equivalent TMS).

**Why:** I read the Concur Travel & Expense API docs. The API requires OAuth2 client credentials registered with the client's IT and Concur's support team — typically a 3–6 week process. The CSV export ("Standard Accounting Extract" or a custom report) is available to any expense manager today. Every Concur user can export this with no IT involvement.

---

## 6. Flight distance calculation: haversine from IATA codes

**The choice:** Look up origin/destination IATA codes → lat/lon → haversine great-circle distance → 8% routing uplift.

**Why:** Concur often provides only the route (`LHR → JFK`), not the actual distance. DEFRA 2023 guidance recommends the distance-based method with uplift for non-direct routing. The 8% figure is from DEFRA's own technical annex.

**Alternative considered:** Using Concur's distance field directly when present. The parser does use this if `DISTANCE_KM` is provided, converting from miles if needed.

---

## 7. Radiative forcing (RF) multiplier for flights

**The choice:** Apply RF = 1.891 (DEFRA 2023) to all flight CO2e calculations.

**Why:** Aviation's non-CO2 effects (NOx, contrails, water vapour at altitude) roughly double the climate impact compared to CO2 alone. DEFRA includes RF; the EPA does not. GHG Protocol guidance recommends including it for comprehensive Scope 3 reporting. I chose to include it and flag it in the record so analysts can see which methodology was used. A client using EPA factors would need to strip RF.

---

## 8. Flight categorisation: domestic / short-haul / long-haul

**The choice:** DEFRA 2023 distance bands: <483 km = domestic, 483–3700 km = short-haul, >3700 km = long-haul.

**Why:** DEFRA publishes separate emission factors per band per cabin class. These thresholds match DEFRA's own published methodology. Each band has a meaningfully different CO2e per pkm.

---

## 9. Cabin class weighting for flights

**The choice:** Economy 1.0×, Premium Economy 1.6×, Business 2.9×, First 4.0× (DEFRA 2023).

**Why:** Business class seats occupy more physical space on an aircraft, so more of the aircraft's total emissions are attributed to each seat. DEFRA's multipliers are the industry standard for passenger-km allocation. If cabin class is missing, we default to economy (conservative) and flag the record.

---

## 10. Grid emission factor selection for electricity

**The choice:** Select factor by country code inferred from service address. Default to UK grid if unknown.

**Why:** Grid emission intensity varies significantly by country (UK ~0.207 kg/kWh, France ~0.052 kg/kWh due to nuclear). Using a global average would be meaningfully wrong. The parser infers country from the service address field or an explicit `COUNTRY` column.

**What I'd ask the PM:** "Does the client have any renewable energy contracts (PPAs, RECs)? If so, the market-based method may apply and could significantly lower their Scope 2 figures. The parser flags green tariff codes for analyst review."

---

## 11. Location-based vs market-based Scope 2

**The choice:** Calculate location-based by default. Flag rows with green tariff codes.

**Why:** GHG Protocol requires companies to report both methods if they have contractual instruments. Location-based is always calculable (just needs grid factor). Market-based requires tracking RECs/PPA details. For a prototype, we calculate location-based and flag potential market-based overrides for the analyst to handle manually.

---

## 12. Approval workflow: PENDING → APPROVED → locked

**The choice:** Three-step workflow. Parser sets PENDING or FLAGGED. Analyst approves/rejects/flags. Batch lock is a separate operation.

**Why:** Auditors need to see that each record was reviewed by a named person at a specific time. The lock step is deliberately separate from approval — an analyst can approve records over time, and only lock the batch when everything is resolved. Locking requires zero pending or flagged records.

---

## 13. Authentication: Django session auth, not JWT

**The choice:** Django's built-in session authentication via cookie.

**Why:** This is an internal analyst tool, not a public-facing API. Session auth is simpler, more secure (no token storage in localStorage), and trivially supported by Django's auth system. JWT would add complexity (token refresh, revocation) with no benefit for this use case.

---

## What I'd ask the PM

1. Is there a real SAP developer available? Could we do a scheduled OData pull?
2. Which utility providers? Are API integrations feasible post-prototype?
3. Does the client have renewable energy contracts affecting Scope 2?
4. Should we report location-based only or both methods?
5. What reporting framework is the audit for — GHG Protocol, ISO 14064, TCFD?
6. Do analysts need role-based permissions (some can flag, only senior can approve)?
