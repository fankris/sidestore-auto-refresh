import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "patch_sidesign_gsa_client_info",
    ROOT / "scripts/patch_sidesign_gsa_client_info.py"
)
patch_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch_module)

SAMPLE_AUTH_SWIFT = """import Foundation
import AltSign

public extension DeveloperPortal {
    func sendAuthenticationRequest() {
        let headers: [String: String] = [
            "Content-Type": "text/x-xml-plist",
            "X-MMe-Client-Info": anisetteData.deviceDescription,
            "Accept": "*/*",
            "User-Agent": Constants.userAgent
        ]
    }

    func makeGrandSlamHeaders(context: Context) {
        let headers = [
            "X-Apple-I-MD-LU": context.anisetteData.localUserID,
            "X-Apple-I-MD-RINFO": "\(context.anisetteData.routingInfo)",
            "X-Mme-Device-Id": context.anisetteData.deviceUniqueIdentifier,
            "X-MMe-Client-Info": context.anisetteData.deviceDescription,
            "X-Apple-I-Client-Time": formatDate(context.anisetteData.date),
        ]
    }
}
"""

class SideSignGsaClientInfoTests(unittest.TestCase):
    def test_patch_application_and_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            auth_path = root / "Sources/DeveloperPortal/Authentication.swift"
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            auth_path.write_text(SAMPLE_AUTH_SWIFT, encoding="utf-8")

            patch_module.patch(root)
            patched = auth_path.read_text(encoding="utf-8")

            self.assertIn("V3_GSA_AKD_CLIENT_INFO_V1", patched)
            self.assertIn('"X-MMe-Client-Info": v3GsaClientInfo(anisetteData.deviceDescription)', patched)
            self.assertIn('"X-MMe-Client-Info": v3GsaClientInfo(context.anisetteData.deviceDescription)', patched)

            # Idempotence
            patch_module.patch(root)
            self.assertEqual(auth_path.read_text(encoding="utf-8"), patched)

if __name__ == "__main__":
    unittest.main()
