# ATC Shift Swap Backend

Backend for managing monthly rosters and shift swaps between Air Traffic Controllers (ATCOs). Controllers belong to teams (A–E); each team has a default monthly schedule. Swaps change who works which shift; team membership does not change.

## What it does

- **Authentication** – JWT login; users are ATCOs identified by employee number.
- **Rosters** – Import monthly schedules from team PDFs (one PDF per team); support for current month and next month (next month often available from around day 10).
- **Shift swaps** – Create swap requests (offer a shift, optionally specify what you want: same day, or multiple options e.g. “day 7 M or T; day 8 T; day 11 T, M or MG”). Direct swap (two people, same or different days) and multi-person cycles (e.g. A→B→C→A) with confirmation from everyone involved.
- **Rules** – Only T and Mt cannot have N the next day; max 9 consecutive working days; DC/DS (rest days) are tradable under the same rules. Swap logic still considers tradable shift families (M/T/N/Mt/MG/DC/DS), while parser/import can store additional roster markers (e.g. `mE`, `AF`, `IB`, future codes) to keep calendar consistency.
- **History** – Swap history is kept; list with GET `/swap-requests/history`, clear/archive with DELETE `/swap-requests/history?before=YYYY-MM-DD`.
- **Notifications** – When a same-day swap request is created, users who can satisfy it (and respect rules: only T and Mt cannot have N the next day; max 9 consecutive working days) receive an in-app notification. Users can disable notifications via PATCH `/users/me` (`notifications_enabled: false`). List: GET `/notifications/`, mark read: PATCH `/notifications/{id}/read`.
- **Rejecting a swap** – For **same-day** and **other-days** (broadcast) requests, one colleague rejecting does **not** close the request; others can still accept. For **direct** swaps, only listed users can accept: the request closes when **all** direct targets have rejected (the usual case is a single target — one reject closes the request).
- **Import guardrails** – Parser accepts short alphanumeric shift codes from PDFs (case-sensitive, e.g. `MT` vs `Mt`), skips rows from the section **"Em qualificação"**, and importer merges per user/day avoiding overwrite of concrete shifts by low-priority team-change markers (`mE`/`AF`).
- **Colors & inconsistencies** – PDF import reads cell colors per shift and stores a `color_bucket` (e.g. red, yellow, pink, gray_light, gray_dark, lime). Red = BHT; yellow = trabalho suplementar/extraordinário; pink = extra/troca; lime = férias/ausência. On Friday re-imports, shifts whose accepted swaps are not yet reflected in the new PDFs are marked with `inconsistency_flag` and an `inconsistency_message` so the user can see a warning flag in the UI.
- **Manual roster fix** – Authenticated users can correct their own shifts with `PATCH /shifts/{shift_id}` (`codigo` required; optional `color_bucket`, `origin_status`). Blocked if an OPEN swap exists for that shift. Clears inconsistency flags. The web UI exposes this as “Editar a minha escala” when the employee number matches the logged-in user.

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

### Ambiente local vs beta online

- **Local (desenvolvimento / debug):** copia `backend_min/.env.example` para `backend_min/.env` e ajusta; por defeito usa SQLite (`test.db`). No frontend, copia `frontend/frontend/.env.example` para `.env.development` ou `.env.local` e define `VITE_API_URL=http://127.0.0.1:8000` se quiseres forçar a API (senão o browser usa o mesmo hostname com porta 8000).
- **Beta online (testes com utilizadores):** no **host da API** (Render, Railway, VPS, …) define `DATABASE_URL` (PostgreSQL), `SECRET_KEY`, `FRONTEND_URL` (URL exata do site, para CORS) e, se precisares de mais domínios, `CORS_EXTRA_ORIGINS` (lista separada por vírgulas). No **build do frontend** (Vercel, Netlify, …) define `VITE_API_URL` com o URL público da API **antes** de `npm run build` (variáveis `VITE_*` são injetadas em tempo de build).
- Ficheiros `.env` locais não são commitados; os `.env.example` servem de modelo.

### Ver no telemóvel (mesma rede Wi‑Fi)

Para aceder ao frontend no telemóvel, o backend tem de aceitar ligações da rede local:

```bash
uvicorn main:app --reload --host 0.0.0.0
```

No frontend, arranca com `npm run dev:host` (em vez de `npm run dev`). Descobre o IP do PC na rede (em Windows: `ipconfig`, em Mac/Linux: `ip addr` ou `ifconfig`) e no browser do telemóvel abre `http://<IP_DO_PC>:5173` (ex.: `http://192.168.1.5:5173`).

### Colocar a funcionar para outros testarem (mesma rede)

Para que outras pessoas (no mesmo Wi‑Fi) possam abrir a app e testar no browser delas:

1. **No PC onde corre o projeto** (backend + frontend):
   - **Backend:** na pasta `backend_min`, com o venv ativado:
     ```bash
     uvicorn main:app --reload --host 0.0.0.0
     ```
     (O `--host 0.0.0.0` faz o servidor aceitar ligações de outros dispositivos na rede.)
   - **Frontend:** na pasta `frontend/frontend`:
     ```bash
     npm run dev:host
     ```
     (O `--host` faz o Vite expor a app na rede, não só em localhost.)

2. **Descobrir o IP do teu PC na rede:**
   - **Windows:** abre uma consola e corre `ipconfig`; procura "Endereço IPv4" da interface Wi‑Fi (ex.: `192.168.1.5`).
   - **Mac/Linux:** `ifconfig` ou `ip addr`; usa o IP da interface `en0`/`wlan0` (ex.: `192.168.1.5`).

3. **O que partilhar com quem vai testar:**
   - URL da app: `http://<TEU_IP>:5173` (ex.: `http://192.168.1.5:5173`).
   - Quem abrir esse link no browser (PC ou telemóvel, na mesma rede) vê a aplicação; as chamadas à API vão automaticamente para `http://<TEU_IP>:8000`.

4. **Requisitos para os testadores:**
   - Estarem na **mesma rede Wi‑Fi** que o teu PC.
   - Terem um browser (Chrome, Edge, Safari, etc.).
   - Para **login/notificações**: precisam de um número de funcionário que exista na base de dados (criada ao importar os PDFs). Sem login conseguem ver escalas e "Quem está de serviço"; com login conseguem trocar turnos e ver notificações.

5. **Pastas dos PDF (opcional):** Se quiseres que o botão "Importar escalas" funcione nesse PC, as pastas dos PDF têm de existir. Por defeito o backend usa:
   - `C:/PARSER_ESCALAS/PDF_Escalas/atual`
   - `C:/PARSER_ESCALAS/PDF_Escalas/seguinte`
   Podes alterar com variáveis de ambiente `PDF_FOLDER_ATUAL` e `PDF_FOLDER_SEGUINTE` antes de correr o uvicorn.

### Limpar escalas (import “limpo” após testes com dados dummy)

Para apagar **todas** as escalas importadas e dados de trocas ligados a turnos (notificações, histórico, pedidos, etc.), mantendo **utilizadores e equipas**:

- **API:** `POST /import/clear-schedules` com JSON `{"confirm": "APAGAR_TODAS_AS_ESCALAS"}`.
- Opcional em produção: define `CLEAR_SCHEDULES_SECRET` e envia o mesmo valor no header `X-Clear-Schedules-Secret`.
- Na UI local (localhost), junto a “Importar escalas”, existe o botão **“Limpar escalas (BD)”** com confirmação em duas etapas.

## Tests

Automated tests live in `tests/` and use an in-memory database (no real DB needed):

```bash
pytest tests/ -v
```

## Development

- **sample_pdfs/** – Folder for reference PDFs (e.g. to tune yellow/trabalho suplementar detection). Ignored by git (see `.gitignore`).

## Documentation

- **DEPLOY_PASSO_A_PASSO.md** – Tutorial detalhado Render + Vercel (fases A–H, tabela de campos, problemas comuns).
- **CHECKLIST_DEPLOY.md** – Lista numerada para seguir até à beta online (PostgreSQL, Web Service, env, PDF, import, Vercel, CORS).
- **DEPLOY_BETA_LIMPO.md** – Beta online: limpar escalas/trocas e importar PDF atuais; secção **Render.com** (disco `/var/data/pdf_escalas`, variáveis, Shell). `render.yaml.example` — blueprint com disco persistente.
- **Scripts:** `scripts/beta-clear-and-import.ps1`, `scripts/render-mkdir-pdf-dirs.sh`.
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

- **Manual edit (own shifts only, JWT)**
  - `PATCH /shifts/{shift_id}` – body: `{ "codigo": "…", "color_bucket"?: "gray_light"|…, "origin_status"?: "rota"|… }`. Omitting bucket/origin applies defaults (e.g. DC/DS → dark gray; else light gray; origin `rota`).

- **Swap history**
  - `GET /swap-requests/history` – list accepted swaps (with optional `limit` and `before`).
  - `DELETE /swap-requests/history?before=YYYY-MM-DD` – clear/archive older history.

## Important rules

- One shift per user per day.
- No swaps for past shifts.
- No accepting your own swap.
- Several OPEN swap requests may reference the same offered shift (parallel options); accepting one closes the others for that shift.
- All swaps require confirmation from every party involved.
- Swap execution is transactional (all or nothing).
