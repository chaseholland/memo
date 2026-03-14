import os
import click
from memo_helpers.notestore_reader import find_paper_notes
from memo_helpers.stroke_parser import parse_bundle
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
                    render_strokes_pdf(note_title, stroke_data, output_file)
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


def _sanitize_filename(name):
    """Remove/replace characters that are invalid in filenames."""
    invalid = ':/\\<>"|?*'
    for ch in invalid:
        name = name.replace(ch, "-")
    if len(name) > 250:
        name = name[:250]
    return name
