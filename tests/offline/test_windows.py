"""Simulated-Windows tests for Fusion Slicer Exporter (Windows paths via ntpath, fake winreg/ctypes)."""
import sys, os, types, ntpath, importlib, unittest, subprocess
from unittest import mock

# The add-in folder: given on the command line, else this repository.
ADDIN = os.path.abspath(sys.argv.pop(1) if len(sys.argv) > 1 else
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
class Any:
    def __getattr__(self, n): return Any()
    def __call__(self, *a, **k): return Any()
    def __bool__(self): return True
adsk = types.ModuleType('adsk'); core = types.ModuleType('adsk.core'); fusion = types.ModuleType('adsk.fusion')
core.Application = types.SimpleNamespace(get=lambda: Any())
core.LogLevels = types.SimpleNamespace(InfoLogLevel=0, ErrorLogLevel=2)
core.LogTypes = types.SimpleNamespace(FileLogType=0, ConsoleLogType=1)
core.CommandEventArgs = core.InputChangedEventArgs = core.Event = object
fusion.BRepBody = fusion.Occurrence = Any()
adsk.core, adsk.fusion = core, fusion
sys.modules.update({'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion})
# Register the add-in folder as the "FusionSlicerExporter" package explicitly, so the
# tests work from any working directory and whatever the clone is called.
pkg = 'FusionSlicerExporter'
_package = types.ModuleType(pkg)
_package.__path__ = [ADDIN]
sys.modules[pkg] = _package
entry = importlib.import_module(f'{pkg}.commands.commandDialog.entry')
config = importlib.import_module(f'{pkg}.config')
slicers = importlib.import_module(f'{pkg}.slicers')

ENV = {'ProgramW6432': r'C:\Program Files', 'ProgramFiles': r'C:\Program Files',
       'ProgramFiles(x86)': r'C:\Program Files (x86)', 'LOCALAPPDATA': r'C:\Users\Pat\AppData\Local'}


UNINSTALL = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'


def fake_winreg(entries):
    """entries: list of (hive, view, {value name: value}) under the Uninstall key."""
    w = types.ModuleType('winreg')
    w.HKEY_LOCAL_MACHINE, w.HKEY_CURRENT_USER = 'HKLM', 'HKCU'
    w.KEY_READ, w.KEY_WOW64_64KEY, w.KEY_WOW64_32KEY = 1, 0x100, 0x200
    class Key:
        def __init__(s, hive, view, values=None): s.hive, s.view, s.values = hive, view, values
        def __enter__(s): return s
        def __exit__(s, *a): return False
    def subkeys(hive, view):
        return [e[2] for e in entries if e[0] == hive and e[1] == view]
    def OpenKey(parent, sub, res=0, access=0):
        view = access & 0x300
        if isinstance(parent, str):  # a hive
            if sub != UNINSTALL or not subkeys(parent, view):
                raise OSError('missing')
            return Key(parent, view)
        return Key(parent.hive, parent.view, subkeys(parent.hive, parent.view)[int(sub)])
    def EnumKey(key, index):
        if index >= len(subkeys(key.hive, key.view)):
            raise OSError('no more')
        return str(index)
    def QueryValueEx(key, name):
        if name not in key.values:
            raise OSError('no value')
        return key.values[name], 1
    w.OpenKey, w.EnumKey, w.QueryValueEx = OpenKey, EnumKey, QueryValueEx
    return w


class Windows(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(sys, 'platform', 'win32'),
                        mock.patch.object(os, 'path', ntpath),
                        mock.patch.dict(os.environ, ENV, clear=False)]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        sys.modules.pop('winreg', None)

    def detect(self, name, existing, registry=(), settings=None):
        sys.modules['winreg'] = fake_winreg(list(registry))
        with mock.patch.object(config, 'load_settings', lambda: settings or {}), \
             mock.patch.object(ntpath, 'exists', lambda p: p in existing):
            return slicers.locate(slicers.by_name(name))

    def test_default_install_folders(self):
        defaults = {'Snapmaker Orca': r'C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe',
                    'Bambu Studio': r'C:\Program Files\Bambu Studio\bambu-studio.exe',
                    'OrcaSlicer': r'C:\Program Files\OrcaSlicer\orca-slicer.exe',
                    'PrusaSlicer': r'C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe'}
        for name, exe in defaults.items():
            self.assertEqual(self.detect(name, set(defaults.values())), (exe, True), name)
            self.assertEqual(self.detect(name, set()), (exe, False), name)  # reported when missing

    def test_registry_install_location(self):
        custom = r'D:\Apps\Bambu\bambu-studio.exe'
        reg = [('HKLM', 0x100, {'DisplayName': 'Some Other App', 'InstallLocation': r'D:\Other'}),
               ('HKLM', 0x100, {'DisplayName': 'Bambu Studio', 'InstallLocation': r'D:\Apps\Bambu'})]
        self.assertEqual(self.detect('Bambu Studio', {custom}, reg), (custom, True))

    def test_registry_display_icon_and_versioned_name(self):
        custom = r'E:\Prusa\prusa-slicer.exe'
        reg = [('HKCU', 0x200, {'DisplayName': 'PrusaSlicer 2.9.6', 'DisplayIcon': '"E:\\Prusa\\prusa-slicer.exe",0'})]
        self.assertEqual(self.detect('PrusaSlicer', {custom}, reg), (custom, True))

    def test_registry_does_not_mix_up_orca_variants(self):
        snap = r'F:\Snap\snapmaker-orca.exe'
        reg = [('HKLM', 0x100, {'DisplayName': 'Snapmaker Orca', 'InstallLocation': r'F:\Snap'})]
        self.assertEqual(self.detect('OrcaSlicer', {snap}, reg)[1], False)
        self.assertEqual(self.detect('Snapmaker Orca', {snap}, reg), (snap, True))

    def test_per_user_install(self):
        exe = r'C:\Users\Pat\AppData\Local\Programs\OrcaSlicer\orca-slicer.exe'
        self.assertEqual(self.detect('OrcaSlicer', {exe}), (exe, True))

    def test_settings_override(self):
        got = self.detect('OrcaSlicer', set(), settings={'slicers': {'OrcaSlicer': r'F:\portable\orca-slicer.exe'}})
        self.assertEqual(got, (r'F:\portable\orca-slicer.exe', False))

    def test_resolve_slicer(self):
        exe = r'C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe'
        with mock.patch.object(ntpath, 'isfile', lambda p: p == exe):
            self.assertEqual(entry._resolve_slicer(exe), exe)
            self.assertEqual(entry._resolve_slicer('C:/Program Files/Snapmaker_Orca/snapmaker-orca.exe'), exe)
            self.assertIsNone(entry._resolve_slicer(r'C:\nope\snapmaker-orca.exe'))

    def launch(self, rc):
        calls, boxes = [], []
        shell32 = types.SimpleNamespace(ShellExecuteW=lambda *a: calls.append(a) or rc)
        fake_ctypes = types.ModuleType('ctypes')
        fake_ctypes.windll = types.SimpleNamespace(shell32=shell32)
        fake_ctypes.c_void_p, fake_ctypes.c_int = 'c_void_p', 'c_int'
        wintypes = types.ModuleType('ctypes.wintypes'); wintypes.HWND = wintypes.LPCWSTR = 'w'
        fake_ctypes.wintypes = wintypes
        files = [r'C:\Users\Pat\AppData\Local\Temp\FusionSlicerExporter\tmp1\My Design.obj',
                 r'C:\Users\Pat\AppData\Local\Temp\FusionSlicerExporter\tmp1\Lid_1.stl']
        with mock.patch.dict(sys.modules, {'ctypes': fake_ctypes, 'ctypes.wintypes': wintypes}), \
             mock.patch.object(entry, 'ui', types.SimpleNamespace(messageBox=lambda *a: boxes.append(a))):
            entry._launch_slicer(r'C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe', files)
        return calls, boxes, shell32

    def test_launch_quotes_paths(self):
        calls, boxes, shell32 = self.launch(42)
        (_, verb, exe, params, _, show), = calls
        self.assertEqual((verb, exe, show), ('open', r'C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe', 1))
        self.assertEqual(params, '"C:\\Users\\Pat\\AppData\\Local\\Temp\\FusionSlicerExporter\\tmp1\\My Design.obj" '
                                 'C:\\Users\\Pat\\AppData\\Local\\Temp\\FusionSlicerExporter\\tmp1\\Lid_1.stl')
        self.assertEqual(boxes, [])
        self.assertEqual(shell32.ShellExecuteW.restype, 'c_void_p')

    def test_launch_error_reported(self):
        for rc in (2, None):  # file not found / NULL
            calls, boxes, _ = self.launch(rc)
            self.assertEqual(len(boxes), 1, rc)

    def test_reserved_names(self):
        f = entry._safe_filename
        self.assertEqual(f('CON'), '_CON')
        self.assertEqual(f('com1'), '_com1')
        self.assertEqual(f('nul.part'), '_nul.part')
        self.assertEqual(f('Console'), 'Console')
        self.assertEqual(f('LPT10'), 'LPT10')


if __name__ == '__main__':
    unittest.main(verbosity=2)
