#!/usr/bin/env python3
"""Download the latest offers.db from Railway to sync locally.

Usage:
    python sync_from_railway.py                          # uses RAILWAY_URL env var
    python sync_from_railway.py https://your-app.railway.app
    RESTORE_SECRET=mysecret python sync_from_railway.py  # if secret is set on Railway
"""
import os
import shutil
import sys
import urllib.request
import urllib.error

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RAILWAY_URL", "")
    if not url:
        print("Usage: python sync_from_railway.py <RAILWAY_URL>")
        print("   or: set RAILWAY_URL env var")
        sys.exit(1)

    url = url.rstrip("/")
    token = os.environ.get("RESTORE_SECRET", "")
    export_url = f"{url}/api/admin/export-db"
    if token:
        export_url += f"?token={token}"

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offers.db")

    print(f"Downloading from {url}/api/admin/export-db ...")
    try:
        req = urllib.request.Request(export_url)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}")
        sys.exit(1)

    if len(data) < 1000:
        print(f"Downloaded file too small ({len(data)} bytes), aborting.")
        sys.exit(1)

    if os.path.exists(db_path):
        backup = db_path + ".local-bak"
        shutil.copy2(db_path, backup)
        print(f"Backed up existing DB to {backup}")

    with open(db_path, "wb") as f:
        f.write(data)
    print(f"Saved {len(data):,} bytes to {db_path}")
    print("Sync complete.")

if __name__ == "__main__":
    main()
