"""
Google Drive download/upload utilities.

Downloads use gdown with shareable links — no credentials required as long as
the file/folder is shared as "Anyone with the link can view".

Usage:
    from src.utils.drive_storage import download_file, download_folder
    download_file("1abc...", Path("data/raw/some_file.csv"))
    download_folder("1xyz...", Path("data/raw/rankings/redraft_adp"))
"""

from pathlib import Path


def download_file(drive_id: str, local_path: Path, force: bool = False) -> bool:
    """Download a single file from Google Drive.

    Args:
        drive_id: The Google Drive file ID (from the share link).
        local_path: Where to save the file locally.
        force: Re-download even if the file already exists.

    Returns:
        True if the file was downloaded, False if skipped (already exists).
    """
    try:
        import gdown
    except ImportError:
        raise ImportError("gdown is required: pip install gdown")

    if local_path.exists() and not force:
        print(f"  [skip] already exists: {local_path}")
        return False

    local_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/uc?id={drive_id}"
    result = gdown.download(url, str(local_path), quiet=False, fuzzy=True)
    if result is None:
        raise RuntimeError(
            f"Download failed for Drive ID {drive_id!r}. "
            "Check that the file is shared as 'Anyone with the link'."
        )
    return True


def download_folder(folder_id: str, local_dir: Path, force: bool = False) -> bool:
    """Download an entire Google Drive folder.

    Args:
        folder_id: The Google Drive folder ID (last segment of the folder URL).
        local_dir: Local directory to download into. Contents are placed directly
                   inside this directory (not in a subfolder).
        force: Re-download even if files already exist.

    Returns:
        True if any files were downloaded, False if all were skipped.
    """
    try:
        import gdown
    except ImportError:
        raise ImportError("gdown is required: pip install gdown")

    if local_dir.exists() and any(local_dir.iterdir()) and not force:
        print(f"  [skip] folder already populated: {local_dir}")
        return False

    local_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    result = gdown.download_folder(url, output=str(local_dir), quiet=False, use_cookies=False)
    if result is None:
        raise RuntimeError(
            f"Folder download failed for Drive folder ID {folder_id!r}. "
            "Check that the folder is shared as 'Anyone with the link'."
        )
    return True
