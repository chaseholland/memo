import subprocess
import click


def pdf_export_memo(path: str, days: int):
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

    tell application "Notes"
        repeat with theNote in notes of default account
            set noteLocked to password protected of theNote as boolean
            if not noteLocked then
                set modDate to modification date of theNote
                if modDate > cutoffDate then
                    set noteName to name of theNote as string
                    set noteBody to body of theNote as string
                    set cleanName to my cleanFileName(noteName)
                    set pdfPath to exportFolder & cleanName & ".pdf"

                    set noteContent to "<html><head><meta charset=\\"UTF-8\\"></head><body>" & noteBody & "</body></html>"
                    set tempFilePath to exportFolder & cleanName & "_temp.html"
                    set f to open for access (POSIX file tempFilePath) with write permission
                    set eof of f to 0
                    write noteContent to f
                    close access f

                    do shell script "/usr/sbin/cupsfilter " & quoted form of tempFilePath & " > " & quoted form of pdfPath & " 2>/dev/null"
                    do shell script "rm -f " & quoted form of tempFilePath
                end if
            end if
        end repeat
    end tell
    """
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        click.secho(f"\nNotes modified in the last {days} days exported as PDF to {path}", fg="green")
    else:
        click.secho("\nError exporting notes to PDF", fg="red")
