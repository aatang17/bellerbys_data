"""
SQLite database for Bellerbys offer letters.
"""
import sqlite3
import os
from contextlib import contextmanager

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BELLERBYS_DB", os.path.join(BASE, "offers.db"))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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
                created_at TEXT NOT NULL
            )
        """)
        # Add new columns if upgrading from an older schema
        for col in ("english_requirement", "subject_requirement"):
            try:
                conn.execute(f"ALTER TABLE offers ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_university ON offers(university)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_student ON offers(student_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_offer_date ON offers(offer_date)")

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
