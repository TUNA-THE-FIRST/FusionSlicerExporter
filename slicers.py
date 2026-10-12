# The slicers the add-in can send to, and where to find them.

import os
import sys

from . import config


class Slicer:
    def __init__(self, name, mac_apps, win_folder, win_exe, color_format, single_instance_setting,
                 filament1_bug=False):
        self.name = name
        self.mac_apps = mac_apps          # app bundles, relative to an Applications folder
        self.win_folder = win_folder      # install folder parts, relative to Program Files
        self.win_exe = win_exe
        # How colors are sent (all verified against each slicer's source):
        # 'obj'         OBJ + MTL; the slicer asks which filament each color uses.
        # '3mf-colors'  3MF with standard color groups; same per-face color prompt.
        #               (Bambu Studio 2.08 turns OBJ colors into a smoothed texture
        #               import that can lose small faces, so it gets this instead.)
        # '3mf-painted' 3MF with triangles already painted onto extruders, for
        #               slicers without a color prompt.
        self.color_format = color_format
        self.single_instance_setting = single_instance_setting
        # Snapmaker Orca 2.4 prints faces mapped to filament 1 with the
        # object's base filament (fixed upstream in Bambu Studio and OrcaSlicer).
        self.filament1_bug = filament1_bug


SLICERS = [
    Slicer('Snapmaker Orca', ['Snapmaker Orca.app'], ('Snapmaker_Orca',), 'snapmaker-orca.exe', 'obj',
           'Allow only one Snapmaker Orca instance', filament1_bug=True),
    Slicer('Bambu Studio', ['BambuStudio.app', 'Bambu Studio.app'], ('Bambu Studio',), 'bambu-studio.exe', '3mf-colors',
           'Keep only one Bambu Studio instance'),
    Slicer('OrcaSlicer', ['OrcaSlicer.app'], ('OrcaSlicer',), 'orca-slicer.exe', 'obj',
           'Allow only one OrcaSlicer instance'),
    Slicer('PrusaSlicer', ['PrusaSlicer.app', 'Original Prusa Drivers/PrusaSlicer.app'], ('Prusa3D', 'PrusaSlicer'),
           'prusa-slicer.exe', '3mf-painted', 'Allow just a single PrusaSlicer instance'),
]


def by_name(name):
    for slicer in SLICERS:
        if slicer.name == name:
            return slicer
    return None


def default_locations(slicer):
    if sys.platform == 'darwin':
        return [os.path.join(folder, app) for folder in ('/Applications', '~/Applications')
                for app in slicer.mac_apps]
    found = [os.path.join(os.environ[var], *sub, *slicer.win_folder, slicer.win_exe)
             for var, sub in (('ProgramW6432', ()), ('ProgramFiles', ()), ('ProgramFiles(x86)', ()),
                              ('LOCALAPPDATA', ('Programs',)))
             if os.environ.get(var)]
    return found or [os.path.join('C:\\Program Files', *slicer.win_folder, slicer.win_exe)]


def _registry_locations(slicer):
    # Windows installers list the program under "Uninstall" with its folder,
    # which also covers custom install locations.
    try:
        import winreg
    except ImportError:
        return []

    def value(key, name):
        try:
            return str(winreg.QueryValueEx(key, name)[0] or '')
        except OSError:
            return ''

    root = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    found = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            access = winreg.KEY_READ | view
            try:
                uninstall = winreg.OpenKey(hive, root, 0, access)
            except OSError:
                continue
            with uninstall:
                index = 0
                while True:
                    try:
                        sub = winreg.EnumKey(uninstall, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(uninstall, sub, 0, access) as key:
                            if not value(key, 'DisplayName').lower().startswith(slicer.name.lower()):
                                continue
                            folder, icon = value(key, 'InstallLocation'), value(key, 'DisplayIcon')
                    except OSError:
                        continue
                    if folder:
                        found.append(os.path.join(folder.strip('"'), slicer.win_exe))
                    icon = icon.split(',')[0].strip('"')
                    if icon.lower().endswith('.exe'):
                        found.append(os.path.join(os.path.dirname(icon), slicer.win_exe))
    return found


def configured_location(slicer):
    settings = config.load_settings()
    path = str((settings.get('slicers') or {}).get(slicer.name) or '').strip()
    if not path and slicer.name == 'Snapmaker Orca':
        path = str(settings.get('orca_executable') or '').strip()  # pre-1.3 settings
    return os.path.expanduser(path) if path else ''


def locate(slicer):
    """Returns (path, found). Without a match, path is where it was expected."""
    configured = configured_location(slicer)
    if configured:
        return configured, os.path.exists(configured)
    defaults = default_locations(slicer)
    candidates = defaults if sys.platform == 'darwin' else _registry_locations(slicer) + defaults
    for path in candidates:
        path = os.path.expanduser(path)
        if os.path.exists(path):
            return path, True
    return os.path.expanduser(defaults[0]), False
