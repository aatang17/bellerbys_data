"""
QS World University Rankings — load from 世界大学排名.xlsx if present, else fallback list.
Excel columns: 排名 (rank), 中文大学名称, 英文大学名称, 国家/地区.
"""
import os
import re

# Fallback: (rank, canonical name) — used when 世界大学排名.xlsx is not found
QS_TOP_100_FALLBACK: list[tuple[int, str]] = [
    (2,   "Imperial College London"),
    (3,   "University of Oxford"),
    (5,   "University of Cambridge"),
    (9,   "University College London (UCL)"),
    (34,  "University of Edinburgh"),
    (35,  "University of Manchester"),
    (37,  "King's College London"),
    (51,  "University of Bristol"),
    (74,  "University of Warwick"),
    (76,  "University of Birmingham"),
    (79,  "University of Glasgow"),
    (86,  "University of Leeds"),
    (87,  "University of Southampton"),
    (92,  "University of Sheffield"),
    (94,  "Durham University"),
    (97,  "University of Nottingham"),
    (110, "Queen Mary University of London"),
    (113, "University of St Andrews"),
    (132, "University of Bath"),
    (137, "Newcastle University"),
    (147, "University of Liverpool"),
    (155, "University of Exeter"),
    (157, "Lancaster University"),
    (169, "University of York"),
    (181, "Cardiff University"),
    (194, "University of Reading"),
    (199, "Queen's University Belfast"),
    (225, "Loughborough University"),
    (251, "University of Strathclyde"),
    (262, "University of Aberdeen"),
    (262, "University of Surrey"),
    (278, "University of Sussex"),
    (287, "Heriot-Watt University"),
    (292, "Swansea University"),
]


def _load_qs_from_excel() -> list[tuple[int, str]] | None:
    """Load (rank, English name) from 世界大学排名.xlsx (Sheet1, cols 0 and 2). Returns None if file missing or unreadable."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "世界大学排名.xlsx")
    if not os.path.isfile(path):
        return None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception:
        return None
    if len(rows) < 2:
        return None
    out: list[tuple[int, str]] = []
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        try:
            rank = int(row[0])
            name = (row[2] or "").strip() if len(row) > 2 else ""
            if name:
                out.append((rank, name))
        except (TypeError, ValueError):
            continue
    return out if out else None


_QS_DEDUPED: list[tuple[int, str]] = _load_qs_from_excel() or QS_TOP_100_FALLBACK

# ---------------------------------------------------------------------------
# Known abbreviations / alternate names → canonical words
# ---------------------------------------------------------------------------
_ABBREV: dict[str, str] = {
    "mit":     "massachusetts institute technology",
    "ucl":     "university college london",
    "lse":     "london school economics political science",
    "kcl":     "king college london",
    "eth":     "zurich federal institute technology",
    "epfl":    "ecole polytechnique lausanne",
    "nus":     "national university singapore",
    "ntu":     "nanyang technological university",
    "hku":     "university hong kong",
    "cuhk":    "chinese university hong kong",
    "hkust":   "hong kong university science technology",
    "anu":     "australian national university",
    "unsw":    "university new south wales",
    "kaist":   "korea advanced institute science technology",
    "ucla":    "university california los angeles",
    "ucsd":    "university california san diego",
    "ucsb":    "university california santa barbara",
    "uq":      "university queensland",
    "uts":     "university technology sydney",
    "tu delft": "delft university technology",
    "tu munich": "technical university munich",
    "tum":     "technical university munich",
    "snu":     "seoul national university",
    "pku":     "peking university",
}

# Words that indicate a non-QS-ranked institution (e.g. Oxford Brookes ≠ Oxford)
_DISQUALIFIERS: frozenset[str] = frozenset({
    "brookes", "metropolitan", "trent", "polytechnic",
    "hallam", "napier", "caledonian", "arts", "anglia",
    "solent", "sunderland", "teesside", "huddersfield",
    "coventry", "brighton", "portsmouth", "westminster",
    "middlesex", "kingston", "bedfordshire", "east london",
    "greenwich", "bolton", "derby", "wigan", "ulster",
    "london south bank", "de montfort",
})

_STOP: frozenset[str] = frozenset({"the", "of", "and", "for", "at", "in", "a", "an", "&"})


def _words(name: str) -> frozenset[str]:
    """Return significant words (no stop-words, no punctuation)."""
    s = name.lower()
    # Expand abbreviations
    for abbr, expansion in _ABBREV.items():
        if s.strip() == abbr or f" {abbr}" in s or s.startswith(abbr + " "):
            s = s.replace(abbr, expansion)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return frozenset(w for w in s.split() if w and w not in _STOP)


# Pre-compute word sets for all QS universities
_QS_ENTRIES: list[tuple[int, str, frozenset[str]]] = [
    (rank, name, _words(name)) for rank, name in _QS_DEDUPED
]


def get_qs_rank(university_name: str) -> int | None:
    """
    Return the QS rank for a university name, or None if not in the rankings list.
    Uses Jaccard similarity on significant words with a disqualifier blocklist.
    Rankings loaded from 世界大学排名.xlsx when present.
    """
    if not university_name or not university_name.strip():
        return None

    lower = university_name.lower()

    # Reject known non-QS variants immediately
    for bad in _DISQUALIFIERS:
        if bad in lower:
            return None

    offer_w = _words(university_name)
    if not offer_w:
        return None

    best_rank: int | None = None
    best_score: float = 0.0

    for rank, qs_name, qs_w in _QS_ENTRIES:
        inter = len(offer_w & qs_w)
        if inter == 0:
            continue
        union = len(offer_w | qs_w)
        score = inter / union if union else 0
        # Require ≥0.5 Jaccard AND at least one non-trivial word match
        if score >= 0.5 and score > best_score:
            best_score = score
            best_rank = rank

    return best_rank
