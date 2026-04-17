"""
SQLite database for Bellerbys offer letters.
"""
import re
import sqlite3
import os
from contextlib import contextmanager

BASE = os.path.dirname(os.path.abspath(__file__))
_VOLUME = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or ""
DB_PATH = os.environ.get("BELLERBYS_DB", os.path.join(_VOLUME, "offers.db") if _VOLUME else os.path.join(BASE, "offers.db"))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _normalize_existing_universities(conn):
    """Migration: merge rows where university names differ only by casing/whitespace.
    Keeps the best display name (mixed-case preferred over ALL-CAPS/all-lower)."""
    rows = conn.execute("SELECT DISTINCT university FROM offers").fetchall()
    groups: dict[str, list[str]] = {}
    for (uni,) in rows:
        key = re.sub(r"\s+", " ", (uni or "").strip()).lower()
        if not key:
            continue
        groups.setdefault(key, []).append(uni)
    for _key, variants in groups.items():
        if len(variants) <= 1:
            continue
        best = variants[0]
        for v in variants[1:]:
            if best == best.upper() or best == best.lower():
                if v != v.upper() and v != v.lower():
                    best = v
        for v in variants:
            if v != best:
                conn.execute(
                    "UPDATE offers SET university = ? WHERE university = ?",
                    (best, v),
                )


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT,
                university TEXT NOT NULL,
                provider_code TEXT,
                course_name TEXT,
                course_code TEXT,
                course_start_date TEXT,
                point_of_entry TEXT,
                offer_type TEXT,
                offer_date TEXT,
                reply_deadline TEXT,
                offer_conditions TEXT,
                english_requirement TEXT,
                subject_requirement TEXT,
                contact_email TEXT,
                file_name TEXT,
                created_at TEXT NOT NULL,
                student_code TEXT,
                aes_overall TEXT,
                aes_listening TEXT,
                aes_reading TEXT,
                aes_writing TEXT,
                aes_speaking TEXT,
                required_scores_json TEXT
            )
        """)
        # Add new columns if upgrading from an older schema
        for col in (
            "english_requirement", "subject_requirement", "student_code",
            "aes_overall", "aes_listening", "aes_reading", "aes_writing", "aes_speaking",
            "required_scores_json",
        ):
            try:
                conn.execute(f"ALTER TABLE offers ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_university ON offers(university)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_student ON offers(student_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_student_code ON offers(student_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_offer_date ON offers(offer_date)")

        try:
            done = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_migrations'"
            ).fetchone()
            if not done:
                conn.execute("CREATE TABLE _migrations (name TEXT PRIMARY KEY)")
            already = conn.execute(
                "SELECT 1 FROM _migrations WHERE name='normalize_universities'"
            ).fetchone()
            if not already:
                _normalize_existing_universities(conn)
                conn.execute("INSERT INTO _migrations VALUES ('normalize_universities')")
        except Exception:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS student_grades (
                student_code TEXT NOT NULL,
                subject TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (student_code, subject)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_student_grades_code ON student_grades(student_code)")
