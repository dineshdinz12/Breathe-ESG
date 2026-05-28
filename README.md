# Breathe ESG — Emissions Ingestion & Review Platform

A Django + React prototype for ingesting, normalising, and reviewing corporate emissions data from SAP, utility portals, and corporate travel systems.

## Live Demo

> **URL:** [deployed link here]  
> **Login:** `admin` / `admin123` · `analyst` / `analyst123`

## Quick Start (Local)

```bash
# Backend
cd backend
python -m venv ../venv && source ../venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Documentation

| File | Contents |
|------|----------|
| [MODEL.md](MODEL.md) | Data model, entity relationships, design decisions |
| [DECISIONS.md](DECISIONS.md) | Every ambiguity resolved and why |
| [TRADEOFFS.md](TRADEOFFS.md) | Three things not built and why |
| [SOURCES.md](SOURCES.md) | Real-world format research for each source |

## Architecture

```
frontend/          React + Vite SPA
backend/
  core/            Data models (EmissionRecord, EmissionFactor, Tenant, ...)
  ingestion/       Upload API + parsers (SAP, Utility, Travel)
  review/          Review queue API (approve, flag, reject, lock)
  breathe_esg/     Django project settings
sample_data/       Realistic demo files for all three sources
```

## Sources Handled

| Source | Format | Scope |
|--------|--------|-------|
| SAP Fuel & Procurement | Tab-delimited SE16N export | Scope 1 |
| Utility Electricity | Portal CSV (Green Button-style) | Scope 2 |
| Corporate Travel | Concur-style CSV export | Scope 3 |
