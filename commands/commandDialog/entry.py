import adsk.core
import adsk.fusion
import os
import re
import sys
import math
import time
import shutil
import tempfile
import traceback
import subprocess
from ...lib import fusionAddInUtils as futil
from ... import config, slicers
from . import color_export

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID=f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_entry'
CMD_NAME='Send to Slicer'
CMD_DESCRIPTION=('Send selected bodies/components, with their Fusion colors, to Snapmaker Orca, '
                 'Bambu Studio, OrcaSlicer or PrusaSlicer')

IS_PROMOTED = True

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'InsertPanel'
COMMAND_BESIDE_ID= ''

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

local_handlers = []

# Each send gets its own private folder under here; folders older than
# EXPORT_MAX_AGE_S are removed on the next send so STLs don't pile up.
EXPORT_ROOT = os.path.join(tempfile.gettempdir(), config.ADDIN_NAME)
EXPORT_MAX_AGE_S = 24 * 60 * 60

# Slider ranges are derived from the selected bodies the same way Fusion's own
# "Save As Mesh" dialog does, using the bounding-box diagonal as the scale.
ND_MIN, ND_MAX, ND_DEFAULT = 1.0, 41.0, 15.0
AR_MIN, AR_MAX, AR_DEFAULT = 1.0, 21.5, 21.5

# (id, label, unitType). Each parameter is rendered as a read-only label row
# with a slider directly below it. All sliders are unitless so they lay out
# identically; mm values are converted to cm when the STL options are set.
PARAMS = [
    ('surfaceDeviation', 'Surface Deviation (mm)', ''),
    ('normalDeviation', 'Normal Deviation (deg)', ''),
    ('maximumEdgeLength', 'Maximum Edge Length (mm)', ''),
    ('aspectRatio', 'Aspect Ratio', ''),
]

LAYOUT_COMBINED = 'One object (keeps layout)'
LAYOUT_SEPARATE = 'Separate objects'


def _occurrence_bodies(occ):
    # Includes bodies in nested sub-components, skipping hidden ones.
    bodies = [b for b in occ.bRepBodies if b.isVisible]
    for child in occ.childOccurrences:
        bodies.extend(_occurrence_bodies(child))
    return bodies


def _bodies_from_selection(selInput, rootComp):
    found = []
    for i in range(selInput.selectionCount):
        entity = selInput.selection(i).entity
        if entity.objectType == adsk.fusion.BRepBody.classType():
            found.append(entity)
        elif entity.objectType == adsk.fusion.Occurrence.classType():
            found.extend(_occurrence_bodies(adsk.fusion.Occurrence.cast(entity)))
    if not found:
        # Nothing selected: send every visible body in the design.
        found = [b for b in rootComp.bRepBodies if b.isVisible]
        for occ in rootComp.allOccurrences:
            found.extend(b for b in occ.bRepBodies if b.isVisible)
    # A body can be picked both directly and via its component.
    bodies = []
    for b in found:
        if b not in bodies:
            bodies.append(b)
    return bodies


def _char_length_cm(bodies):
    dmin = [1e18, 1e18, 1e18]
    dmax = [-1e18, -1e18, -1e18]
    count = 0
    for body in bodies:
        try:
            bb = body.boundingBox
        except Exception:
            continue
        for pt in (bb.minPoint, bb.maxPoint):
            for i in range(3):
                v = pt.asArray()[i]
                if v < dmin[i]:
                    dmin[i] = v
                if v > dmax[i]:
                    dmax[i] = v
        count += 1
    if count == 0:
        return 1.0
    dx = dmax[0] - dmin[0]
    dy = dmax[1] - dmin[1]
    dz = dmax[2] - dmin[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _length_scale_cm(length_cm):
    # M mirrors Fusion's maximum mesh edge length limit for the body.
    return 10.0 * length_cm


def _children(inputs):
    return inputs.itemById('customGroup').children


def _slider(inputs, iid):
    return _children(inputs).itemById(iid + 'Slider')


def _ranges(pid, M):
    if pid == 'surfaceDeviation':
        return (M / 100000.0, M / 1000.0, M / 20000.0)
    if pid == 'normalDeviation':
        return (ND_MIN, ND_MAX, ND_DEFAULT)
    if pid == 'maximumEdgeLength':
        return (M / 1000.0, M, M)
    return (AR_MIN, AR_MAX, AR_DEFAULT)


def _apply_scale(inputs, length_cm, set_values):
    M = _length_scale_cm(length_cm) * 10.0  # mm
    for pid, _label, _units in PARAMS:
        lo, hi, dflt = _ranges(pid, M)
        slider = _slider(inputs, pid)
        # Order the updates so minimum never exceeds maximum mid-way, which
        # happens when the selection jumps to a much larger or smaller body.
        if lo > slider.maximumValue:
            slider.maximumValue = hi
            slider.minimumValue = lo
        else:
            slider.minimumValue = lo
            slider.maximumValue = hi
        v = dflt if set_values else slider.valueOne
        slider.valueOne = max(lo, min(hi, v))


def _restore_values(inputs, state):
    for pid, _label, _units in PARAMS:
        if pid not in state:
            continue
        try:
            v = float(state[pid])
        except (TypeError, ValueError):
            continue
        slider = _slider(inputs, pid)
        v = max(slider.minimumValue, min(slider.maximumValue, v))
        slider.valueOne = v


def _save_state(inputs, refinementName):
    state = config.load_state()
    state.update({
        'refinement': refinementName,
        'slicer': _selected_slicer(inputs).name,
        'keepColors': inputs.itemById('keepColors').value,
        'colorLayout': inputs.itemById('colorLayout').selectedItem.name,
    })
    for pid, _label, _units in PARAMS:
        try:
            state[pid] = _slider(inputs, pid).valueOne
        except Exception:
            pass
    config.save_state(state)


def start():
    # Clear leftovers from a previous run that didn't stop cleanly, otherwise
    # addButtonDefinition fails because the ID is already taken.
    stop()
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID)
    control.isPromoted = IS_PROMOTED

def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()

def command_created(args: adsk.core.CommandEventArgs):
    futil.log(f'Command Created: {CMD_ID}')
    cmd = args.command
    cmd.isExecutedWhenPreempted = False
    inputs = cmd.commandInputs
    selInput = inputs.addSelectionInput('sel', 'Select Bodies', 'Select bodies or components to send to slicer')
    selInput.addSelectionFilter('SolidBodies')
    selInput.addSelectionFilter('Occurrences')
    selInput.setSelectionLimits(0, 0)

    state = config.load_state()
    _add_slicer_input(inputs, state.get('slicer'))
    last_ref = state.get('refinement', 'High')
    if last_ref not in ('Low', 'Medium', 'High', 'Custom'):
        last_ref = 'High'

    refinementInput = inputs.addDropDownCommandInput(
        'refinement', 'Mesh Refinement', adsk.core.DropDownStyles.TextListDropDownStyle)
    for name in ('Low', 'Medium', 'High', 'Custom'):
        refinementInput.listItems.add(name, name == last_ref)

    customGroup = inputs.addGroupCommandInput('customGroup', 'Custom Refinement')
    customGroup.isVisible = (last_ref == 'Custom')
    cg = customGroup.children
    for pid, label, units in PARAMS:
        cg.addTextBoxCommandInput(pid + 'Label', '', label, 1, True)
        slider = cg.addFloatSliderCommandInput(pid + 'Slider', '', units, 0.0, 1.0)
        slider.isFullWidth = True

    keep_colors = state.get('keepColors', True) is not False
    keepInput = inputs.addBoolValueInput('keepColors', 'Keep Fusion colors', True, '', keep_colors)
    keepInput.tooltip = ('Send colors applied with the Appearance tool so the slicer paints '
                         'them with your filaments. Designs without applied colors are sent '
                         'as plain STL.')
    last_layout = state.get('colorLayout', LAYOUT_COMBINED)
    layoutInput = inputs.addDropDownCommandInput(
        'colorLayout', 'Colored bodies', adsk.core.DropDownStyles.TextListDropDownStyle)
    for name in (LAYOUT_COMBINED, LAYOUT_SEPARATE):
        layoutInput.listItems.add(name, name == last_layout)
    if layoutInput.selectedItem is None:
        layoutInput.listItems.item(0).isSelected = True
    layoutInput.tooltip = ('One object keeps the bodies where they are in Fusion and asks '
                           'about colors once. Separate objects can be arranged freely, but '
                           'Orca-based slicers ask about colors for each body.')
    layoutInput.isVisible = keep_colors

    design = adsk.fusion.Design.cast(app.activeProduct)
    if design:
        length_cm = _char_length_cm(_bodies_from_selection(selInput, design.rootComponent))
        _apply_scale(inputs, length_cm, True)
        _restore_values(inputs, state)

    futil.add_handler(cmd.inputChanged, input_changed_handler, local_handlers=local_handlers)
    futil.add_handler(cmd.execute, execute_handler, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def _add_slicer_input(inputs, last_name):
    slicerInput = inputs.addDropDownCommandInput(
        'slicer', 'Slicer', adsk.core.DropDownStyles.TextListDropDownStyle)
    found = [slicers.locate(s)[1] for s in slicers.SLICERS]
    names = [s.name for s in slicers.SLICERS]
    if last_name in names:
        selected = names.index(last_name)
    else:
        selected = found.index(True) if True in found else 0
    for i, s in enumerate(slicers.SLICERS):
        slicerInput.listItems.add(s.name if found[i] else f'{s.name} (not found)', i == selected)
    slicerInput.tooltip = ('Slicers that are installed somewhere else can be set in settings.json '
                           'in the add-in folder.')


def _selected_slicer(inputs):
    return slicers.SLICERS[inputs.itemById('slicer').selectedItem.index]


def command_destroy(args: adsk.core.CommandEventArgs):
    # Release this dialog's handlers so they don't accumulate on every use.
    global local_handlers
    local_handlers = []


def input_changed_handler(args: adsk.core.InputChangedEventArgs):
    try:
        cmd = args.input.parentCommand
        inputs = cmd.commandInputs
        iid = args.input.id
        if iid == 'refinement':
            inputs.itemById('customGroup').isVisible = (
                inputs.itemById('refinement').selectedItem.name == 'Custom')
        elif iid == 'keepColors':
            inputs.itemById('colorLayout').isVisible = inputs.itemById('keepColors').value
        elif iid == 'sel':
            design = adsk.fusion.Design.cast(app.activeProduct)
            if design:
                length_cm = _char_length_cm(
                    _bodies_from_selection(inputs.itemById('sel'), design.rootComponent))
                _apply_scale(inputs, length_cm, False)
    except Exception as e:
        futil.log(f'inputChanged failed: {str(e)}')

def execute_handler(args: adsk.core.CommandEventArgs):
    try:
        cmd = args.command
        inputs = cmd.commandInputs
        selInput = inputs.itemById('sel')
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        if not design:
            ui.messageBox('No active Fusion design', 'No Design')
            return
        rootComp = design.rootComponent
        selectedBodies = _bodies_from_selection(selInput, rootComp)
        refinementName = inputs.itemById('refinement').selectedItem.name
        _save_state(inputs, refinementName)

        # Check the slicer before spending time on the export.
        target = _selected_slicer(inputs)
        wanted, _found = slicers.locate(target)
        slicer = _resolve_slicer(wanted)
        if not slicer:
            ui.messageBox(
                f'{target.name} was not found at:\n{wanted}\n\n'
                f'Install it, or set its location under "slicers" in:\n{config.SETTINGS_PATH}',
                'Slicer Not Found'
            )
            return

        temp_dir = _new_export_dir()
        exportMgr = design.exportManager
        export_files, palette = None, None
        if inputs.itemById('keepColors').value:
            combine = inputs.itemById('colorLayout').selectedItem.name == LAYOUT_COMBINED
            try:
                export_files, palette = _export_colored(exportMgr, selectedBodies, refinementName,
                                                        inputs, temp_dir, combine, target)
            except Exception:
                futil.log(f'Color export failed:\n{traceback.format_exc()}',
                          adsk.core.LogLevels.ErrorLogLevel, force_console=True)
                ui.messageBox('Could not export the colors, so the bodies will be sent without '
                              'them.\n\nDetails are in the Text Commands window.', 'Colors Skipped')
        if export_files is None:
            export_files = _export_stl(exportMgr, list(enumerate(selectedBodies)), refinementName,
                                       inputs, temp_dir)
        if any(f.endswith(('.obj', '.3mf')) for f in export_files):
            _show_color_notes(target, palette)
        if export_files:
            _launch_slicer(slicer, export_files)
        else:
            ui.messageBox('No bodies were exported', 'Export Failed')
    except Exception as e:
        futil.log(f'Failed to export: {str(e)}')
        ui.messageBox(f'Failed to export: {str(e)}', 'Error')


def _export_stl(exportMgr, indexed_bodies, refinementName, inputs, temp_dir):
    files = []
    for index, body in indexed_bodies:
        try:
            stl_file = os.path.join(temp_dir, f'{_safe_filename(body.name)}_{index}.stl')
            stlOptions = exportMgr.createSTLExportOptions(body, stl_file)
            # Slicers assume STL coordinates are mm; Fusion would otherwise
            # use the design's units (e.g. inches -> 25.4x too small).
            try:
                stlOptions.unitType = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
            except Exception:
                pass  # Fusion builds before May 2025 have no unitType.
            apply_refinement(stlOptions, refinementName, inputs)
            if export_to_stl(exportMgr, stlOptions):
                files.append(stl_file)
        except Exception as e:
            futil.log(f'Error exporting body {body.name}: {str(e)}')
    return files


def _mesh_quality(exportMgr, body, refinementName, inputs, temp_dir):
    # Read the tolerances Fusion's STL export would use for this body and
    # refinement so colored and plain exports come out equally fine.
    opts = exportMgr.createSTLExportOptions(body, os.path.join(temp_dir, 'unused.stl'))
    apply_refinement(opts, refinementName, inputs)
    return {
        'surface_deviation': opts.surfaceDeviation,
        'normal_deviation': opts.normalDeviation,
        'max_edge_length': opts.maximumEdgeLength,
        'aspect_ratio': opts.aspectRatio,
    }


def _export_colored(exportMgr, bodies, refinementName, inputs, temp_dir, combine, target):
    # Returns (files to send, extruder palette for painted 3MFs), or (None,
    # None) when nothing has colors applied: the caller then sends plain STLs,
    # which slicers open without a color prompt.
    colored = [color_export.uses_custom_colors(body) for body in bodies]
    if not any(colored):
        return None, None
    fmt = target.color_format

    def mesh(body):
        quality = _mesh_quality(exportMgr, body, refinementName, inputs, temp_dir)
        part = color_export.mesh_body(body, quality, body.name)
        if part:
            futil.log(f'{body.name}: {len(part.triangles)} triangles, '
                      f'{len(set(part.colors))} colors ({part.method} mesh)')
        return part

    def write(meshes, stem):
        if fmt == '3mf-painted':
            palette = color_export.extruder_palette(meshes)
            return color_export.write_3mf(os.path.join(temp_dir, f'{stem}.3mf'), meshes, palette), palette
        if fmt == '3mf-colors':
            return color_export.write_3mf(os.path.join(temp_dir, f'{stem}.3mf'), meshes), None
        return color_export.write_obj(os.path.join(temp_dir, f'{stem}.obj'), meshes[0]), None

    if combine:
        # Every body goes into one object so they keep their Fusion layout.
        combined = color_export.ColoredMesh(_design_name())
        for body in bodies:
            part = mesh(body)
            if part:
                combined.extend(part)
        if not combined.triangles:
            return [], None
        path, palette = write([combined], _safe_filename(combined.name).replace(' ', '_'))
        return [path], palette

    # Separate objects: only bodies with applied colors are colored; the rest
    # go as plain STLs. A 3MF holds them all as separate objects, while the
    # OBJ route needs a file (and a color prompt) per body.
    parts, plain = [], []
    for index, body in enumerate(bodies):
        if not colored[index]:
            plain.append((index, body))
            continue
        part = mesh(body)
        if part and part.triangles:
            parts.append((index, part))
    files, palette = [], None
    if fmt != 'obj' and parts:
        path, palette = write([part for _, part in parts], _safe_filename(_design_name()).replace(' ', '_'))
        files.append(path)
    elif parts:
        for index, part in parts:
            files.append(write([part], f'{_safe_filename(part.name)}_{index}'.replace(' ', '_'))[0])
    return files + _export_stl(exportMgr, plain, refinementName, inputs, temp_dir), palette


def _show_color_notes(target, palette):
    if target.color_format == '3mf-painted':
        # PrusaSlicer has no color prompt, so say which extruder got which color.
        by_extruder = {}
        for rgb, extruder in sorted(palette.items(), key=lambda kv: kv[1]):
            by_extruder.setdefault(extruder, []).append(rgb)
        lines = [f'  Extruder {e}: ' + ', '.join(f'{color_export.color_name(c)} (#{c[0]:02X}{c[1]:02X}{c[2]:02X})'
                                                 for c in colors)
                 for e, colors in sorted(by_extruder.items())]
        ui.messageBox(
            f'{target.name} can\'t import colors, so they were painted onto extruders, the color '
            'covering the most surface first:\n\n' + '\n'.join(lines) +
            '\n\nLoad matching filaments in those extruders. The painting is used by printer '
            'profiles with that many extruders or tools (e.g. MMU3 or XL).',
            f'Colors Sent to {target.name}')
        return

    state = config.load_state()
    key = 'colorTipShown' if target.filament1_bug else f'colorTipShown:{target.name}'
    if state.get(key):
        return
    if target.filament1_bug:
        message = (
            f'{target.name} will now ask how to print your Fusion colors:\n\n'
            '  \u2022 "Color match" uses the closest filaments you have loaded.\n'
            '  \u2022 "Keep color" / "Add" creates filaments in the exact Fusion colors.\n\n'
            'After clicking OK there, select the imported object and set its filament '
            'to 1. Snapmaker Orca 2.4 otherwise prints faces mapped to filament 1 with '
            'another filament (an Orca bug, already fixed in upstream OrcaSlicer). '
            'Setting filament 1 is always safe: every other color is painted on.')
    else:
        message = (
            f'{target.name} will now ask how to print your Fusion colors. "Color match" '
            'picks the closest filaments you have loaded; you can change the filament for '
            'each color in its list before clicking OK.')
        if target.color_format == '3mf-colors' and sys.platform == 'darwin':
            message += (f'\n\nIf {target.name} is already open, the model opens in a new '
                        f'{target.name} window. To use your open window instead, turn on '
                        f'"{target.single_instance_setting}" in its Preferences and choose to import '
                        'the geometry when it asks how to open the file.')
    ui.messageBox(message + '\n\nThis tip is shown once.', f'Sending Colors to {target.name}')
    state[key] = True
    config.save_state(state)


def _design_name():
    try:
        return app.activeDocument.name or 'Fusion design'
    except Exception:
        return 'Fusion design'


# Names Windows reserves for devices, even with an extension (CON.obj).
_WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}


def _safe_filename(name):
    # Body names come from the design (possibly someone else's file), so keep
    # them from escaping the export folder or breaking the slicer arguments.
    name = re.sub(r'[^\w.\- ]+', '_', name).strip(' .')[:100] or 'body'
    if name.split('.')[0].upper() in _WINDOWS_RESERVED:
        name = '_' + name
    return name


def _new_export_dir():
    os.makedirs(EXPORT_ROOT, mode=0o700, exist_ok=True)
    cutoff = time.time() - EXPORT_MAX_AGE_S
    for entry in os.listdir(EXPORT_ROOT):
        path = os.path.join(EXPORT_ROOT, entry)
        try:
            if not os.path.islink(path) and os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
    return tempfile.mkdtemp(dir=EXPORT_ROOT)


def _resolve_slicer(path):
    path = os.path.normpath(path)
    if sys.platform == 'darwin':
        # Apps are .app bundles (folders). Accept a path to the binary inside
        # the bundle too, since `open -a` needs the bundle itself.
        idx = path.find('.app' + os.sep)
        if idx != -1:
            path = path[:idx + 4]
        return path if path.endswith('.app') and os.path.isdir(path) else None
    return path if os.path.isfile(path) else None


def _launch_slicer(slicer, files):
    if sys.platform == 'darwin':
        # `open -a` hands the files to the slicer if it is already running,
        # otherwise launches it. Arguments are a list; no shell is involved.
        result = subprocess.run(['/usr/bin/open', '-a', slicer] + files,
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            ui.messageBox(f'Could not open the slicer:\n{result.stderr.strip()}', 'Launch Failed')
    else:
        import ctypes
        from ctypes import wintypes
        shell_execute = ctypes.windll.shell32.ShellExecuteW
        shell_execute.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
        shell_execute.restype = ctypes.c_void_p  # an HINSTANCE; values <= 32 are errors
        # list2cmdline quotes each path the way the slicer's command line expects.
        rc = shell_execute(None, 'open', slicer, subprocess.list2cmdline(files), None, 1) or 0
        if rc <= 32:
            ui.messageBox(f'Could not open the slicer (error {rc}).', 'Launch Failed')

def apply_refinement(stlOptions, refinementName, inputs):
    mr = adsk.fusion.MeshRefinementSettings
    if refinementName == 'Low':
        stlOptions.meshRefinement = mr.MeshRefinementLow
    elif refinementName == 'Medium':
        stlOptions.meshRefinement = mr.MeshRefinementMedium
    elif refinementName == 'Custom':
        stlOptions.meshRefinement = mr.MeshRefinementCustom
        stlOptions.surfaceDeviation = _slider(inputs, 'surfaceDeviation').valueOne / 10.0
        # The slider is in degrees like Fusion's own mesh dialog; the API wants radians.
        stlOptions.normalDeviation = math.radians(_slider(inputs, 'normalDeviation').valueOne)
        stlOptions.maximumEdgeLength = _slider(inputs, 'maximumEdgeLength').valueOne / 10.0
        stlOptions.aspectRatio = _slider(inputs, 'aspectRatio').valueOne
    else:
        stlOptions.meshRefinement = mr.MeshRefinementHigh


def export_to_stl(exportMgr, stlOptions):
    try:
        result = exportMgr.execute(stlOptions)
        return result
    except Exception as e:
        futil.log(f'Export to STL failed with error: {str(e)}')
        return False
