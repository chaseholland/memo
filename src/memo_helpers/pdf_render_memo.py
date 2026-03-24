import os
import subprocess
import time
import click
from memo_helpers.notestore_reader import find_paper_notes
from memo_helpers.stroke_parser import count_bundle_rows, parse_bundle
from memo_helpers.stroke_renderer import render_fallback_pdf, render_strokes_pdf


def pdf_render_memo(path, days=None, folder="", title=None):
    """Headless PDF export of handwritten (paper) notes.

    Reads drawing data directly from the Apple Notes database and renders
    to PDF without opening the Notes app.
    """
    notes = find_paper_notes(title=title, folder=folder or None, days=days)

    if not notes:
        click.secho("\nNo handwritten notes found matching criteria.", fg="yellow")
        return

    # Touch each note via AppleScript to trigger CloudKit sync of Paper bundles
    _sync_notes(notes)

    os.makedirs(path, exist_ok=True)

    exported = 0
    for note in notes:
        note_title = note["note_title"] or "Untitled"
        safe_title = _sanitize_filename(note_title)
        output_file = os.path.join(path, f"{safe_title}.pdf")

        # Try stroke parsing first (fully headless), fall back to fallback image
        bundle = note.get("bundle_path")
        fallback = note.get("fallback_image_path")

        rendered = False
        if bundle:
            try:
                stroke_data = parse_bundle(bundle)
                if stroke_data and stroke_data["strokes"]:
                    if _stroke_data_complete(stroke_data, fallback):
                        render_strokes_pdf(note_title, stroke_data, output_file)
                        rendered = True
                    elif fallback:
                        render_fallback_pdf(note_title, fallback, output_file)
                        rendered = True
            except Exception as e:
                click.secho(f"\n  Stroke parse failed for '{note_title}': {e}", fg="yellow")

        if not rendered and fallback:
            render_fallback_pdf(note_title, fallback, output_file)
            rendered = True

        if not rendered:
            click.secho(f"\n  Skipping '{note_title}': no data source found.", fg="yellow")
            continue

        exported += 1
        click.echo(f"  Exported: {output_file}")

    folder_msg = f" from folder '{folder}'" if folder else ""
    title_msg = f" matching '{title}'" if title else ""
    click.secho(
        f"\n{exported} handwritten note(s){folder_msg}{title_msg} exported to {path}",
        fg="green",
    )


def _sync_notes(notes):
    """Trigger CloudKit sync for notes with incomplete Paper bundles.

    Snapshots each bundle's row count, triggers a sync via AppleScript,
    then polls up to 20s for any row counts to change — indicating that
    CloudKit has written new stroke data.
    """
    # Snapshot row counts for bundles that look small
    bundles_to_watch = {}
    for n in notes:
        bundle = n.get("bundle_path")
        title = n.get("note_title")
        if not bundle or not title:
            continue
        rows = count_bundle_rows(bundle)
        # Only watch bundles with few records (likely incomplete)
        if rows < 100:
            bundles_to_watch[bundle] = (title, rows)

    if not bundles_to_watch:
        return

    click.echo(
        f"  Syncing {len(bundles_to_watch)} note(s) with small bundles..."
    )

    # Trigger sync via AppleScript
    titles = [t for t, _ in bundles_to_watch.values()]
    escaped = [t.replace("\\", "\\\\").replace('"', '\\"') for t in titles]
    note_refs = "\n".join(
        f'        try\n'
        f'            get body of note "{t}"\n'
        f'        end try'
        for t in escaped
    )
    script = (
        'tell application "Notes"\n'
        f'{note_refs}\n'
        'end tell'
    )

    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=30,
        )
    except Exception:
        return  # sync is best-effort; completeness check is the safety net

    # Poll for up to 20s for any row counts to change
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(2)
        changed = False
        for bundle, (title, old_rows) in list(bundles_to_watch.items()):
            new_rows = count_bundle_rows(bundle)
            if new_rows != old_rows:
                click.echo(f"    Synced '{title}': {old_rows} -> {new_rows} rows")
                del bundles_to_watch[bundle]
                changed = True
        if not bundles_to_watch or changed:
            break


def _stroke_data_complete(stroke_data, fallback_path):
    """Check if parsed stroke data appears complete vs the fallback image.

    Partial iCloud syncs can leave bundles with only a few strokes while the
    fallback image shows the full note.  Detect this by comparing the vertical
    extent of the extracted strokes against the fallback image height.
    """
    if not fallback_path:
        return True  # no fallback to compare against, trust strokes

    all_ys = [pt["y"] for s in stroke_data["strokes"] for pt in s["points"]]
    if not all_ys:
        return False

    stroke_y_range = max(all_ys) - min(all_ys)

    try:
        from PIL import Image
        img = Image.open(fallback_path)
        # Fallback images are 2x resolution (1536px / 768 note units)
        fallback_note_height = img.size[1] / 2.0
        img.close()
    except Exception:
        return True

    # If strokes cover less than 10% of the fallback's content height,
    # the bundle data is likely incomplete from a partial sync.
    return stroke_y_range >= fallback_note_height * 0.1


def _sanitize_filename(name):
    """Remove/replace characters that are invalid in filenames."""
    invalid = ':/\\<>"|?*\n\r\t\x00'
    for ch in invalid:
        name = name.replace(ch, "-")
    if len(name) > 250:
        name = name[:250]
    return name
