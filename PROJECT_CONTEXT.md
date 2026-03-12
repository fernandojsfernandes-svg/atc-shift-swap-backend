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

- **Done:**
  - Auth, teams, users, monthly schedules, shifts.
  - Swap request create/accept (same-day direct) com:
    - preferências (`acceptable_shift_types`) gravadas em `SwapPreference`,
    - `wanted_options` em vários dias/tipos gravadas em `SwapWantedOption`,
    - validação T→N/Mt→N e máximo 9 dias na aceitação e em ciclos.
  - Ciclos:
    - proposta/confirm (`CycleProposal`, `CycleSwap`, `CycleConfirmation`),
    - deteção de ciclos 2..N, incluindo cross-day, com base em `wanted_options`,
    - execução transacional com validação prévia (simulação).
  - Import:
    - pastas configuráveis por env (`PDF_FOLDER_ATUAL`/`SEGUINTE`),
    - aviso se menos de 5 equipas processadas,
    - parser de PDF com deteção de cor da célula (`color_bucket`) por turno.
  - Histórico:
    - `SwapHistory` gravado em swaps simples e em ciclos,
    - endpoints `GET /swap-requests/history` e `DELETE /swap-requests/history?before=YYYY-MM-DD`.
  - Re-import de sextas:
    - após novo `POST /import/schedules`, marca em `Shift` os turnos incoerentes com o histórico de trocas (`inconsistency_flag`/`inconsistency_message`).
  - API de leitura para frontend:
    - `GET /schedules/{team_code}/{year}/{month}` (escala da equipa),
    - `GET /users/{employee_number}/shifts/{year}/{month}` (escala pessoal).

- **To do / improve:**
  - Afinar a semântica das cores (significado de cada `color_bucket`) assim que a legenda estiver fechada.
  - Eventuais filtros adicionais (por utilizador/equipa) nos históricos e endpoints.
  - Mais testes automatizados específicos para import real de PDFs e reconciliação de sexta-feira.

## Documentation updates

README, ARCHITECTURE, SWAP_ENGINE_RULES, and PROJECT_CONTEXT may be updated by the development process. The user is notified when these files are changed.
