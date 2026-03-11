# Offer Letter Generator

Generate Bellerbys GBA offer letters from a Word template. Admin enters student details (name, ID, DOB, program, optional scholarship); the app fills the template and returns a DOCX.

## Setup

```bash
cd Offer_Letter_Generator
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` if you want to override paths (optional).

## Template placeholders

The template in `templates/offer_letter_template.docx` should use placeholders that the app replaces:

| Placeholder | Description |
|-------------|-------------|
| `{{Student_ID}}` | Student ID (also used as Application No.) |
| `{{Name_En}}` | Full name (English) |
| `{{Name_Zh}}` | Name in Chinese |
| `{{DOB}}` | Date of birth (e.g. 29 November 2007) |
| `{{DOB_Short}}` | DOB in short form (e.g. 2007 / 11 / 29) |
| `{{Email}}` | Student email |
| `{{Program}}` | Program / course name |
| `{{Tuition_Fee}}`, `{{Tuition_Amount}}`, `{{Dormitory_Amount}}` | From Settings |
| `{{Enrollment_Deposit}}`, `{{Deposit_Deadline}}`, `{{Tuition_Deadline}}` | From Settings |
| `{{Issue_Date}}`, `{{Issue_Date_ZH}}`, `{{Payment_Deadline}}`, `{{Payment_Deadline_ZH}}` | From Settings |
| `{{Scholarship_Amount}}` | Amount or "—" if no scholarship |
| `{{Total_Amount}}` | Total (from Settings) |
| `{{Campus}}`, `{{Commencement}}`, `{{Expected_Graduation}}` | From Settings |

**Scholarship:** If the student has no scholarship, the "Scholarship Award" section (EN + ZH) in the template is removed from the generated letter. If they have a scholarship, `{{Scholarship_Amount}}` is filled and the section stays.

## Run

```bash
uvicorn app:app --reload --port 8005
```

Open **http://127.0.0.1:8005**. Use **Generate** to enter student details and download the letter; **Settings** to edit global variables (tuition, dates, etc.); **Generated letters** to see history and re-download.

## Project layout

- `app.py` — FastAPI app and API routes
- `db.py` — SQLite (global_vars, generated_letters)
- `letter_generator.py` — Load template, replace placeholders, optional scholarship block, save DOCX
- `static/index.html` — Single-page UI (tabs: Generate, Settings, Generated letters)
- `templates/offer_letter_template.docx` — Your Word template (add `{{...}}` where values should go)
- `generated/` — Output DOCX files (gitignore this folder if you use git)
