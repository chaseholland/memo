import subprocess
import click


def pdf_export_memo(path: str, days: int, folder: str = ""):
    if folder:
        note_collection = f"""
    -- Collect all folders matching the target name plus their subfolders
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
        -- Search all folders in default account for the target name
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

    -- Gather the target folder + all descendants
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
        set matchingNotes to {{}}
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

    {note_collection}

    tell application "Notes"
        activate
    end tell
    delay 1

    set savedFiles to {{}}
    set usedNames to {{}}

    repeat with theNote in matchingNotes
        tell application "Notes"
            set noteName to name of theNote as string
        end tell
        set cleanName to my cleanFileName(noteName)

        -- Deduplicate: append counter if name already used
        set baseName to cleanName
        set nameCounter to 1
        repeat while usedNames contains cleanName
            set nameCounter to nameCounter + 1
            set cleanName to baseName & "-" & nameCounter
        end repeat
        set end of usedNames to cleanName

        tell application "Notes"
            activate
            show theNote
        end tell
        delay 2

        tell application "System Events"
            tell process "Notes"
                set frontmost to true
                delay 0.5
                -- Wait for window with no sheets
                repeat 20 times
                    try
                        if (count of windows) > 0 and (count of sheets of window 1) = 0 then exit repeat
                    end try
                    delay 0.5
                end repeat
                delay 0.5
                -- Open print dialog
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
                -- Wait for save sheet
                repeat 20 times
                    try
                        if (count of sheets of sheet 1 of window 1) > 0 then exit repeat
                    end try
                    delay 0.5
                end repeat
                delay 1
                set saveSheet to sheet 1 of sheet 1 of window 1
                set saveSplitter to splitter group 1 of saveSheet
                -- Set filename only (not path)
                set value of text field "Save As:" of saveSplitter to cleanName
                delay 0.5
                -- Click Save (saves to whatever default location the dialog has)
                click button "Save" of saveSplitter
                delay 2
                -- Handle Replace if file exists
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

    -- Move all saved PDFs to the export folder
    -- The save dialog defaults to the last used location; find and move the files
    set homePath to POSIX path of (path to home folder)
    set searchPaths to {{homePath & "Desktop/", homePath & "Documents/", homePath & "Downloads/", homePath}}
    repeat with fileName in savedFiles
        set pdfName to fileName & ".pdf"
        set destPath to exportFolder & pdfName
        repeat with searchPath in searchPaths
            set srcPath to searchPath & pdfName
            try
                do shell script "test -f " & quoted form of srcPath
                do shell script "mv -f " & quoted form of srcPath & " " & quoted form of destPath
                exit repeat
            end try
        end repeat
    end repeat
    """
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        folder_msg = f" from folder '{folder}'" if folder else ""
        click.secho(
            f"\nNotes{folder_msg} modified in the last {days} days exported as PDF to {path}",
            fg="green",
        )
    else:
        click.secho("\nError exporting notes to PDF", fg="red")
        click.secho(f"Details: {result.stderr.strip()}", fg="red")
