#!/usr/bin/env python3
"""Bulk-upload offer PDFs and PNGs to the Bellerbys app via /api/upload.

Features:
  - Pre-checks existing offers on the server to skip duplicates BEFORE uploading
  - Matches by (student_code, university) using fuzzy keyword matching
  - Retries transient failures
  - Summarises results at the end

Usage:
    python bulk_upload.py <APP_URL> [FOLDER ...]
    python bulk_upload.py https://bellerbysdata-production.up.railway.app ./offers_folder
    python bulk_upload.py http://localhost:8000  # scans default temp dirs
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}
RETRY_COUNT = 2
DELAY_BETWEEN = 1.5  # seconds between uploads (Gemini rate limit)


def fetch_existing_offers(base_url: str) -> list[dict]:
    """GET /api/offers/all and return the list."""
    url = f"{base_url}/api/offers/all?limit=9999"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read()).get("offers", [])


def build_existing_index(offers: list[dict]) -> set[tuple[str, str]]:
    """Build a set of (student_code, university_lower) for dedup."""
    idx = set()
    for o in offers:
        code = (o.get("student_code") or "").strip()
        uni = (o.get("university") or "").strip().lower()
        if code and uni:
            idx.add((code, uni))
    return idx


def parse_filename(filename: str) -> tuple[str, str]:
    """Extract (student_code, university_hint) from a filename like
    '51111760-Jason - Southampton.png' or '51111759-Mulan-UWA.pdf'."""
    basename = Path(filename).stem
    m = re.match(r"(\d{8})", basename)
    code = m.group(1) if m else ""

    rest = re.sub(r"^\d{8}\s*[-–]\s*", "", basename)
    parts = re.split(r"\s*[-–]\s*", rest, maxsplit=1)
    uni_hint = parts[1].strip().lower() if len(parts) > 1 else ""

    if not uni_hint:
        tokens = rest.split()
        if len(tokens) > 1:
            uni_hint = " ".join(tokens[1:]).lower()

    return code, uni_hint


def is_likely_duplicate(code: str, uni_hint: str, existing: set[tuple[str, str]]) -> bool:
    """Check if (code, uni_hint) likely matches an existing offer using keyword overlap."""
    if not code or not uni_hint:
        return False

    hint_words = set(re.findall(r"[a-z]+", uni_hint))
    trivial = {"university", "of", "the", "and", "in"}
    hint_words -= trivial
    if not hint_words:
        hint_words = set(re.findall(r"[a-z]+", uni_hint))

    for ec, eu in existing:
        if ec != code:
            continue
        eu_words = set(re.findall(r"[a-z]+", eu))
        overlap = hint_words & eu_words
        if overlap and len(overlap) >= min(len(hint_words), 1):
            return True
    return False


def upload_file(base_url: str, filepath: Path) -> dict:
    """Upload a single file via multipart POST to /api/upload."""
    boundary = f"----BellerbysUpload{int(time.time() * 1000)}"
    filename = filepath.name
    file_data = filepath.read_bytes()

    ct = {".pdf": "application/pdf", ".png": "image/png",
          ".jpg": "image/jpeg", ".jpeg": "image/jpeg"
          }.get(filepath.suffix.lower(), "application/octet-stream")

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {ct}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{base_url}/api/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def collect_files(folders: list[str]) -> list[Path]:
    """Recursively collect offer files from the given folders."""
    files = []
    for folder in folders:
        p = Path(folder)
        if p.is_file() and p.suffix.lower() in ALLOWED_EXT:
            files.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in ALLOWED_EXT \
                        and "__MACOSX" not in str(f) and not f.name.startswith("."):
                    files.append(f)
    return files


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    folders = sys.argv[2:] if len(sys.argv) > 2 else [
        "/tmp/bellerbys_bulk_upload/aus",
        "/tmp/bellerbys_bulk_upload/ucas",
    ]

    files = collect_files(folders)
    if not files:
        print("No offer files found.")
        sys.exit(1)

    print(f"Found {len(files)} offer files")
    print(f"Fetching existing offers from {base_url} ...")
    try:
        existing_offers = fetch_existing_offers(base_url)
        existing_idx = build_existing_index(existing_offers)
        print(f"  {len(existing_offers)} offers already on server")
    except Exception as e:
        print(f"  Warning: could not fetch existing offers ({e}), skipping dedup")
        existing_idx = set()

    to_upload = []
    skipped_dup = []
    for f in files:
        code, uni_hint = parse_filename(f.name)
        if is_likely_duplicate(code, uni_hint, existing_idx):
            skipped_dup.append(f.name)
        else:
            to_upload.append(f)

    print(f"  {len(skipped_dup)} skipped (already on server)")
    print(f"  {len(to_upload)} to upload")
    print()

    if not to_upload:
        print("Nothing to upload — all files are already on the server.")
        return

    success, failed, server_dup = 0, 0, 0
    errors = []
    for i, f in enumerate(to_upload, 1):
        print(f"[{i}/{len(to_upload)}] {f.name} ... ", end="", flush=True)
        last_err = None
        for attempt in range(1 + RETRY_COUNT):
            try:
                result = upload_file(base_url, f)
                uni = result.get("university", "?")
                print(f"OK -> {uni}")
                success += 1
                last_err = None
                break
            except urllib.error.HTTPError as e:
                raw = e.read().decode()
                try:
                    detail = json.loads(raw).get("detail", raw)
                except Exception:
                    detail = raw
                if "duplicate" in str(detail).lower() or "already exists" in str(detail).lower():
                    print(f"SKIP (server duplicate)")
                    server_dup += 1
                    last_err = None
                    break
                last_err = (e.code, detail)
                if attempt < RETRY_COUNT:
                    print(f"RETRY ({e.code}) ", end="", flush=True)
                    time.sleep(3)
            except Exception as e:
                last_err = (0, str(e))
                if attempt < RETRY_COUNT:
                    print("RETRY ", end="", flush=True)
                    time.sleep(3)

        if last_err:
            print(f"FAIL ({last_err[0]}): {last_err[1]}")
            failed += 1
            errors.append((f.name, last_err[1]))

        time.sleep(DELAY_BETWEEN)

    print()
    print(f"Results: {success} uploaded, {len(skipped_dup) + server_dup} skipped (duplicate), {failed} failed")
    if errors:
        print("\nFailed files:")
        for name, detail in errors:
            print(f"  {name}: {detail}")


if __name__ == "__main__":
    main()
