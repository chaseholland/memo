import sqlite3
import os
import shutil
import tempfile
import glob as globmod
from datetime import datetime, timedelta


NOTES_BASE = os.path.expanduser(
    "~/Library/Group Containers/group.com.apple.notes"
)
NOTESTORE_PATH = os.path.join(NOTES_BASE, "NoteStore.sqlite")


def _copy_db(src):
    """Copy a sqlite DB to a temp file to avoid locking the live database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    shutil.copy2(src, tmp.name)
    return tmp.name


def _open_notestore():
    """Open a read-only copy of NoteStore.sqlite."""
    tmp_path = _copy_db(NOTESTORE_PATH)
    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    return conn, tmp_path


def find_paper_notes(title=None, folder=None, days=None):
    """Find notes that have com.apple.paper attachments.

    Returns a list of dicts with keys:
        note_pk, note_title, attachment_pk, attachment_uuid, account_uuid
    """
    conn, tmp_path = _open_notestore()
    try:
        # Find notes with paper attachments
        query = """
            SELECT
                note.Z_PK as note_pk,
                note.ZTITLE1 as note_title,
                att.Z_PK as attachment_pk,
                att.ZIDENTIFIER as attachment_uuid,
                att.ZTYPEUTI as type_uti,
                note.ZMODIFICATIONDATE1 as mod_date,
                note.ZMARKEDFORDELETION as deleted
            FROM ZICCLOUDSYNCINGOBJECT att
            JOIN ZICCLOUDSYNCINGOBJECT note ON att.ZNOTE = note.Z_PK
            WHERE att.ZTYPEUTI IN ('com.apple.paper', 'com.apple.drawing.2')
              AND (note.ZMARKEDFORDELETION IS NULL OR note.ZMARKEDFORDELETION = 0)
        """
        params = []

        if title:
            query += " AND note.ZTITLE1 LIKE ?"
            params.append(f"%{title}%")

        if days:
            # Apple stores dates as seconds since 2001-01-01 (Core Data epoch)
            epoch_2001 = datetime(2001, 1, 1)
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_cd = (cutoff - epoch_2001).total_seconds()
            query += " AND note.ZMODIFICATIONDATE1 > ?"
            params.append(cutoff_cd)

        query += " ORDER BY note.ZMODIFICATIONDATE1 DESC"

        rows = conn.execute(query, params).fetchall()

        # Resolve account UUID (needed for file paths)
        accounts_dir = os.path.join(NOTES_BASE, "Accounts")
        account_uuids = []
        if os.path.isdir(accounts_dir):
            account_uuids = [
                d for d in os.listdir(accounts_dir)
                if os.path.isdir(os.path.join(accounts_dir, d))
                and not d.startswith(".")
            ]

        results = []
        for row in rows:
            att_uuid = row["attachment_uuid"]
            if not att_uuid:
                continue

            # Find which account has this paper bundle or fallback image
            for acct_uuid in account_uuids:
                bundle_path = _paper_bundle_path(acct_uuid, att_uuid)
                fallback_path = _fallback_image_path(acct_uuid, att_uuid)

                if bundle_path or fallback_path:
                    results.append({
                        "note_pk": row["note_pk"],
                        "note_title": row["note_title"],
                        "attachment_pk": row["attachment_pk"],
                        "attachment_uuid": att_uuid,
                        "type_uti": row["type_uti"],
                        "account_uuid": acct_uuid,
                        "bundle_path": bundle_path,
                        "fallback_image_path": fallback_path,
                    })
                    break

        if folder:
            results = _filter_by_folder(conn, results, folder)

        return results
    finally:
        conn.close()
        os.unlink(tmp_path)


def _filter_by_folder(conn, results, folder):
    """Filter results to only include notes in the given folder (or subfolders)."""
    # Get folder names for each note via the ZSECTION (folder) FK
    note_pks = [r["note_pk"] for r in results]
    if not note_pks:
        return results

    placeholders = ",".join("?" * len(note_pks))
    folder_query = f"""
        SELECT note.Z_PK as note_pk, folder.ZTITLE2 as folder_name
        FROM ZICCLOUDSYNCINGOBJECT note
        JOIN ZICCLOUDSYNCINGOBJECT folder ON note.ZFOLDER = folder.Z_PK
        WHERE note.Z_PK IN ({placeholders})
    """
    rows = conn.execute(folder_query, note_pks).fetchall()
    note_folders = {row["note_pk"]: row["folder_name"] for row in rows}

    return [
        r for r in results
        if note_folders.get(r["note_pk"], "").lower() == folder.lower()
    ]


def _paper_bundle_path(account_uuid, attachment_uuid):
    """Resolve the path to a Paper bundle's data.sqlite3, or None."""
    path = os.path.join(
        NOTES_BASE, "Accounts", account_uuid,
        "Paper", "Bundles", f"{attachment_uuid}.bundle",
        "Database", "data.sqlite3"
    )
    return path if os.path.isfile(path) else None


def _fallback_image_path(account_uuid, attachment_uuid):
    """Find the fallback image PNG for an attachment, or None."""
    pattern = os.path.join(
        NOTES_BASE, "Accounts", account_uuid,
        "FallbackImages", attachment_uuid, "*", "FallbackImage.png"
    )
    matches = globmod.glob(pattern)
    return matches[0] if matches else None
