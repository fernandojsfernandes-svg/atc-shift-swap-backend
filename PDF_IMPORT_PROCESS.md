# PDF Schedule Import Process

The system obtains controller schedules from monthly roster PDF files.

Each operational team has its own roster document.

There are five teams in total:

Team A
Team B
Team C
Team D
Team E

Each team roster is distributed as a separate PDF file.

---

# Import Workflow

1. Five roster PDF files are provided (one per team).
2. Each PDF contains the monthly schedule for all controllers in that team.
3. The parser extracts shift assignments for each controller.
4. The extracted data is normalized.
5. Shift records are stored in the database.

The swap engine uses this data as the base schedule for all swap operations.

---

# Extracted Data

From each PDF the parser identifies:

• Controller identifier
• Date
• Assigned shift type
• Cell background color (stored as `color_bucket`: red/BHT, yellow/trabalho suplementar, pink/extra, gray_light, gray_dark, lime/férias)

Example extracted record:

User: ATCO_01
Date: 2026-03-12
Shift: M

---

# Team-Based Rosters

The rosters are organized by operational team rather than by shift type.

Each team PDF contains the full monthly schedule for all controllers in that team.

Example structure:

Team A roster
Controller 1 → shifts for entire month
Controller 2 → shifts for entire month
Controller 3 → shifts for entire month

---

# Availability of Future Rosters

The roster for the following month may become available from day 10 of the current month.

Example:

On March 10, the roster for April may be imported.

At this moment the system may contain schedules for both March and April.

---

# Swap Time Horizon

Because the next month's roster may be available before the current month ends, controllers may request swaps across two months.

However, swaps are limited to the shifts present in the imported rosters.

This means the system normally allows swaps within a **maximum horizon of two months**.

---

# Purpose

The goal of the parser is to convert the team-based roster PDFs into structured database records.

Once imported, this data becomes the base schedule used by the swap engine to validate and execute shift swaps.

---

# Importing into production (Render)

**Nota:** Antes do deploy online, a aplicação funcionava corretamente em localhost (SQLite + PDFs locais). Em produção, o objetivo é manter o mesmo comportamento: os mesmos PDFs e o mesmo parser são usados; a única diferença é que a base de dados é a do Render. Por isso o import deve ser executado **no teu PC** (com `DATABASE_URL` apontando ao PostgreSQL do Render), usando as mesmas pastas de PDFs que já usavas em local.

The Render backend has no access to your local PDF folders. To populate the **production database** (used by the Vercel site), run the import **from your PC** against the Render PostgreSQL database.

## One-time setup

1. **Create a `.env` file** in the backend root (`backend_min/`) with:
   - `DATABASE_URL` = Render PostgreSQL **External** connection string (from Render dashboard → your PostgreSQL → Connect → External Database URL).
   - `PDF_FOLDER_ATUAL` = path to the folder with current month PDFs (e.g. `C:\PARSER_ESCALAS\PDF_Escalas\atual`).
   - `PDF_FOLDER_SEGUINTE` = path to the folder with next month PDFs (e.g. `C:\PARSER_ESCALAS\PDF_Escalas\seguinte`).

2. **Install dependencies** (including `python-dotenv` and `psycopg2-binary`):
   ```bash
   pip install -r requirements.txt
   ```

## Run the import

1. **Start the backend locally** (reads `.env` automatically):
   ```bash
   venv\Scripts\activate
   uvicorn main:app --reload --port 8000
   ```

2. **Trigger the import** (in another terminal, or use Swagger at http://localhost:8000/docs):
   ```bash
   curl -X POST http://127.0.0.1:8000/import/schedules
   ```
   Or in PowerShell: `Invoke-RestMethod -Uri "http://127.0.0.1:8000/import/schedules" -Method Post`

3. Wait for the response (can take a few minutes). You should see `teams_processed`, `schedules_count`, and optionally a `warning` if fewer than 5 teams were found.

4. **Verify**: open the Vercel site and click “Carregar escala”; the data should appear.

Repeat this process whenever you have new PDFs (new month or updated rosters). The `.env` file is in `.gitignore` and is not deployed to Render.
