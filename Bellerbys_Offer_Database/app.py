"""
Bellerbys Offer Letters — upload PDFs and store extracted data.
Run: uvicorn app:app --reload --port 8000
"""
import json
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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import db
from parse_offer_pdf import parse_pdf_from_bytes, parse_image_with_gemini
from grades_loader import (
    EXCLUDED_STUDENT_NAMES,
    get_excluded_student_codes,
    get_grades_by_pathway,
    get_student_name_by_code,
    load_grades_excel_with_grades,
)
from qs_rankings import get_qs_rank

app = FastAPI(title="Bellerbys Offer Letters")

# Allow ngrok and any other origin so the app works when shared via tunnel (e.g. ngrok)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent browsers/proxies from caching so ngrok and shared links always see fresh data (e.g. student count)."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(NoCacheMiddleware)

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = Path(os.environ.get("BELLERBYS_UPLOAD_DIR", os.path.join(BASE, "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Excel grades file: set BELLERBYS_GRADES_EXCEL or use default below
GRADES_EXCEL_PATH = os.environ.get("BELLERBYS_GRADES_EXCEL") or os.path.join(BASE, "data", "BNBU SAPM - Semester 1 Grades_v2.xlsx")


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

    # Reject PDFs that are too small (e.g. OneDrive placeholder / "online-only" file)
    if _is_pdf(file.filename) and len(contents) < 10_000:
        raise HTTPException(
            status_code=400,
            detail="PDF is too small to be a real offer letter. If the file is in OneDrive, right-click it and choose "
                   "'Always keep on this device' so it downloads fully, then upload again.",
        )

    try:
        if _is_pdf(file.filename):
            data = parse_pdf_from_bytes(contents)
            file_path.write_bytes(contents)
        elif _is_image(file.filename):
            file_path.write_bytes(contents)
            data = parse_image_with_gemini(str(file_path))
        else:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Unsupported file type.")
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    # Require filename to start with a student ID that is in the grades Excel (reject students not in cohort)
    student_code_from_file = _student_id_from_filename(file.filename)
    if not student_code_from_file:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Filename must start with a student ID (e.g. 51111759-Mulan-RMIT.pdf). Only students in the grades Excel can have offers uploaded.",
        )
    name_by_code = get_student_name_by_code(GRADES_EXCEL_PATH)
    if student_code_from_file not in name_by_code and student_code_from_file.strip() not in name_by_code:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Student ID {student_code_from_file} is not in the grades Excel. Only students in the cohort can have offers uploaded. Use a filename like 51111759-Name-University.pdf.",
        )
    # When we have a student code, always use the cohort name (Excel + NAME_OVERRIDES e.g. Chen Yu for 51111738)
    # so the stored offer shows the correct display name, not the filename (e.g. "Iris").
    name = name_by_code.get(student_code_from_file) or name_by_code.get(student_code_from_file.strip())
    if not name:
        name = (student_name or "").strip()
    if not name:
        name = _student_name_from_filename(file.filename)
    now = datetime.utcnow().isoformat() + "Z"

    with db.get_db() as conn:
        # Reject duplicates: same student (by code if set, else by name) + same university + same course
        if student_code_from_file:
            existing = conn.execute(
                """
                SELECT id FROM offers
                WHERE (student_code IS NOT NULL AND student_code = ?)
                  AND LOWER(TRIM(university)) = LOWER(TRIM(?))
                  AND LOWER(TRIM(course_name)) = LOWER(TRIM(?))
                """,
                (student_code_from_file, data.get("university") or "", data.get("course_name") or ""),
            ).fetchone()
        else:
            existing = None
        if not existing:
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
                student_code, student_name, university, provider_code, course_name, course_code,
                course_start_date, point_of_entry, offer_type, offer_date, reply_deadline,
                offer_conditions, english_requirement, subject_requirement, contact_email, file_name, created_at,
                aes_overall, aes_listening, aes_reading, aes_writing, aes_speaking, required_scores_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                student_code_from_file or None,
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
    """Normalize for matching: lower, strip, collapse internal whitespace to single space."""
    t = (s or "").strip().lower()
    return re.sub(r"\s+", " ", t) if t else ""


def _merge_offers(code_offers: list, name_offers: list, key_university: str = "university", key_course: str = "course_name") -> list:
    """Merge offers from code match and name match so Students and Universities stay in sync.
    Deduplicate by (university, course_name) so the same offer is not listed twice."""
    seen: set[tuple[str, str]] = set()
    out = []
    for o in code_offers + name_offers:
        k = (o.get(key_university) or "", o.get(key_course) or "")
        if k in seen:
            continue
        seen.add(k)
        out.append(o)
    return out


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

    # Build maps: student_code -> offers, normalized name -> offers (for offers without code)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT student_code, student_name, course_code, offer_type, offer_date, university, course_name,"
            " subject_requirement, english_requirement,"
            " aes_overall, aes_listening, aes_reading, aes_writing, aes_speaking, required_scores_json"
            " FROM offers ORDER BY offer_date DESC"
        ).fetchall()
    import json as _json
    code_to_offers_pathway: dict[str, list] = {}
    name_to_offers_pathway: dict[str, list] = {}
    for r in rows:
        code = (r[0] or "").strip() or None
        name = _normalize_name(r[1])
        req_scores = {}
        try:
            if r[14]:
                req_scores = _json.loads(r[14])
        except Exception:
            pass
        offer_row = {
            "course_code": r[2] or "",
            "offer_type": r[3] or "",
            "offer_date": str(r[4] or "") if r[4] else "",
            "university": r[5] or "",
            "course_name": r[6] or "",
            "subject_requirement": r[7] or "",
            "english_requirement": r[8] or "",
            "aes_overall": r[9] or "",
            "aes_listening": r[10] or "",
            "aes_reading": r[11] or "",
            "aes_writing": r[12] or "",
            "aes_speaking": r[13] or "",
            "required_scores": req_scores,
        }
        if code:
            code_to_offers_pathway.setdefault(code, []).append(offer_row)
        if name:
            name_to_offers_pathway.setdefault(name, []).append(offer_row)

    out = []
    for s in students:
        norm = _normalize_name(s["student_name"]) or _normalize_name(s["english_name"])
        code_offers = code_to_offers_pathway.get(s["student_code"], [])
        name_offers = name_to_offers_pathway.get(norm, []) if norm else []
        offers = _merge_offers(code_offers, name_offers, "university", "course_name")
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
        total_students = sum(len(students) for students in by_pathway.values())
    except Exception:
        by_pathway = {"Business Mgmt": [], "Media": [], "Computing": []}
        total_students = 0
    code_to_name: dict[str, str] = {}
    norm_to_codes: dict[str, list[str]] = {}
    for students in by_pathway.values():
        for s in students:
            code = s["student_code"]
            code_to_name[code] = s["student_name"] or s["english_name"] or code
            norm = _normalize_name(s["student_name"] or s["english_name"])
            if norm:
                norm_to_codes.setdefault(norm, []).append(code)

    # Load all offers (with student_code for unique-ID matching)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT student_code, student_name, university, offer_type, offer_date, "
            "aes_overall, required_scores_json FROM offers ORDER BY offer_date DESC"
        ).fetchall()

    university_counts: dict[str, int] = {}
    offer_type_counts: dict[str, int] = {"Conditional": 0, "Unconditional": 0, "Unknown": 0}
    aes_score_counts: dict[str, int] = {}
    qs_uni_map: dict[str, int] = {}
    qs_top100_offers_count: int = 0
    student_codes_with_offers: set[str] = set()
    code_offer_counts: dict[str, int] = {}
    students_with_top100_codes: set[str] = set()

    for r in rows:
        code = (r[0] or "").strip() or None
        name = _normalize_name(r[1])
        uni = (r[2] or "Unknown").strip()
        otype = (r[3] or "").strip()
        aes = (r[5] or "").strip()

        # Attribute this offer to student_code(s): by code if set, else by name
        codes_this_offer: list[str] = [code] if code else (norm_to_codes.get(name) or [])
        for c in codes_this_offer:
            student_codes_with_offers.add(c)
            code_offer_counts[c] = code_offer_counts.get(c, 0) + 1

        university_counts[uni] = university_counts.get(uni, 0) + 1
        if otype in offer_type_counts:
            offer_type_counts[otype] += 1
        else:
            offer_type_counts["Unknown"] += 1
        if aes:
            aes_score_counts[_norm_aes(aes)] = aes_score_counts.get(_norm_aes(aes), 0) + 1

        rank = get_qs_rank(uni)
        if rank is not None:
            qs_top100_offers_count += 1
            if uni not in qs_uni_map or qs_uni_map[uni] > rank:
                qs_uni_map[uni] = rank
            for c in codes_this_offer:
                students_with_top100_codes.add(c)

    total_offers = len(rows)
    students_with_offers = sum(
        1 for students in by_pathway.values() for s in students
        if s["student_code"] in student_codes_with_offers
    )

    pathway_stats = []
    for pathway, students in by_pathway.items():
        count = len(students)
        with_offer = sum(1 for s in students if s["student_code"] in student_codes_with_offers)
        pathway_stats.append({
            "pathway": pathway,
            "total": count,
            "with_offer": with_offer,
            "without_offer": count - with_offer,
        })

    def _sort_key(item):
        s = item[0].replace("%", "").replace("IELTS", "").strip()
        try:
            return float(s)
        except ValueError:
            return 999
    top_unis = sorted(university_counts.items(), key=lambda x: -x[1])[:10]
    aes_dist = sorted(aes_score_counts.items(), key=_sort_key)

    missing_deduped = [
        {"student_code": s["student_code"], "student_name": s["student_name"], "pathway": s["pathway"]}
        for students in by_pathway.values()
        for s in students
        if s["student_code"] not in student_codes_with_offers
    ]

    multi = sorted(
        [{"name": code_to_name.get(code, code), "count": count} for code, count in code_offer_counts.items() if count > 1],
        key=lambda x: -x["count"],
    )

    qs_top100_offers = [
        {"university": uni, "rank": rank}
        for uni, rank in sorted(qs_uni_map.items(), key=lambda x: x[1])
    ]
    students_top100_count = sum(
        1 for students in by_pathway.values() for s in students
        if s["student_code"] in students_with_top100_codes
    )
    # % of QS 100 offers = (offers that are QS-ranked) / (total offers)
    qs_top100_offers_pct = round(qs_top100_offers_count / total_offers * 100) if total_offers else 0
    # % of students with at least one QS 100 offer
    qs_top100_students_pct = round(students_top100_count / total_students * 100) if total_students else 0

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
        "qs_top100_students_pct": qs_top100_students_pct,
        "qs_top100_offers_count": qs_top100_offers_count,
        "qs_top100_offers_pct": qs_top100_offers_pct,
        "qs_top100_offers": qs_top100_offers,
    }


@app.get("/api/universities")
def get_universities():
    """List universities with students (name + ID) who received an offer from each. Sorted by QS rank."""
    # Build name -> student_code from cohort so we can fill missing IDs
    try:
        by_pathway = get_grades_by_pathway(GRADES_EXCEL_PATH)
        norm_to_codes: dict[str, list[str]] = {}
        for students in by_pathway.values():
            for s in students:
                norm = _normalize_name(s.get("student_name") or s.get("english_name") or "")
                if norm:
                    norm_to_codes.setdefault(norm, []).append(s["student_code"])
    except Exception:
        norm_to_codes = {}

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT university, student_code, student_name FROM offers ORDER BY university, student_name"
        ).fetchall()
    uni_to_students: dict[str, list[dict[str, str]]] = {}
    uni_seen: dict[str, set[str]] = {}
    for uni, code, name in rows:
        uni = (uni or "").strip() or "Unknown"
        code = (code or "").strip() or ""
        name = (name or "").strip() or ""
        if not code and name:
            offer_norm = _normalize_name(name)
            codes = norm_to_codes.get(offer_norm, [])
            if not codes and offer_norm:
                # Match "Mulan RMIT" to cohort "Mulan": cohort name as word-prefix of offer name
                for cohort_norm, codelist in norm_to_codes.items():
                    if cohort_norm and (offer_norm == cohort_norm or offer_norm.startswith(cohort_norm + " ")):
                        codes = codelist
                        break
            code = codes[0] if codes else ""
        key = code if code else (name if name else None)
        if not key:
            continue
        if uni not in uni_to_students:
            uni_to_students[uni] = []
            uni_seen[uni] = set()
        if key not in uni_seen[uni]:
            uni_seen[uni].add(key)
            uni_to_students[uni].append({"student_code": code or "—", "student_name": name or "—"})
    # Sort by QS rank (lowest first), then unranked by name
    out = []
    for uni, students in uni_to_students.items():
        rank = get_qs_rank(uni)
        out.append({
            "university": uni,
            "qs_rank": rank,
            "students": students,
        })
    out.sort(key=lambda x: (x["qs_rank"] if x["qs_rank"] is not None else 9999, x["university"].lower()))
    return {"universities": out}


@app.get("/api/offers/all")
def get_all_offers(limit: int = 200):
    """List all offers in the DB (newest first). Use to verify uploads for students not in the grades Excel (e.g. Mulan)."""
    # Build name -> student_code from cohort so we can infer IDs for offers that
    # were uploaded without a student_code (older uploads, manual entries).
    try:
        by_pathway = get_grades_by_pathway(GRADES_EXCEL_PATH)
        norm_to_codes: dict[str, list[str]] = {}
        for students in by_pathway.values():
            for s in students:
                norm = _normalize_name(s.get("student_name") or s.get("english_name") or "")
                if norm:
                    norm_to_codes.setdefault(norm, []).append(s["student_code"])
    except Exception:
        norm_to_codes = {}

    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, student_code, student_name, university, course_name, course_code, offer_type, offer_date, file_name, created_at
            FROM offers ORDER BY created_at DESC LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
    offers: list[dict[str, str]] = []
    for r in rows:
        code = (r[1] or "").strip()
        name = (r[2] or "").strip()
        if not code and name:
            offer_norm = _normalize_name(name)
            codes = norm_to_codes.get(offer_norm, [])
            if not codes and offer_norm:
                # Match "Mulan RMIT" to cohort "Mulan": cohort name as word-prefix of offer name
                for cohort_norm, codelist in norm_to_codes.items():
                    if cohort_norm and (
                        offer_norm == cohort_norm or offer_norm.startswith(cohort_norm + " ")
                    ):
                        codes = codelist
                        break
            code = codes[0] if codes else ""
        offers.append(
            {
                "id": r[0],
                "student_code": code,
                "student_name": name,
                "university": r[3] or "",
                "course_name": r[4] or "",
                "course_code": r[5] or "",
                "offer_type": r[6] or "",
                "offer_date": r[7] or "",
                "file_name": r[8] or "",
                "created_at": r[9] or "",
            }
        )
    return {"total": len(offers), "offers": offers}


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
            "SELECT student_code, student_name, university, course_name, course_code, offer_type, offer_date,"
            " reply_deadline, subject_requirement, english_requirement,"
            " aes_overall, aes_listening, aes_reading, aes_writing, aes_speaking, required_scores_json"
            " FROM offers ORDER BY offer_date DESC"
        ).fetchall()

    code_to_offers: dict[str, list] = {}
    name_to_offers: dict[str, list] = {}
    for r in rows:
        code = (r[0] or "").strip() or None
        name = _normalize_name(r[1])
        req_scores: dict = {}
        try:
            if r[15]:
                req_scores = _json.loads(r[15])
        except Exception:
            pass
        offer_entry = {
            "university":          r[2]  or "",
            "course_name":         r[3]  or "",
            "course_code":         r[4]  or "",
            "offer_type":          r[5]  or "",
            "offer_date":          r[6]  or "",
            "subject_requirement": r[8]  or "",
            "english_requirement": r[9]  or "",
            "aes_overall":         r[10] or "",
            "aes_listening":       r[11] or "",
            "aes_reading":         r[12] or "",
            "aes_writing":         r[13] or "",
            "aes_speaking":        r[14] or "",
            "required_scores":     req_scores,
            "qs_rank":             get_qs_rank(r[2] or ""),
        }
        if code:
            code_to_offers.setdefault(code, []).append(offer_entry)
        if name:
            name_to_offers.setdefault(name, []).append(offer_entry)

    pathway_order = {"Business Mgmt": 0, "Media": 1, "Computing": 2}
    students = []
    for pathway, pathway_students in by_pathway.items():
        for s in pathway_students:
            norm = _normalize_name(s["student_name"] or s["english_name"])
            # Merge offers by code AND name so we show all (e.g. Durham with no code + Nottingham with code)
            code_offers = code_to_offers.get(s["student_code"], [])
            name_offers = name_to_offers.get(norm, []) if norm else []
            offers = _merge_offers(code_offers, name_offers)
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
async def import_grades_from_excel():
    """Import current grades into student_grades table from the configured Excel path."""
    from datetime import datetime

    path_to_use = GRADES_EXCEL_PATH

    try:
        students_with_grades = load_grades_excel_with_grades(path_to_use)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read Excel: {e}")

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
    return FileResponse(
        os.path.join(BASE, "static", "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
