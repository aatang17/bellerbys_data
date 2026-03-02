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

## To update this file periodically

- After a significant change: add a bullet under **Recent changes** (and the date if you like).
- When you discover a useful way to brief the AI: add it under **How to prompt the AI**.
- If you change stack, hosting, or main workflows: update **What this project is** and **Key files**.
