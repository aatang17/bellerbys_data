"""
Offer Letter Generator — admin enters student details, app fills template and returns DOCX.
Run: uvicorn app:app --reload --port 8005
"""
import os
from datetime import datetime
from pathlib import Path

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import db
from letter_generator import generate_letter, get_global_vars, GENERATED_DIR

app = FastAPI(title="Offer Letter Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(NoCacheMiddleware)

BASE = Path(__file__).parent


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


# Issue dates are always current date at generation time; hide from Settings form
_SETTINGS_HIDDEN_KEYS = {"Issue_Date", "Issue_Date_ZH"}


@app.get("/api/settings")
def api_get_settings():
    """Return global variables for the template (excludes Issue_Date / Issue_Date_ZH, which use current date)."""
    all_vars = get_global_vars()
    return {k: v for k, v in all_vars.items() if k not in _SETTINGS_HIDDEN_KEYS}


@app.put("/api/settings")
def api_put_settings(settings: dict = Body(...)):
    """Save global variables (Issue_Date / Issue_Date_ZH are ignored; they use current date when generating)."""
    if not isinstance(settings, dict):
        raise HTTPException(status_code=400, detail="Settings must be a JSON object")
    with db.get_db() as conn:
        for key, value in settings.items():
            key_str = str(key).strip() if key is not None else ""
            if not key_str or key_str in _SETTINGS_HIDDEN_KEYS:
                continue
            val_str = str(value).strip() if value is not None else ""
            conn.execute(
                "INSERT INTO global_vars (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
                (key_str, val_str, val_str),
            )
    return {"ok": True}


@app.post("/api/generate")
def api_generate(
    student_id: str = Body(..., embed=True),
    student_name: str = Body(..., embed=True),
    name_zh: str = Body("", embed=True),
    dob: str = Body("", embed=True),
    email: str = Body("", embed=True),
    program: str = Body("", embed=True),
    scholarship_amount: str | None = Body(None, embed=True),
    scholarship_details: str | None = Body(None, embed=True),
):
    """Generate offer letter DOCX; return download URL and save to history."""
    try:
        out_path, file_name = generate_letter(
            student_id=student_id.strip(),
            student_name=student_name.strip(),
            name_zh=name_zh.strip() if name_zh else "",
            dob=dob.strip() if dob else "",
            email=email.strip() if email else "",
            program=program.strip() if program else "",
            scholarship_amount=scholarship_amount.strip() if scholarship_amount else None,
            scholarship_details=scholarship_details.strip() if scholarship_details else None,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    now = datetime.utcnow().isoformat() + "Z"
    with db.get_db() as conn:
        cur = conn.execute(
            """INSERT INTO generated_letters (student_id, student_name, dob, program, scholarship_amount, file_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (student_id.strip(), student_name.strip(), dob or None, program or None, scholarship_amount or None, file_name, now),
        )
        row_id = cur.lastrowid

    return {
        "id": row_id,
        "file_name": file_name,
        "download_url": f"/api/letters/{row_id}/download",
        "created_at": now,
    }


@app.get("/api/letters")
def api_list_letters():
    """List generated letters (newest first)."""
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT id, student_id, student_name, dob, program, scholarship_amount, file_name, created_at
               FROM generated_letters ORDER BY created_at DESC LIMIT 200"""
        ).fetchall()
    return {
        "letters": [
            {
                "id": r["id"],
                "student_id": r["student_id"],
                "student_name": r["student_name"],
                "dob": r["dob"],
                "program": r["program"],
                "scholarship_amount": r["scholarship_amount"],
                "file_name": r["file_name"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@app.get("/api/letters/{letter_id}/download")
def api_download_letter(letter_id: int):
    """Serve the generated DOCX file."""
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT file_name FROM generated_letters WHERE id = ?",
            (letter_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Letter not found")
    file_path = Path(GENERATED_DIR) / row["file_name"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=row["file_name"], media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
