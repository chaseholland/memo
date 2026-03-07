from click.testing import CliRunner
from memo.memo import cli
from memo_helpers.pdf_export_memo import move_pdfs_to_export_folder
from unittest.mock import patch, MagicMock
import os


# --- CLI option tests ---


def test_pdf_export_requires_days_argument():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export"])
    assert result.exit_code == 2
    assert "requires an argument" in result.output or "Missing" in result.output


def test_pdf_export_rejects_non_integer_days():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "abc"])
    assert result.exit_code == 2


def test_pdf_export_rejects_zero_days():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "0"])
    assert result.exit_code != 0


def test_pdf_export_rejects_negative_days():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "-1"])
    assert result.exit_code != 0


def test_pdf_export_cannot_combine_with_edit():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7", "--edit"])
    assert result.exit_code == 2


def test_pdf_export_cannot_combine_with_delete():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7", "--delete"])
    assert result.exit_code == 2


def test_pdf_export_cannot_combine_with_export():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7", "--export"])
    assert result.exit_code == 2


def test_pdf_export_user_declines_confirmation():
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7"], input="n\n")
    assert result.exit_code == 0


# --- PDF export function tests ---


@patch("subprocess.run")
def test_pdf_export_default_path(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    assert result.exit_code == 0


@patch("subprocess.run")
def test_pdf_export_custom_path(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["notes", "--pdf-export", "7"], input="y\nn\n/tmp/test_export\n"
    )
    assert result.exit_code == 0


@patch("subprocess.run")
def test_pdf_export_calls_osascript(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "30"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    assert len(osascript_calls) > 0


@patch("subprocess.run")
def test_pdf_export_filters_by_modification_date(mock_subprocess):
    """The AppleScript should filter notes by modification date, not creation date."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "14"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    script_text = str(osascript_calls)
    assert "modification date" in script_text


@patch("subprocess.run")
def test_pdf_export_uses_correct_day_range(mock_subprocess):
    """The day range passed to the CLI should appear in the AppleScript date filter."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "21"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    script_text = str(osascript_calls)
    assert "21" in script_text


@patch("subprocess.run")
def test_pdf_export_reads_note_name(mock_subprocess):
    """Should read the note name to use as the PDF filename."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    script_text = str(osascript_calls)
    assert "name of theNote" in script_text


@patch("subprocess.run")
def test_pdf_export_does_not_modify_note_body(mock_subprocess):
    """Export must be read-only. The AppleScript should never set/write note properties."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    for c in osascript_calls:
        script = str(c)
        # Should never set the body or name of a note
        assert "set body of" not in script
        assert "set name of" not in script


@patch("subprocess.run")
def test_pdf_export_does_not_delete_notes(mock_subprocess):
    """Export must not delete any notes."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    for c in osascript_calls:
        script = str(c)
        assert "delete" not in script.lower()


@patch("subprocess.run")
def test_pdf_export_does_not_move_notes(mock_subprocess):
    """Export must not move notes between folders."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    for c in osascript_calls:
        script = str(c)
        assert "move" not in script.lower() or "move note" not in script.lower()


@patch("subprocess.run")
def test_pdf_export_preserves_note_content_unchanged(mock_subprocess):
    """The export script should only read note properties, never write them back."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "5"], input="y\ny\n")
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    for c in osascript_calls:
        script = str(c)
        # Should not use 'set' on any note property
        assert "set body" not in script
        assert "set plaintext" not in script
        assert "set html" not in script


@patch("subprocess.run")
def test_pdf_export_handles_osascript_failure(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=1, stderr="error", stdout="")
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    assert "error" in result.output.lower() or result.exit_code != 0


@patch("subprocess.run")
def test_pdf_export_success_message(mock_subprocess):
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    assert "export" in result.output.lower() or "pdf" in result.output.lower()


# --- Folder filter tests ---


def _get_osascript_text(mock_subprocess):
    """Extract the AppleScript text from the osascript subprocess call."""
    calls = mock_subprocess.call_args_list
    osascript_calls = [c for c in calls if c[0][0][0] == "osascript"]
    assert len(osascript_calls) > 0
    return osascript_calls[0][0][0][2]  # ["osascript", "-e", <script>]


@patch("subprocess.run")
def test_pdf_export_with_folder_gets_notes_from_folder_directly(mock_subprocess):
    """When --folder is specified, the script should get notes from that folder directly."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Work"], input="y\ny\n"
    )
    script = _get_osascript_text(mock_subprocess)
    assert 'name of f is "Work"' in script
    assert "notes of aFolder" in script


@patch("subprocess.run")
def test_pdf_export_without_folder_iterates_all_notes(mock_subprocess):
    """When no --folder is specified, the script should iterate notes of default account."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    script = _get_osascript_text(mock_subprocess)
    assert "notes of default account" in script
    assert "collectSubfolders" not in script


@patch("subprocess.run")
def test_pdf_export_folder_matches_by_name(mock_subprocess):
    """The folder filter should find the folder by comparing names."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Projects"], input="y\ny\n"
    )
    script = _get_osascript_text(mock_subprocess)
    assert 'name of f is "Projects"' in script


@patch("subprocess.run")
def test_pdf_export_folder_collects_subfolders_recursively(mock_subprocess):
    """The folder filter should recursively collect subfolders for export."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Work"], input="y\ny\n"
    )
    script = _get_osascript_text(mock_subprocess)
    assert "collectSubfolders" in script
    assert "folders of parentFolder" in script


@patch("subprocess.run")
def test_pdf_export_folder_errors_if_not_found(mock_subprocess):
    """The script should error if the specified folder does not exist."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Work"], input="y\ny\n"
    )
    script = _get_osascript_text(mock_subprocess)
    assert 'Folder \\"Work\\" not found' in script or "not found" in script.lower()


@patch("subprocess.run")
def test_pdf_export_without_folder_has_no_subfolder_logic(mock_subprocess):
    """Without --folder, there should be no subfolder collection logic."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    script = _get_osascript_text(mock_subprocess)
    assert "collectSubfolders" not in script
    assert "foldersToExport" not in script


@patch("subprocess.run")
def test_pdf_export_folder_confirm_message_includes_folder(mock_subprocess):
    """The confirmation prompt should mention the folder name when filtering."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Recipes"], input="y\ny\n"
    )
    assert "Recipes" in result.output


@patch("subprocess.run")
def test_pdf_export_folder_confirm_message_without_folder(mock_subprocess):
    """Without --folder, the confirmation prompt should not mention any folder."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    result = runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    assert "from folder" not in result.output


@patch("subprocess.run")
def test_pdf_export_folder_success_message_includes_folder(mock_subprocess):
    """The success message should mention the folder when one was specified."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Recipes"], input="y\ny\n"
    )
    assert "from folder 'Recipes'" in result.output


@patch("subprocess.run")
def test_pdf_export_folder_does_not_hardcode_wrong_folder(mock_subprocess):
    """The script should use the user-specified folder, not a hardcoded value."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(
        cli, ["notes", "--pdf-export", "7", "--folder", "Travel"], input="y\ny\n"
    )
    script = _get_osascript_text(mock_subprocess)
    assert 'name of f is "Travel"' in script
    assert "Work" not in script
    assert "Projects" not in script


@patch("subprocess.run")
def test_pdf_export_filenames_include_timestamp(mock_subprocess):
    """Exported filenames should include a timestamp prefix to prevent conflicts."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    script = _get_osascript_text(mock_subprocess)
    assert "exportTimestamp" in script


@patch("subprocess.run")
def test_pdf_export_uses_print_to_pdf(mock_subprocess):
    """Should use macOS print-to-PDF GUI automation via System Events."""
    mock_subprocess.return_value = MagicMock(returncode=0, stderr="", stdout="")
    runner = CliRunner()
    runner.invoke(cli, ["notes", "--pdf-export", "7"], input="y\ny\n")
    script = _get_osascript_text(mock_subprocess)
    assert "keystroke" in script
    assert "System Events" in script


# --- move_pdfs_to_export_folder tests ---


def test_move_finds_file_in_documents(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    dest = tmp_path / "export"
    dest.mkdir()
    (docs / "2026-01-01_10-00-00 - My Note.pdf").write_text("pdf")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    moved = move_pdfs_to_export_folder(
        ["2026-01-01_10-00-00 - My Note"],
        str(dest) + "/",
    )

    assert moved == 1
    assert (dest / "2026-01-01_10-00-00 - My Note.pdf").exists()
    assert not (docs / "2026-01-01_10-00-00 - My Note.pdf").exists()


def test_move_finds_file_in_desktop(tmp_path, monkeypatch):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    dest = tmp_path / "export"
    dest.mkdir()
    (desktop / "note.pdf").write_text("pdf")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    moved = move_pdfs_to_export_folder(["note"], str(dest) + "/")

    assert moved == 1
    assert (dest / "note.pdf").exists()


def test_move_finds_file_in_downloads(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    dest = tmp_path / "export"
    dest.mkdir()
    (downloads / "note.pdf").write_text("pdf")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    moved = move_pdfs_to_export_folder(["note"], str(dest) + "/")

    assert moved == 1
    assert (dest / "note.pdf").exists()


def test_move_only_moves_targeted_files(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    dest = tmp_path / "export"
    dest.mkdir()
    (docs / "target.pdf").write_text("pdf")
    (docs / "unrelated.pdf").write_text("pdf")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    move_pdfs_to_export_folder(["target"], str(dest) + "/")

    assert (dest / "target.pdf").exists()
    assert not (dest / "unrelated.pdf").exists()
    assert (docs / "unrelated.pdf").exists()


def test_move_missing_file_not_counted(tmp_path, monkeypatch):
    dest = tmp_path / "export"
    dest.mkdir()
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    moved = move_pdfs_to_export_folder(["nonexistent"], str(dest) + "/")

    assert moved == 0
    assert list(dest.iterdir()) == []


def test_move_multiple_files(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    dest = tmp_path / "export"
    dest.mkdir()
    (docs / "note-a.pdf").write_text("pdf")
    (desktop / "note-b.pdf").write_text("pdf")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    moved = move_pdfs_to_export_folder(["note-a", "note-b"], str(dest) + "/")

    assert moved == 2
    assert (dest / "note-a.pdf").exists()
    assert (dest / "note-b.pdf").exists()


def test_move_prefers_desktop_over_documents(tmp_path, monkeypatch):
    """Desktop is searched before Documents; file in Desktop should win."""
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    docs = tmp_path / "Documents"
    docs.mkdir()
    dest = tmp_path / "export"
    dest.mkdir()
    (desktop / "note.pdf").write_text("desktop-version")
    (docs / "note.pdf").write_text("docs-version")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    move_pdfs_to_export_folder(["note"], str(dest) + "/")

    assert (dest / "note.pdf").read_text() == "desktop-version"


def test_move_fallback_finds_nested_file(tmp_path, monkeypatch):
    nested = tmp_path / "sub1" / "sub2"
    nested.mkdir(parents=True)
    dest = tmp_path / "export"
    dest.mkdir()
    (nested / "deep-note.pdf").write_text("pdf")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)

    moved = move_pdfs_to_export_folder(["deep-note"], str(dest) + "/")

    assert moved == 1
    assert (dest / "deep-note.pdf").exists()


def test_move_empty_list_returns_zero(tmp_path):
    dest = tmp_path / "export"
    dest.mkdir()

    moved = move_pdfs_to_export_folder([], str(dest) + "/")

    assert moved == 0
