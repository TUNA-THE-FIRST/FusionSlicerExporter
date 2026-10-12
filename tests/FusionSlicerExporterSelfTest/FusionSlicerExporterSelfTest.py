# Self-test for Fusion Slicer Exporter's color export. Run it from Fusion's
# Scripts and Add-Ins dialog. It builds a new, unsaved test design with
# colored bodies, checks the colored meshes, writes a report to the
# "output" folder next to this script, and leaves the design open so the
# Send to Slicer button can be tried on it. Close it without saving.

import adsk.core
import adsk.fusion
import importlib.util
import json
import math
import os
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, 'output')
ADDIN_MODULE = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'AddIns', 'FusionSlicerExporter',
                            'commands', 'commandDialog', 'color_export.py')

RED, WHITE, GREEN, YELLOW = (200, 30, 30), (240, 240, 240), (20, 160, 60), (240, 200, 20)


def _load_color_export():
    spec = importlib.util.spec_from_file_location('fusionslicerexporter_color_export', ADDIN_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _template_appearance(app):
    # A library appearance with a plain (untextured) opaque color to copy.
    for lib in app.materialLibraries:
        try:
            appearances = lib.appearances
        except Exception:
            continue
        for i in range(min(appearances.count, 400)):
            a = appearances.item(i)
            prop = adsk.core.ColorProperty.cast(a.appearanceProperties.itemById('opaque_albedo'))
            if prop and prop.value is not None and not a.hasTexture:
                return a
    raise RuntimeError('No plain opaque appearance found in the material libraries')


def _colored(design, template, name, rgb):
    a = design.appearances.addByCopy(template, name)
    prop = adsk.core.ColorProperty.cast(a.appearanceProperties.itemById('opaque_albedo'))
    prop.value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
    return a


def _box(tbm, cx, cy, cz, lx, ly, lz):
    obb = adsk.core.OrientedBoundingBox3D.create(
        adsk.core.Point3D.create(cx, cy, cz), adsk.core.Vector3D.create(1, 0, 0),
        adsk.core.Vector3D.create(0, 1, 0), lx, ly, lz)
    return tbm.createBox(obb)


def _build(app, design):
    root = design.rootComponent
    tbm = adsk.fusion.TemporaryBRepManager.get()
    template = _template_appearance(app)
    red = _colored(design, template, 'SelfTest Red', RED)
    white = _colored(design, template, 'SelfTest White', WHITE)
    green = _colored(design, template, 'SelfTest Green', GREEN)
    yellow = _colored(design, template, 'SelfTest Yellow', YELLOW)

    # Dimensions in cm. Base plate 60 x 30 x 4 mm, red, top face white.
    base = root.bRepBodies.add(_box(tbm, 3.0, 1.5, 0.2, 6.0, 3.0, 0.4))
    base.name = 'Base'
    base.appearance = red
    top = max(base.faces, key=lambda f: f.boundingBox.minPoint.z)
    top.appearance = white

    cyl = root.bRepBodies.add(tbm.createCylinderOrCone(
        adsk.core.Point3D.create(1.5, 1.5, 0.4), 0.6, adsk.core.Point3D.create(1.5, 1.5, 1.4), 0.6))
    cyl.name = 'Cylinder'
    cyl.appearance = green

    sphere = root.bRepBodies.add(tbm.createSphere(adsk.core.Point3D.create(4.5, 1.5, 1.0), 0.6))
    sphere.name = 'Sphere (no color)'

    # A component placed 25 mm / 10 mm / 4 mm away, colored at the occurrence level.
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(2.5, 1.0, 0.4)
    occ = root.occurrences.addNewComponent(m)
    occ.component.name = 'Badge'
    occ.component.bRepBodies.add(_box(tbm, 0.5, 0.5, 0.15, 1.0, 1.0, 0.3)).name = 'Badge body'
    occ.appearance = yellow
    badge = occ.bRepBodies.item(0)  # proxy in the design's space

    expected = {
        'Base': {RED, WHITE},
        'Cylinder': {GREEN},
        'Sphere (no color)': None,  # material color, whatever it is
        'Badge body': {YELLOW},
    }
    return [base, cyl, sphere, badge], expected


def _quality(design, body):
    opts = design.exportManager.createSTLExportOptions(body, os.path.join(OUTPUT, 'unused.stl'))
    opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
    return {
        'surface_deviation': opts.surfaceDeviation,
        'normal_deviation': opts.normalDeviation,
        'max_edge_length': opts.maximumEdgeLength,
        'aspect_ratio': opts.aspectRatio,
    }


def _signed_volume(mesh):
    v = 0.0
    for a, b, c in mesh.triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (mesh.vertices[i] for i in (a, b, c))
        v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return v / 6.0


def _consistent(mesh):
    directed = set()
    for a, b, c in mesh.triangles:
        for e in ((a, b), (b, c), (c, a)):
            if e in directed:
                return False
            directed.add(e)
    return all((v, u) in directed for u, v in directed)


def _check_body(ce, design, body, expected, report):
    r = {'name': body.name, 'checks': {}}
    report['bodies'].append(r)
    r['face_sources'] = sorted({f.appearanceSourceType for f in body.faces})
    r['uses_custom_colors'] = ce.uses_custom_colors(body)
    t0 = time.time()
    mesh = ce.mesh_body(body, _quality(design, body), body.name)
    r['seconds'] = round(time.time() - t0, 3)
    r['method'] = mesh.method
    r['triangles'] = len(mesh.triangles)
    r['colors'] = sorted({'#%02X%02X%02X' % c for c in mesh.colors})
    checks = r['checks']
    checks['watertight'] = ce.open_edge_count(mesh.triangles) == 0
    checks['consistent winding'] = _consistent(mesh)
    vol = _signed_volume(mesh)
    ref = body.volume * 1000.0  # cm^3 -> mm^3
    r['volume_mm3'] = [round(vol, 3), round(ref, 3)]
    checks['outward and right size'] = vol > 0 and abs(vol - ref) / ref < 0.03
    bb = body.boundingBox
    lo = [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10]
    hi = [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10]
    xs, ys, zs = zip(*mesh.vertices)
    mlo, mhi = [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]
    r['bbox_mm'] = {'fusion': [lo, hi], 'mesh': [mlo, mhi]}
    checks['in the right place'] = all(abs(a - b) < 0.5 for a, b in zip(lo + hi, mlo + mhi))
    want = expected.get(body.name)
    if want is not None:
        checks['expected colors'] = set(mesh.colors) == want
        checks['custom colors detected'] = r['uses_custom_colors']
    else:
        checks['single material color'] = len(set(mesh.colors)) == 1
        checks['material-only body not flagged'] = not r['uses_custom_colors']
    if body.name == 'Base':
        top = [c for t, c in zip(mesh.triangles, mesh.colors)
               if all(abs(mesh.vertices[i][2] - hi[2]) < 1e-3 for i in t)]
        checks['top face white, rest red'] = bool(top) and set(top) == {WHITE} and \
            mesh.colors.count(RED) == len(mesh.colors) - len(top)
    return mesh


def _appearance_survey(app, ce, report):
    # Which color property ids library appearances use, and what we'd read.
    survey = []
    for lib in app.materialLibraries:
        try:
            appearances = lib.appearances
        except Exception:
            continue
        step = max(1, appearances.count // 60)
        for i in range(0, appearances.count, step):
            a = appearances.item(i)
            ids = []
            for p in a.appearanceProperties:
                if adsk.core.ColorProperty.cast(p):
                    ids.append(p.id)
            survey.append({'library': lib.name, 'name': a.name, 'color_ids': ids,
                           'rgb': '#%02X%02X%02X' % ce.appearance_rgb(a)})
    report['appearance_survey'] = survey


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    os.makedirs(OUTPUT, exist_ok=True)
    report = {'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'fusion_version': app.version,
              'bodies': [], 'errors': []}
    try:
        ce = _load_color_export()
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.DirectDesignType
        bodies, expected = _build(app, design)
        combined = ce.ColoredMesh('SelfTest')
        for body in bodies:
            try:
                combined.extend(_check_body(ce, design, body, expected, report))
            except Exception:
                report['errors'].append(f'{body.name}: {traceback.format_exc()}')
        report['obj'] = ce.write_obj(os.path.join(OUTPUT, 'SelfTest.obj'), combined)
        try:
            _appearance_survey(app, ce, report)
        except Exception:
            report['errors'].append('survey: ' + traceback.format_exc())
    except Exception:
        report['errors'].append(traceback.format_exc())

    failed = [f"{b['name']}: {k}" for b in report['bodies'] for k, ok in b['checks'].items() if not ok]
    passed = sum(1 for b in report['bodies'] for ok in b['checks'].values() if ok)
    report['summary'] = {'passed': passed, 'failed': failed}
    path = os.path.join(OUTPUT, 'report.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    msg = f'{passed} checks passed, {len(failed)} failed, {len(report["errors"])} errors.'
    if failed:
        msg += '\n\nFailed:\n' + '\n'.join(failed[:10])
    if report['errors']:
        msg += '\n\nFirst error:\n' + report['errors'][0][-600:]
    ui.messageBox(msg + f'\n\nReport saved to:\n{path}\n\nThe test design is left open: try '
                  '"Send to Slicer" on it, then close it without saving.',
                  'Fusion Slicer Exporter self-test')
