# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Memo is a macOS-only CLI app for managing Apple Notes and Apple Reminders via AppleScript. Built with Python 3.13, Click, and the uv package manager.

## Build & Development Commands

```bash
# Setup
uv venv && source .venv/bin/activate && uv sync

# Install in editable mode
uv tool install . -e

# Run tests
pytest

# Run a single test
pytest test/memo_notes_test.py::test_name

# Build and deploy docs
pip install ".[docs]"
mkdocs serve        # local preview
mkdocs gh-deploy    # deploy to GitHub Pages
```

## Architecture

**Entry point:** `src/memo/memo.py` — Click CLI with two command groups: `notes` and `rem` (reminders).

**Helper modules in `src/memo_helpers/`** — each handles a single operation:
- `get_memo.py` — fetches notes/reminders via AppleScript, builds `note_map` (ID → metadata) and `notes_list` (titles)
- `add_memo.py` — creates temp markdown file, converts to HTML via Mistune, adds to Notes
- `edit_memo.py` — fetches note HTML → converts to Markdown → opens in `$EDITOR` → converts back to HTML → updates
- `delete_memo.py`, `move_memo.py`, `export_memo.py` — CRUD operations via AppleScript
- `search_memo.py` — fuzzy search using system `fzf` with `bat` preview
- `validation_memo.py` — validates CLI flag combinations
- `md_converter.py` — HTML↔Markdown conversion using html2text

**Key pattern:** All Apple Notes/Reminders interactions use `subprocess.run` with `osascript` to execute AppleScript. Image/attachment data can be lost during edit/move operations.

## Code Style

- 4-space indentation, 88 char max line length (editorconfig)
- Conventional Commits for commit messages
- AI-generated code is not accepted per CONTRIBUTING.md — humans must understand and own contributions
