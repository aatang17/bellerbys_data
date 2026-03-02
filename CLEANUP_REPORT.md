# Bellerbys – Codebase cleanup report

## 1. Lines of code that can be deleted

### `app.py`
- **Line 29:** Remove `load_grades_excel` from the import from `grades_loader`.
  - **Reason:** `app.py` only uses `get_grades_by_pathway` and `load_grades_excel_with_grades`. It never calls `load_grades_excel` directly. `load_grades_excel` is still used inside `grades_loader.py` by other functions, so keep the function in `grades_loader.py`, only remove the unused import in `app.py`.

**Change:** In the `from grades_loader import (...)` block, delete the line `load_grades_excel,`.

---

## 2. Entire files that are unnecessary

**None.** Every file in the project root is used:

| File | Role |
|------|------|
| `app.py` | Main FastAPI app and all API routes |
| `db.py` | SQLite connection and schema (used by `app.py`) |
| `grades_loader.py` | Excel loading and pathway logic (used by `app.py`) |
| `parse_offer_pdf.py` | PDF/image parsing with Gemini (used by `app.py`) |
| `qs_rankings.py` | QS rank lookup (used by `app.py`) |
| `static/index.html` | Full front end (served at `/`) |
| `RUN.command` / `RUN.bat` | One-click run for non-technical users |
| `.env.example` | Template for API key and config |
| `README.md`, `PROJECT_NOTES.md`, `INSTRUCTIONS_FOR_NON_TECHNICAL_USERS.txt` | Docs and onboarding |

Do **not** delete `venv/`; it is the Python environment. Data files (`offers.db`, the Excel file) are required at runtime.

---

## 3. Crucial files and why

| File | Why it’s crucial |
|------|-------------------|
| **`app.py`** | Entry point of the app (`uvicorn app:app`). Defines all HTTP routes: upload, pathway grades, analytics, students, grades import, and student grades update. Serves the front end and mounts static files. Without it the app does not run. |
| **`db.py`** | Creates and connects to the SQLite database (`offers.db`). Defines `get_db()` and `init_db()`, and the schema for `offers` and `student_grades`. All offer and grade persistence goes through here. |
| **`grades_loader.py`** | Loads the cohort and grades from the Excel file. Exposes `get_grades_by_pathway`, `load_grades_excel_with_grades`, `get_excluded_student_codes`, and `EXCLUDED_STUDENT_NAMES`. Powers the pathway tabs, Students tab, analytics, and grades import. Business Mgmt Maths vs Economics logic lives here. |
| **`parse_offer_pdf.py`** | Extracts structured data from PDF and image offer letters using Gemini. Exposes `parse_pdf_with_pdfplumber` and `parse_image_with_gemini`. Required for the upload flow; without it, offer upload cannot work. |
| **`qs_rankings.py`** | Provides `get_qs_rank(university_name)` for QS World University Rankings. Used to show “best” university and QS-related stats in Analytics and Students. |
| **`static/index.html`** | The only front-end asset. Contains the full UI: tabs (Analytics, Students, optional pathway tabs), upload, tables, filters, and all `fetch()` calls to the API. Served at `/`. |
| **`requirements.txt`** | Declares Python dependencies (FastAPI, openpyxl, pdfplumber, google-genai, etc.). Needed for `pip install -r requirements.txt`. |
| **`.env`** (or `.env.example`)** | Holds `GEMINI_API_KEY` (and optionally `BELLERBYS_DB`, `BELLERBYS_GRADES_EXCEL`). Required for PDF/image parsing and for correct DB and Excel paths. |

**Data / config (required at runtime but not “code”):**
- **`offers.db`** – SQLite database; all offers and student_grades.
- **Grades Excel** (e.g. `BNBU SAPM - Semester 1 Grades_v2.xlsx`) – student list and grade columns; path set in app or `.env`.

---

## Summary

- **One change recommended:** Remove the unused `load_grades_excel` import from `app.py` (line 29).
- **No files to delete:** All current files have a clear role.
- **Crucial files:** `app.py`, `db.py`, `grades_loader.py`, `parse_offer_pdf.py`, `qs_rankings.py`, `static/index.html`, `requirements.txt`, and `.env`/`.env.example` are all essential for building, running, and using the app.
