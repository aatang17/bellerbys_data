# Deploy Bellerbys apps on Railway

Use this guide to put the **Bellerbys Offers** app (and optionally **Offer Letter Generator**) on Railway so your team can use them from a permanent URL.

---

## 1. Push to GitHub (already done if you ran the steps)

Your repo is at: `https://github.com/aatang17/bellerbys_data.git`

- Code is pushed; **do not** commit `.env`, `offers.db`, or `uploads/` (they are in `.gitignore`).
- On Railway you will set env vars (e.g. `GEMINI_API_KEY`) in the dashboard; the Excel path and DB will use Railway’s disk (see Volume below).

---

## 2. Create a Railway account and project

1. Go to [railway.app](https://railway.app) and sign up (GitHub login is easiest).
2. Click **“New Project”**.
3. Choose **“Deploy from GitHub repo”** and connect your GitHub account if needed.
4. Select the repo: **`aatang17/bellerbys_data`** (or your repo name).
5. Railway will create a new **service** from that repo. You’ll configure it in the next steps.

---

## 3. Deploy the Bellerbys Offers app (main app)

**Option A – Use the root Dockerfile (easiest):** Leave **Root Directory** blank. The repo has a `Dockerfile` at the root that builds and runs the Bellerbys Offer Database app. Push to GitHub and Railway will build with Docker.

**Option B – Use Railpack:** Set **Root Directory** to `Bellerbys_Offer_Database` in the service **Settings** so Railway builds only from that folder (no Dockerfile needed).

1. In the project, click the service that was created (one service per repo by default).
2. Open the **Variables** tab and add:
   - **`GEMINI_API_KEY`** = your Gemini API key (**required** — without it, offer extraction returns no data and uploads fail or save empty rows). Get a free key at [Google AI Studio](https://aistudio.google.com/app/apikey).
   - Optional: `BELLERBYS_GRADES_EXCEL` = leave empty to use the default path; if you upload the Excel to the app, set the path (e.g. `/data/grades.xlsx` after adding a volume — see step 5).
3. Open the **Settings** tab:
   - **Root Directory:** leave blank to use the root `Dockerfile`, or set to `Bellerbys_Offer_Database` to use Railpack.
   - **Build / Start:** leave default when using the root Dockerfile; if using Root Directory, start command comes from the Procfile.
4. Click **Deploy** (or push to GitHub; Railway will redeploy on push if you enabled that).
5. **Persistent data (DB + uploads):**
   - In the service, go to the **Volumes** tab (or **Storage**).
   - Click **Add Volume**, name it e.g. `data`, and set **Mount Path** to `/data`.
   - In **Variables**, add:
     - `BELLERBYS_DB` = `/data/offers.db`
     - `BELLERBYS_UPLOAD_DIR` = `/data/uploads`
   - Restart the service so the app uses `/data` for the database and uploaded files.
6. **Public URL:**
   - In **Settings**, open **Networking** → **Generate Domain**. You’ll get a URL like `https://your-app.up.railway.app`. Share this with your team.

**Excel grades file:** The app expects a grades Excel; the default path is `data/BNBU SAPM - Semester 1 Grades_v2.xlsx` inside the `Bellerbys_Offer_Database` folder. On Railway the same path works. Override with `BELLERBYS_GRADES_EXCEL` if you use a different path (e.g. on a volume).

**Missing offer data or wrong count (e.g. 41 instead of 64)?**
- **Offer info empty:** Set **GEMINI_API_KEY** in the service **Variables**. Without it, extraction cannot fill university, course, conditions, etc. Redeploy after adding the variable.
- **Different count:** Railway’s database is separate from your local one. To get the same 64 offers on Railway, either (1) re-upload the offer letters on the deployed app (with GEMINI_API_KEY set), or (2) replace the DB on the volume: copy your local `offers.db` into the volume (e.g. via a one-off run or by downloading from Railway’s volume and uploading your file, if your host supports it).

---

## 4. (Optional) Deploy Offer Letter Generator as a second service

1. In the **same** Railway project, click **“New”** → **“GitHub Repo”** and select the **same** repo again.
2. A second service is created. Click it.
3. **Settings:**
   - **Root Directory:** set to `Offer_Letter_Generator` (so Railway builds and runs from that folder).
   - **Start Command:** leave blank (it will use `Offer_Letter_Generator/Procfile`: `uvicorn app:app --host 0.0.0.0 --port $PORT`).
4. **Variables:**
   - Add `OFFER_TEMPLATE_PATH` or leave default (template is in the repo).
   - For persistent generated letters and DB, add a **Volume** with mount path `/data`, then:
     - `OFFER_GENERATED_DIR` = `/data/generated`
     - `OFFER_GENERATOR_DB` = `/data/offer_generator.db`
5. **Networking:** Generate a domain for this service so it has its own URL.

---

## 5. Summary

| Item | Bellerbys Offers | Offer Letter Generator |
|------|------------------|-------------------------|
| Repo | Same repo | Same repo |
| Root Directory | `Bellerbys_Offer_Database` | `Offer_Letter_Generator` |
| Start | Procfile: `uvicorn app:app --host 0.0.0.0 --port $PORT` | Same, from subfolder |
| Env vars | `GEMINI_API_KEY`, `BELLERBYS_DB`, `BELLERBYS_UPLOAD_DIR`, optional `BELLERBYS_GRADES_EXCEL` | Optional `OFFER_GENERATOR_DB`, `OFFER_GENERATED_DIR` |
| Volume | `/data` for DB + uploads | `/data` for DB + generated letters |

After deployment, everyone uses the same app and same database; no one needs their own Gemini key. Data is shared for all users.
