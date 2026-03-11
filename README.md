# ATC Shift Swap Backend

Backend for managing monthly rosters and shift swaps between Air Traffic Controllers (ATCOs). Controllers belong to teams (A–E); each team has a default monthly schedule. Swaps change who works which shift; team membership does not change.

## What it does

- **Authentication** – JWT login; users are ATCOs identified by employee number.
- **Rosters** – Import monthly schedules from team PDFs (one PDF per team); support for current month and next month (next month often available from around day 10).
- **Shift swaps** – Create swap requests (offer a shift, optionally specify what you want: same day, or multiple options e.g. “day 7 M or T; day 8 T; day 11 T, M or MG”). Direct swap (two people, same or different days) and multi-person cycles (e.g. A→B→C→A) with confirmation from everyone involved.
- **Rules** – No T→N or Mt→N next-day sequence; max 9 consecutive working days; DC/DS (rest days) are tradable under the same rules. Only M, T, N, Mt, MG, DC, DS participate in swaps; holidays, leave, travel, etc. do not.
- **History** – Swap history is kept; can be cleared or archived each month (to be implemented).

## Tech stack

- **Framework:** FastAPI  
- **ORM:** SQLAlchemy  
- **Database:** SQLite (development)  
- **Auth:** JWT (OAuth2 password bearer)  
- **Server:** Uvicorn  

## Running the app

```bash
# From project root, with venv activated
uvicorn main:app --reload
```

API docs: `http://127.0.0.1:8000/docs`

## Tests

Automated tests live in `tests/` and use an in-memory database (no real DB needed):

```bash
pytest tests/ -v
```

## Documentation

- **PROJECT_CONTEXT.md** – Product context, domain rules, current status and roadmap.
- **ARCHITECTURE.md** – Code layout, layers, data flow.
- **SWAP_ENGINE_RULES.md** – Rules for detecting and executing swaps.
- **PDF_IMPORT_PROCESS.md** – How roster PDFs are imported (teams, months, folders).

## Important rules

- One shift per user per day.
- No swaps for past shifts.
- No accepting your own swap.
- At most one OPEN swap per shift.
- All swaps require confirmation from every party involved.
- Swap execution is transactional (all or nothing).
