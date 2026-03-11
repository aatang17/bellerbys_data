# Bellerbys – Project notes

**Update this file periodically** so the AI (and you) have context when you return. Add new bullets under "Recent changes" and "How to prompt the AI" as you go.

---

## What this project is

- **Bellerbys Progression Status** – Web app for staff to upload university offer letters (PDF/images), view students, grades, and progression. Data in SQLite (`offers.db`) and grades from an Excel file.
- **Stack:** FastAPI (Python), SQLite, Excel, Gemini for PDF/image extraction, Tesseract for OCR. Front end: single `static/index.html` (vanilla JS, Tailwind).
- **Users:** School staff in different locations; everyone should access the same data (shared platform).

---

## Key files

| File | Purpose |
|------|--------|
| `app.py` | Backend: upload, grades import, API for pathway/analytics/students |
| `static/index.html` | Full front end (tabs, tables, upload, Students with expandable offers) |
| `grades_loader.py` | Load cohort and grades from Excel; Business Mgmt Maths vs Economics logic |
| `db.py` | SQLite helpers |
| `offers.db` | SQLite DB (offers, student_grades); override with `BELLERBYS_DB` |
| Default Excel | `BNBU SAPM - Semester 1 Grades_v2.xlsx` (override with `BELLERBYS_GRADES_EXCEL`) |

---

## UI convention: collapsible tabs

- **New tabs that show a list of items** (e.g. Universities) should use **collapsible sections** for consistency:
  - Use `<details>` and `<summary>` for each item.
  - Add a shared class (e.g. `js-collapsible-*`) so "Expand all" / "Collapse all" can target them.
  - See the Universities tab in `static/index.html`: convention comment in the main content block, and `renderUniversities()` with `expandAllUniversities()` / `collapseAllUniversities()`.

---

## Recent changes (add here when you make updates)

- **Tabs:** Business Mgmt, Media, Computing tabs are **hidden** by default. Toggle in `static/index.html`: set `SHOW_PATHWAY_TABS = true` to show them again. Default tab on load is Analytics.
- **Students tab:** Each offer row has a **Conditions** column (right side); click to expand/collapse **Subject conditions** and **English conditions** for that offer.
- **Sharing:** Staff don’t need GitHub. Best option: one person runs the app and shares a link (e.g. ngrok). Alternative: send folder + `INSTRUCTIONS_FOR_NON_TECHNICAL_USERS.txt`; they use RUN.command / RUN.bat.
- **Hosting:** For staff in different locations, cloud hosting (e.g. Alibaba Cloud ECS) is the right fit. See README for Alicloud steps (no custom domain; use ECS public IP and port 8000).

---

## How to prompt the AI when you return

Copy-paste or adapt these when starting a new chat so the AI has context:

- *“This is the Bellerbys progression app (FastAPI + SQLite + Excel). See PROJECT_NOTES.md and README.md for context.”*
- *“Pathway tabs (Business Mgmt, Media, Computing) are hidden by default; the flag is SHOW_PATHWAY_TABS in static/index.html.”*
- *“Students tab: offers have a collapsible Conditions column (Subject / English conditions) on the right.”*
- *“We want all staff to access the same data; we’re considering/using cloud (e.g. Alibaba Cloud) because staff are in different locations.”*
- *“Non-technical users should not need GitHub; sharing is via a link or the folder + INSTRUCTIONS_FOR_NON_TECHNICAL_USERS.txt.”*

---

## Known issues / Data corrections

- **Iris Yang vs Iris Chen (different people):** Student **51111798** is **Iris Yang**; **51111738** is **Iris Chen**. Offers are matched by the `student_name` stored in the DB (normalized). If offers were stored as just "Iris", they could attach to the wrong person. **Intended state:** Iris Yang (51111798) should have the correct offers; Iris Chen (51111738) should show **no offers** (blank). Fix: ensure each offer’s `student_name` in the DB matches the Excel name for the correct student (e.g. "Iris Yang" for Yang’s offers). Use the Analytics tab → Recent offers → **Fix name** to set the stored name to the exact Excel name, or run a one-off DB update to set offers from "Iris" to "Iris Yang" so they attach to Yang and Chen is blank.
- **Student numbers / duplicate names:** The app now ensures **unique display names** per student. If the Excel has two students with the same name (e.g. both "Iris"), the loader disambiguates using First + Last (e.g. "Iris Yang", "Iris Chen") so each person gets the correct offers. Analytics counts **every student row** (by student_code), not by name, so two Irises are never collapsed into one in totals or missing-offer lists.
- **Count by unique ID:** Offers can store **student_code** (from upload filename, e.g. `51111798-Iris_Yang-RMIT.pdf`). Matching uses student_code first, then falls back to name. Analytics and the Students tab count and attribute offers by **unique student_code**, so each student (ID) is counted once and gets only their own offers.

---

## To update this file periodically

- After a significant change: add a bullet under **Recent changes** (and the date if you like).
- When you discover a useful way to brief the AI: add it under **How to prompt the AI**.
- If you change stack, hosting, or main workflows: update **What this project is** and **Key files**.
