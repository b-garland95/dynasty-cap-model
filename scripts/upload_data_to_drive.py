"""
Upload generated pipeline outputs back to Google Drive.

This script requires Google Drive API credentials (a service account JSON key
or OAuth2 client secrets). It is optional — you can also upload files manually
by dragging them into the appropriate Drive folder.

SETUP (one-time):
  1. Go to https://console.cloud.google.com → APIs & Services → Credentials.
  2. Create a Service Account, download the JSON key.
  3. Save the key as  credentials/drive_service_account.json  (gitignored).
  4. Share your Drive data folder with the service account's email address.

USAGE:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
  python scripts/upload_data_to_drive.py --section interim_files
  python scripts/upload_data_to_drive.py --section raw_files

The Drive IDs in src/config/drive_config.yaml are used to identify which
Drive file to overwrite. If a file doesn't have a Drive ID yet, this script
will print its path and skip it.
"""

import argparse
import mimetypes
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIVE_CONFIG = REPO_ROOT / "src" / "config" / "drive_config.yaml"
CREDENTIALS_PATH = REPO_ROOT / "credentials" / "drive_service_account.json"
PLACEHOLDER = "FILL_IN_AFTER_UPLOAD"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API client libraries required:\n"
            "  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"Service account key not found at {CREDENTIALS_PATH}.\n"
            "See the SETUP instructions at the top of this script."
        )

    creds = service_account.Credentials.from_service_account_file(
        str(CREDENTIALS_PATH), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def upload_file(service, drive_id: str, local_path: Path) -> None:
    from googleapiclient.http import MediaFileUpload

    mime_type, _ = mimetypes.guess_type(str(local_path))
    mime_type = mime_type or "application/octet-stream"
    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
    service.files().update(fileId=drive_id, media_body=media).execute()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--section",
        choices=["raw_files", "interim_files"],
        help="Section of drive_config.yaml to upload (default: interim_files).",
        default="interim_files",
    )
    args = parser.parse_args()

    config = yaml.safe_load(DRIVE_CONFIG.read_text())
    entries = config.get(args.section, [])

    if not entries:
        print(f"No entries found under '{args.section}' in drive_config.yaml.")
        sys.exit(0)

    print("Connecting to Google Drive...")
    service = get_drive_service()

    uploaded = skipped = errored = 0

    print(f"\n── uploading {args.section} ──")
    for entry in entries:
        local = REPO_ROOT / entry["local"]
        drive_id = entry["drive_id"]

        if drive_id == PLACEHOLDER:
            print(f"  [todo ] no Drive ID — {entry['local']}")
            skipped += 1
            continue

        if not local.exists():
            print(f"  [miss ] local file not found — {entry['local']}")
            skipped += 1
            continue

        print(f"  [up   ] {entry['local']}")
        try:
            upload_file(service, drive_id, local)
            uploaded += 1
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            errored += 1

    print(f"\nDone. uploaded={uploaded}  skipped={skipped}  errors={errored}")
    if errored:
        sys.exit(1)


if __name__ == "__main__":
    main()
