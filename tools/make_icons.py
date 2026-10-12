"""Generates the add-in's icons (toolbar PNGs + AddInIcon.svg).

A stylised multi-toolhead printer: white body, dark window with a
multicolor print, smoky hood with four colored toolheads, side spools.
Run: python3 tools/make_icons.py [preview.png]
"""
import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'commands', 'commandDialog', 'resources')

RED, BLUE, YELLOW, GREEN = '#E5484D', '#3B82F6', '#F5C518', '#22C55E'


def rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


# ------------------------------------------------------------------ designs
# Shapes: ('rrect', x0, y0, x1, y1, radius, fill, stroke, stroke_width)
#         ('circle', cx, cy, r, fill, stroke, stroke_width)
# Coordinates are in design units; the design's size maps to the image size.

def design_large(dark):
    """64-unit design used for 32 px and up."""
    outline = rgba('#A7B0BA') if dark else rgba('#5F6873')
    body = rgba('#F7F8FA')
    ink = rgba('#1E2228')
    spool, spool_rim, hub = rgba('#F2B33D'), rgba('#B7791F'), rgba('#7A5A1E')
    s = []
    # side spools, behind the body
    for cx in (8, 56):
        s.append(('circle', cx, 44, 6, spool, spool_rim, 2))
        s.append(('circle', cx, 44, 2, hub, None, 0))
    # Smoky dome-like hood (its bottom corners hide behind the body) with
    # four colored toolheads. Edges sit on even units so 32 px stays crisp.
    hood_line = rgba('#A7B0BA') if dark else rgba('#76808B')
    s.append(('rrect', 12, 4, 52, 30, 8, rgba('#B8C6D4', 0.45), hood_line, 2))
    for i, color in enumerate((RED, BLUE, YELLOW, GREEN)):
        x = 14 + i * 10
        s.append(('rrect', x, 10, x + 6, 20, 1.5, rgba(color), None, 0))
        s.append(('rrect', x + 2, 20, x + 4, 23, 0.5, ink, None, 0))
    # body
    s.append(('rrect', 10, 24, 54, 60, 6, body, outline, 2))
    # window with bed and a stacked multicolor print
    s.append(('rrect', 14, 29, 40, 54, 3, ink, None, 0))
    s.append(('rrect', 16, 49, 38, 51, 1, rgba('#59626D'), None, 0))
    for (x0, x1, y0, y1, color) in ((19, 35, 44, 49, BLUE), (21, 33, 40, 44, RED),
                                    (23, 31, 36, 40, YELLOW), (25, 29, 33, 36, GREEN)):
        s.append(('rrect', x0, y0, x1, y1, 1, rgba(color), None, 0))
    # touchscreen
    s.append(('rrect', 44, 30, 50, 36, 1.2, ink, None, 0))
    s.append(('rrect', 45.2, 31.2, 48.8, 34.8, 0.6, rgba('#38BDF8'), None, 0))
    return 64, s


def design_small(dark):
    """16-unit design for the 16 px toolbar icon, aligned to whole pixels."""
    outline = rgba('#A7B0BA') if dark else rgba('#5F6873')
    ink = rgba('#1E2228')
    s = []
    s.append(('rrect', 2, 1, 14, 7, 1.5, rgba('#9FB0C2', 0.55), outline, 1))
    for i, color in enumerate((RED, BLUE, YELLOW, GREEN)):
        s.append(('rrect', 4 + i * 2, 3, 6 + i * 2, 5, 0, rgba(color), None, 0))
    s.append(('rrect', 1, 6, 15, 16, 2, rgba('#F7F8FA'), outline, 1))
    s.append(('rrect', 3, 8, 10, 14, 0.5, ink, None, 0))
    for (x0, x1, y0, y1, color) in ((5, 8, 12, 13, BLUE), (5, 8, 11, 12, RED), (6, 7, 10, 11, YELLOW)):
        s.append(('rrect', x0, y0, x1, y1, 0, rgba(color), None, 0))
    s.append(('rrect', 11, 8, 13, 10, 0, ink, None, 0))
    return 16, s


# --------------------------------------------------------------- rasterizer

def _sdf_rrect(px, py, x0, y0, x1, y1, r):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    qx, qy = abs(px - cx) - hx, abs(py - cy) - hy
    outside = math.hypot(max(qx, 0), max(qy, 0))
    return outside + min(max(qx, qy), 0) - r


def _sdf(shape, px, py):
    if shape[0] == 'rrect':
        return _sdf_rrect(px, py, *shape[1:6])
    _, cx, cy, r = shape[:4]
    return math.hypot(px - cx, py - cy) - r


def _paint_parts(shape):
    if shape[0] == 'rrect':
        fill, stroke, width = shape[6:9]
    else:
        fill, stroke, width = shape[4:7]
    return fill, stroke, width


def render(design, size, ss=8):
    units, shapes = design
    scale = units / size
    img = [[(0.0, 0.0, 0.0, 0.0)] * size for _ in range(size)]
    offs = [(i + 0.5) / ss for i in range(ss)]
    for shape in shapes:
        fill, stroke, width = _paint_parts(shape)
        for y in range(size):
            row = img[y]
            for x in range(size):
                fill_cov = stroke_cov = 0
                for oy in offs:
                    for ox in offs:
                        d = _sdf(shape, (x + ox) * scale, (y + oy) * scale)
                        if d <= 0:
                            if stroke and d > -width:
                                stroke_cov += 1
                            else:
                                fill_cov += 1
                n = ss * ss
                for paint, cov in ((fill, fill_cov), (stroke, stroke_cov)):
                    if paint is None or cov == 0:
                        continue
                    a = paint[3] * cov / n
                    r0, g0, b0, a0 = row[x]
                    out_a = a + a0 * (1 - a)
                    if out_a > 0:
                        mix = lambda c, c0: (c * a + c0 * a0 * (1 - a)) / out_a
                        row[x] = (mix(paint[0], r0), mix(paint[1], g0), mix(paint[2], b0), out_a)
    return img


def write_png(path, img):
    size = len(img)
    raw = b''.join(b'\x00' + bytes(
        v for (r, g, b, a) in row for v in (round(r), round(g), round(b), round(a * 255))) for row in img)
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


def write_svg(path, design):
    units, shapes = design
    def paint(p):
        return f'#{p[0]:02X}{p[1]:02X}{p[2]:02X}" fill-opacity="{p[3]:g}' if p else 'none'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {units} {units}">']
    for shape in shapes:
        fill, stroke, width = _paint_parts(shape)
        if shape[0] == 'rrect':
            x0, y0, x1, y1, r = shape[1:6]
            out.append(f'  <rect x="{x0:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                       f'rx="{r:g}" fill="{paint(fill)}"/>')
            if stroke:  # inner stroke, as rendered in the PNGs
                h = width / 2
                out.append(f'  <rect x="{x0 + h:g}" y="{y0 + h:g}" width="{x1 - x0 - width:g}" '
                           f'height="{y1 - y0 - width:g}" rx="{max(r - h, 0):g}" fill="none" '
                           f'stroke="#{stroke[0]:02X}{stroke[1]:02X}{stroke[2]:02X}" stroke-width="{width:g}"/>')
        else:
            cx, cy, r = shape[1:4]
            out.append(f'  <circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{paint(fill)}"/>')
            if stroke:
                out.append(f'  <circle cx="{cx:g}" cy="{cy:g}" r="{r - width / 2:g}" fill="none" '
                           f'stroke="#{stroke[0]:02X}{stroke[1]:02X}{stroke[2]:02X}" stroke-width="{width:g}"/>')
    out.append('</svg>\n')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))


# Fusion picks these by name: 16/32/64 px, @2x for Retina, -dark for the dark theme.
OUTPUTS = [
    ('16x16', 16, design_small), ('16x16@2x', 32, design_large),
    ('32x32', 32, design_large), ('32x32@2x', 64, design_large),
    ('64x64', 64, design_large),
]


def preview(path, rendered):
    # Each icon at actual size and zoomed, on light and dark backgrounds.
    zoom = {16: 8, 32: 4, 64: 2}
    tiles = []
    for name, img in rendered:
        n = len(img)
        tiles.append((name, img, zoom[n]))
    pad = 12
    cell = 128 + 2 * pad
    width = cell * len([t for t in tiles if '-dark' not in t[0]]) + pad
    height = (cell + 64 + pad) * 2 + pad
    canvas = [[(0, 0, 0)] * width for _ in range(height)]
    for band, (bg, dark) in enumerate(((rgba('#F0F1F3'), False), (rgba('#2C2E33'), True))):
        y0 = pad + band * (cell + 64 + pad)
        for yy in range(y0 - pad // 2, y0 + cell + 64):
            for xx in range(width):
                canvas[yy][xx] = bg[:3]
        group = [t for t in tiles if ('-dark' in t[0]) == dark]
        for i, (name, img, z) in enumerate(group):
            n = len(img)
            x0 = pad + i * cell
            for (ox, oy, zz) in ((x0, y0, z), (x0 + (cell - n) // 2, y0 + cell + 8, 1)):
                for y in range(n * zz):
                    for x in range(n * zz):
                        r, g, b, a = img[y // zz][x // zz]
                        br, bgc, bb = canvas[oy + y][ox + x]
                        canvas[oy + y][ox + x] = (r * a + br * (1 - a), g * a + bgc * (1 - a), b * a + bb * (1 - a))
    write_png(path, [[(r, g, b, 1.0) for (r, g, b) in row] for row in canvas])


def main():
    rendered = []
    for dark in (False, True):
        suffix = '-dark' if dark else ''
        for name, size, design in OUTPUTS:
            base, _, retina = name.partition('@')
            fname = f'{base}{suffix}' + (f'@{retina}' if retina else '') + '.png'
            img = render(design(dark), size)
            write_png(os.path.join(RES, fname), img)
            if not retina:
                rendered.append((fname, img))
    write_svg(os.path.join(ROOT, 'AddInIcon.svg'), design_large(False))
    if len(sys.argv) > 1:
        preview(sys.argv[1], rendered)


if __name__ == '__main__':
    main()
