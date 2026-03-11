import subprocess
import os
import glob
import shutil
import click


def move_pdfs_to_export_folder(saved_files: list, export_folder: str) -> int:
    """Move exported PDFs from common default save locations to export_folder.

    Searches ~/Desktop, ~/Documents, ~/Downloads, and ~/ in order, then falls
    back to a recursive search (max depth 4) under ~/ if not found.

    Returns the count of successfully moved files.
    """
    home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
        home,
    ]

    moved = 0
    for file_name in saved_files:
        pdf_name = file_name + ".pdf"
        dest = os.path.join(export_folder, pdf_name)
        found = False
        for search_dir in search_dirs:
            src = os.path.join(search_dir, pdf_name)
            if os.path.isfile(src):
                shutil.move(src, dest)
                moved += 1
                found = True
                break
        if not found:
            home_depth = len(os.path.normpath(home).split(os.sep))
            for match in glob.glob(os.path.join(home, "**", pdf_name), recursive=True):
                match_depth = len(os.path.normpath(match).split(os.sep))
                if match_depth - home_depth <= 4:
                    shutil.move(match, dest)
                    moved += 1
                    break
    return moved


def pdf_export_memo(path: str, days: int, folder: str = ""):
    if folder:
        note_collection = f"""
    on collectSubfolders(parentFolder, folderList)
        tell application "Notes"
            repeat with childFolder in folders of parentFolder
                set end of folderList to childFolder
                my collectSubfolders(childFolder, folderList)
            end repeat
        end tell
        return folderList
    end collectSubfolders

    tell application "Notes"
        set targetFolderRef to missing value
        set allFolders to every folder of default account
        repeat with f in allFolders
            if name of f is "{folder}" then
                set targetFolderRef to f
                exit repeat
            end if
        end repeat
        if targetFolderRef is missing value then
            error "Folder \\"{folder}\\" not found"
        end if
    end tell

    set foldersToExport to {{targetFolderRef}}
    my collectSubfolders(targetFolderRef, foldersToExport)

    set matchingNotes to {{}}
    tell application "Notes"
        repeat with aFolder in foldersToExport
            repeat with theNote in notes of aFolder
                set noteLocked to password protected of theNote as boolean
                if not noteLocked then
                    set modDate to modification date of theNote
                    if modDate > cutoffDate then
                        set end of matchingNotes to theNote
                    end if
                end if
            end repeat
        end repeat
    end tell"""
    else:
        note_collection = """
    tell application "Notes"
        set matchingNotes to {}
        repeat with theNote in notes of default account
            set noteLocked to password protected of theNote as boolean
            if not noteLocked then
                set modDate to modification date of theNote
                if modDate > cutoffDate then
                    set end of matchingNotes to theNote
                end if
            end if
        end repeat
    end tell"""

    script = f"""
    set exportFolder to "{path}"
    do shell script "mkdir -p " & quoted form of exportFolder

    on cleanFileName(t)
        set prevTIDs to text item delimiters of AppleScript
        set text item delimiters to ":"
        set t to text items of t
        set text item delimiters to "-"
        set t to "" & t
        set text item delimiters to "/"
        set t to text items of t
        set text item delimiters to "-"
        set t to "" & t
        set text item delimiters to prevTIDs
        if length of t > 250 then
            set t to text 1 thru 250 of t
        end if
        return t
    end cleanFileName

    set cutoffDate to (current date) - ({days} * days)
    set exportTimestamp to do shell script "date '+%Y-%m-%d_%H-%M-%S'"

    {note_collection}

    tell application "Notes"
        activate
    end tell
    delay 1

    set savedFiles to {{}}

    repeat with theNote in matchingNotes
        tell application "Notes"
            set noteName to name of theNote as string
        end tell
        set cleanName to exportTimestamp & " - " & my cleanFileName(noteName)
        if length of cleanName > 250 then
            set cleanName to text 1 thru 250 of cleanName
        end if

        tell application "Notes"
            activate
            show theNote
        end tell
        delay 15

        tell application "System Events"
            tell process "Notes"
                set frontmost to true
                delay 0.5
                repeat 20 times
                    try
                        if (count of windows) > 0 and (count of sheets of window 1) = 0 then exit repeat
                    end try
                    delay 0.5
                end repeat
                delay 0.5
                keystroke "p" using command down
                repeat 20 times
                    try
                        if (count of sheets of window 1) > 0 then exit repeat
                    end try
                    delay 0.5
                end repeat
                delay 1
                set printSheet to splitter group 1 of sheet 1 of window 1
                set pdfMenuBtn to menu button 1 of group 2 of printSheet
                click pdfMenuBtn
                delay 0.5
                click menu item 1 of menu 1 of pdfMenuBtn
                repeat 20 times
                    try
                        if (count of sheets of sheet 1 of window 1) > 0 then exit repeat
                    end try
                    delay 0.5
                end repeat
                delay 1
                set saveSheet to sheet 1 of sheet 1 of window 1
                set saveSplitter to splitter group 1 of saveSheet
                set value of text field "Save As:" of saveSplitter to cleanName
                delay 0.5
                click button "Save" of saveSplitter
                delay 2
                try
                    if (count of sheets of saveSheet) > 0 then
                        click button "Replace" of sheet 1 of saveSheet
                        delay 1
                    end if
                end try
                delay 1
            end tell
        end tell

        set end of savedFiles to cleanName
    end repeat

    -- Return saved filenames for Python to move to the target folder
    set output to ""
    repeat with fileName in savedFiles
        if output is not "" then
            set output to output & "\\n"
        end if
        set output to output & fileName
    end repeat
    return output
    """

    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        saved_files = [f for f in result.stdout.strip().split("\n") if f]
        os.makedirs(path, exist_ok=True)
        move_pdfs_to_export_folder(saved_files, path)
        folder_msg = f" from folder '{folder}'" if folder else ""
        click.secho(
            f"\n{len(saved_files)} note(s){folder_msg} modified in the last {days} days exported as PDF to {path}",
            fg="green",
        )
    else:
        click.secho("\nError exporting notes to PDF", fg="red")
        click.secho(f"Details: {result.stderr.strip()}", fg="red")
