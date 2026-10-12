"""Offline tests for Fusion Slicer Exporter color export using a stubbed adsk API."""
import sys, os, types, math, tempfile, importlib, unittest
from unittest import mock

# The add-in folder: given on the command line, else this repository.
ADDIN = os.path.abspath(sys.argv.pop(1) if len(sys.argv) > 1 else
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# ------------------------------------------------------------------ adsk stub
class Any:
    def __getattr__(self, n): return Any()
    def __call__(self, *a, **k): return Any()
    def __bool__(self): return True

adsk = types.ModuleType('adsk'); core = types.ModuleType('adsk.core'); fusion = types.ModuleType('adsk.fusion')
core.Application = types.SimpleNamespace(get=lambda: Any())
core.LogLevels = types.SimpleNamespace(InfoLogLevel=0, ErrorLogLevel=2)
core.LogTypes = types.SimpleNamespace(FileLogType=0, ConsoleLogType=1)
core.CommandEventArgs = core.InputChangedEventArgs = core.Event = object
core.AppearanceSourceTypes = types.SimpleNamespace(MaterialAppearanceSource=0, BodyAppearanceSource=1,
                                                  OccurrenceAppearanceSource=2, FaceAppearanceSource=3,
                                                  OverrideAppearanceSource=4)

class Color:
    def __init__(s, r, g, b, a=255): s.red, s.green, s.blue, s.opacity = r, g, b, a

class ColorProperty:
    def __init__(s, pid, color): s.id, s.value = pid, color
    @staticmethod
    def cast(x): return x if isinstance(x, ColorProperty) else None

class FloatProperty:
    def __init__(s, pid): s.id, s.value = pid, 0.5

class Props(list):
    def itemById(s, pid):
        for p in s:
            if p.id == pid: return p
        return None

class Appearance:
    _n = 0
    def __init__(s, props, color=None, raise_color=False):
        Appearance._n += 1
        s.id = f'app{Appearance._n}'
        s.appearanceProperties = Props(props)
        s._color, s._raise = color, raise_color
    @property
    def color(s):
        if s._raise: raise AttributeError('no preview api')
        return s._color

core.ColorProperty = ColorProperty
class MR: MeshRefinementLow, MeshRefinementMedium, MeshRefinementHigh, MeshRefinementCustom = 0, 1, 2, 3
fusion.MeshRefinementSettings = MR
fusion.DistanceUnits = types.SimpleNamespace(MillimeterDistanceUnits=0)
fusion.BRepBody = fusion.Occurrence = Any()
adsk.core, adsk.fusion = core, fusion
sys.modules.update({'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion})

# Register the add-in folder as the "FusionSlicerExporter" package explicitly, so the
# tests work from any working directory and whatever the clone is called.
pkg = 'FusionSlicerExporter'
_package = types.ModuleType(pkg)
_package.__path__ = [ADDIN]
sys.modules[pkg] = _package
ce = importlib.import_module(f'{pkg}.commands.commandDialog.color_export')
entry = importlib.import_module(f'{pkg}.commands.commandDialog.entry')
slicers = importlib.import_module(f'{pkg}.slicers')

# --------------------------------------------------------------- mesh stubs
class TriMesh:
    def __init__(s, pts, tris, normals=None):
        s.nodeCoordinatesAsDouble = [c for p in pts for c in p]
        s.nodeIndices = [i for t in tris for i in t]
        s.normalVectorsAsDouble = [c for n in normals for c in n] if normals else []
        s.triangleCount = len(tris)

class Calc:
    def __init__(s, mesh): s.mesh = mesh
    def calculate(s): return s.mesh

class MeshManager:
    def __init__(s, mesh): s.mesh, s.calcs = mesh, []
    def createMeshCalculator(s):
        c = Calc(s.mesh); s.calcs.append(c); return c

class Face:
    def __init__(s, mesh, appearance, source=1):
        s.meshManager, s.appearance, s.appearanceSourceType = MeshManager(mesh), appearance, source

class P3:
    def __init__(s, x, y, z): s.x, s.y, s.z = x, y, z

class Body:
    def __init__(s, faces, whole=None, occ=None, bbox=None, name='Body1'):
        s.faces, s.name, s.assemblyContext = faces, name, occ
        s.meshManager = MeshManager(whole)
        lo, hi = bbox or ((0, 0, 0), (1, 1, 1))
        s.boundingBox = types.SimpleNamespace(minPoint=P3(*lo), maxPoint=P3(*hi))

class Occ:
    def __init__(s, tx, ty, tz):
        m = [1, 0, 0, tx, 0, 1, 0, ty, 0, 0, 1, tz, 0, 0, 0, 1]
        s.transform2 = types.SimpleNamespace(asArray=lambda: m)

def solid(rgb):
    return Appearance([FloatProperty('surface_roughness'), ColorProperty('opaque_albedo', Color(*rgb))])

# Unit cube (1 cm) split into 6 face patches, 2 triangles each, sharing corner
# coordinates exactly like Fusion face meshes along shared edges.
CUBE_FACES = {
    #        4 corners (counter-clockwise seen from outside)          outward normal
    'bottom': ([(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], (0, 0, -1)),
    'top':    ([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], (0, 0, 1)),
    'front':  ([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], (0, -1, 0)),
    'back':   ([(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], (0, 1, 0)),
    'left':   ([(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)], (-1, 0, 0)),
    'right':  ([(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], (1, 0, 0)),
}

def face_mesh(name, flip=False, offset=(0, 0, 0)):
    pts, n = CUBE_FACES[name]
    pts = [(x + offset[0], y + offset[1], z + offset[2]) for x, y, z in pts]
    tris = [(0, 1, 2), (0, 2, 3)]
    if flip:  # Fusion may wind a face inward; normals still point out
        tris = [(0, 2, 1), (0, 3, 2)]
    return TriMesh(pts, tris, [n] * 4)

def whole_cube(offset=(0, 0, 0)):
    pts, tris, normals, index = [], [], [], {}
    for name, (corners, n) in CUBE_FACES.items():
        ids = []
        for c in corners:
            c = (c[0] + offset[0], c[1] + offset[1], c[2] + offset[2])
            if c not in index:
                index[c] = len(pts); pts.append(c); normals.append((0, 0, 0))
            ids.append(index[c])
        tris += [(ids[0], ids[1], ids[2]), (ids[0], ids[2], ids[3])]
    # node normals: direction from cube centre
    normals = [(x - 0.5 - offset[0], y - 0.5 - offset[1], z - 0.5 - offset[2]) for x, y, z in pts]
    return TriMesh(pts, tris, normals)

RED, BLUE, GREEN = (200, 30, 30), (20, 40, 220), (10, 180, 60)

def cube_body(top_color=BLUE, flip=(), split_top_edge=False, occ=None, offset=(0, 0, 0), bbox_offset=None):
    faces = []
    for name in CUBE_FACES:
        if name == 'top' and split_top_edge:
            # Extra node mid-edge: a T-junction against the 'front' face.
            pts = [(0, 0, 1), (0.5, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
            pts = [(x + offset[0], y + offset[1], z + offset[2]) for x, y, z in pts]
            m = TriMesh(pts, [(0, 1, 4), (1, 3, 4), (1, 2, 3)], [(0, 0, 1)] * 5)
            faces.append(Face(m, solid(top_color), 4))
            continue
        app = solid(top_color) if name == 'top' else solid(RED)
        faces.append(Face(face_mesh(name, name in flip, offset), app, 4 if name == 'top' else 1))
    bo = bbox_offset if bbox_offset is not None else offset
    return Body(faces, whole_cube(offset), occ=occ,
                bbox=((bo[0], bo[1], bo[2]), (1 + bo[0], 1 + bo[1], 1 + bo[2])))

QUALITY = {'surface_deviation': 0.01, 'normal_deviation': 0.3, 'max_edge_length': 5.0, 'aspect_ratio': 10.0}

def signed_volume(mesh):
    v = 0.0
    for a, b, c in mesh.triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (mesh.vertices[i] for i in (a, b, c))
        v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return v / 6.0

def consistently_oriented(mesh):
    directed = set()
    for a, b, c in mesh.triangles:
        for e in ((a, b), (b, c), (c, a)):
            if e in directed: return False
            directed.add(e)
    return all((v, u) in directed for u, v in directed)

# ----------------------------------------------- Orca OBJ/MTL reader (python port)
def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines(True)


def orca_read(obj_path):
    """Mirror of the parts of Snapmaker Orca 2.4.0 objparser/OBJ.cpp we rely on."""
    folder = os.path.dirname(obj_path)
    verts, faces, usemtls, mtllibs = [], [], [], []
    for raw in _read_lines(obj_path):
        line = raw.rstrip('\n')
        if not line or line[0] == '#': continue
        tag, _, rest = line.partition(' ')
        if tag == 'v':
            parts = rest.split()
            assert len(parts) == 3, 'vertex colors would switch Orca to vertex-color mode'
            verts.append(tuple(float(p) for p in parts))
        elif tag == 'f':
            idx = [int(p.split('/')[0]) - 1 for p in rest.split()]
            assert len(idx) in (3, 4)
            assert all(0 <= i < len(verts) for i in idx), 'invalid vertex index'
            faces.append(idx)
            if usemtls: usemtls[-1][2] += 1
        elif tag == 'usemtl':
            start = usemtls[-1][1] + usemtls[-1][2] if usemtls else 0
            usemtls.append([rest, start, 0])
        elif tag == 'mtllib':
            mtllibs.append(rest)
        elif tag in ('o', 'g', 's'):
            raise AssertionError(f'{tag} lines can break Orca\'s parser with spaces in names')
        else:
            raise AssertionError(f'unknown OBJ command {tag!r}')
    mtl = {}
    cur = None
    for lib in mtllibs:
        for raw in _read_lines(os.path.join(folder, lib)):
            line = raw.strip()
            if not line or line[0] == '#': continue
            tag, _, rest = line.partition(' ')
            if tag == 'newmtl':
                cur = rest; mtl[cur] = {'Ka': (0, 0, 0), 'Kd': None}
            elif tag in ('Ka', 'Kd'):
                mtl[cur][tag] = tuple(float(x) for x in rest.split())
    colors = []
    for fi in range(len(faces)):
        name = next((n for n, s, c in usemtls if s <= fi < s + c), None)
        assert name in mtl, f'face {fi} has no material -> Orca drops all colors'
        ka, kd = mtl[name]['Ka'], mtl[name]['Kd']
        merged = all(ka[i] + kd[i] <= 1.0 for i in range(3))
        colors.append(tuple(round(255 * (ka[i] + kd[i] if merged else kd[i])) for i in range(3)))
    return verts, faces, colors


class ColorTests(unittest.TestCase):
    def test_appearance_rgb_preference_and_fallbacks(self):
        self.assertEqual(ce.appearance_rgb(solid((1, 2, 3))), (1, 2, 3))
        metal = Appearance([ColorProperty('metal_f0', Color(9, 8, 7))])
        self.assertEqual(ce.appearance_rgb(metal), (9, 8, 7))
        textured = Appearance([ColorProperty('opaque_albedo', None)], color=Color(4, 5, 6))
        self.assertEqual(ce.appearance_rgb(textured), (4, 5, 6))
        other = Appearance([ColorProperty('some_tint', Color(11, 12, 13))], raise_color=True)
        self.assertEqual(ce.appearance_rgb(other), (11, 12, 13))
        nothing = Appearance([FloatProperty('x')], raise_color=True)
        self.assertEqual(ce.appearance_rgb(nothing), ce.FALLBACK_RGB)
        self.assertEqual(ce.appearance_rgb(None), ce.FALLBACK_RGB)

    def test_copied_appearances_sharing_an_id_keep_their_colors(self):
        # Regression: Fusion gives copies of an appearance the same id.
        body = cube_body()
        red_copy = solid(RED); white_copy = solid((240, 240, 240))
        red_copy.id = white_copy.id = 'same-asset-id'
        names = list(CUBE_FACES)
        for name, face in zip(names, body.faces):
            face.appearance = white_copy if name == 'top' else red_copy
        # Put the top face first, as Fusion did in the self-test.
        top = names.index('top')
        body.faces.insert(0, body.faces.pop(top))
        m = ce.mesh_body(body, QUALITY, 'cube')
        self.assertEqual(sorted(set(m.colors)), sorted({RED, (240, 240, 240)}))
        self.assertEqual(m.colors.count(RED), 10)

    def test_uses_custom_colors(self):
        mat = Body([Face(None, None, 0), Face(None, None, 0)])
        self.assertFalse(ce.uses_custom_colors(mat))
        self.assertTrue(ce.uses_custom_colors(Body([Face(None, None, 0), Face(None, None, 4)])))
        self.assertTrue(ce.uses_custom_colors(Body([Face(None, None, 2)])))  # occurrence colour

    def test_cube_per_face_watertight_colored_oriented(self):
        body = cube_body(flip=('left', 'top'))
        m = ce.mesh_body(body, QUALITY, 'cube')
        self.assertEqual(len(m.vertices), 8)
        self.assertEqual(len(m.triangles), 12)
        self.assertEqual(ce.open_edge_count(m.triangles), 0)
        self.assertTrue(consistently_oriented(m))
        self.assertAlmostEqual(signed_volume(m), 1000.0, places=6)  # 10 mm cube, outward
        top = [c for t, c in zip(m.triangles, m.colors) if all(m.vertices[i][2] == 10 for i in t)]
        self.assertEqual(top, [BLUE, BLUE])
        self.assertEqual(m.colors.count(RED), 10)
        # quality settings reach the calculator
        calc = body.faces[0].meshManager.calcs[0]
        self.assertEqual((calc.surfaceTolerance, calc.maxNormalDeviation, calc.maxSideLength, calc.maxAspectRatio),
                         (0.01, 0.3, 5.0, 10.0))

    def test_t_junction_falls_back_to_whole_body(self):
        body = cube_body(split_top_edge=True)
        m = ce.mesh_body(body, QUALITY, 'cube')
        self.assertEqual(ce.open_edge_count(m.triangles), 0)
        self.assertTrue(consistently_oriented(m))
        self.assertGreater(signed_volume(m), 0)
        top = [c for t, c in zip(m.triangles, m.colors) if all(m.vertices[i][2] == 10 for i in t)]
        self.assertEqual(top, [BLUE, BLUE])
        self.assertEqual(m.colors.count(RED), 10)

    def test_component_transform_applied_when_meshes_are_local(self):
        body = cube_body(occ=Occ(5, 0, 0), bbox_offset=(5, 0, 0))  # meshes local, bbox in design space
        m = ce.mesh_body(body, QUALITY, 'cube')
        xs = [v[0] for v in m.vertices]
        self.assertEqual((min(xs), max(xs)), (50.0, 60.0))

    def test_component_transform_skipped_when_meshes_are_already_placed(self):
        body = cube_body(occ=Occ(5, 0, 0), offset=(5, 0, 0))  # meshes and bbox already in design space
        m = ce.mesh_body(body, QUALITY, 'cube')
        xs = [v[0] for v in m.vertices]
        self.assertEqual((min(xs), max(xs)), (50.0, 60.0))

    def test_nearest_colors(self):
        ref = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (100, 100, 100)]
        cols = ['a', 'b', 'c', 'd']
        got = ce.nearest_colors([(1, 0, 0), (9, 1, 0), (0, 8, 0), (90, 90, 90), (-50, -50, -50)], ref, cols)
        self.assertEqual(got, ['a', 'b', 'c', 'd', 'a'])
        # brute-force agreement on random data
        import random
        rnd = random.Random(1)
        ref = [(rnd.uniform(0, 50), rnd.uniform(0, 50), rnd.uniform(0, 5)) for _ in range(500)]
        q = [(rnd.uniform(-5, 55), rnd.uniform(-5, 55), rnd.uniform(-5, 10)) for _ in range(300)]
        got = ce.nearest_colors(q, ref, list(range(500)))
        for p, g in zip(q, got):
            best = min(range(500), key=lambda i: sum((ref[i][k] - p[k]) ** 2 for k in range(3)))
            self.assertAlmostEqual(sum((ref[g][k] - p[k]) ** 2 for k in range(3)),
                                   sum((ref[best][k] - p[k]) ** 2 for k in range(3)))

    def test_write_obj_readable_by_orca_rules(self):
        m = ce.mesh_body(cube_body(), QUALITY, 'cube')
        with tempfile.TemporaryDirectory() as d:
            path = ce.write_obj(os.path.join(d, 'My_Part_0.obj'), m)
            self.assertTrue(os.path.exists(os.path.join(d, 'My_Part_0.mtl')))
            verts, faces, colors = orca_read(path)
        self.assertEqual(len(verts), 8)
        self.assertEqual(len(faces), 12)
        self.assertEqual(sorted(colors), sorted(m.colors))
        self.assertEqual(colors.count(BLUE), 2)

    def test_combined_meshes_keep_separate_shells(self):
        a = ce.mesh_body(cube_body(), QUALITY, 'a')
        b = ce.mesh_body(cube_body(offset=(2, 0, 0)), QUALITY, 'b')
        c = ce.ColoredMesh('both'); c.extend(a); c.extend(b)
        self.assertEqual(len(c.vertices), 16)
        self.assertEqual(ce.open_edge_count(c.triangles), 0)
        self.assertAlmostEqual(signed_volume(c), 2000.0, places=6)
        with tempfile.TemporaryDirectory() as d:
            verts, faces, colors = orca_read(ce.write_obj(os.path.join(d, 'both.obj'), c))
        self.assertEqual((len(verts), len(faces)), (16, 24))


# ------------------------------------ PrusaSlicer 3MF reader (python port)
import zipfile, xml.parsers.expat

def prusa_decode(code):
    """PrusaSlicer 2.9.6 FacetsAnnotation::set_triangle_from_string + decode_leaf_state."""
    if code == '':
        return 0
    bits = []
    for ch in reversed(code):
        dec = int(ch, 16)
        bits += [bool(dec & (1 << i)) for i in range(4)]
    pos = [0]
    def nibble():
        n = sum(bits[pos[0] + i] << i for i in range(4)); pos[0] += 4; return n
    c = nibble()
    assert c & 0b11 == 0, 'split triangle'
    if (c & 0b1100) != 0b1100:
        return c >> 2
    second = nibble()
    assert second != 0b1110, 'extended states not used'
    return second + 3

def prusa_read(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert '3D/3dmodel.model' in names
        assert not any(n.startswith('Metadata/Slic3r_PE') for n in names), 'would be treated as a project'
        data = z.read('3D/3dmodel.model')
    objects, items, cur = {}, [], {}
    model_attrs = {}
    def start(tag, a):
        if tag == 'model': model_attrs.update(a)
        elif tag == 'object': cur.update(id=int(a['id']), name=a.get('name'), v=[], t=[])
        elif tag == 'vertex': cur['v'].append((float(a['x']), float(a['y']), float(a['z'])))
        elif tag == 'triangle':
            cur['t'].append(((int(a['v1']), int(a['v2']), int(a['v3'])), a.get('slic3rpe:mmu_segmentation', '')))
        elif tag == 'item': items.append(int(a['objectid']))
        elif tag == 'metadata': assert a.get('name') != 'slic3rpe:Version3mf'
    def end(tag):
        if tag == 'object': objects[cur['id']] = dict(cur)
    p = xml.parsers.expat.ParserCreate()  # no namespace processing, like PrusaSlicer
    p.StartElementHandler, p.EndElementHandler = start, end
    p.Parse(data, True)
    assert model_attrs.get('unit') == 'millimeter'
    for o in objects.values():
        for (a, b, c), _ in o['t']:
            assert max(a, b, c) < len(o['v'])
    return [objects[i] for i in items]


def bambu_read(path):
    """Bambu Studio 2.08 _BBS_3MF_Importer rules for 3MFs from other programs:
    m:colorgroup/m:color colors, and per-triangle pid/p1 (else the object's pid/pindex).
    Colors are only used when every triangle has one."""
    with zipfile.ZipFile(path) as z:
        data = z.read('3D/3dmodel.model')
    groups, cur_group, objects, cur = {}, [None], [], {}
    def start(tag, a):
        if tag == 'metadata': assert a.get('name') != 'Application', 'would look like a Bambu project'
        elif tag == 'm:colorgroup': cur_group[0] = int(a['id']); groups[cur_group[0]] = []
        elif tag == 'm:color': groups[cur_group[0]].append(a['color'])
        elif tag == 'object': cur.update(name=a.get('name'), pid=int(a.get('pid', -1)), pindex=int(a.get('pindex', -1)), t=[], colors=[])
        elif tag == 'triangle':
            cur['t'].append(1)
            pid = int(a['pid']) if 'pid' in a else cur['pid']
            if pid >= 0:
                p1 = int(a['p1']) if 'p1' in a else cur['pindex']
                cur['colors'].append(groups[pid][p1])
    def end(tag):
        if tag == 'object':
            assert len(cur['colors']) == len(cur['t']), 'Bambu ignores colors unless every triangle has one'
            objects.append(dict(cur))
    p = xml.parsers.expat.ParserCreate()
    p.StartElementHandler, p.EndElementHandler = start, end
    p.Parse(data, True)
    return objects


class BambuTests(unittest.TestCase):
    def test_colorgroup_3mf_exact_colors(self):
        a = ce.mesh_body(cube_body(), QUALITY, 'Lid')
        b = ce.mesh_body(cube_body(top_color=GREEN, offset=(2, 0, 0)), QUALITY, 'Base')
        with tempfile.TemporaryDirectory() as d:
            path = ce.write_3mf(os.path.join(d, 'x.3mf'), [a, b])
            objs = bambu_read(path)
            with zipfile.ZipFile(path) as z:
                self.assertNotIn(b'mmu_segmentation', z.read('3D/3dmodel.model'))
        self.assertEqual([o['name'] for o in objs], ['Lid', 'Base'])
        for o, src in zip(objs, (a, b)):
            self.assertEqual(o['colors'], ['#%02X%02X%02X' % c for c in src.colors])

    def test_painted_3mf_has_no_color_groups(self):
        a = ce.mesh_body(cube_body(), QUALITY, 'Lid')
        with tempfile.TemporaryDirectory() as d:
            path = ce.write_3mf(os.path.join(d, 'x.3mf'), [a], ce.extruder_palette([a]))
            with zipfile.ZipFile(path) as z:
                self.assertNotIn(b'colorgroup', z.read('3D/3dmodel.model'))


class PrusaTests(unittest.TestCase):
    def test_paint_codes_decode_to_extruders(self):
        for extruder in range(1, ce.MAX_EXTRUDERS + 1):
            self.assertEqual(prusa_decode(ce.PAINT_CODES[extruder]), extruder)

    def test_palette_orders_by_area_and_caps_at_16(self):
        m = ce.ColoredMesh('m')
        big, small = [(0, 0, 0), (10, 0, 0), (0, 10, 0)], [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        def tri(pts, rgb):
            base = len(m.vertices); m.vertices.extend(pts)
            m.triangles.append((base, base + 1, base + 2)); m.colors.append(rgb)
        tri(small, RED); tri(big, BLUE); tri(small, BLUE)
        self.assertEqual(ce.extruder_palette([m]), {BLUE: 1, RED: 2})
        n = ce.ColoredMesh('n')
        for i in range(18):
            m2 = ce.ColoredMesh('x'); m2.vertices = [(0, 0, 0), (20 - i, 0, 0), (0, 10, 0)]
            m2.triangles = [(0, 1, 2)]; m2.colors = [(i * 14, 0, 0)]; n.extend(m2)
        pal = ce.extruder_palette([n])
        self.assertEqual(max(pal.values()), 16)
        self.assertEqual(pal[(16 * 14, 0, 0)], pal[(15 * 14, 0, 0)])  # extras share the closest

    def test_write_3mf_readable_by_prusa_rules(self):
        a = ce.mesh_body(cube_body(), QUALITY, 'Lid & "Top" <1>')
        b = ce.mesh_body(cube_body(offset=(2, 0, 0)), QUALITY, 'Base')
        pal = ce.extruder_palette([a, b])
        with tempfile.TemporaryDirectory() as d:
            objs = prusa_read(ce.write_3mf(os.path.join(d, 'x.3mf'), [a, b], pal))
        self.assertEqual([o['name'] for o in objs], ['Lid & "Top" <1>', 'Base'])
        for o, src in zip(objs, (a, b)):
            self.assertEqual(len(o['v']), len(src.vertices))
            got = [prusa_decode(code) for _, code in o['t']]
            self.assertEqual(got, [pal[c] for c in src.colors])
        self.assertEqual(pal[RED], 1)  # red covers 10 of each cube's 12 faces

    def test_color_names(self):
        self.assertEqual(ce.color_name((0xEC, 0x12, 0x12)), 'red')
        self.assertEqual(ce.color_name((0x00, 0x11, 0xFF)), 'blue')
        self.assertEqual(ce.color_name((0xDB, 0xB9, 0x52)), 'gold')
        self.assertEqual(ce.color_name((255, 255, 255)), 'white')


class EntryFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stl_calls = []
        def fake_stl(exportMgr, indexed, ref, inputs, temp_dir):
            self.stl_calls.append([i for i, _ in indexed])
            return [os.path.join(temp_dir, f'{i}.stl') for i, _ in indexed]
        self.p1 = mock.patch.object(entry, '_export_stl', fake_stl)
        self.p2 = mock.patch.object(entry, '_mesh_quality', lambda *a: QUALITY)
        self.p3 = mock.patch.object(entry, '_design_name', lambda: 'My Design v2')
        for p in (self.p1, self.p2, self.p3): p.start()
        self.orca, self.prusa = slicers.by_name('OrcaSlicer'), slicers.by_name('PrusaSlicer')
        self.bambu = slicers.by_name('Bambu Studio')

    def tearDown(self):
        for p in (self.p1, self.p2, self.p3): p.stop()
        self.tmp.cleanup()

    def plain_body(self, offset):
        b = cube_body(offset=offset)
        for f in b.faces: f.appearanceSourceType = 0
        return b

    def export(self, bodies, combine, target):
        return entry._export_colored(None, bodies, 'High', None, self.tmp.name, combine, target)

    def test_no_colors_returns_none(self):
        for target in (self.orca, self.prusa, self.bambu):
            self.assertEqual(self.export([self.plain_body((0, 0, 0))], True, target), (None, None))

    def test_combined_one_obj_with_all_bodies(self):
        files, palette = self.export([cube_body(), self.plain_body((3, 0, 0))], True, self.orca)
        self.assertIsNone(palette)
        self.assertEqual([os.path.basename(f) for f in files], ['My_Design_v2.obj'])
        verts, faces, colors = orca_read(files[0])
        self.assertEqual(len(faces), 24)
        self.assertEqual(self.stl_calls, [])

    def test_separate_colored_obj_plain_stl(self):
        bodies = [self.plain_body((0, 0, 0)), cube_body(offset=(3, 0, 0))]
        bodies[1].name = 'Lid Top'
        files, _ = self.export(bodies, False, self.orca)
        self.assertEqual([os.path.basename(f) for f in files], ['Lid_Top_1.obj', '0.stl'])
        self.assertEqual(self.stl_calls, [[0]])
        orca_read(files[0])

    def test_prusa_combined_one_painted_object(self):
        files, palette = self.export([cube_body(), self.plain_body((3, 0, 0))], True, self.prusa)
        self.assertEqual([os.path.basename(f) for f in files], ['My_Design_v2.3mf'])
        (obj,) = prusa_read(files[0])
        self.assertEqual(obj['name'], 'My Design v2')
        self.assertEqual(len(obj['t']), 24)
        self.assertEqual(sorted({prusa_decode(c) for _, c in obj['t']}), sorted(set(palette.values())))
        self.assertEqual(self.stl_calls, [])

    def test_prusa_separate_one_file_many_objects(self):
        bodies = [cube_body(), self.plain_body((3, 0, 0)), cube_body(offset=(6, 0, 0))]
        bodies[0].name, bodies[2].name = 'A', 'C'
        files, palette = self.export(bodies, False, self.prusa)
        self.assertEqual([os.path.basename(f) for f in files], ['My_Design_v2.3mf', '1.stl'])
        self.assertEqual([o['name'] for o in prusa_read(files[0])], ['A', 'C'])
        self.assertEqual(self.stl_calls, [[1]])


    def test_bambu_combined_and_separate_use_color_group_3mf(self):
        files, palette = self.export([cube_body(), self.plain_body((3, 0, 0))], True, self.bambu)
        self.assertIsNone(palette)
        self.assertEqual([os.path.basename(f) for f in files], ['My_Design_v2.3mf'])
        (obj,) = bambu_read(files[0])
        self.assertEqual(len(obj['colors']), 24)
        bodies = [cube_body(), self.plain_body((3, 0, 0)), cube_body(offset=(6, 0, 0))]
        bodies[0].name, bodies[2].name = 'A', 'C'
        files, _ = self.export(bodies, False, self.bambu)
        self.assertEqual([os.path.basename(f) for f in files], ['My_Design_v2.3mf', '1.stl'])
        self.assertEqual([o['name'] for o in bambu_read(files[0])], ['A', 'C'])

    def test_every_slicer_has_a_known_format(self):
        self.assertEqual({s.name: s.color_format for s in slicers.SLICERS},
                         {'Snapmaker Orca': 'obj', 'Bambu Studio': '3mf-colors',
                          'OrcaSlicer': 'obj', 'PrusaSlicer': '3mf-painted'})


class NotesTests(unittest.TestCase):
    def run_notes(self, target, palette=None, store=None):
        store = {} if store is None else store
        shown = []
        with mock.patch.object(entry.config, 'load_state', lambda: dict(store)), \
             mock.patch.object(entry.config, 'save_state', lambda s: (store.clear(), store.update(s))), \
             mock.patch.object(entry, 'ui', types.SimpleNamespace(messageBox=lambda *a: shown.append(a))):
            entry._show_color_notes(target, palette)
        return shown, store

    def test_snapmaker_tip_once_with_filament1_step(self):
        snap = slicers.by_name('Snapmaker Orca')
        shown, store = self.run_notes(snap)
        self.assertIn('set its filament to 1', shown[0][0].replace('\n', ' '))
        self.assertEqual(self.run_notes(snap, store=store)[0], [])
        self.assertEqual(self.run_notes(snap, store={'colorTipShown': True})[0], [])  # pre-1.3 state

    def test_bambu_and_orca_tips_separate_and_without_filament1_step(self):
        store = {}
        for name in ('Bambu Studio', 'OrcaSlicer'):
            shown, store = self.run_notes(slicers.by_name(name), store=store)
            self.assertEqual(len(shown), 1, name)
            self.assertNotIn('filament to 1', shown[0][0])
            self.assertEqual('new Bambu Studio window' in shown[0][0], name == 'Bambu Studio' and sys.platform == 'darwin')
            self.assertEqual(self.run_notes(slicers.by_name(name), store=store)[0], [])

    def test_prusa_lists_extruders_every_time(self):
        prusa = slicers.by_name('PrusaSlicer')
        pal = {RED: 1, BLUE: 2, (250, 0, 0): 2}
        for _ in range(2):
            shown, _ = self.run_notes(prusa, pal)
            text = shown[0][0]
            self.assertIn('Extruder 1: red (#C81E1E)', text)
            self.assertIn('Extruder 2: blue (#1428DC), red (#FA0000)', text)


class TipAndStateTests(unittest.TestCase):
    def test_state_merged_on_save(self):
        store = {'refinement': 'High', 'customKey': 1, 'colorTipShown': True}
        items = {'keepColors': types.SimpleNamespace(value=False),
                 'colorLayout': types.SimpleNamespace(selectedItem=types.SimpleNamespace(name=entry.LAYOUT_SEPARATE)),
                 'slicer': types.SimpleNamespace(selectedItem=types.SimpleNamespace(index=3))}
        inputs = types.SimpleNamespace(itemById=lambda i: items[i])
        with mock.patch.object(entry.config, 'load_state', lambda: dict(store)), \
             mock.patch.object(entry.config, 'save_state', lambda s: (store.clear(), store.update(s))), \
             mock.patch.object(entry, '_slider', lambda inputs, pid: types.SimpleNamespace(valueOne=1.5)):
            entry._save_state(inputs, 'Custom')
        self.assertTrue(store['colorTipShown'])
        self.assertEqual(store['customKey'], 1)
        self.assertEqual((store['refinement'], store['keepColors'], store['colorLayout'], store['slicer']),
                         ('Custom', False, entry.LAYOUT_SEPARATE, 'PrusaSlicer'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
