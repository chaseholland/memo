# Apple Notes Handwriting Format (Paper Bundles)

Reverse-engineered format documentation for Apple Notes handwritten (Paper) note storage on macOS.

## File Locations

All paths are relative to `~/Library/Group Containers/group.com.apple.notes/`.

- **NoteStore**: `NoteStore.sqlite` — main notes database, links notes to attachments
- **Paper bundles**: `Accounts/<ACCOUNT_UUID>/Paper/Bundles/<ATTACHMENT_UUID>.bundle/Database/data.sqlite3`
- **Fallback images**: `Accounts/<ACCOUNT_UUID>/FallbackImages/<ATTACHMENT_UUID>/<VERSION>/FallbackImage.png`

## NoteStore Queries

Paper notes are identified by joining attachments with `ZTYPEUTI IN ('com.apple.paper', 'com.apple.drawing.2')` back to their parent note via `att.ZNOTE = note.Z_PK`. The attachment's `ZIDENTIFIER` is the UUID used in file paths.

Dates are stored as seconds since the Core Data epoch (2001-01-01 00:00:00 UTC).

## Paper Bundle Database Schema

Each bundle's `data.sqlite3` has two tables:

### `Reference`
| Column | Type | Description |
|--------|------|-------------|
| `Id` | BLOB PK | Prefix byte + 16-byte UUID |
| `Version` | BLOB | CRDT vector clock |
| `RetainCount` | INT | Always 1 |
| `ChildRetainCounts` | BLOB | Container row only; lists child row IDs |
| `Data` | BLOB | CRDT envelope wrapping protobuf payload |

### `Assets`
For embedded images/attachments. Empty in stroke-only drawings.

## CRDT Envelope

Every `Data` blob starts with an 8-byte header:
- 4 bytes magic: `crdt` (0x63726474)
- 4 bytes version: `06 00 00 00`
- Remainder: raw protobuf (no .proto schema; decode schema-less)

## Record Types (by Id prefix byte)

| Prefix | Count (typical) | Description |
|--------|----------------|-------------|
| `0xFF` | 1 | Root/header |
| `0x01` | 1 | Page definition (Id = `01` + ASCII `"default"`) |
| `0x02` | ~4 per stroke + 1 container | All stroke-related records |

## Record Hierarchy (per stroke)

Each stroke is represented by 4 `0x02`-prefix records, plus a shared container:

1. **Container** (1 per bundle, large ~42KB): CRDT ordered list referencing all leaf nodes via fractional indexing. `ChildRetainCounts` has 21-byte entries (5-byte header + 16-byte UUID) listing children.

2. **Leaf reference** (~63 bytes data): Points from container to an inherited_properties record via embedded UUID.

3. **Inherited properties** (~164 bytes data): Links an ink_properties record to a stroke_data record. Contains two 16-byte UUID references.

4. **Ink properties** (~200 bytes data): Pen configuration including type, color, transform.

5. **Stroke data** (100–2100 bytes data): Actual point coordinates.

## Ink Properties (Protobuf Structure)

- **Pen type**: string field, e.g. `com.apple.ink.pen`, `com.apple.ink.marker`
- **Color**: 4× f32 (RGBA, little-endian) at protobuf fields 1–4 with wire type 5 (tags `0x0D`, `0x15`, `0x1D`, `0x25`)
- **Pen variant**: protobuf field 3, varint (e.g. value 3)
- **Blending**: string field, e.g. `"linear"` (markers only)
- **Opacity**: f64 field (e.g. -0.5)
- **Transform matrix**: 6× f64, **big-endian**, representing 3×2 affine `[a, b, c, d, tx, ty]`

## Stroke Data (Protobuf Structure)

Nested path: `F1 → F10 → F1 → F2` where F2 is the stroke segment:

| Field | Wire Type | Description |
|-------|-----------|-------------|
| F1 | bytes | 16-byte stroke UUID |
| F2 | fixed64 | Timestamp (Apple epoch, seconds since 2001-01-01) |
| F3 | varint | `npoints` — number of points in the stroke |
| F4 | varint | `bitmask` — point format bitmask (see below) |
| F5 | varint | Constant per bundle (e.g. 984, 1020) |
| F6 | bytes | Per-stroke metadata (variable length) |
| F7 | bytes | Packed point array |

### F6 Per-Stroke Metadata

Variable length, ends with sentinel `FF 7F 00 00 80 3F` (f16 NaN + f32 1.0). Contains:
- Default stroke width as f32 (e.g. 2.83) — used when per-point width is absent
- u32 value of 1000 (scale factor / DPI)

## Point Format Bitmask (F4)

F4 is a bitmask controlling which fields are present per point. Points are fixed-size records; total size is the sum of sizes for all set bits.

| Bit | Value | Size | Field | Type |
|-----|-------|------|-------|------|
| 0 | 1 | 8 bytes | x, y | 2× f32 little-endian |
| 1 | 2 | 4 bytes | time | f32 (`point_index / 240` at 240Hz) |
| 2 | 4 | 4 bytes | width | f32 |
| 3 | 8 | 2 bytes | unknown | u16 |
| 4 | 16 | 2 bytes | unknown | u16 |
| 5 | 32 | 2 bytes | force | u16 (Apple Pencil, ~0–1024) |
| 6 | 64 | 2 bytes | altitude | u16 |
| 7 | 128 | 2 bytes | azimuth | u16 |
| 8 | 256 | 2 bytes | unknown | u16 |

**Formula**: `bytes_per_point = sum(size for each set bit)`. Verified against 42,232 strokes with 100% match.

### Common Formats

| F4 | Frequency | Bytes/pt | Fields |
|----|-----------|----------|--------|
| 3 | 78.7% | 12 | x, y, time |
| 39 | 18.6% | 18 | x, y, time, width, force |
| 103 | 1.4% | 20 | x, y, time, width, force, altitude |
| 1 | 0.3% | 8 | x, y only (single-tap dots) |

## Page Definition

The `01default` row contains:
- Page dimensions as **big-endian** f64: width=768.0, height=1987.0 (scrollable canvas)
- Frame dimensions: width=768.0, height=240.0 (visible viewport)
- References the container row UUID

## Coordinate System

- Origin: top-left of the canvas
- X range: 0–768 (iPad screen width at 1x)
- Y range: 0–1987+ (scrollable; long notes exceed the page height)
- Points can have negative Y values (content above the initial viewport)

## Rendering Notes

- Scale factor for letter-size PDF: `usable_width / 768.0`
- Y axis is inverted for PDF (PDF origin is bottom-left)
- Long notes require multi-page pagination; clip strokes at page boundaries
- Marker strokes (`com.apple.ink.marker`) should be rendered semi-transparent
- Single-point strokes (dots) render as filled circles
- Round line caps and joins produce the smoothest output

## Fallback Images

macOS generates `FallbackImage.png` files during iCloud sync (via the Notes sync daemon, not the GUI). These exist for all synced notes on a machine even without opening Notes.app. However, this behavior is not guaranteed by Apple and could change — the stroke parser is the reliable headless path.

## Implementation

See `src/memo_helpers/stroke_parser.py` for the parser and `src/memo_helpers/stroke_renderer.py` for the PDF renderer. The parser handles:
- Schema-less protobuf decoding
- CRDT header stripping
- Record classification by data size and content heuristics
- Stroke-to-ink linking via inherited_properties UUID chain
- Variable-size point decoding from the bitmask format
