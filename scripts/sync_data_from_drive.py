"""
Download pipeline data files from Google Drive to their expected local paths.

Run this at the start of any session on a new machine (or cloud environment)
before running any pipeline scripts.

    python scripts/sync_data_from_drive.py           # skip files that exist
    python scripts/sync_data_from_drive.py --force   # re-download everything
    python scripts/sync_data_from_drive.py --section raw_files   # one section only

File IDs are stored in src/config/drive_config.yaml. Upload your data to
Google Drive first, share each file/folder as "Anyone with the link can view",
then paste the IDs into that config file.
"""

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIVE_CONFIG = REPO_ROOT / "src" / "config" / "drive_config.yaml"
PLACEHOLDER = "FILL_IN_AFTER_UPLOAD"


def load_config() -> dict:
    if not DRIVE_CONFIG.exists():
        print(f"ERROR: Drive config not found at {DRIVE_CONFIG}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(DRIVE_CONFIG.read_text())


def sync_files(entries: list[dict], force: bool) -> tuple[int, int, int]:
    """Sync a list of file entries. Returns (downloaded, skipped, errored)."""
    from src.utils.drive_storage import download_file

    downloaded = skipped = errored = 0
    for entry in entries:
        local = REPO_ROOT / entry["local"]
        drive_id = entry["drive_id"]

        if drive_id == PLACEHOLDER:
            print(f"  [todo ] no Drive ID yet — {entry['local']}")
            skipped += 1
            continue

        print(f"  [file ] {entry['local']}")
        try:
            fetched = download_file(drive_id, local, force=force)
            if fetched:
                downloaded += 1
            else:
                skipped += 1
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            errored += 1

    return downloaded, skipped, errored


def sync_folders(entries: list[dict], force: bool) -> tuple[int, int, int]:
    """Sync a list of folder entries. Returns (downloaded, skipped, errored)."""
    from src.utils.drive_storage import download_folder

    downloaded = skipped = errored = 0
    for entry in entries:
        local = REPO_ROOT / entry["local"]
        drive_id = entry["drive_id"]

        if drive_id == PLACEHOLDER:
            print(f"  [todo ] no Drive ID yet — {entry['local']}/")
            skipped += 1
            continue

        print(f"  [dir  ] {entry['local']}/")
        try:
            fetched = download_folder(drive_id, local, force=force)
            if fetched:
                downloaded += 1
            else:
                skipped += 1
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            errored += 1

    return downloaded, skipped, errored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download files even if they already exist locally.",
    )
    parser.add_argument(
        "--section",
        choices=["raw_files", "raw_folders", "interim_files"],
        help="Only sync one section of the config (default: all).",
    )
    args = parser.parse_args()

    config = load_config()

    sections_to_run = (
        [args.section] if args.section else ["raw_files", "raw_folders", "interim_files"]
    )

    total_dl = total_skip = total_err = 0

    for section in sections_to_run:
        entries = config.get(section, [])
        if not entries:
            continue

        print(f"\n── {section} ({'force' if args.force else 'skip existing'}) ──")

        if section == "raw_folders":
            dl, sk, err = sync_folders(entries, force=args.force)
        else:
            dl, sk, err = sync_files(entries, force=args.force)

        total_dl += dl
        total_skip += sk
        total_err += err

    print(f"\nDone. downloaded={total_dl}  skipped={total_skip}  errors={total_err}")
    if total_err:
        sys.exit(1)


if __name__ == "__main__":
    main()
