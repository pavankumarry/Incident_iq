"""
fix_bug.py — Restore the clean versions of ShopApp backend files from .bak backups.

Run from the project root:
    python scripts/fix_bug.py
"""

import os
import shutil

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")

FILES = [
    "routes/sessions.py",
    "routes/products.py",
    "routes/orders.py",
]


def restore(rel_path: str):
    src = os.path.join(BACKEND, rel_path + ".bak")
    dst = os.path.join(BACKEND, rel_path)
    if not os.path.exists(src):
        print(f"  [skip]    No backup found for {rel_path} — already clean?")
        return
    shutil.copy2(src, dst)
    os.remove(src)
    print(f"  [restore] {rel_path} (clean version restored, .bak removed)")


def main():
    print("=" * 60)
    print("fix_bug.py — Restoring clean ShopApp backend")
    print("=" * 60)
    print()
    for f in FILES:
        restore(f)
    print("\nAll files restored to clean state.")
    print("Restart the backend to apply changes:")
    print("  uvicorn backend.main:app --port 8001 --reload")


if __name__ == "__main__":
    main()
