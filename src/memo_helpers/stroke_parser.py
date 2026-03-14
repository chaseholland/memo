"""Parse Apple Notes Paper bundle databases to extract stroke data.

Reads stroke points, ink properties (color, pen type), and page layout
directly from the Paper bundle's data.sqlite3 without needing the Notes GUI.
"""

import os
import shutil
import sqlite3
import struct
import tempfile


# Point format bitmask: (bit_index, byte_size, field_name)
POINT_FIELDS = [
    (0, 8, "xy"),        # x, y as 2x f32 LE
    (1, 4, "time"),      # f32
    (2, 4, "width"),     # f32
    (3, 2, "unk1"),      # u16
    (4, 2, "unk2"),      # u16
    (5, 2, "force"),     # u16
    (6, 2, "altitude"),  # u16
    (7, 2, "azimuth"),   # u16
    (8, 2, "unk3"),      # u16
]


# --- Protobuf decoder (schema-less) ---

def _decode_varint(data, pos):
    """Decode a protobuf varint. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if (b & 0x80) == 0:
            return result, pos
        shift += 7
    raise ValueError("Truncated varint")


def _decode_protobuf(data):
    """Decode raw protobuf bytes into [(field_num, wire_type, value), ...]."""
    fields = []
    pos = 0
    while pos < len(data):
        try:
            tag, pos = _decode_varint(data, pos)
        except ValueError:
            break
        wire_type = tag & 0x07
        field_num = tag >> 3

        if field_num == 0:
            break  # invalid

        if wire_type == 0:  # varint
            try:
                value, pos = _decode_varint(data, pos)
            except ValueError:
                break
            fields.append((field_num, wire_type, value))
        elif wire_type == 1:  # 64-bit
            if pos + 8 > len(data):
                break
            value = data[pos:pos + 8]
            pos += 8
            fields.append((field_num, wire_type, value))
        elif wire_type == 2:  # length-delimited
            try:
                length, pos = _decode_varint(data, pos)
            except ValueError:
                break
            if pos + length > len(data):
                break
            value = data[pos:pos + length]
            pos += length
            fields.append((field_num, wire_type, value))
        elif wire_type == 5:  # 32-bit
            if pos + 4 > len(data):
                break
            value = data[pos:pos + 4]
            pos += 4
            fields.append((field_num, wire_type, value))
        else:
            break  # unknown wire type
    return fields


def _strip_crdt(data):
    """Strip the 8-byte CRDT header (magic 'crdt' + version) from a Data blob."""
    if len(data) >= 8 and data[:4] == b"crdt":
        return data[8:]
    return data


# --- Point decoding ---

def _bytes_per_point(bitmask):
    """Calculate bytes per point from the format bitmask."""
    total = 0
    for bit, size, _ in POINT_FIELDS:
        if bitmask & (1 << bit):
            total += size
    return total


def _decode_points(packed, npoints, bitmask):
    """Decode packed point array into list of point dicts."""
    bpp = _bytes_per_point(bitmask)
    if bpp == 0 or len(packed) < npoints * bpp:
        return []

    points = []
    for i in range(npoints):
        base = i * bpp
        offset = 0
        point = {}

        for bit, size, name in POINT_FIELDS:
            if not (bitmask & (1 << bit)):
                continue
            pos = base + offset
            if name == "xy":
                point["x"], point["y"] = struct.unpack_from("<ff", packed, pos)
            elif size == 4:
                point[name] = struct.unpack_from("<f", packed, pos)[0]
            elif size == 2:
                point[name] = struct.unpack_from("<H", packed, pos)[0]
            offset += size

        points.append(point)
    return points


# --- Record classification ---

def _find_stroke_segment(fields):
    """Recursively search protobuf fields for a stroke segment.

    A stroke segment has fields F3 (npoints), F4 (bitmask), F7 (packed points)
    where len(F7) == npoints * bytes_per_point(F4).

    Returns dict with 'npoints', 'bitmask', 'packed', 'metadata' or None.
    """
    for field_num, wire_type, value in fields:
        if wire_type != 2:
            continue
        try:
            nested = _decode_protobuf(value)
        except Exception:
            continue
        if not nested:
            continue

        # Check if this message has the stroke segment signature
        field_nums = {f[0] for f in nested}
        if {3, 4, 7}.issubset(field_nums):
            npoints = None
            bitmask = None
            packed = None
            metadata = None

            for fn, wt, val in nested:
                if fn == 3 and wt == 0:
                    npoints = val
                elif fn == 4 and wt == 0:
                    bitmask = val
                elif fn == 6 and wt == 2:
                    metadata = val
                elif fn == 7 and wt == 2:
                    packed = val

            if npoints and bitmask is not None and packed:
                bpp = _bytes_per_point(bitmask)
                if bpp > 0 and len(packed) == npoints * bpp:
                    return {
                        "npoints": npoints,
                        "bitmask": bitmask,
                        "packed": packed,
                        "metadata": metadata,
                    }

        # Recurse into nested messages
        result = _find_stroke_segment(nested)
        if result:
            return result

    return None


def _find_ink_properties(fields):
    """Search protobuf fields for ink properties (pen type, color).

    Returns dict with 'pen_type', 'r', 'g', 'b', 'a' or None.
    """
    result = {}

    # Look for color floats (fields 1-4, wire type 5) and pen type string
    color_floats = {}
    for fn, wt, val in fields:
        if wt == 5 and fn in (1, 2, 3, 4):
            f = struct.unpack_from("<f", val, 0)[0]
            if 0.0 <= f <= 1.0:
                color_floats[fn] = f
        elif wt == 2:
            try:
                s = val.decode("utf-8")
                if s.startswith("com.apple.ink"):
                    result["pen_type"] = s
            except (UnicodeDecodeError, ValueError):
                pass

    if len(color_floats) >= 3:
        result["r"] = color_floats.get(1, 0.0)
        result["g"] = color_floats.get(2, 0.0)
        result["b"] = color_floats.get(3, 0.0)
        result["a"] = color_floats.get(4, 1.0)

    # Recurse into nested messages to find deeper properties
    for fn, wt, val in fields:
        if wt == 2 and len(val) > 10:
            try:
                nested = _decode_protobuf(val)
                if nested:
                    sub = _find_ink_properties(nested)
                    if sub:
                        for k, v in sub.items():
                            if k not in result:
                                result[k] = v
            except Exception:
                pass

    return result if result else None


def _find_uuid_refs(fields, valid_uuids):
    """Find all 16-byte bytes fields matching known UUIDs, recursively."""
    refs = []
    for fn, wt, val in fields:
        if wt == 2:
            if len(val) == 16 and val in valid_uuids:
                refs.append(val)
            else:
                try:
                    nested = _decode_protobuf(val)
                    if nested:
                        refs.extend(_find_uuid_refs(nested, valid_uuids))
                except Exception:
                    pass
    return refs


def _extract_default_width(metadata):
    """Extract default stroke width from F6 per-stroke metadata."""
    if metadata and len(metadata) >= 4:
        w = struct.unpack_from("<f", metadata, 0)[0]
        if 0.1 < w < 50.0:
            return w
    return 2.0


# --- Main parser ---

def parse_bundle(db_path):
    """Parse a Paper bundle database and return structured stroke data.

    Args:
        db_path: Path to the bundle's data.sqlite3

    Returns:
        dict with 'page_width', 'page_height', 'strokes' list, or None on failure.
        Each stroke has 'points', 'color' (r,g,b,a tuple), 'pen_type', 'width'.
    """
    # Copy DB + WAL to avoid locking
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    tmp_files = [tmp.name]
    shutil.copy2(db_path, tmp.name)
    for ext in ("-wal", "-shm"):
        src = db_path + ext
        if os.path.isfile(src):
            shutil.copy2(src, tmp.name + ext)
            tmp_files.append(tmp.name + ext)

    try:
        conn = sqlite3.connect(tmp.name)
        rows = conn.execute("SELECT Id, Data FROM Reference").fetchall()
        conn.close()
    finally:
        for f in tmp_files:
            if os.path.isfile(f):
                os.unlink(f)

    # Parse all records
    records = []
    uuid_map = {}
    for row_id, data in rows:
        if not data or len(data) < 8:
            continue
        prefix = row_id[0] if row_id else 0
        uuid_bytes = bytes(row_id[1:]) if row_id and len(row_id) > 1 else None
        proto_data = _strip_crdt(bytes(data))
        fields = _decode_protobuf(proto_data)

        rec = {
            "prefix": prefix,
            "uuid": uuid_bytes,
            "fields": fields,
            "data_len": len(proto_data),
            "raw_proto": proto_data,
        }
        records.append(rec)
        if uuid_bytes:
            uuid_map[uuid_bytes] = rec

    # Classify 0x02 records
    stroke_data_recs = []
    ink_prop_recs = []
    inherited_prop_recs = []
    leaf_ref_recs = []

    for rec in records:
        if rec["prefix"] != 0x02:
            continue

        seg = _find_stroke_segment(rec["fields"])
        if seg:
            rec["stroke_segment"] = seg
            stroke_data_recs.append(rec)
            continue

        ink = _find_ink_properties(rec["fields"])
        if ink and "pen_type" in ink:
            rec["ink"] = ink
            ink_prop_recs.append(rec)
            continue

        if rec["data_len"] > 5000:
            pass  # container
        elif rec["data_len"] < 100:
            leaf_ref_recs.append(rec)
        else:
            inherited_prop_recs.append(rec)

    # Link strokes to ink properties via inherited_properties
    stroke_uuids = {rec["uuid"] for rec in stroke_data_recs if rec["uuid"]}
    ink_uuids = {rec["uuid"] for rec in ink_prop_recs if rec["uuid"]}
    all_known = set(uuid_map.keys())

    stroke_ink_map = {}  # stroke_uuid -> ink dict
    for inh_rec in inherited_prop_recs:
        refs = _find_uuid_refs(inh_rec["fields"], all_known)
        s_uuid = None
        i_uuid = None
        for uid in refs:
            if uid in stroke_uuids:
                s_uuid = uid
            elif uid in ink_uuids:
                i_uuid = uid
        if s_uuid and i_uuid:
            ink_rec = uuid_map[i_uuid]
            if "ink" in ink_rec:
                stroke_ink_map[s_uuid] = ink_rec["ink"]

    # Try to get stroke ordering from leaf references -> inherited -> strokes
    leaf_uuid_set = {rec["uuid"] for rec in leaf_ref_recs if rec["uuid"]}
    inh_uuid_set = {rec["uuid"] for rec in inherited_prop_recs if rec["uuid"]}

    ordered_stroke_uuids = []
    for leaf_rec in leaf_ref_recs:
        refs = _find_uuid_refs(leaf_rec["fields"], all_known)
        for uid in refs:
            if uid in inh_uuid_set:
                inh_rec = uuid_map[uid]
                inh_refs = _find_uuid_refs(inh_rec["fields"], all_known)
                for s_uid in inh_refs:
                    if s_uid in stroke_uuids:
                        ordered_stroke_uuids.append(s_uid)
                        break
                break

    # Use ordered strokes if we have them, otherwise all stroke records
    if ordered_stroke_uuids:
        ordered_recs = [uuid_map[u] for u in ordered_stroke_uuids if u in uuid_map]
    else:
        ordered_recs = stroke_data_recs

    # Build output strokes
    strokes = []
    for rec in ordered_recs:
        seg = rec.get("stroke_segment")
        if not seg:
            continue

        points = _decode_points(seg["packed"], seg["npoints"], seg["bitmask"])
        if not points:
            continue

        # Ink properties
        ink = stroke_ink_map.get(rec["uuid"], {})
        r = ink.get("r", 0.0)
        g = ink.get("g", 0.0)
        b = ink.get("b", 0.0)
        a = ink.get("a", 1.0)
        pen_type = ink.get("pen_type", "com.apple.ink.pen")

        # Skip eraser strokes
        if "eraser" in pen_type:
            continue

        # Width: use per-point average if available, else default from metadata
        if "width" in points[0]:
            width = sum(p.get("width", 2.0) for p in points) / len(points)
        else:
            width = _extract_default_width(seg.get("metadata"))

        strokes.append({
            "points": points,
            "color": (r, g, b, a),
            "pen_type": pen_type,
            "width": width,
        })

    if not strokes:
        return None

    return {
        "page_width": 768.0,
        "page_height": 1987.0,
        "strokes": strokes,
    }
