"""The shipped app.js must be exactly what the editor sources build, and the
editor's pure modules must pass their unit tests. Both need only Python and Node."""
import shutil, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class EditorBuildTests(unittest.TestCase):
    def test_dist_matches_sources(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/build_ui.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bundle_is_the_only_editor_code_in_dist(self):
        text = (ROOT / 'depibeans/ui/dist/app.js').read_text(encoding='utf-8')
        self.assertEqual(text.count('const DepiEditor = (() => {'), 1)
        self.assertNotIn('installGraphScriptEditor', text)

    @unittest.skipUnless(shutil.which('node'), 'Node is not installed')
    def test_editor_modules(self):
        result = subprocess.run(['node', '--test', str(ROOT / 'tests/js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-2000:])

    @unittest.skipUnless(shutil.which('node'), 'Node is not installed')
    def test_dist_is_valid_javascript(self):
        result = subprocess.run(['node', '--check', str(ROOT / 'depibeans/ui/dist/app.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
