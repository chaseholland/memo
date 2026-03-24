import os
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# Margins and layout (in points, 72 pts per inch)
MARGIN_LEFT = 0.5 * inch
MARGIN_TOP = 0.5 * inch
MARGIN_BOTTOM = 0.5 * inch
TITLE_FONT_SIZE = 16
TITLE_SPACING = 12  # space below title


def render_fallback_pdf(title, fallback_image_path, output_path):
    """Render a PDF from a note's fallback image with a title header.

    The image is scaled to fit the page width while preserving aspect ratio.
    """
    page_width, page_height = letter
    c = canvas.Canvas(output_path, pagesize=letter)

    # Draw title
    usable_width = page_width - 2 * MARGIN_LEFT
    title_y = page_height - MARGIN_TOP - TITLE_FONT_SIZE
    c.setFont("Helvetica-Bold", TITLE_FONT_SIZE)
    c.drawString(MARGIN_LEFT, title_y, title)

    # Draw a thin line under the title
    line_y = title_y - 4
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, line_y, MARGIN_LEFT + usable_width, line_y)

    # Load and draw the image
    img = ImageReader(fallback_image_path)
    img_w, img_h = img.getSize()

    # Scale to fit usable width
    scale = usable_width / img_w
    draw_w = usable_width
    draw_h = img_h * scale

    # If the scaled image is too tall, scale down further
    max_img_height = line_y - MARGIN_BOTTOM - TITLE_SPACING
    if draw_h > max_img_height:
        scale = max_img_height / img_h
        draw_w = img_w * scale
        draw_h = max_img_height

    # Position image below the title line
    img_x = MARGIN_LEFT
    img_y = line_y - TITLE_SPACING - draw_h

    c.drawImage(
        fallback_image_path,
        img_x, img_y,
        width=draw_w, height=draw_h,
        preserveAspectRatio=True,
        anchor="nw",
    )

    c.save()
    return output_path


def render_strokes_pdf(title, stroke_data, output_path):
    """Render parsed stroke data to a multi-page PDF.

    Strokes are drawn as vector paths with their original colors and widths.
    The note canvas (768 wide) is scaled to fit the PDF page width.
    Content is paginated vertically as needed.
    """
    strokes = stroke_data["strokes"]
    if not strokes:
        return None

    # Find vertical extent of all strokes
    all_ys = [pt["y"] for s in strokes for pt in s["points"]]
    if not all_ys:
        return None

    min_y = min(all_ys)
    max_y = max(all_ys)

    page_width, page_height = letter
    usable_width = page_width - 2 * MARGIN_LEFT

    # Scale note coords (768 wide) to PDF page width
    note_page_width = stroke_data.get("page_width", 768.0)
    scale = usable_width / note_page_width

    # Content area heights
    title_h = TITLE_FONT_SIZE + 4 + TITLE_SPACING
    first_page_h = page_height - MARGIN_TOP - title_h - MARGIN_BOTTOM
    other_page_h = page_height - MARGIN_TOP - MARGIN_BOTTOM

    # Determine page breaks in note-y coordinates
    total_note_h = max_y - min_y
    page_breaks = [min_y]

    first_note_h = first_page_h / scale
    if total_note_h <= first_note_h:
        page_breaks.append(max_y)
    else:
        page_breaks.append(min_y + first_note_h)
        remaining = total_note_h - first_note_h
        other_note_h = other_page_h / scale
        while remaining > 0:
            page_breaks.append(page_breaks[-1] + min(other_note_h, remaining))
            remaining -= other_note_h

    num_pages = len(page_breaks) - 1
    c = canvas.Canvas(output_path, pagesize=letter)

    for page_idx in range(num_pages):
        if page_idx > 0:
            c.showPage()

        # Title on first page
        if page_idx == 0:
            _draw_title(c, title, page_width, page_height)
            content_top = page_height - MARGIN_TOP - title_h
        else:
            content_top = page_height - MARGIN_TOP

        y_start = page_breaks[page_idx]
        y_end = page_breaks[page_idx + 1]

        # Clip drawing to this page's content area
        content_bottom = MARGIN_BOTTOM
        c.saveState()
        clip = c.beginPath()
        clip.rect(0, content_bottom, page_width, content_top - content_bottom)
        c.clipPath(clip, stroke=0, fill=0)

        # Draw each stroke
        for stroke in strokes:
            _draw_stroke(c, stroke, scale, y_start, content_top, y_start, y_end)

        c.restoreState()

    c.save()
    return output_path


def _draw_title(c, title, page_width, page_height):
    """Draw the note title and separator line."""
    usable_width = page_width - 2 * MARGIN_LEFT
    title_y = page_height - MARGIN_TOP - TITLE_FONT_SIZE
    c.setFont("Helvetica-Bold", TITLE_FONT_SIZE)
    c.drawString(MARGIN_LEFT, title_y, title)
    line_y = title_y - 4
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, line_y, MARGIN_LEFT + usable_width, line_y)


def _draw_stroke(c, stroke, scale, y_offset, content_top, y_clip_start, y_clip_end):
    """Draw a single stroke on the current page."""
    points = stroke["points"]
    if not points:
        return

    # Check if any points fall within this page's y range
    ys = [p["y"] for p in points]
    if min(ys) > y_clip_end or max(ys) < y_clip_start:
        return

    r, g, b, a = stroke.get("color", (0, 0, 0, 1))
    pen_type = stroke.get("pen_type", "com.apple.ink.pen")

    # Marker strokes are semi-transparent
    alpha = a * 0.4 if "marker" in pen_type else a
    c.setStrokeColor(Color(r, g, b, alpha=alpha))

    width = stroke.get("width", 2.0) * scale
    width = max(0.3, min(width, 20.0))
    c.setLineWidth(width)
    c.setLineCap(1)   # round
    c.setLineJoin(1)  # round

    if len(points) == 1:
        # Single point: draw a dot
        px = MARGIN_LEFT + points[0]["x"] * scale
        py = content_top - (points[0]["y"] - y_offset) * scale
        c.setFillColor(Color(r, g, b, alpha=alpha))
        c.circle(px, py, width / 2, stroke=0, fill=1)
        return

    # Draw connected line segments
    path = c.beginPath()
    first = True
    for pt in points:
        px = MARGIN_LEFT + pt["x"] * scale
        py = content_top - (pt["y"] - y_offset) * scale
        if first:
            path.moveTo(px, py)
            first = False
        else:
            path.lineTo(px, py)
    c.drawPath(path, stroke=1, fill=0)
