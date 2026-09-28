"""Regression tests for status-only GSA HTTP 429 classification."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "patch_sidesign_gsa_rate_limit", ROOT / "scripts/patch_sidesign_gsa_rate_limit.py"
)
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


SOURCE = '''import Foundation
public extension DeveloperPortal {
    func sendAuthenticationRequest() {
        let statusCode = httpResponse?.statusCode ?? 0

        guard !data.isEmpty else {
            throw ServerError.badServerResponse(reason: "empty", jsonPayload: "")
        }
        parsePlistOrJSON(data)
    }

    private func sendTrustedDevice2FACodeRequest() throws {
        let statusCode = httpResponse?.safeStatusCode ?? 0
        try throwIfXMLUIErrorAlert(in: data, statusCode: statusCode, actionName: "sendTrustedDevice2FACodeRequest")
        guard statusCode == HTTPStatusCodes.ok else { throw ServerError.badServerResponse(reason: "status", jsonPayload: "") }
    }

    private func sendPhone2FACodeRequest() throws {
        let statusCode = httpResponse?.safeStatusCode ?? 0

        let rawStr = prettyJSONString(from: data)
        try throwIfXMLUIErrorAlert(in: data, statusCode: statusCode, actionName: "sendPhone2FACodeRequest")
    }
}
'''


class SideSignGsaRateLimitPatchTests(unittest.TestCase):
    def fixture(self, directory: Path) -> Path:
        root = directory / "SideSign"
        source = root / patcher.AUTH
        source.parent.mkdir(parents=True)
        source.write_text(SOURCE, encoding="utf-8")
        return root

    def test_maps_429_before_empty_body_and_xml_alert_parsing(self):
        with tempfile.TemporaryDirectory() as name:
            root = self.fixture(Path(name))
            patcher.patch(root, enforce_pin=False)
            source = (root / patcher.AUTH).read_text(encoding="utf-8")
            patcher.patch(root, enforce_pin=False)
            replay = (root / patcher.AUTH).read_text(encoding="utf-8")

        self.assertEqual(source, replay)
        self.assertEqual(source.count(patcher.MARKER), 1)
        self.assertEqual(source.count("try v3ThrowIfGsaRateLimited(statusCode)"), 3)
        initial = patcher.function_body(source, "sendAuthenticationRequest")
        trusted = patcher.function_body(source, "sendTrustedDevice2FACodeRequest")
        phone = patcher.function_body(source, "sendPhone2FACodeRequest")
        self.assertLess(initial.index("try v3ThrowIfGsaRateLimited(statusCode)"), initial.index("guard !data.isEmpty"))
        self.assertLess(trusted.index("try v3ThrowIfGsaRateLimited(statusCode)"), trusted.index("try throwIfXMLUIErrorAlert"))
        self.assertLess(phone.index("try v3ThrowIfGsaRateLimited(statusCode)"), phone.index("try throwIfXMLUIErrorAlert"))

    def test_fails_closed_when_a_response_path_anchor_drifts(self):
        with tempfile.TemporaryDirectory() as name:
            root = self.fixture(Path(name))
            source = root / patcher.AUTH
            drifted = SOURCE.replace("let statusCode = httpResponse?.statusCode ?? 0", "let statusCode = 200")
            source.write_text(drifted, encoding="utf-8")
            with self.assertRaises(SystemExit):
                patcher.patch(root, enforce_pin=False)
            self.assertEqual(source.read_text(encoding="utf-8"), drifted)

    def test_rate_limit_helper_only_throws_for_http_429(self):
        compiler = shutil.which("swiftc")
        if not compiler:
            self.skipTest("Swift compiler unavailable")
        program = "import Foundation\n" + r'''
enum HTTPStatusCodes { static let tooManyRequests = 429 }
enum DeveloperPortalError: Error { case tooManyAttempts(cause: String) }
''' + patcher.HELPER + r'''
func isRateLimited(_ statusCode: Int) -> Bool {
    do {
        try v3ThrowIfGsaRateLimited(statusCode)
        return false
    } catch DeveloperPortalError.tooManyAttempts(_) {
        return true
    } catch {
        return false
    }
}
precondition(isRateLimited(429))
precondition(!isRateLimited(503))
print("SideSign GSA HTTP 429 classification PASS")
'''
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "main.swift"
            executable = Path(name) / "gsa-429-tests"
            source.write_text(program, encoding="utf-8")
            built = subprocess.run([compiler, str(source), "-o", str(executable)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SideSign GSA HTTP 429 classification PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
