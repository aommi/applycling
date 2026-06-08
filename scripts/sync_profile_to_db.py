#!/usr/bin/env python3
"""Sync local data/ profile files into a hosted user's Postgres row.

Reads the local source-of-truth files and writes them onto one user's row via
the normal store API (PostgresStore.save_user_profile). Use this to push an
updated resume / stories / profile (e.g. after a Resume OS sync) to the hosted
deployment, since data/* is gitignored and never ships in the image.

Files read (all optional except --user-id):
    data/profile.json    -> users.profile  (JSONB: name, contact, positioning, ...)
    data/resume.md       -> users.resume
    data/stories.md      -> users.stories
    <linkedin file>      -> users.linkedin_profile  (only with --linkedin PATH)

Backend selection is the same as the app: requires
    APPLYCLING_DB_BACKEND=postgres
    DATABASE_URL=postgresql://...
Run it wherever that DATABASE_URL points at the target DB (locally against a
tunnel, or on the VPS via `docker compose exec applycling`).

Usage:
    # dry run (default): show what WOULD change, write nothing
    python scripts/sync_profile_to_db.py --user-id <uuid>

    # actually write
    python scripts/sync_profile_to_db.py --user-id <uuid> --apply

    # also push LinkedIn text from a file, and pick which local fields to send
    python scripts/sync_profile_to_db.py --user-id <uuid> \
        --linkedin ../path/linkedin-profile-draft.md \
        --only resume,stories --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"

FIELDS = ("profile", "resume", "stories", "linkedin_profile")


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _preview(label: str, value, current) -> None:
    """Print a short before/after summary for one field."""
    def summarize(v):
        if v is None:
            return "(absent — leaving unchanged)"
        if isinstance(v, dict):
            return f"dict with {len(v)} keys"
        text = str(v)
        first = text.strip().splitlines()[0] if text.strip() else "(empty)"
        return f"{len(text)} chars — starts: {first[:70]!r}"

    print(f"  {label:18} {summarize(current)}  ->  {summarize(value)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-id", required=True,
                    help="UUID of the target users.id row")
    ap.add_argument("--apply", action="store_true",
                    help="actually write (default is a dry run)")
    ap.add_argument("--linkedin", metavar="PATH",
                    help="path to a LinkedIn markdown/text file to push")
    ap.add_argument("--only", metavar="F1,F2",
                    help=f"comma list, subset of {','.join(FIELDS)}; "
                         "default = all present files")
    ap.add_argument("--confirm-email", metavar="EMAIL",
                    help="must match the target row's email; required to --apply "
                         "when the row has an email (guards against wrong user)")
    args = ap.parse_args()

    if os.environ.get("APPLYCLING_DB_BACKEND") != "postgres":
        print("Refusing to run: APPLYCLING_DB_BACKEND must be 'postgres'.",
              file=sys.stderr)
        return 2
    if not os.environ.get("DATABASE_URL"):
        print("Refusing to run: DATABASE_URL is not set.", file=sys.stderr)
        return 2

    # Gather local values.
    profile_raw = _read_text(DATA / "profile.json")
    values: dict[str, object | None] = {
        "profile": json.loads(profile_raw) if profile_raw else None,
        "resume": _read_text(DATA / "resume.md"),
        "stories": _read_text(DATA / "stories.md"),
        "linkedin_profile": _read_text(Path(args.linkedin)) if args.linkedin else None,
    }

    if args.only:
        wanted = {f.strip() for f in args.only.split(",")}
        unknown = wanted - set(FIELDS)
        if unknown:
            print(f"Unknown field(s) in --only: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            return 2
        values = {k: (v if k in wanted else None) for k, v in values.items()}

    to_write = {k: v for k, v in values.items() if v is not None}
    if not to_write:
        print("Nothing to sync (no matching local files / fields present).")
        return 1

    from applycling import tracker

    store = tracker.get_store(user_id=args.user_id)
    try:
        current = store.load_user_profile()
    except Exception as e:  # noqa: BLE001 - surface any lookup failure plainly
        print(f"Could not load user {args.user_id}: {e}", file=sys.stderr)
        return 1

    print(f"Target user: {args.user_id}")
    print(f"Backend:     postgres ({os.environ['DATABASE_URL'].split('@')[-1]})")
    print(f"Mode:        {'APPLY (writing)' if args.apply else 'DRY RUN (no write)'}")
    print("Fields:")
    for f in FIELDS:
        if f in to_write:
            _preview(f, to_write[f], current.get(f))

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write these changes.")
        return 0

    # --- apply: identity confirmation + backup before writing ---
    current_email = ""
    if isinstance(current.get("profile"), dict):
        current_email = (current["profile"].get("email") or "").strip()
    display_name = current.get("display_name") or ""
    print(f"\nRow identity: email={current_email or '(none)'}  "
          f"display_name={display_name or '(none)'}")

    if current_email:
        if not args.confirm_email:
            print("Refusing to write: this row has an email. Pass --confirm-email "
                  "to confirm you are targeting the right user.", file=sys.stderr)
            return 2
        if args.confirm_email.strip().lower() != current_email.lower():
            print(f"Refusing to write: --confirm-email does not match the row email "
                  f"({current_email}).", file=sys.stderr)
            return 2

    # Back up the current row before overwriting, so an apply is reversible.
    import datetime
    backup_dir = ROOT / "data" / ".sync_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{args.user_id}-{ts}.json"
    backup_path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Backup of current row written to: {backup_path}")

    store.save_user_profile(**to_write)
    print("\nDone. Wrote: " + ", ".join(to_write))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
