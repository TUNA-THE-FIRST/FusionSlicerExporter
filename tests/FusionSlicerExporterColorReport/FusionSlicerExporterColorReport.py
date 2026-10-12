# Read-only diagnostic for Fusion Slicer Exporter's color export. Run it with the
# design you want to send open. It lists every appearance used on the
# design's bodies and faces and the color the add-in reads from each, and
# writes output/color_report.json next to this script. Nothing is changed.

import adsk.core
import adsk.fusion
import importlib.util
import json
import os
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, 'output')
ADDIN_MODULE = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'AddIns', 'FusionSlicerExporter',
                            'commands', 'commandDialog', 'color_export.py')
SOURCES = {0: 'material', 1: 'body', 2: 'occurrence', 3: 'face', 4: 'override'}


def _load_color_export():
    spec = importlib.util.spec_from_file_location('fusionslicerexporter_color_export', ADDIN_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hex(rgb):
    return '#%02X%02X%02X' % tuple(rgb)


def _describe(appearance):
    info = {'name': appearance.name, 'id': appearance.id, 'hasTexture': appearance.hasTexture,
            'color_properties': {}}
    for prop in appearance.appearanceProperties:
        cp = adsk.core.ColorProperty.cast(prop)
        if not cp:
            continue
        try:
            value = cp.value
            info['color_properties'][prop.id] = _hex((value.red, value.green, value.blue)) if value else \
                ('texture' if cp.hasConnectedTexture else None)
        except Exception as e:
            info['color_properties'][prop.id] = f'error: {e}'
    try:
        c = appearance.color
        info['preview_color'] = _hex((c.red, c.green, c.blue)) if c else None
    except Exception as e:
        info['preview_color'] = f'unavailable: {e}'
    return info


def _bodies(root):
    yield from root.bRepBodies
    for occ in root.allOccurrences:
        yield from occ.bRepBodies


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    os.makedirs(OUTPUT, exist_ok=True)
    report = {'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'fusion_version': app.version,
              'appearances': [], 'bodies': [], 'errors': []}
    try:
        ce = _load_color_export()
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('Open the design you want to check first.', 'Fusion Slicer Exporter color report')
            return
        report['document'] = app.activeDocument.name
        groups = {}  # appearance name -> aggregated info
        for body in _bodies(design.rootComponent):
            b = {'name': body.name, 'visible': body.isVisible,
                 'component': body.assemblyContext.name if body.assemblyContext else '(root)',
                 'faces': body.faces.count, 'uses_custom_colors': ce.uses_custom_colors(body),
                 'colors': {}}
            report['bodies'].append(b)
            for face in body.faces:
                try:
                    appearance = face.appearance
                    source = SOURCES.get(face.appearanceSourceType, face.appearanceSourceType)
                    rgb = _hex(ce.appearance_rgb(appearance))
                    name = appearance.name if appearance else '(none)'
                    key = f'{name} | {rgb}'
                    g = groups.get(key)
                    if g is None:
                        g = groups[key] = _describe(appearance) if appearance else {'name': name}
                        g.update({'rgb_sent': rgb, 'faces': 0, 'sources': {}, 'bodies': []})
                    g['faces'] += 1
                    g['sources'][source] = g['sources'].get(source, 0) + 1
                    if body.name not in g['bodies']:
                        g['bodies'].append(body.name)
                    b['colors'][rgb] = b['colors'].get(rgb, 0) + 1
                except Exception:
                    report['errors'].append(f'{body.name}: {traceback.format_exc()}')
        report['appearances'] = sorted(groups.values(), key=lambda g: -g['faces'])
        used = []
        for a in design.appearances:
            try:
                if a.isUsed:
                    used.append({'name': a.name, 'id': a.id, 'rgb_read': _hex(ce.appearance_rgb(a))})
            except Exception:
                pass
        report['design_appearances_in_use'] = used
    except Exception:
        report['errors'].append(traceback.format_exc())

    path = os.path.join(OUTPUT, 'color_report.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    colors = sorted({g.get('rgb_sent') for g in report['appearances'] if g.get('rgb_sent')})
    ui.messageBox(f'{len(report["appearances"])} appearance(s) on {len(report["bodies"])} bodies, '
                  f'read as {len(colors)} distinct color(s).\n\nReport saved to:\n{path}',
                  'Fusion Slicer Exporter color report')
