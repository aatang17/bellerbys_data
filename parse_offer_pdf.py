"""
Extract structured data from offer letter images and PDFs using Gemini 2.5 Flash.
"""
import json
import os
import re

from google import genai
from google.genai import types
import PIL.Image


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT = """You are reading a university offer letter (UK, Australian, or other). Extract these fields and return ONLY a valid JSON object with exactly these keys:

{
  "university": "full provider/university name",
  "provider_code": "numeric or alphanumeric code next to the university name",
  "course_name": "full course title",
  "course_code": "course code (e.g. N201)",
  "offer_type": "Conditional or Unconditional",
  "offer_date": "date of offer in the format shown (e.g. 23 Feb 2026)",
  "course_start_date": "course start date",
  "point_of_entry": "year of entry e.g. Year 1, or semester/trimester for Australian letters",
  "reply_deadline": "application reply deadline if shown",
  "subject_requirement": "full academic/subject conditions text (e.g. ATAR, final grades, or foundation average for Australian offers)",
  "english_requirement": "concise English language requirement — just the test name and scores, e.g. 'IELTS 6.5 overall, 6.0 in all components', 'EAP 60%', or PTE/TOEFL. Remove URLs and policy links.",
  "aes_overall": "the overall score required for the English test. For IELTS/TOEFL use the band score (e.g. '6.5'). For EAP/AES use percentage (e.g. '60%'). Just the number.",
  "aes_listening": "minimum Listening score. For IELTS use band (e.g. '6.0'). For EAP use % (e.g. '50%'). If letter says 'all components' or 'all skills', use that value for all four.",
  "aes_reading": "minimum Reading score. Same rules as aes_listening.",
  "aes_writing": "minimum Writing score. Same rules as aes_listening.",
  "aes_speaking": "minimum Speaking score. Same rules as aes_listening.",
  "required_scores": {
    "SUBJECT NAME": "score",
    "...": "..."
  }
}

For required_scores: extract the minimum score required for EACH academic subject mentioned.
Use EXACTLY these subject name keys where applicable: "AES", "Business Management", "Economics", "Statistics with Project Skills", "Mathematics", "Physics", "Media Analysis", "Film Production", "Print & Digital News", and "Overall".
- CRITICAL: If the letter states an overall/final average (e.g. "70% overall", "with 70% overall", "final overall average of 70%", "obtaining a final overall average of 75%"), you MUST set "Overall" to that percentage (e.g. "Overall": "70%" or "75%").
- For subject-specific minimums: "60% in Mathematics or Statistics and project skills" → set "Statistics with Project Skills" and/or "Mathematics" to "60%" as stated.
- Include "AES" with the overall English score (e.g. EAP 60% overall → "AES": "60%").
- Use % for foundation/subject scores and band scores for IELTS/PTE (e.g. "6.5").
- Omit subjects not mentioned.

Rules:
- Return ONLY the JSON, no markdown, no explanation.
- Use null for any field not found. If the letter is Australian (e.g. RMIT, UQ, Monash), still extract university name, course/program name, offer type, dates, and conditions in the same key structure."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_code_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw


def _map_response(data: dict) -> dict:
    """Normalise raw Gemini JSON to the internal schema."""
    NULL_VALUES = {None, "null", "None", ""}

    req_scores = data.get("required_scores")
    if isinstance(req_scores, dict):
        req_scores = {k: v for k, v in req_scores.items() if v and v not in NULL_VALUES}
        req_scores_str = json.dumps(req_scores) if req_scores else None
    else:
        req_scores_str = None

    result = {
        "university":          data.get("university"),
        "provider_code":       data.get("provider_code"),
        "course_name":         data.get("course_name"),
        "course_code":         data.get("course_code"),
        "offer_type":          data.get("offer_type"),
        "offer_date":          data.get("offer_date"),
        "course_start_date":   data.get("course_start_date"),
        "point_of_entry":      data.get("point_of_entry"),
        "reply_deadline":      data.get("reply_deadline"),
        "offer_conditions":    None,
        "english_requirement": data.get("english_requirement"),
        "subject_requirement": data.get("subject_requirement"),
        "aes_overall":         data.get("aes_overall"),
        "aes_listening":       data.get("aes_listening"),
        "aes_reading":         data.get("aes_reading"),
        "aes_writing":         data.get("aes_writing"),
        "aes_speaking":        data.get("aes_speaking"),
        "required_scores_json": req_scores_str,
        "contact_email":       None,
    }
    return {k: v if v not in NULL_VALUES else None for k, v in result.items()}


def _gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Image extraction (PNG / JPG)
# ---------------------------------------------------------------------------

def parse_image_with_gemini(image_path: str) -> dict:
    """Send an image directly to Gemini 2.5 Flash vision."""
    client = _gemini_client()
    img = PIL.Image.open(image_path)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[_PROMPT, img],
    )
    data = json.loads(_strip_code_fences(response.text.strip()))
    return _map_response(data)


# ---------------------------------------------------------------------------
# PDF extraction (Gemini reads the whole PDF)
# ---------------------------------------------------------------------------

def parse_pdf_from_bytes(pdf_bytes: bytes) -> dict:
    """Send PDF bytes to Gemini for extraction. Use this for uploads so we parse exactly what was received."""
    if not pdf_bytes:
        raise ValueError("PDF file is empty")
    client = _gemini_client()
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[_PROMPT, pdf_part],
    )
    raw_text = (response.text or "").strip()
    data = json.loads(_strip_code_fences(raw_text))
    # Diagnostic: log what Gemini returned (so we can see why upload shows blank)
    _log_diagnostic("parse_pdf", {"pdf_len": len(pdf_bytes), "response_len": len(raw_text), "university": data.get("university"), "course_name": data.get("course_name"), "preview": raw_text[:400] if raw_text else ""})
    return _map_response(data)


def _log_diagnostic(tag: str, info: dict) -> None:
    try:
        log_path = os.path.join(os.path.dirname(__file__), "upload_diagnostic.log")
        with open(log_path, "a") as f:
            f.write(f"[{tag}] {json.dumps(info)}\n")
    except Exception:
        pass


def parse_pdf_from_path(pdf_path: str) -> dict:
    """Read a PDF from disk and send it to Gemini for extraction (e.g. for CLI or tests)."""
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    return parse_pdf_from_bytes(pdf_bytes)
