"""Regression tests for the build-time SideSign GSA client identity patch."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "patch_sidesign_gsa_client_info", ROOT / "scripts/patch_sidesign_gsa_client_info.py"
)
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


SOURCE = '''import Foundation
public extension DeveloperPortal {
    func sendAuthenticationRequest() {
        let headers = ["X-MMe-Client-Info": anisetteData.clientInfo, "Accept": "*/*"]
    }
    func makeTwoFactorAuthRequest() {
        let headers = ["X-MMe-Client-Info": a.clientInfo, "Accept": "*/*"]
    }
}
'''


class SideSignGsaClientInfoPatchTests(unittest.TestCase):
    def fixture(self, directory: Path) -> Path:
        root = directory / "SideSign"
        source = root / patcher.AUTH
        source.parent.mkdir(parents=True)
        source.write_text(SOURCE, encoding="utf-8")
        return root

    def test_normalizes_both_gsa_request_headers_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as name:
            root = self.fixture(Path(name))
            patcher.patch(root, enforce_pin=False)
            first = (root / patcher.AUTH).read_text(encoding="utf-8")
            patcher.patch(root, enforce_pin=False)
            second = (root / patcher.AUTH).read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertEqual(first.count(patcher.MARKER), 1)
        self.assertIn('"X-MMe-Client-Info": v3GsaClientInfo(anisetteData.clientInfo)', first)
        self.assertIn('"X-MMe-Client-Info": v3GsaClientInfo(a.clientInfo)', first)
        self.assertNotIn('"X-MMe-Client-Info": anisetteData.clientInfo', first)
        self.assertNotIn('"X-MMe-Client-Info": a.clientInfo', first)

    def test_fails_closed_when_upstream_request_anchors_drift(self):
        with tempfile.TemporaryDirectory() as name:
            root = self.fixture(Path(name))
            source = root / patcher.AUTH
            drifted = SOURCE.replace('"X-MMe-Client-Info": a.clientInfo', '"X-MMe-Client-Info": changed')
            source.write_text(drifted, encoding="utf-8")
            with self.assertRaises(SystemExit):
                patcher.patch(root, enforce_pin=False)
            self.assertEqual(source.read_text(encoding="utf-8"), drifted)

    def test_swift_normalizer_replaces_xcode_tokens_and_preserves_non_xcode_identities(self):
        compiler = shutil.which("swiftc")
        if not compiler:
            self.skipTest("Swift compiler unavailable")
        program = "import Foundation\n" + patcher.HELPER + r'''
let cases: [(String, String)] = [
    ("<MacBookPro15,1> <Mac OS X;10.15.2;19C57> <com.apple.AuthKit/1 (com.apple.dt.Xcode/3594.4.19)>",
     "<MacBookPro15,1> <Mac OS X;10.15.2;19C57> <com.apple.AuthKit/1 (com.apple.akd/1.0)>") ,
    ("<MacBookPro13,2> <macOS;14.4;23E214> <com.apple.AuthKit/1 (com.apple.dt.Xcode/21507)>",
     "<MacBookPro13,2> <macOS;14.4;23E214> <com.apple.AuthKit/1 (com.apple.akd/1.0)>") ,
    ("<MacBookPro13,2> <macOS;14.4;23E214> <com.apple.akd/1.0>",
     "<MacBookPro13,2> <macOS;14.4;23E214> <com.apple.akd/1.0>") ,
    ("com.apple.dt.Xcode", "com.apple.akd/1.0"),
    ("<com.apple.dt.XcodeExperimental/1>", "<com.apple.akd/1.0>")
]
for (input, expected) in cases {
    precondition(v3GsaClientInfo(input) == expected)
}
print("SideSign GSA client identity PASS")
'''
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "main.swift"
            executable = Path(name) / "gsa-client-info-tests"
            source.write_text(program, encoding="utf-8")
            built = subprocess.run([compiler, str(source), "-o", str(executable)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SideSign GSA client identity PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
