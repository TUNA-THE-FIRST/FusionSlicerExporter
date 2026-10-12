"""Builds the shareable zips in dist/:

  FusionSlicerExporter-v<version>-Windows.zip
  FusionSlicerExporter-v<version>-macOS.zip

Both hold the same cross-platform "FusionSlicerExporter" add-in folder, ready to drop
into Fusion's AddIns folder, plus an INSTALL.txt for that system. Personal
and generated files are left out.
Run: python3 tools/make_release.py
"""
import fnmatch
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = 'FusionSlicerExporter'
EXCLUDE_DIRS = {'dist', '__pycache__', '.git', '.github', 'output', 'offline'}
EXCLUDE_FILES = {'state.json', '.DS_Store', '*.pyc', '.gitignore', '.gitattributes'}

COMMON_END = """
Using it
  Select bodies or components (or nothing, to send every visible body), click
  "Send to Slicer" in the Solid workspace's Insert panel, pick the slicer and
  click OK. Colors applied with Fusion's Appearance tool are sent along:

  - Snapmaker Orca, OrcaSlicer, Bambu Studio: the slicer asks which filament
    each color should use. In Snapmaker Orca, afterwards select the imported
    object and set its filament to 1 (works around a Snapmaker Orca 2.4 bug;
    always safe).
  - PrusaSlicer: colors are painted onto extruders 1, 2, 3... and the add-in
    tells you which color went where.

  More in README.md inside the FusionSlicerExporter folder.
"""

SLICER_TIP = """
2. Install the slicers you use: Snapmaker Orca, Bambu Studio, OrcaSlicer
   and/or PrusaSlicer. The add-in finds them automatically{where}.
   A slicer somewhere else? Put its path in FusionSlicerExporter{sep}settings.json, e.g.
     "OrcaSlicer": "{example}"
"""

INSTALL = {
    'Windows': """Fusion Slicer Exporter {version} for Autodesk Fusion (Windows)

1. Move the "FusionSlicerExporter" folder (next to this file) into Fusion's
   Add-Ins folder. Paste this into File Explorer's address bar to open it:

     %APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns

   Keep the folder name "FusionSlicerExporter", or Fusion won't load it.
""" + SLICER_TIP.format(where=', also in custom install folders', sep='\\',
                        example='D:/Tools/OrcaSlicer/orca-slicer.exe') + """
3. Restart Fusion. The add-in starts by itself. If it doesn't, press
   Shift+S, open the Add-Ins tab, select FusionSlicerExporter and click Run.

Tip: turn on each slicer's single-instance preference so sends open in your
current slicer window instead of a new one:
  Snapmaker Orca: "Allow only one Snapmaker Orca instance"
  Bambu Studio:   "Keep only one Bambu Studio instance"
  OrcaSlicer:     "Allow only one OrcaSlicer instance"
  PrusaSlicer:    "Allow just a single PrusaSlicer instance"
""",
    'macOS': """Fusion Slicer Exporter {version} for Autodesk Fusion (macOS)

1. Move the "FusionSlicerExporter" folder (next to this file) into Fusion's
   Add-Ins folder. In Finder choose Go > Go to Folder... and paste:

     ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns

   Keep the folder name "FusionSlicerExporter", or Fusion won't load it.
""" + SLICER_TIP.format(where=' in Applications', sep='/', example='/Users/you/Apps/OrcaSlicer.app') + """
3. Restart Fusion. The add-in starts by itself. If it doesn't, press
   Shift+S, open the Add-Ins tab, select FusionSlicerExporter and click Run.

Tip: colored models for Bambu Studio open in a new Bambu Studio window if
it's already open, unless Preferences > "Keep only one Bambu Studio instance"
is on.
""",
}


def _included(rel):
    parts = rel.split('/')
    if any(p in EXCLUDE_DIRS for p in parts[:-1]):
        return False
    return not any(fnmatch.fnmatch(parts[-1], pat) for pat in EXCLUDE_FILES)


def _addin_files():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            if _included(rel):
                yield path, rel


def main():
    with open(os.path.join(ROOT, f'{FOLDER}.manifest'), encoding='utf-8') as f:
        version = json.load(f)['version']
    with open(os.path.join(ROOT, 'settings.json'), encoding='utf-8') as f:
        settings = json.load(f)
    if settings.get('orca_executable') or any((settings.get('slicers') or {}).values()):
        raise SystemExit('settings.json has a personal slicer path; clear it before releasing.')

    dist = os.path.join(ROOT, 'dist')
    os.makedirs(dist, exist_ok=True)
    files = list(_addin_files())
    for system, text in INSTALL.items():
        out = os.path.join(dist, f'{FOLDER}-v{version}-{system}.zip')
        text = (text + COMMON_END).format(version=version)
        if system == 'Windows':
            text = text.replace('\n', '\r\n')  # for Notepad
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('INSTALL.txt', text)
            for path, rel in files:
                z.write(path, f'{FOLDER}/{rel}')
        print(f'{out} ({len(files)} add-in files + INSTALL.txt)')


if __name__ == '__main__':
    main()
