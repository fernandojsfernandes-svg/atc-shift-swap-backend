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
