# ATC Shift Swap Backend

Backend for managing monthly rosters and shift swaps between Air Traffic Controllers (ATCOs). Controllers belong to teams (A–E); each team has a default monthly schedule. Swaps change who works which shift; team membership does not change.

## What it does

- **Authentication** – JWT login; users are ATCOs identified by employee number.
- **Rosters** – Import monthly schedules from team PDFs (one PDF per team); support for current month and next month (next month often available from around day 10).
- **Shift swaps** – Create swap requests (offer a shift, optionally specify what you want: same day, or multiple options e.g. “day 7 M or T; day 8 T; day 11 T, M or MG”). Direct swap (two people, same or different days) and multi-person cycles (e.g. A→B→C→A) with confirmation from everyone involved.
- **Rules** – Only T and Mt cannot have N the next day; max 9 consecutive working days; DC/DS (rest days) are tradable under the same rules. Only M, T, N, Mt, MG, DC, DS participate in swaps; holidays, leave, travel, etc. do not.
- **History** – Swap history is kept; list with GET `/swap-requests/history`, clear/archive with DELETE `/swap-requests/history?before=YYYY-MM-DD`.
- **Notifications** – When a same-day swap request is created, users who can satisfy it (and respect rules: only T and Mt cannot have N the next day; max 9 consecutive working days) receive an in-app notification. Users can disable notifications via PATCH `/users/me` (`notifications_enabled: false`). List: GET `/notifications/`, mark read: PATCH `/notifications/{id}/read`.
- **Colors & inconsistencies** – PDF import reads cell colors per shift and stores a `color_bucket` (e.g. red, yellow, pink, gray_light, gray_dark, lime). Red = BHT; yellow = trabalho suplementar/extraordinário; pink = extra/troca; lime = férias/ausência. On Friday re-imports, shifts whose accepted swaps are not yet reflected in the new PDFs are marked with `inconsistency_flag` and an `inconsistency_message` so the user can see a warning flag in the UI.

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

### Ver no telemóvel (mesma rede Wi‑Fi)

Para aceder ao frontend no telemóvel, o backend tem de aceitar ligações da rede local:

```bash
uvicorn main:app --reload --host 0.0.0.0
```

No frontend, arranca com `npm run dev:host` (em vez de `npm run dev`). Descobre o IP do PC na rede (em Windows: `ipconfig`, em Mac/Linux: `ip addr` ou `ifconfig`) e no browser do telemóvel abre `http://<IP_DO_PC>:5173` (ex.: `http://192.168.1.5:5173`).

## Tests

Automated tests live in `tests/` and use an in-memory database (no real DB needed):

```bash
pytest tests/ -v
```

## Development

- **sample_pdfs/** – Folder for reference PDFs (e.g. to tune yellow/trabalho suplementar detection). Ignored by git (see `.gitignore`).

## Documentation

- **PROJECT_CONTEXT.md** – Product context, domain rules, current status and roadmap.
- **ARCHITECTURE.md** – Code layout, layers, data flow.
- **SWAP_ENGINE_RULES.md** – Rules for detecting and executing swaps.
- **PDF_IMPORT_PROCESS.md** – How roster PDFs are imported (teams, months, folders).

## Key API endpoints (for frontend)

- **Import rosters**
  - `POST /import/schedules` – scan configured folders, parse PDFs, create/update teams, users, schedules and shifts; on re-import, mark inconsistent shifts using swap history.

- **Schedules**
  - `GET /schedules/{team_code}/{year}/{month}` – full month schedule for a team (list of shifts with `data`, `codigo`, `color_bucket`, `inconsistency_flag`, `inconsistency_message`).

- **User view**
  - `GET /users/{employee_number}/shifts/{year}/{month}` – all shifts for a controller in a given month (same fields as above).

- **Swap history**
  - `GET /swap-requests/history` – list accepted swaps (with optional `limit` and `before`).
  - `DELETE /swap-requests/history?before=YYYY-MM-DD` – clear/archive older history.

## Important rules

- One shift per user per day.
- No swaps for past shifts.
- No accepting your own swap.
- At most one OPEN swap per shift.
- All swaps require confirmation from every party involved.
- Swap execution is transactional (all or nothing).
