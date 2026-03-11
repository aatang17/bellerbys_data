# Bellerbys Offer Letters

Upload PDF or image (PNG/JPG) offer letters (UCAS-style format) and store extracted data in a SQLite database. Images are read using OCR (Tesseract).

## What gets extracted

From each PDF we read:

- **University** (Provider name)
- **Provider code**, **Course name**, **Course code**
- **Course start date**, **Point of entry**
- **Offer type** (Conditional / Unconditional)
- **Offer date**, **Application reply deadline**
- **Offer conditions** (full "Conditions for acceptance" text)
- **Contact email** (from "Please send supporting documents to …")

**Student name** is not on the letter. You can:

- Enter it when uploading, or  
- Rely on the filename (e.g. `Alan_-_Southampton.pdf` → we suggest "Alan").

## Setup

```bash
cd Bellerbys_Offer_Database
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**For PNG/JPG uploads** you need Tesseract OCR installed:

- **macOS:** `brew install tesseract`
- **Windows:** download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

## Run

**Terminal 1 – start the app (leave this running):**
```bash
cd Bellerbys_Offer_Database
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
Wait until you see: `Application startup complete`.

Open **http://127.0.0.1:8000** in your browser (port is **8000**, not 800).

**If using ngrok** – open a **second** terminal (Terminal 2), then run:
```bash
ngrok http --host-header=localhost:8000 8000
```
Use the `https://...ngrok-free.app` URL ngrok shows. The app must already be running in Terminal 1.

## Usage

1. **Upload** — Choose a PDF or image (PNG/JPG) and optionally type the student name; click "Upload and extract".
2. **View** — The table lists all offers; use the filters to search by university or student.

Database file: `offers.db` in this folder (override with `BELLERBYS_DB`). Uploaded files are kept in `uploads/`. Grades Excel and QS rankings Excel live in `data/` (override with `BELLERBYS_GRADES_EXCEL` if needed).

**Repo layout:** This folder contains the app code, `static/`, and `data/`. For [Railway deployment](../docs/RAILWAY.md) and [project notes](../docs/PROJECT_NOTES.md) see the repo root `docs/`. The separate letter-generation app is in `Offer_Letter_Generator/` at repo root.

---

## Sharing with someone else (let them try it)

### How can my internal team use the database? (No GitHub needed)

Nobody on your team needs to use GitHub, git, or the command line. Two simple ways:

| What you want | What to do |
|---------------|------------|
| **Everyone uses the same database** (one source of truth) | **You run the app and share a link.** Start the app on your computer, then create a shareable link (e.g. with [ngrok](https://ngrok.com): run `ngrok http 8000` and copy the URL). Send that link to your team. They open it in a browser and use the app. All of them see the same offers and data—your `offers.db` and grades Excel. They never install anything. |
| **Someone has their own copy** (e.g. offline or separate data) | **Send them this folder (as a zip).** Include the app files, `offers.db`, and the grades Excel if you want. They double‑click **RUN.command** (Mac) or **RUN.bat** (Windows), add a free Gemini API key once, then use the app in their browser. No GitHub. |

**Summary:** Easiest for the team = you host and send a link. They just click and use. The "database" is the app they see in the browser; it's all driven by your `offers.db` and Excel when you're the one running it.

---

### For someone with no coding experience (easiest options)

**Best for them: you host, they use a link**

1. You run the app on your computer and create a public link (e.g. with [ngrok](https://ngrok.com): run `ngrok http 8000` after starting the app).
2. Send them the link (e.g. `https://abc123.ngrok.io`).
3. They open it in their browser and use the app. No setup, no installation.

**If they have the folder:** give them this folder (zip Bellerbys_Offer_Database). They double-click **RUN.command** (Mac) or **RUN.bat** (Windows). First time they need to add a free Gemini API key (copy from `.env.example` to `.env` and add the key).

When you zip the folder for them, include: **RUN.command**, **RUN.bat**, **.env.example**, and this **README.md**.

---

### Ngrok: why it might not work, and a permanent URL

**If `ngrok http 8000` doesn't work, check:**

1. **App is running first**  
   In another terminal run:  
   `uvicorn app:app --host 0.0.0.0 --port 8000`  
   (from inside the Bellerbys_Offer_Database folder.)  
   Then run `ngrok http 8000`. Ngrok only forwards; something must be listening on 8000.

2. **"Endpoint already online" (ERR_NGROK_334)**  
   Another ngrok tunnel is already using your URL (e.g. another terminal or machine).  
   - **Fix:** Stop the other tunnel (close that terminal or run `pkill -f ngrok`), then run `ngrok http 8000` again.  
   - Or run the second tunnel with `ngrok http 8000 --pooling-enabled` if you want two tunnels to share the same URL (load balancing).

3. **Port 8000 in use by something else**  
   Make sure no other app is using 8000, or run the app on another port (e.g. 8001) and use `ngrok http 8001`.

4. **"400 Server host not allowed"**  
   The app (or stack) may reject requests whose `Host` header is the ngrok URL.  
   - **Fix:** Run ngrok with host-header rewrite so the app sees `localhost`:  
     `ngrok http --host-header=localhost:8000 8000`  
   Use that ngrok URL in the browser; the tunnel will rewrite the Host header for requests to your app.

5. **See the current tunnel**  
   While ngrok is running, open **http://127.0.0.1:4040** in your browser. The ngrok inspector shows the public URL and request log.

**Making the URL permanent (same URL every time):**

- **Free:** Sign in at [ngrok](https://ngrok.com) and claim **one free static domain** (e.g. `https://yourname.ngrok-free.app`). It stays the same every time you run ngrok. In the dashboard: **Domains → Create Domain**, then run e.g. `ngrok http 8000 --domain=yourname.ngrok-free.app`.
- **Paid:** Reserved/custom domains and more tunnels are available on paid plans. Your current URL (e.g. `nicholle-unsegmented-lyn.ngrok-free.dev`) may already be a reserved domain; if so, it is already permanent for your account.

---

### Option A: They run it on their own computer (with some setup)

1. **Package the project** (don't send your API keys or virtualenv):
   - Zip the **Bellerbys_Offer_Database** folder, but **exclude**: `venv/`, `__pycache__/`, `.env`
   - **Include**: all `.py` files, `static/`, `data/`, `requirements.txt`, `README.md`, `.env.example`
   - **Optional**: include the grades Excel and/or `offers.db` if you want them to see sample students and offers.

2. **They set up and run:**
   ```bash
   unzip Bellerbys_Offer_Database.zip   # or wherever they put it
   cd Bellerbys_Offer_Database
   cp .env.example .env
   # Edit .env and add their own GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app:app --reload --port 8000
   ```
   Then open **http://localhost:8000**.

3. If you didn't include the Excel, they need to put a grades Excel (same layout: Student ID, First name, Last name, English name, Pathway in col 8) in `data/` or set `BELLERBYS_GRADES_EXCEL` in `.env`.

### Option B: You host it and send them a link

Run the app on a server (your machine with a tunnel, or a cloud host) so they can use it in the browser:

- **Quick local tunnel** (they can try it from elsewhere while your app runs):
  ```bash
  cd Bellerbys_Offer_Database
  uvicorn app:app --host 0.0.0.0 --port 8000
  ```
  Then use a tunnel (e.g. [ngrok](https://ngrok.com) or Cloudflare Tunnel) and send them the public URL. Your `.env` and `offers.db` stay on your machine.

- **Deploy to a host** (e.g. Railway, Render, Fly.io): see [Railway deployment](../docs/RAILWAY.md). That gives a permanent link.
