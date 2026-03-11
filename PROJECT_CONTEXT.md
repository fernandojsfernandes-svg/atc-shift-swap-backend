# ATC Shift Swap Backend – Project Context

## Purpose

Backend for managing rosters and shift swaps between Air Traffic Controllers (ATCOs). Supports authentication, roster import from PDFs, swap requests (direct and multi-person cycles), and enforcement of operational rules.

## Domain rules (agreed with product)

### Teams and rosters

- Controllers belong to a base operational team (A–E). Each team has a default monthly roster.
- Swap results in a controller working a shift originally assigned to another team; **team membership does not change**.
- Rosters are organised by team (one PDF per team). Five teams ⇒ five PDFs per month.
- The next month’s roster may be available from around day 10 of the current month ⇒ system may hold two months of schedules.
- Every Friday the scheduling office may send updated rosters; these must be processable (re-import). When a swap was agreed on Friday but not yet in the new PDF, the system keeps the swapped assignment and marks it with an inconsistency warning so the user can confirm with the scheduling office.

### Shift codes

- **Tradable:** M, T, N, Mt, MG (work), DC, DS (rest). Only these participate in swaps.
- **Not tradable:** Holidays, leave, travel, etc. — no swap logic applies.

### Operational rules

- **Forbidden next-day sequences:** T→N, Mt→N (user must be warned / confirm before approving).
- **Max consecutive working days:** 9. DC/DS count as non-working; same rule applies when swapping rest days.
- More restrictions may be added later (e.g. other conflicting shift types).

### Swaps in practice

- **~90% same-day**; system must also support **3-way swaps** and **cross-day swaps**.
- **Two situations:**  
  1. **Direct proposal** – User has already agreed with a colleague; proposes in the app; colleague must confirm.  
  2. **Open request** – User offers a shift (e.g. M on day 5) and states multiple options for what they want, e.g. day 7 (M or T), day 8 (T), day 11 (T, M or MG). System can then suggest matches or cycles.
- **All swaps require confirmation from everyone involved** (no “record only” without confirmation).
- **History:** Keep a swap history; may be cleared or archived each month.

### Import and PDFs

- PDF folder(s) are configurable; user places current-month and next-month PDFs there.
- File names may be inconsistent; team and month might need to be read from PDF content. After import, report how many teams were processed; if not 5, warn.
- **Controller identity:** Employee number in the PDF uniquely identifies the controller. Same number in two team PDFs in the same month (e.g. team change mid-month) ⇒ same user, shifts in different team schedules.

## Tech stack

- FastAPI, SQLAlchemy, SQLite (dev), JWT auth, Uvicorn.

## Current status

- **Done:** Auth, teams, users, monthly schedules, shifts, swap request create/accept (same-day direct), preferences (partially: schema exists, persistence on create to be fixed), T→N/Mt→N and 9-day checks on accept, cycle proposal/confirm (with duplicate route bug to fix), 3-way same-day cycle detection.
- **To do / improve:** Persist swap preferences on create; remove duplicate routes in swaps router; validate cycles before execute (simulate → validate → execute); extend “wanted” to multiple days and types; extend cycle detection to cross-day and N-way; import: configurable folders, team count warning, Friday reconciliation with inconsistency flag; swap history and optional monthly cleanup; README/ARCHITECTURE already updated.

## Documentation updates

README, ARCHITECTURE, SWAP_ENGINE_RULES, and PROJECT_CONTEXT may be updated by the development process. The user is notified when these files are changed.
