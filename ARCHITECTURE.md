# Architecture

High-level structure of the ATC Shift Swap backend.

## Layers

| Layer      | Location        | Role |
|-----------|-----------------|------|
| **API**   | `routers/*.py`  | HTTP endpoints: teams, users, schedules, shifts, swap-requests, import, dev. |
| **Models**| `models.py`     | SQLAlchemy: Team, User, MonthlySchedule, Shift, ShiftType, SwapRequest, SwapPreference, CycleProposal, CycleSwap, CycleConfirmation. |
| **Schemas**| `schemas/*.py`  | Pydantic request/response (e.g. SwapCreate, SwapRead). |
| **Security** | `security.py` | JWT, password hashing, `get_current_user`. |
| **Rules**  | `rules/shift_rules.py` | Operational rules: forbidden next-day pairs (T→N, Mt→N), max 9 consecutive working days. |
| **Services** | `services/swap_engine.py` | Cycle detection (2..N users, same-day and cross-day, using wanted options). |
| **Parsers** | `parsers/*.py`  | PDF parsing: extract controller id, date, shift code and cell color per team roster. |
| **Database** | `database.py`  | Engine, session, `get_db`. |

## Main flows

### Import

- **Endpoint:** `POST /import/schedules`.
- **Input:** Reads from configured PDF folders (current month and next month). Expects one PDF per team (e.g. A, B, C, D, E); file names may be inconsistent; team/month may need to be read from PDF content.
- **Behaviour:** Creates/updates Team, User (by employee number), MonthlySchedule (team + month), Shift. Same employee number can appear in two teams in the same month (e.g. A then leave then D); all shifts attach to the same User.
- **Output:** Should report how many teams were processed; if fewer than 5, warn so the user can check files or parser.
- **Friday updates:** When re-importing updated PDFs, shifts that are part of an accepted swap but not yet reflected in the PDF are kept as-is and marked on the corresponding `Shift` row with `inconsistency_flag` and `inconsistency_message` so the user can reconcile (e.g. “Confirm with scheduling office”).

### Direct swap

1. User creates a swap request (offered shift; optional: acceptable shift types or “wanted” options for future: multiple days + accepted types).
2. Another user accepts (same-day swap: acceptor must have a shift on that day).
3. System validates: OPEN, not self-accept, same-day shift exists, preferences, T→N/Mt→N, max 9 days.
4. In one transaction: swap `Shift.user_id` for the two shifts, set `accepter_id`, set status ACCEPTED.

### Cycle (3 or more users, same or different days)

1. Requests express “offer shift X” and “want shift (or day/type options)”.
2. Engine builds a directed graph and detects cycles (to be extended beyond 3-way same-day).
3. System proposes cycle → all involved users must confirm.
4. Before execution: simulate result, validate (one shift per day per user, no T→N/Mt→N, max 9 days), then execute atomically or reject with reason.

## Data highlights

- **Shift:** `user_id`, `data`, `codigo` (M/T/N/Mt/MG/DC/DS), `shift_type_id`, `schedule_id`. Unique `(user_id, data)`.
- **SwapRequest:** `shift_id` (offered), `requester_id`, `accepter_id`, `status`. “Wanted” will be extended (e.g. wanted_shift_id or list of (date, accepted types)).
- **User:** one `team_id` (base team); shifts can come from different MonthlySchedules (different teams) in the same month.

## Tests

- **Location:** `tests/`.
- **Convention:** Tests use an in-memory SQLite DB (override `get_db`) so no real database is required. Example: `tests/test_swap.py` runs a full swap flow (team, users, schedule, shifts, create swap, accept, assert ownership).
