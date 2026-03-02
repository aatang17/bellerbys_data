# Bellerbys Offer Letters

Upload PDF or image (PNG/JPG) offer letters (UCAS-style format) and store extracted data in a SQLite database. Images are read using OCR (Tesseract).

## What gets extracted

From each PDF we read:

- **University** (Provider name)
- **Provider code**, **Course name**, **Course code**
- **Course start date**, **Point of entry**
- **Offer type** (Conditional / Unconditional)
- **Offer date**, **Application reply deadline**
- **Offer conditions** (full “Conditions for acceptance” text)
- **Contact email** (from “Please send supporting documents to …”)

**Student name** is not on the letter. You can:

- Enter it when uploading, or  
- Rely on the filename (e.g. `Alan_-_Southampton.pdf` → we suggest “Alan”).

## Setup

```bash
cd Bellerbys
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**For PNG/JPG uploads** you need Tesseract OCR installed:

- **macOS:** `brew install tesseract`
- **Windows:** download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

## Run

```bash
uvicorn app:app --reload --port 8000
```

Open **http://localhost:8000** to upload PDFs and view/search offers.

## Usage

1. **Upload** — Choose a PDF or image (PNG/JPG) and optionally type the student name; click “Upload and extract”.
2. **View** — The table lists all offers; use the filters to search by university or student.

Database file: `offers.db` in the project folder (override with `BELLERBYS_DB`). Uploaded files are kept in `uploads/`.

---

## Sharing with someone else (let them try it)

### How can my internal team use the database? (No GitHub needed)

Nobody on your team needs to use GitHub, git, or the command line. Two simple ways:

| What you want | What to do |
|---------------|------------|
| **Everyone uses the same database** (one source of truth) | **You run the app and share a link.** Start the app on your computer, then create a shareable link (e.g. with [ngrok](https://ngrok.com): run `ngrok http 8000` and copy the URL). Send that link to your team. They open it in a browser and use the app. All of them see the same offers and data—your `offers.db` and grades Excel. They never install anything. |
| **Someone has their own copy** (e.g. offline or separate data) | **Send them the folder (as a zip).** Include the app files, `offers.db`, and the grades Excel if you want. They follow **INSTRUCTIONS_FOR_NON_TECHNICAL_USERS.txt**: double‑click **RUN.command** (Mac) or **RUN.bat** (Windows), add a free Gemini API key once, then use the app in their browser. No GitHub. |

**Summary:** Easiest for the team = you host and send a link. They just click and use. The “database” is the app they see in the browser; it’s all driven by your `offers.db` and Excel when you’re the one running it.

---

### For someone with no coding experience (easiest options)

**Best for them: you host, they use a link**

1. You run the app on your computer and create a public link (e.g. with [ngrok](https://ngrok.com): run `ngrok http 8000` after starting the app).
2. Send them the link (e.g. `https://abc123.ngrok.io`).
3. They open it in their browser and use the app. No setup, no installation.

**If they have the folder:** give them **INSTRUCTIONS_FOR_NON_TECHNICAL_USERS.txt** from the project. It explains:
- **Option 1:** If you sent a link → they just click it.
- **Option 2:** If you sent the folder → they double-click **RUN.command** (Mac) or **RUN.bat** (Windows). First time they need to add a free Gemini API key (steps are in the file).

When you zip the project for them, include: **RUN.command**, **RUN.bat**, **.env.example**, and **INSTRUCTIONS_FOR_NON_TECHNICAL_USERS.txt**.

---

### Option A: They run it on their own computer (with some setup)

1. **Package the project** (don’t send your API keys or virtualenv):
   - Zip the project folder, but **exclude**: `venv/`, `__pycache__/`, `.env`
   - **Include**: all `.py` files, `static/`, `requirements.txt`, `README.md`, `.env.example`
   - **Optional**: include `BNBU SAPM - Semester 1 Grades_v2.xlsx` and/or `offers.db` if you want them to see sample students and offers.

2. **They set up and run:**
   ```bash
   unzip Bellerbys.zip   # or wherever they put it
   cd Bellerbys
   cp .env.example .env
   # Edit .env and add their own GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app:app --reload --port 8000
   ```
   Then open **http://localhost:8000**.

3. If you didn’t include the Excel, they need to put a grades Excel (same layout: Student ID, First name, Last name, English name, Pathway in col 8) in the folder or set `BELLERBYS_GRADES_EXCEL` in `.env`.

### Option B: You host it and send them a link

Run the app on a server (your machine with a tunnel, or a cloud host) so they can use it in the browser:

- **Quick local tunnel** (they can try it from elsewhere while your app runs):
  ```bash
  uvicorn app:app --host 0.0.0.0 --port 8000
  ```
  Then use a tunnel (e.g. [ngrok](https://ngrok.com) or Cloudflare Tunnel) and send them the public URL. Your `.env` and `offers.db` stay on your machine.

- **Deploy to a host** (e.g. Railway, Render, Fly.io): you’d need to add the Excel and DB to the deployment or use a hosted database. That’s more setup but gives a permanent link.
