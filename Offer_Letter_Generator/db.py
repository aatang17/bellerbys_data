"""
SQLite database for Offer Letter Generator.
Stores global/fixed variables and generated letter history.
"""
import sqlite3
import os
from contextlib import contextmanager

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("OFFER_GENERATOR_DB", os.path.join(BASE, "offer_generator.db"))


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
            CREATE TABLE IF NOT EXISTS global_vars (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generated_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                student_name TEXT,
                dob TEXT,
                program TEXT,
                scholarship_amount TEXT,
                file_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_letters_created ON generated_letters(created_at)")
        # Seed default global vars if empty
        cur = conn.execute("SELECT COUNT(*) FROM global_vars")
        if cur.fetchone()[0] == 0:
            defaults = [
                ("Tuition_Fee", "CNY 158,000  （壹拾伍万捌仟元整）"),
                ("Tuition_Amount", "¥158,000"),
                ("Dormitory_Amount", "¥10,000"),
                ("Enrollment_Deposit", "CNY 20,000   （贰万元整）（Deductible from tuition fee）"),
                ("Deposit_Deadline", "1 May 2026"),
                ("Tuition_Deadline", "1 August 2026"),
                ("Payment_Deadline", "23 March 2026"),
                ("Payment_Deadline_ZH", "2026年3月23日"),
                ("Campus", "Beijing Normal-Hong Kong Baptist University (BNBU) 北师香港浸会大学"),
                ("Commencement", "14 September 2026"),
                ("Expected_Graduation", "30 June 2027"),
                ("Total_Amount", "¥148,000"),
            ]
            conn.executemany("INSERT OR IGNORE INTO global_vars (key, value) VALUES (?, ?)", defaults)
