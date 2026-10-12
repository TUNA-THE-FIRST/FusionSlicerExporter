# Exports Fusion bodies together with their appearance colors as OBJ + MTL.
#
# STL has no color. Snapmaker Orca (like Bambu Studio) reads per-face MTL
# colors from an OBJ, asks which filament each color should use and paints
# the model accordingly, so colors set with Fusion's Appearance tool carry over.

import math
import os
import zipfile
from xml.sax.saxutils import quoteattr

import adsk.core

MM_PER_CM = 10.0

# Color property ids used by Fusion's appearance schemas: opaque (plastics,
# paints), metal, glass, then the older layered/generic schemas.
COLOR_PROPERTY_IDS = ('opaque_albedo', 'metal_f0', 'transparent_color',
                      'layered_diffuse', 'generic_diffuse')
FALLBACK_RGB = (128, 128, 128)

# Vertices are welded by rounding their mm coordinates to this many decimals.
WELD_DECIMALS = 4


class ColoredMesh:
    def __init__(self, name):
        self.name = name
        self.vertices = []   # (x, y, z) in mm
        self.triangles = []  # (a, b, c) indices into vertices
        self.colors = []     # (r, g, b) per triangle, 0-255
        self.method = 'faces'  # or 'body' when the whole-body fallback was used

    def extend(self, other):
        offset = len(self.vertices)
        self.vertices.extend(other.vertices)
        self.triangles.extend((a + offset, b + offset, c + offset) for a, b, c in other.triangles)
        self.colors.extend(other.colors)


# ---------------------------------------------------------------- colors

def _color_property_rgb(prop):
    prop = adsk.core.ColorProperty.cast(prop) if prop is not None else None
    if prop is None:
        return None
    color = prop.value  # None when the color comes from a texture
    if color is None:
        return None
    return (int(color.red), int(color.green), int(color.blue))


def appearance_rgb(appearance):
    # Not cached by appearance.id: copies of an appearance (e.g. after editing
    # its color in Fusion) share the same id but have different colors.
    if appearance is None:
        return FALLBACK_RGB
    props = appearance.appearanceProperties
    for pid in COLOR_PROPERTY_IDS:
        rgb = _color_property_rgb(props.itemById(pid))
        if rgb:
            return rgb
    try:
        # Preview API in newer Fusion builds; maps to the schema's main color.
        color = appearance.color
        if color:
            return (int(color.red), int(color.green), int(color.blue))
    except Exception:
        pass
    for prop in props:
        rgb = _color_property_rgb(prop)
        if rgb:
            return rgb
    return FALLBACK_RGB


def uses_custom_colors(body):
    # True when any face gets its appearance from something the user applied
    # (body, face, component/occurrence) rather than from the body's material.
    material = adsk.core.AppearanceSourceTypes.MaterialAppearanceSource
    for face in body.faces:
        try:
            if face.appearanceSourceType != material:
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------- geometry

def _transform(m, x, y, z):
    return (m[0] * x + m[1] * y + m[2] * z + m[3],
            m[4] * x + m[5] * y + m[6] * z + m[7],
            m[8] * x + m[9] * y + m[10] * z + m[11])


def _bbox(points):
    xs, ys, zs = zip(*points)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _bbox_error(points, ref):
    (lo, hi) = _bbox(points)
    return sum(abs(a - b) for a, b in zip(lo + hi, ref[0] + ref[1]))


def _pick_transform(raw_points, body):
    # Bodies inside components may be meshed in the component's own space or
    # already in the design's space. Use whichever matches Fusion's bounding
    # box for the body, which is always in design space.
    occ = body.assemblyContext
    if occ is None or not raw_points:
        return None
    m = occ.transform2.asArray()
    try:
        bb = body.boundingBox
        ref = ((bb.minPoint.x, bb.minPoint.y, bb.minPoint.z),
               (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z))
    except Exception:
        return m
    moved = [_transform(m, *p) for p in raw_points]
    return m if _bbox_error(moved, ref) < _bbox_error(raw_points, ref) else None


def _configure(calc, quality):
    calc.surfaceTolerance = quality['surface_deviation']
    calc.maxNormalDeviation = quality['normal_deviation']
    calc.maxSideLength = quality['max_edge_length']
    calc.maxAspectRatio = quality['aspect_ratio']


def _calculate(mesh_manager, quality):
    calc = mesh_manager.createMeshCalculator()
    _configure(calc, quality)
    mesh = calc.calculate()
    if mesh is None or mesh.triangleCount == 0:
        return None
    coords = mesh.nodeCoordinatesAsDouble
    points = [(coords[i], coords[i + 1], coords[i + 2]) for i in range(0, len(coords), 3)]
    idx = mesh.nodeIndices
    tris = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx), 3)]
    normals = mesh.normalVectorsAsDouble
    if len(normals) == len(coords):
        normals = [(normals[i], normals[i + 1], normals[i + 2]) for i in range(0, len(normals), 3)]
    else:
        normals = None
    return points, tris, normals


def _orient(points, tris, normals):
    # Fusion's face meshes aren't guaranteed to wind outward; slicers need
    # them to. Flip any triangle that disagrees with the surface normals.
    if not normals:
        return tris
    out = []
    for a, b, c in tris:
        pa, pb, pc = points[a], points[b], points[c]
        u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        v = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        g = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        n = [normals[a][i] + normals[b][i] + normals[c][i] for i in range(3)]
        out.append((a, c, b) if g[0] * n[0] + g[1] * n[1] + g[2] * n[2] < 0 else (a, b, c))
    return out


class _Welder:
    def __init__(self, mesh):
        self.mesh = mesh
        self.index = {}

    def add(self, p):
        key = (round(p[0], WELD_DECIMALS), round(p[1], WELD_DECIMALS), round(p[2], WELD_DECIMALS))
        i = self.index.get(key)
        if i is None:
            i = self.index[key] = len(self.mesh.vertices)
            self.mesh.vertices.append(p)
        return i


def _add_patch(welder, points, tris, matrix, rgb):
    mesh = welder.mesh
    ids = []
    for p in points:
        if matrix is not None:
            p = _transform(matrix, *p)
        ids.append(welder.add((p[0] * MM_PER_CM, p[1] * MM_PER_CM, p[2] * MM_PER_CM)))
    for a, b, c in tris:
        a, b, c = ids[a], ids[b], ids[c]
        if a != b and b != c and a != c:
            mesh.triangles.append((a, b, c))
            mesh.colors.append(rgb)


def open_edge_count(triangles):
    counts = {}
    for a, b, c in triangles:
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            counts[key] = counts.get(key, 0) + 1
    return sum(1 for n in counts.values() if n == 1)


def _centroid(mesh, tri):
    a, b, c = (mesh.vertices[i] for i in tri)
    return ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0, (a[2] + b[2] + c[2]) / 3.0)


def nearest_colors(points, ref_points, ref_colors):
    # Grid-accelerated nearest-neighbour lookup of each point's color.
    if not ref_points:
        return [FALLBACK_RGB] * len(points)
    lo, hi = _bbox(ref_points)
    extent = max(hi[i] - lo[i] for i in range(3)) or 1.0
    cell = max(2.0 * extent / math.sqrt(len(ref_points)), 1e-6)
    grid = {}
    for i, (x, y, z) in enumerate(ref_points):
        grid.setdefault((int(x // cell), int(y // cell), int(z // cell)), []).append(i)
    max_ring = int(extent / cell) + 2
    out = []
    for x, y, z in points:
        cx, cy, cz = int(x // cell), int(y // cell), int(z // cell)
        best, best_d = None, float('inf')
        for r in range(max_ring + 1):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        if max(abs(dx), abs(dy), abs(dz)) != r:
                            continue
                        for i in grid.get((cx + dx, cy + dy, cz + dz), ()):
                            p = ref_points[i]
                            d = (p[0] - x) ** 2 + (p[1] - y) ** 2 + (p[2] - z) ** 2
                            if d < best_d:
                                best, best_d = i, d
            # Anything in a farther ring is at least r * cell away.
            if best is not None and best_d <= (r * cell) ** 2:
                break
        out.append(ref_colors[best] if best is not None else FALLBACK_RGB)
    return out


def mesh_body(body, quality, name):
    # Mesh face by face so every triangle knows its face's color, then weld
    # the patches into one mesh.
    patches = []
    for face in body.faces:
        result = _calculate(face.meshManager, quality)
        if result is None:
            continue
        points, tris, normals = result
        patches.append((points, _orient(points, tris, normals), appearance_rgb(face.appearance)))
    if not patches:
        return None

    matrix = _pick_transform([p for patch in patches for p in patch[0]], body)
    mesh = ColoredMesh(name)
    welder = _Welder(mesh)
    for points, tris, rgb in patches:
        _add_patch(welder, points, tris, matrix, rgb)
    if open_edge_count(mesh.triangles) == 0:
        return mesh

    # Face meshes didn't line up exactly along shared edges. Use the
    # watertight whole-body mesh and color it from the nearest face triangle.
    result = _calculate(body.meshManager, quality)
    if result is None:
        return mesh
    points, tris, normals = result
    whole = ColoredMesh(name)
    whole.method = 'body'
    _add_patch(_Welder(whole), points, _orient(points, tris, normals),
               _pick_transform(points, body), FALLBACK_RGB)
    whole.colors = nearest_colors([_centroid(whole, t) for t in whole.triangles],
                                  [_centroid(mesh, t) for t in mesh.triangles], mesh.colors)
    return whole


# ---------------------------------------------------------------- writing

def write_obj(obj_path, mesh):
    # Every face must have a material: Snapmaker Orca rejects the colors
    # otherwise. Names avoid spaces, which its OBJ parser doesn't handle.
    folder = os.path.dirname(obj_path)
    stem = os.path.splitext(os.path.basename(obj_path))[0]
    mtl_name = stem + '.mtl'

    palette = sorted(set(mesh.colors))
    material = {rgb: f'color_{i + 1}' for i, rgb in enumerate(palette)}

    with open(os.path.join(folder, mtl_name), 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Fusion appearance colors\n')
        for rgb in palette:
            r, g, b = (c / 255.0 for c in rgb)
            f.write(f'newmtl {material[rgb]}\n# #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}\n'
                    f'Ka 0 0 0\nKd {r:.6f} {g:.6f} {b:.6f}\nd 1\n\n')

    by_color = {}
    for tri, rgb in zip(mesh.triangles, mesh.colors):
        by_color.setdefault(rgb, []).append(tri)

    with open(obj_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'# Exported from Autodesk Fusion by Fusion Slicer Exporter (units: mm)\nmtllib {mtl_name}\n')
        f.write(''.join(f'v {x:.5f} {y:.5f} {z:.5f}\n' for x, y, z in mesh.vertices))
        for rgb in palette:
            f.write(f'usemtl {material[rgb]}\n')
            f.write(''.join(f'f {a + 1} {b + 1} {c + 1}\n' for a, b, c in by_color[rgb]))
    return obj_path


# ---------------------------------------------------- painted 3MF (PrusaSlicer)

# Paint state of a triangle for extruders 1-16, as PrusaSlicer, Bambu Studio
# and OrcaSlicer serialize it in 3MF files (TriangleSelector bit encoding).
PAINT_CODES = ['', '4', '8', '0C', '1C', '2C', '3C', '4C', '5C', '6C', '7C', '8C', '9C', 'AC', 'BC', 'CC', 'DC']
MAX_EXTRUDERS = len(PAINT_CODES) - 1

COLOR_NAMES = {
    'black': (0, 0, 0), 'dark grey': (64, 64, 64), 'grey': (128, 128, 128), 'light grey': (192, 192, 192),
    'white': (255, 255, 255), 'red': (220, 30, 30), 'dark red': (128, 0, 0), 'orange': (255, 140, 0),
    'yellow': (250, 220, 30), 'gold': (212, 175, 80), 'brown': (120, 70, 30), 'beige': (225, 205, 165),
    'green': (30, 170, 60), 'dark green': (0, 90, 30), 'lime': (160, 230, 50), 'teal': (0, 140, 140),
    'cyan': (0, 200, 230), 'blue': (30, 80, 230), 'navy': (10, 30, 110), 'purple': (130, 50, 180),
    'pink': (240, 130, 180), 'magenta': (220, 0, 200),
}


def color_name(rgb):
    return min(COLOR_NAMES, key=lambda n: sum((a - b) ** 2 for a, b in zip(COLOR_NAMES[n], rgb)))


def _triangle_area(mesh, tri):
    a, b, c = (mesh.vertices[i] for i in tri)
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return 0.5 * math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2 +
                           (u[0] * v[1] - u[1] * v[0]) ** 2)


def extruder_palette(meshes):
    """Maps each color to an extruder (1-based): the color covering the most
    surface gets extruder 1. Past 16 colors, the rest share the closest one."""
    area = {}
    for mesh in meshes:
        for tri, rgb in zip(mesh.triangles, mesh.colors):
            area[rgb] = area.get(rgb, 0.0) + _triangle_area(mesh, tri)
    ordered = sorted(area, key=lambda rgb: (-area[rgb], rgb))
    palette = {rgb: i + 1 for i, rgb in enumerate(ordered[:MAX_EXTRUDERS])}
    for rgb in ordered[MAX_EXTRUDERS:]:
        nearest = min(ordered[:MAX_EXTRUDERS], key=lambda p: sum((a - b) ** 2 for a, b in zip(p, rgb)))
        palette[rgb] = palette[nearest]
    return palette


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
    ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
    ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
    '</Types>\n')
_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
    ' <Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
    '</Relationships>\n')


def write_3mf(path, meshes, palette=None):
    """One object per mesh. With a palette (color -> extruder), every triangle
    is painted with its extruder, for slicers without a color prompt. Without
    one, triangles reference a standard 3MF color group, which Bambu Studio
    turns into its per-face color prompt.

    No slicer settings are included, so slicers treat the file as geometry
    from another program rather than as one of their own projects."""
    colors = sorted({rgb for mesh in meshes for rgb in mesh.colors})
    color_index = {rgb: i for i, rgb in enumerate(colors)}
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n'
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
           'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02" '
           'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n <resources>\n']
    group_id, first_object = 1, 2  # 3MF resource ids share one numbering
    if palette is None:
        out.append(f'  <m:colorgroup id="{group_id}">\n')
        out.append(''.join(f'   <m:color color="#{r:02X}{g:02X}{b:02X}"/>\n' for r, g, b in colors))
        out.append('  </m:colorgroup>\n')
    for object_id, mesh in enumerate(meshes, first_object):
        out.append(f'  <object id="{object_id}" name={quoteattr(mesh.name)} type="model">\n'
                   '   <mesh>\n    <vertices>\n')
        out.append(''.join(f'     <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>\n' for x, y, z in mesh.vertices))
        out.append('    </vertices>\n    <triangles>\n')
        if palette is None:
            out.append(''.join(f'     <triangle v1="{a}" v2="{b}" v3="{c}" pid="{group_id}" p1="{color_index[rgb]}"/>\n'
                               for (a, b, c), rgb in zip(mesh.triangles, mesh.colors)))
        else:
            out.append(''.join(f'     <triangle v1="{a}" v2="{b}" v3="{c}" '
                               f'slic3rpe:mmu_segmentation="{PAINT_CODES[palette[rgb]]}"/>\n'
                               for (a, b, c), rgb in zip(mesh.triangles, mesh.colors)))
        out.append('    </triangles>\n   </mesh>\n  </object>\n')
    out.append(' </resources>\n <build>\n')
    out.append(''.join(f'  <item objectid="{i}"/>\n' for i in range(first_object, first_object + len(meshes))))
    out.append(' </build>\n</model>\n')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _CONTENT_TYPES)
        z.writestr('_rels/.rels', _RELS)
        z.writestr('3D/3dmodel.model', ''.join(out))
    return path
