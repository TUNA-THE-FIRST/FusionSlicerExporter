"""Offline tests for Fusion Slicer Exporter's entry.py using a stubbed adsk API."""
import sys, os, json, types, math, time, tempfile, importlib, unittest, posixpath, contextlib
from unittest import mock

# The add-in folder: given on the command line, else this repository.
ADDIN = os.path.abspath(sys.argv.pop(1) if len(sys.argv) > 1 else
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# ---- stub adsk ----
class Any:
    def __getattr__(self, n): return Any()
    def __call__(self, *a, **k): return Any()
    def __bool__(self): return True
adsk = types.ModuleType('adsk'); core = types.ModuleType('adsk.core'); fusion = types.ModuleType('adsk.fusion')
core.Application = types.SimpleNamespace(get=lambda: Any())
core.LogLevels = types.SimpleNamespace(InfoLogLevel=0, ErrorLogLevel=2)
core.LogTypes = types.SimpleNamespace(FileLogType=0, ConsoleLogType=1)
core.CommandEventArgs = core.InputChangedEventArgs = core.Event = object
class MR: MeshRefinementLow, MeshRefinementMedium, MeshRefinementHigh, MeshRefinementCustom = 0, 1, 2, 3
fusion.MeshRefinementSettings = MR
fusion.DistanceUnits = types.SimpleNamespace(MillimeterDistanceUnits=0)
class Body:
    def __init__(s, name, vis=True): s.name, s.isVisible, s.objectType = name, vis, 'Body'
    @staticmethod
    def classType(): return 'Body'
class Occ:
    def __init__(s, bodies, kids=()): s.bRepBodies, s.childOccurrences, s.objectType = bodies, list(kids), 'Occ'
    @staticmethod
    def classType(): return 'Occ'
    @staticmethod
    def cast(x): return x
fusion.BRepBody, fusion.Occurrence = Body, Occ
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

class Slider:
    """Mimics Fusion: rejects min > max."""
    def __init__(s): s._min, s._max, s.valueOne = 0.0, 1.0, 0.5
    @property
    def minimumValue(s): return s._min
    @minimumValue.setter
    def minimumValue(s, v):
        if v > s._max: raise RuntimeError('min > max')
        s._min = v
    @property
    def maximumValue(s): return s._max
    @maximumValue.setter
    def maximumValue(s, v):
        if v < s._min: raise RuntimeError('max < min')
        s._max = v

class Sel:
    def __init__(s, ents): s.ents = ents; s.selectionCount = len(ents)
    def selection(s, i): return types.SimpleNamespace(entity=s.ents[i])

@contextlib.contextmanager
def macos():
    """Runs the macOS code paths on any OS (like test_windows.py does for Windows)."""
    with mock.patch.object(sys, 'platform', 'darwin'), mock.patch.object(os, 'path', posixpath), \
         mock.patch.object(os, 'sep', '/'):
        yield


class T(unittest.TestCase):
    def test_mac_slicer_detection(self):
        with macos():
            self._test_mac_slicer_detection()

    def _test_mac_slicer_detection(self):
        slicers = importlib.import_module(f'{pkg}.slicers')
        apps = {'Snapmaker Orca': '/Applications/Snapmaker Orca.app', 'Bambu Studio': '/Applications/BambuStudio.app',
                'OrcaSlicer': '/Users/me/Applications/OrcaSlicer.app',
                'PrusaSlicer': '/Applications/Original Prusa Drivers/PrusaSlicer.app'}
        with mock.patch.object(slicers.config, 'load_settings', lambda: {}), \
             mock.patch.object(slicers.os.path, 'exists', lambda p: p in apps.values()), \
             mock.patch.object(slicers.os.path, 'expanduser', lambda p: p.replace('~', '/Users/me')):
            for s in slicers.SLICERS:
                self.assertEqual(slicers.locate(s), (apps[s.name], True), s.name)
        with mock.patch.object(slicers.config, 'load_settings', lambda: {}), \
             mock.patch.object(slicers.os.path, 'exists', lambda p: False):
            self.assertEqual(slicers.locate(slicers.by_name('PrusaSlicer')), ('/Applications/PrusaSlicer.app', False))

    def test_slicer_settings_override_and_legacy_key(self):
        with macos():
            self._test_slicer_settings_override_and_legacy_key()

    def _test_slicer_settings_override_and_legacy_key(self):
        slicers = importlib.import_module(f'{pkg}.slicers')
        snap, bambu = slicers.by_name('Snapmaker Orca'), slicers.by_name('Bambu Studio')
        with mock.patch.object(slicers.config, 'load_settings',
                               lambda: {'slicers': {'Bambu Studio': '~/B.app', 'Snapmaker Orca': ''},
                                        'orca_executable': '/Apps/Old Orca.app'}), \
             mock.patch.object(slicers.os.path, 'exists', lambda p: p == '/Apps/Old Orca.app'):
            self.assertEqual(slicers.locate(bambu), (os.path.expanduser('~/B.app'), False))
            self.assertEqual(slicers.locate(snap), ('/Apps/Old Orca.app', True))

    def test_shipped_settings_are_empty(self):
        with open(os.path.join(ADDIN, 'settings.json')) as f:
            data = json.load(f)
        slicers = importlib.import_module(f'{pkg}.slicers')
        self.assertEqual(sorted(data['slicers']), sorted(s.name for s in slicers.SLICERS))
        self.assertTrue(all(v == '' for v in data['slicers'].values()))

    def test_safe_filename(self):
        with macos():
            self._test_safe_filename()

    def _test_safe_filename(self):
        f = entry._safe_filename
        self.assertEqual(f('Body1'), 'Body1')
        self.assertNotIn('/', f('../../Library/LaunchAgents/x'))
        self.assertFalse(f('../../x').startswith('.'))
        self.assertNotIn('"', f('a" --evil "b'))
        self.assertEqual(f('///'), '_')
        self.assertEqual(f(''), 'body')
        self.assertLessEqual(len(f('x' * 500)), 100)
        p = os.path.join('/tmp/exp', f'{f("../../etc/passwd")}_0.stl')
        self.assertEqual(os.path.dirname(os.path.normpath(p)), '/tmp/exp')

    def test_resolve_slicer(self):
        with macos():
            self._test_resolve_slicer()

    def _test_resolve_slicer(self):
        # Pretend the app is installed: these runs must not depend on this machine.
        with mock.patch.object(posixpath, 'isdir', lambda p: p == '/Applications/Snapmaker Orca.app'):
            self._check_resolve_slicer()

    def _check_resolve_slicer(self):
        r = entry._resolve_slicer
        self.assertEqual(r('/Applications/Snapmaker Orca.app'), '/Applications/Snapmaker Orca.app')
        self.assertEqual(r('/Applications/Snapmaker Orca.app/'), '/Applications/Snapmaker Orca.app')
        self.assertEqual(r('/Applications/Snapmaker Orca.app/Contents/MacOS/Snapmaker_Orca'),
                         '/Applications/Snapmaker Orca.app')
        self.assertIsNone(r(r'C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe'))
        self.assertIsNone(r('/Applications/Nope.app'))

    def test_export_dir_cleanup(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(entry, 'EXPORT_ROOT', os.path.join(root, 'X')):
            d1 = entry._new_export_dir()
            if os.name == 'posix':  # Windows has no Unix permissions
                self.assertEqual(os.stat(d1).st_mode & 0o777, 0o700)
            old = time.time() - entry.EXPORT_MAX_AGE_S - 10
            os.utime(d1, (old, old))
            d2 = entry._new_export_dir()
            self.assertFalse(os.path.exists(d1))
            self.assertTrue(os.path.isdir(d2))

    def test_slider_scaling_big_to_small_and_back(self):
        sliders = {pid: Slider() for pid, *_ in entry.PARAMS}
        with mock.patch.object(entry, '_slider', lambda inputs, pid: sliders[pid]):
            entry._apply_scale(None, 500.0, True)   # huge part
            entry._apply_scale(None, 0.01, False)  # tiny part: would raise with old ordering
            for s in sliders.values():
                self.assertLessEqual(s.minimumValue, s.valueOne); self.assertLessEqual(s.valueOne, s.maximumValue)
            entry._apply_scale(None, 500.0, False)
            for s in sliders.values():
                self.assertLessEqual(s.minimumValue, s.valueOne); self.assertLessEqual(s.valueOne, s.maximumValue)

    def test_normal_deviation_radians(self):
        vals = {'surfaceDeviation': 0.5, 'normalDeviation': 15.0, 'maximumEdgeLength': 20.0, 'aspectRatio': 21.5}
        with mock.patch.object(entry, '_slider', lambda inputs, pid: types.SimpleNamespace(valueOne=vals[pid])):
            o = types.SimpleNamespace()
            entry.apply_refinement(o, 'Custom', None)
        self.assertAlmostEqual(o.normalDeviation, math.radians(15))
        self.assertAlmostEqual(o.surfaceDeviation, 0.05)
        self.assertAlmostEqual(o.maximumEdgeLength, 2.0)

    def test_body_collection(self):
        a, b, hidden, nested = Body('a'), Body('b'), Body('h', False), Body('n')
        occ = Occ([b, hidden], [Occ([nested])])
        got = entry._bodies_from_selection(Sel([occ, b]), None)
        self.assertEqual([x.name for x in got], ['b', 'n'])  # nested included, hidden skipped, deduped
        root = types.SimpleNamespace(bRepBodies=[a, hidden], allOccurrences=[Occ([nested])])
        got = entry._bodies_from_selection(Sel([]), root)
        self.assertEqual([x.name for x in got], ['a', 'n'])

    def test_launch_uses_open_without_shell(self):
        with macos():
            self._test_launch_uses_open_without_shell()

    def _test_launch_uses_open_without_shell(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append((cmd, kw)); return types.SimpleNamespace(returncode=0, stderr='')
        with mock.patch.object(entry.subprocess, 'run', fake_run):
            entry._launch_slicer('/Applications/Snapmaker Orca.app', ['/t/a b.stl', '/t/c.stl'])
        cmd, kw = calls[0]
        self.assertEqual(cmd, ['/usr/bin/open', '-a', '/Applications/Snapmaker Orca.app', '/t/a b.stl', '/t/c.stl'])
        self.assertNotIn('shell', kw)

if __name__ == '__main__':
    unittest.main(verbosity=2)
