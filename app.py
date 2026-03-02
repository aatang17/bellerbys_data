"""
Bellerbys Offer Letters — upload PDFs and store extracted data.
Run: uvicorn app:app --reload --port 8000
"""
import os
import re
from datetime import datetime
from pathlib import Path

# Load .env file if present (e.g. GEMINI_API_KEY, BELLERBYS_GRADES_EXCEL)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db
from parse_offer_pdf import parse_pdf_with_pdfplumber, parse_image_with_gemini
from grades_loader import (
    EXCLUDED_STUDENT_NAMES,
    get_excluded_student_codes,
    get_grades_by_pathway,
    get_student_name_by_code,
    load_grades_excel_with_grades,
)
from qs_rankings import get_qs_rank

app = FastAPI(title="Bellerbys Offer Letters")

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = Path(os.environ.get("BELLERBYS_UPLOAD_DIR", os.path.join(BASE, "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Excel grades file: set BELLERBYS_GRADES_EXCEL or use default below
GRADES_EXCEL_PATH = os.environ.get("BELLERBYS_GRADES_EXCEL") or os.path.join(BASE, "BNBU SAPM - Semester 1 Grades_v2.xlsx")


def _student_id_from_filename(file_name: str) -> str | None:
    """Extract student ID from start of filename. E.g. '12345 RMIT.pdf', '12345_Mulan_RMIT.pdf' -> '12345'."""
    if not file_name:
        return None
    stem = Path(file_name).stem
    # Leading digits only (Excel Student ID is numeric), or leading alphanumeric run before _/space/-
    match = re.match(r"^(\d+)(?:_|\s|-|$)", stem) or re.match(r"^([A-Za-z0-9]+)(?:_|\s|-|$)", stem)
    return match.group(1).strip() if match else None


def _student_name_from_filename(file_name: str) -> str | None:
    """Suggest student name from filename like 'Alan_-_Southampton-....pdf' -> 'Alan'."""
    if not file_name:
        return None
    name = Path(file_name).stem
    # "Alan_-_Southampton-xxx" or "Alan_Southampton" -> take part before _-_ or first _
    match = re.match(r"^([^_\-]+)(?:_\-_|_|-)", name)
    if match:
        return match.group(1).strip() or None
    if "_" in name or "-" in name:
        return name.split("_")[0].split("-")[0].strip() or None
    return name.strip() or None


@app.on_event("startup")
def startup():
    db.init_db()
    # Remove excluded students (e.g. Cici, Vivian) from offers and student_grades
    excluded_lower = [n.strip().lower() for n in EXCLUDED_STUDENT_NAMES if n]
    if excluded_lower:
        with db.get_db() as conn:
            placeholders = ",".join("?" * len(excluded_lower))
            conn.execute(
                f"DELETE FROM offers WHERE LOWER(TRIM(student_name)) IN ({placeholders})",
                excluded_lower,
            )
            codes = get_excluded_student_codes(GRADES_EXCEL_PATH)
            if codes:
                conn.execute(
                    "DELETE FROM student_grades WHERE student_code IN (" + ",".join("?" * len(codes)) + ")",
                    codes,
                )


ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def _is_image(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg"))


@app.post("/api/upload")
async def upload_offer(
    file: UploadFile = File(...),
    student_name: str | None = Form(None),
):
    """Upload a PDF or image (PNG/JPG) offer letter. Optional student_name; if omitted, inferred from filename."""
    fn = (file.filename or "").lower()
    if not file.filename or not any(fn.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF or image file (.pdf, .png, .jpg).",
        )

    contents = await file.read()
    safe_name = re.sub(r"[^\w\-_.]", "_", file.filename)[:200]
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(contents)

    try:
        if _is_pdf(file.filename):
            data = parse_pdf_with_pdfplumber(str(file_path))
        elif _is_image(file.filename):
            data = parse_image_with_gemini(str(file_path))
        else:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Unsupported file type.")
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    # Resolve student name: form value, else by student ID from filename (Excel lookup), else from filename text
    name = (student_name or "").strip()
    if not name:
        student_id = _student_id_from_filename(file.filename)
        if student_id:
            name_by_code = get_student_name_by_code(GRADES_EXCEL_PATH)
            name = name_by_code.get(student_id) or name_by_code.get(student_id.strip())
        if not name:
            name = _student_name_from_filename(file.filename)
    now = datetime.utcnow().isoformat() + "Z"

    with db.get_db() as conn:
        # Reject duplicates: same student + same university + same course
        existing = conn.execute(
            """
            SELECT id FROM offers
            WHERE LOWER(TRIM(student_name)) = LOWER(TRIM(?))
              AND LOWER(TRIM(university))   = LOWER(TRIM(?))
              AND LOWER(TRIM(course_name))  = LOWER(TRIM(?))
            """,
            (name or "", data.get("university") or "", data.get("course_name") or ""),
        ).fetchone()
        if existing:
            file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=409,
                detail=f"Duplicate: an offer for '{name}' at '{data.get('university')}' "
                       f"for '{data.get('course_name')}' already exists (id={existing[0]})."
            )

        conn.execute(
            """
            INSERT INTO offers (
                student_name, university, provider_code, course_name, course_code,
                course_start_date, point_of_entry, offer_type, offer_date, reply_deadline,
                offer_conditions, english_requirement, subject_requirement, contact_email, file_name, created_at,
                aes_overall, aes_listening, aes_reading, aes_writing, aes_speaking, required_scores_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name or None,
                data.get("university") or "",
                data.get("provider_code"),
                data.get("course_name"),
                data.get("course_code"),
                data.get("course_start_date"),
                data.get("point_of_entry"),
                data.get("offer_type"),
                data.get("offer_date"),
                data.get("reply_deadline"),
                data.get("offer_conditions"),
                data.get("english_requirement"),
                data.get("subject_requirement"),
                data.get("contact_email"),
                file.filename,
                now,
                data.get("aes_overall"),
                data.get("aes_listening"),
                data.get("aes_reading"),
                data.get("aes_writing"),
                data.get("aes_speaking"),
                data.get("required_scores_json"),
            ),
        )
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "id": row_id,
        "student_name": name,
        **data,
        "file_name": file.filename,
    }


def _normalize_name(s: str) -> str:
    return (s or "").strip().lower()


def _fuzzy_score(subject: str, scores: dict) -> str:
    """Return the required score for a subject using exact then fuzzy key matching."""
    if not scores:
        return ""
    if subject in scores:
        return scores[subject]
    subj_low = subject.lower()
    stop = {"with", "and", "or", "in", "of", "the", "a", "an", "project", "skills", "module"}
    subj_words = {w for w in re.split(r'\W+', subj_low) if w and w not in stop}
    for key, val in scores.items():
        key_words = {w for w in re.split(r'\W+', key.lower()) if w and w not in stop}
        if key_words and len(key_words & subj_words) >= max(1, len(key_words) - 1):
            return val
    return ""


def _normalize_required_scores(req_scores: dict) -> dict:
    """Merge overall-like keys into 'Overall' so UI shows required average (e.g. '70% overall', 'overall average')."""
    if not req_scores:
        return {}
    out = dict(req_scores)
    for key in list(out.keys()):
        k = (key or "").strip().lower()
        if k == "overall":
            out["Overall"] = out.get("Overall") or out[key]
            if key != "Overall":
                del out[key]
            continue
        if "overall" in k and ("average" in k or "final" in k):
            out["Overall"] = out.get("Overall") or out[key]
            if key != "Overall":
                del out[key]
    return out


def _subject_scores_for_offer(subjects: list, req_scores: dict, aes_overall: str) -> dict:
    """Compute per-subject required scores with fallback for 'X% overall' offers."""
    req_scores = _normalize_required_scores(req_scores or {})
    pathway_scores = {}
    for subj in subjects:
        if subj not in ("AES", "EAP"):
            pathway_scores[subj] = _fuzzy_score(subj, req_scores)

    # If some subjects are missing, use the most common found score as fallback
    found = [v for v in pathway_scores.values() if v]
    fallback = max(set(found), key=found.count) if found else ""

    result = {}
    for subj in subjects:
        if subj in ("AES", "EAP"):
            result[subj] = aes_overall or _fuzzy_score(subj, req_scores)
        else:
            result[subj] = pathway_scores.get(subj) or fallback
    if req_scores and "Overall" in req_scores:
        result["Overall"] = req_scores["Overall"]
    return result


def _norm_aes(val: str) -> str:
    """Normalise an AES/English score for display (1 dp).
    - Percentages: '50', '50%' → '50.0%'
    - IELTS band scores (≤ 9.5): '6', '6.0', '6.5' → 'IELTS 6.0', 'IELTS 6.5'
    """
    s = (val or "").strip().rstrip("%").strip()
    try:
        n = float(s)
    except ValueError:
        return val.strip()
    n = round(n, 1)
    if n <= 9.5:
        return f"IELTS {n:.1f}"
    return f"{n:.1f}%"


@app.get("/api/grades/pathway/{pathway}")
def get_grades_pathway(pathway: str):
    """Get students and grades for one pathway (Business Mgmt, Media, Computing), joined with offers."""
    pathway_key = pathway.replace("-", " ").strip()
    if pathway_key == "business mgmt":
        pathway_key = "Business Mgmt"
    elif pathway_key == "media":
        pathway_key = "Media"
    elif pathway_key == "computing":
        pathway_key = "Computing"
    else:
        raise HTTPException(status_code=404, detail="Unknown pathway")

    try:
        by_pathway = get_grades_by_pathway(GRADES_EXCEL_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load grades: {e}")

    students = by_pathway.get(pathway_key, [])

    # Build map: normalized student name -> list of all offers (one row per offer)
    # University = Provider name (e.g. Durham University), Course = Course name (e.g. Business and Management)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT student_name, course_code, offer_type, offer_date, university, course_name,"
            " subject_requirement, english_requirement,"
            " aes_overall, aes_listening, aes_reading, aes_writing, aes_speaking, required_scores_json"
            " FROM offers ORDER BY offer_date DESC"
        ).fetchall()
    name_to_offers = {}
    for r in rows:
        name = _normalize_name(r[0])
        if not name:
            continue
        if name not in name_to_offers:
            name_to_offers[name] = []
        import json as _json
        req_scores = {}
        try:
            if r[13]:
                req_scores = _json.loads(r[13])
        except Exception:
            pass
        name_to_offers[name].append({
            "course_code": r[1] or "",
            "offer_type": r[2] or "",
            "offer_date": str(r[3] or "") if r[3] else "",
            "university": r[4] or "",
            "course_name": r[5] or "",
            "subject_requirement": r[6] or "",
            "english_requirement": r[7] or "",
            "aes_overall": r[8] or "",
            "aes_listening": r[9] or "",
            "aes_reading": r[10] or "",
            "aes_writing": r[11] or "",
            "aes_speaking": r[12] or "",
            "required_scores": req_scores,
        })

    out = []
    for s in students:
        norm = _normalize_name(s["student_name"]) or _normalize_name(s["english_name"])
        offers = name_to_offers.get(norm, [])
        if not offers:
            # One row with blank offer so student still appears
            row = {
                "student_code": s["student_code"],
                "student_name": s["student_name"],
                "course_code": "",
                "course_name": "",
                "offer_type": "",
                "offer_date": "",
                "university": "",
                "offer_index": 0,
                "offer_count": 0,
            }
            for subj in s["subjects"]:
                row[subj] = s["grades"].get(subj, "")
            out.append(row)
        else:
            for i, offer in enumerate(offers):
                req_scores = offer.get("required_scores", {})
                row = {
                    "student_code": s["student_code"],
                    "student_name": s["student_name"],
                    "course_code": offer.get("course_code", ""),
                    "course_name": offer.get("course_name", ""),
                    "offer_type": offer.get("offer_type", ""),
                    "offer_date": offer.get("offer_date", ""),
                    "university": offer.get("university", ""),
                    "subject_requirement": offer.get("subject_requirement", ""),
                    "english_requirement": offer.get("english_requirement", ""),
                    "aes_overall": offer.get("aes_overall", ""),
                    "aes_listening": offer.get("aes_listening", ""),
                    "aes_reading": offer.get("aes_reading", ""),
                    "aes_writing": offer.get("aes_writing", ""),
                    "aes_speaking": offer.get("aes_speaking", ""),
                    "offer_index": i + 1,
                    "offer_count": len(offers),
                }
                scores = _subject_scores_for_offer(
                    s["subjects"], req_scores, offer.get("aes_overall", "")
                )
                for subj in s["subjects"]:
                    row[subj] = scores.get(subj, "")
                out.append(row)

    subjects = students[0]["subjects"] if students else []
    return {"pathway": pathway_key, "subjects": subjects, "rows": out}


@app.get("/api/analytics")
def get_analytics():
    """Aggregated stats for the analytics tab."""
    import json as _json

    # Load all students from Excel
    try:
        by_pathway = get_grades_by_pathway(GRADES_EXCEL_PATH)
    except Exception:
        by_pathway = {"Business Mgmt": [], "Media": [], "Computing": []}

    all_students = {
        _normalize_name(s["student_name"] or s["english_name"]): s["pathway"]
        for pathway, students in by_pathway.items()
        for s in students
    }
    total_students = len(all_students)

    # Load all offers
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT student_name, university, offer_type, offer_date, "
            "aes_overall, required_scores_json FROM offers ORDER BY offer_date DESC"
        ).fetchall()

    # Per-student offer counts
    student_offer_counts: dict[str, int] = {}
    university_counts: dict[str, int] = {}
    offer_type_counts: dict[str, int] = {"Conditional": 0, "Unconditional": 0, "Unknown": 0}
    aes_score_counts: dict[str, int] = {}
    qs_uni_map: dict[str, int] = {}   # uni display name -> QS rank
    students_with_top100: set[str] = set()

    for r in rows:
        name = _normalize_name(r[0])
        uni = (r[1] or "Unknown").strip()
        otype = (r[2] or "").strip()
        aes = (r[4] or "").strip()

        if name:
            student_offer_counts[name] = student_offer_counts.get(name, 0) + 1

        university_counts[uni] = university_counts.get(uni, 0) + 1

        if otype in offer_type_counts:
            offer_type_counts[otype] += 1
        else:
            offer_type_counts["Unknown"] += 1

        if aes:
            aes_score_counts[_norm_aes(aes)] = aes_score_counts.get(_norm_aes(aes), 0) + 1

        # QS ranking check
        rank = get_qs_rank(uni)
        if rank is not None:
            if uni not in qs_uni_map or qs_uni_map[uni] > rank:
                qs_uni_map[uni] = rank
            if name:
                students_with_top100.add(name)

    total_offers = len(rows)
    # Coverage = current cohort (Excel) only: count students who are in Excel AND have at least one offer
    students_with_offers = sum(1 for norm in all_students if norm in student_offer_counts)

    # Pathway breakdown
    pathway_stats = []
    for pathway, students in by_pathway.items():
        count = len(students)
        with_offer = sum(
            1 for s in students
            if _normalize_name(s["student_name"] or s["english_name"]) in student_offer_counts
        )
        pathway_stats.append({
            "pathway": pathway,
            "total": count,
            "with_offer": with_offer,
            "without_offer": count - with_offer,
        })

    # Top universities (up to 10)
    top_unis = sorted(university_counts.items(), key=lambda x: -x[1])[:10]

    # AES score distribution (sorted by score value then count)
    def _sort_key(item):
        s = item[0].replace("%", "").replace("IELTS", "").strip()
        try:
            return float(s)
        except ValueError:
            return 999
    aes_dist = sorted(aes_score_counts.items(), key=_sort_key)

    # Students without any offer
    missing = [
        {"student_name": s["student_name"], "pathway": s["pathway"]}
        for norm, pathway in all_students.items()
        for s in by_pathway.get(pathway, [])
        if _normalize_name(s["student_name"] or s["english_name"]) == norm
        and norm not in student_offer_counts
    ]
    # Deduplicate (dict comprehension above can double-emit); use ordered set via dict
    seen: set[str] = set()
    missing_deduped = []
    for m in missing:
        key = _normalize_name(m["student_name"])
        if key not in seen:
            seen.add(key)
            missing_deduped.append(m)

    # Multiple-offer students
    multi = sorted(
        [{"name": k, "count": v} for k, v in student_offer_counts.items() if v > 1],
        key=lambda x: -x["count"],
    )

    # QS top 100 summary (only count current cohort)
    qs_top100_offers = [
        {"university": uni, "rank": rank}
        for uni, rank in sorted(qs_uni_map.items(), key=lambda x: x[1])
    ]
    students_top100_count = sum(1 for norm in all_students if norm in students_with_top100)
    top100_pct = round(students_top100_count / total_students * 100) if total_students else 0

    return {
        "total_students": total_students,
        "total_offers": total_offers,
        "students_with_offers": students_with_offers,
        "students_without_offers": total_students - students_with_offers,
        "offer_type_counts": offer_type_counts,
        "pathway_stats": pathway_stats,
        "top_universities": [{"university": u, "count": c} for u, c in top_unis],
        "aes_distribution": [{"score": s, "count": c} for s, c in aes_dist],
        "students_missing_offer": missing_deduped,
        "students_multiple_offers": multi,
        "qs_top100_students": students_top100_count,
        "qs_top100_pct": top100_pct,
        "qs_top100_offers": qs_top100_offers,
    }


@app.get("/api/offers/all")
def get_all_offers(limit: int = 200):
    """List all offers in the DB (newest first). Use to verify uploads for students not in the grades Excel (e.g. Mulan)."""
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, student_name, university, course_name, course_code, offer_type, offer_date, file_name, created_at
            FROM offers ORDER BY created_at DESC LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
    return {
        "total": len(rows),
        "offers": [
            {
                "id": r[0],
                "student_name": r[1] or "",
                "university": r[2] or "",
                "course_name": r[3] or "",
                "course_code": r[4] or "",
                "offer_type": r[5] or "",
                "offer_date": r[6] or "",
                "file_name": r[7] or "",
                "created_at": r[8] or "",
            }
            for r in rows
        ],
    }


@app.patch("/api/offers/{offer_id}")
def update_offer_student_name(offer_id: int, student_name: str = Body(..., embed=True)):
    """Update an offer's student_name so it matches the Excel (fixes 'offer in DB but not showing under student')."""
    name = (student_name or "").strip() or None
    with db.get_db() as conn:
        cur = conn.execute("UPDATE offers SET student_name = ? WHERE id = ?", (name, offer_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"No offer with id={offer_id}")
    return {"id": offer_id, "student_name": name}


@app.get("/api/students")
def get_students():
    """All students across pathways joined with their offers, for the Students tab."""
    import json as _json

    try:
        by_pathway = get_grades_by_pathway(GRADES_EXCEL_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load grades: {e}")

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT student_name, university, course_name, course_code, offer_type, offer_date,"
            " reply_deadline, subject_requirement, english_requirement,"
            " aes_overall, aes_listening, aes_reading, aes_writing, aes_speaking, required_scores_json"
            " FROM offers ORDER BY offer_date DESC"
        ).fetchall()

    name_to_offers: dict[str, list] = {}
    for r in rows:
        name = _normalize_name(r[0])
        if not name:
            continue
        req_scores: dict = {}
        try:
            if r[14]:
                req_scores = _json.loads(r[14])
        except Exception:
            pass
        name_to_offers.setdefault(name, []).append({
            "university":          r[1]  or "",
            "course_name":         r[2]  or "",
            "course_code":         r[3]  or "",
            "offer_type":          r[4]  or "",
            "offer_date":          r[5]  or "",
            "subject_requirement": r[7]  or "",
            "english_requirement": r[8]  or "",
            "aes_overall":         r[9]  or "",
            "aes_listening":       r[10] or "",
            "aes_reading":         r[11] or "",
            "aes_writing":         r[12] or "",
            "aes_speaking":        r[13] or "",
            "required_scores":     req_scores,
            "qs_rank":             get_qs_rank(r[1] or ""),
        })

    pathway_order = {"Business Mgmt": 0, "Media": 1, "Computing": 2}
    students = []
    for pathway, pathway_students in by_pathway.items():
        for s in pathway_students:
            norm = _normalize_name(s["student_name"] or s["english_name"])
            offers = name_to_offers.get(norm, [])
            qs_ranks = [o["qs_rank"] for o in offers if o["qs_rank"] is not None]
            types = {(o["offer_type"] or "").lower() for o in offers}
            if "unconditional" in types:
                status = "unconditional"
            elif "conditional" in types:
                status = "conditional"
            else:
                status = "none"
            subjects = s["subjects"]  # e.g. ["AES", "Business Management", ...]
            enriched_offers = []
            for o in offers:
                o_copy = dict(o)
                o_copy["subject_scores"] = _subject_scores_for_offer(
                    subjects, o.get("required_scores", {}), o.get("aes_overall", "")
                )
                enriched_offers.append(o_copy)

            students.append({
                "student_code": s["student_code"],
                "student_name": s["student_name"],
                "pathway":      pathway,
                "subjects":     subjects,
                "offer_count":  len(enriched_offers),
                "best_qs_rank": min(qs_ranks) if qs_ranks else None,
                "status":       status,
                "offers":       enriched_offers,
            })

    # Attach current grades from DB
    with db.get_db() as conn:
        grade_rows = conn.execute(
            "SELECT student_code, subject, value FROM student_grades"
        ).fetchall()
    code_to_grades: dict[str, dict[str, str]] = {}
    for r in grade_rows:
        code_to_grades.setdefault(r[0], {})[r[1]] = r[2] or ""
    for s in students:
        s["current_grades"] = code_to_grades.get(s["student_code"], {})

    students.sort(key=lambda x: (pathway_order.get(x["pathway"], 99), x["student_name"].lower()))
    return {"students": students, "total": len(students)}


@app.post("/api/grades/import")
async def import_grades_from_excel(file: UploadFile | None = File(None)):
    """Import current grades into student_grades table.
    - If no file uploaded: use the configured Excel path (BELLERBYS_GRADES_EXCEL or default).
    - If file uploaded: use that file (Excel .xlsx with same layout: Student ID, Pathway, grade columns).
    """
    from datetime import datetime
    import tempfile

    path_to_use = None
    temp_path = None
    if file and file.filename:
        ext = (file.filename or "").lower()
        if not (ext.endswith(".xlsx") or ext.endswith(".xls")):
            raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx or .xls).")
        try:
            content = await file.read()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
        if not content:
            raise HTTPException(status_code=400, detail="File is empty.")
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".xlsx")
            os.write(fd, content)
            os.close(fd)
            path_to_use = temp_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")
    else:
        path_to_use = GRADES_EXCEL_PATH

    try:
        students_with_grades = load_grades_excel_with_grades(path_to_use)
    except Exception as e:
        if temp_path and os.path.isfile(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to read Excel: {e}")
    finally:
        if temp_path and os.path.isfile(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    # AES/IELTS are left blank on import; staff enter manually. Clear any existing AES for these students.
    AES_SUBJECTS = ("AES", "AES Listening", "AES Reading", "AES Writing", "AES Speaking")
    now = datetime.utcnow().isoformat() + "Z"
    imported = 0
    with db.get_db() as conn:
        for s in students_with_grades:
            code = s.get("student_code")
            if not code:
                continue
            for subj in AES_SUBJECTS:
                conn.execute(
                    "DELETE FROM student_grades WHERE student_code = ? AND subject = ?",
                    (code, subj),
                )
        for s in students_with_grades:
            code = s.get("student_code")
            if not code:
                continue
            for subject, value in (s.get("grades") or {}).items():
                if not value:
                    continue
                conn.execute(
                    "INSERT INTO student_grades (student_code, subject, value, updated_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(student_code, subject) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (code, subject, value, now),
                )
                imported += 1
    source = "uploaded file" if file else "configured Excel"
    return {"imported": imported, "message": f"Imported {imported} grade entries from {source}."}


@app.put("/api/students/{student_code}/grades")
def update_student_grades(student_code: str, body: dict = Body(...)):
    """Update current grades for one student. Body: { \"grades\": { \"AES\": \"65%\", ... } }."""
    from datetime import datetime

    grades = body.get("grades")
    if not isinstance(grades, dict):
        raise HTTPException(status_code=400, detail="Body must include 'grades' object.")

    now = datetime.utcnow().isoformat() + "Z"
    with db.get_db() as conn:
        for subject, value in grades.items():
            if not subject:
                continue
            subject = str(subject).strip()
            val_str = "" if value is None else str(value).strip()
            if val_str:
                conn.execute(
                    "INSERT INTO student_grades (student_code, subject, value, updated_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(student_code, subject) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (student_code, subject, val_str, now),
                )
            else:
                conn.execute(
                    "DELETE FROM student_grades WHERE student_code = ? AND subject = ?",
                    (student_code, subject),
                )
    return {"student_code": student_code, "updated": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
