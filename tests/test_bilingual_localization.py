from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


localization = load_module(
    "apply_bilingual_localization",
    ROOT / ".github/scripts/apply_bilingual_localization.py",
)
service_patch = load_module("patch_v3_service", ROOT / "scripts/patch_v3_service.py")


class BilingualLocalizationTests(unittest.TestCase):
    def test_translation_dictionary_has_no_duplicate_keys(self):
        tree = ast.parse((ROOT / ".github/scripts/apply_bilingual_localization.py").read_text(encoding="utf-8"))
        assignment = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", None) == "V3_TRANSLATIONS"
        )
        keys = [ast.literal_eval(key) for key in assignment.value.keys]
        self.assertEqual(len(keys), len(set(keys)))

    def test_v3_auth_and_setup_strings_are_translated(self):
        required = {
            "Apple ID Sign In",
            "Choose Verification Method",
            "Choose Phone Number",
            "Enter Verification Code",
            "Verification request sent to your trusted devices.",
            "Verification code requested by SMS.",
            "Account Attention Needed",
            "Open Apple Account Repair",
            "Sign-in timed out. Start a new sign-in when you are ready.",
            "Start New Sign-In",
            "Check Password and Start New Sign-In",
            "The saved Apple session is no longer valid.",
            "SideStore could not identify this device for registration.",
            "Next: Set Up JIT-Less",
            "LiveContainer needs a JIT-Less certificate configured before guest apps can launch on iOS 26 and later.",
            "Pairing file available",
            "No verified refresh in this session yet",
            "Open Refresh Manager to inspect this run, then try Test Refresh again. Copy Diagnostics if the result remains unclear.",
        }
        self.assertFalse(required.difference(localization.V3_TRANSLATIONS))
        self.assertTrue(all(localization.V3_TRANSLATIONS[key].strip() for key in required))

    def test_all_unified_shell_static_display_keys_have_translations(self):
        shell = (ROOT / "scripts/templates/v3_unified_shell.swift").read_text(encoding="utf-8")
        patterns = (
            r'\b(?:Text|Button|Section|Label|Link|DisclosureGroup|TextField|ProgressView|navigationTitle|navigationBarTitle|accessibilityLabel|accessibilityHint|confirmationDialog)\("([^"\n]+)"',
            r'title: "([^"\n]+)"',
        )
        literals = []
        for pattern in patterns:
            literals.extend(re.findall(pattern, shell))
        display_keys = {value for value in literals if "\\(" not in value and not value.startswith("http")}
        nontext = {"\\", "-", "0"}
        missing = sorted(display_keys.difference(localization.V3_TRANSLATIONS).difference(nontext))
        self.assertFalse(missing, f"missing Chinese strings: {missing}")

    def test_dynamic_status_and_recovery_policy_text_has_translations(self):
        policy = (ROOT / "scripts/templates/v3_behavioral_primitives.swift").read_text(encoding="utf-8")
        scopes = (
            ("struct V3JITLessPresentation", "enum V3JITLessSetupAction"),
            ("enum V3StatusSeverity", "enum V3IssueAction"),
            ("enum V3IssueAction", "struct V3UserFacingIssue"),
            ("enum V3TwoFactorStep", "enum V3AuthTerminalPolicy"),
            ("enum V3AuthTerminalFailureActionPolicy", "enum V3AuthRepairURLPolicy"),
        )
        values = []
        for start_marker, end_marker in scopes:
            start = policy.index(start_marker)
            end = policy.index(end_marker, start)
            scope = policy[start:end]
            values.extend(re.findall(r'\b(?:return|title|detail):?\s*"([^"\n]+)"', scope))
        route_values = {"certificates", "connection", "ipa", "pairing", "setup", "signIn", "sources"}
        display_values = {value for value in values if ("." not in value or " " in value) and value not in route_values}
        missing = sorted(display_values.difference(localization.V3_TRANSLATIONS))
        self.assertFalse(missing, f"missing dynamic policy translations: {missing}")

    def test_auth_runtime_messages_have_translations(self):
        message_sources = (
            (ROOT / "scripts/templates/v3_behavioral_primitives.swift", r'message:\s*"([^"\n]+)"'),
            (ROOT / "scripts/templates/v3_headless_runtime.swift", r'(?:return|message:)\s*"([^"\n]+)"'),
        )
        values = []
        for path, pattern in message_sources:
            values.extend(re.findall(pattern, path.read_text(encoding="utf-8")))
        display_values = {value for value in values if "\\(" not in value and value != "{}"}
        missing = sorted(display_values.difference(localization.V3_TRANSLATIONS))
        self.assertFalse(missing, f"missing auth/service message translations: {missing}")

    def test_dynamic_auth_prompts_resolve_through_host_catalog(self):
        shell = (ROOT / "scripts/templates/v3_unified_shell.swift").read_text(encoding="utf-8")
        for anchor in (
            "private func v3LocalizedString(_ value: String) -> String",
            "rawMessage.components(separatedBy: \"\\n\\n\")",
            "v3LocalizedString(row[\"label\"] as? String ?? key)",
            "v3LocalizedString(row[\"label\"] as? String ?? id)",
            "Text(v3LocalizedString(auth.message))",
            "Text(v3LocalizedString(state.detail.isEmpty ? stateLabel(state.state) : state.detail))",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, shell)

    def test_localization_precedes_layout_regression_and_first_host_build(self):
        workflow = (ROOT / ".github/workflows/livecontainer-build.yml").read_text(encoding="utf-8")
        integration = workflow.index("- name: Apply and verify host integration")
        localization_step = workflow.index("- name: Apply Chinese bilingual localization")
        layout = workflow.index("- name: Execute real layout regression on final generated source")
        host_build = workflow.index("- name: Build unified host before transport compilation")
        self.assertLess(integration, localization_step)
        self.assertLess(localization_step, layout)
        self.assertLess(layout, host_build)
        self.assertEqual(workflow.count("- name: Apply Chinese bilingual localization"), 1)

    def test_livecontainer_catalog_receives_verified_zh_hans_entries(self):
        with self.subTest("catalog update and locale preservation"), patch("builtins.print"):
            import tempfile
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "LiveContainer"
                resources = root / "Resources"
                resources.mkdir(parents=True)
                catalog = resources / "Localizable.xcstrings"
                catalog.write_text(json.dumps({
                    "sourceLanguage": "en",
                    "strings": {
                        "Apple ID": {
                            "localizations": {
                                "en": {"stringUnit": {"state": "translated", "value": "Apple ID"}}
                            }
                        }
                    },
                }), encoding="utf-8")
                zh_cn = resources / "zh_CN.lproj"
                zh_cn.mkdir()
                (zh_cn / "InfoPlist.strings").write_text('"CFBundleName" = "测试";\n', encoding="utf-8")

                localization.patch_livecontainer(root)

                output = json.loads(catalog.read_text(encoding="utf-8"))
                self.assertEqual(
                    output["strings"]["Apple ID"]["localizations"]["zh-Hans"]["stringUnit"]["value"],
                    localization.V3_TRANSLATIONS["Apple ID"],
                )
                self.assertIn("Apple ID Sign In", output["strings"])
                self.assertIn("en", output["strings"]["Apple ID"]["localizations"])
                self.assertTrue((resources / "zh-Hans.lproj/InfoPlist.strings").is_file())

    def test_sidestore_gets_a_complete_zh_hans_strings_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary, patch("builtins.print"):
            root = Path(temporary) / "EmbeddedSideStore"
            project = root / "AltStore.xcodeproj/project.pbxproj"
            project.parent.mkdir(parents=True)
            project.write_text(
                "isa = PBXFileSystemSynchronizedRootGroup; path = AltStore;",
                encoding="utf-8",
            )
            localization.patch_sidestore(root)
            strings = (root / "AltStore/Resources/zh-Hans.lproj/Localizable.strings").read_text(encoding="utf-8")
            self.assertIn('"Apple ID Sign In" = "Apple ID 登录";', strings)
            entries = [line for line in strings.splitlines() if line.startswith('"') and line.endswith('";')]
            self.assertEqual(len(entries), len(localization.V3_TRANSLATIONS))

    def test_missing_localization_resources_fail_instead_of_silently_skipping(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "missing"
            root.mkdir()
            with self.assertRaises(SystemExit):
                localization.patch_livecontainer(root)
            with self.assertRaises(SystemExit):
                localization.patch_sidestore(root)

    def test_signin_operation_patch_matches_private_pinned_anchor_and_is_idempotent(self):
        fixture = (ROOT / "tests/fixtures/v3_signin_operation_patch_anchors.swift").read_text(encoding="utf-8")
        self.assertIn("    private func getAnisetteData() async throws -> ALTAnisetteData {", fixture)
        patched = service_patch.patch_sign_in_operation(fixture)
        self.assertIn("V3_ANISSETTE_REMOTE_PREFLIGHT_V1", patched)
        self.assertIn("V3AuthAnisetteRemoteSyncPolicy.shouldSyncRemote", patched)
        self.assertIn('UserDefaults.standard.bool(forKey: "useOnDeviceAnisette")', patched)
        self.assertIn('let serverCatalogOfflineMode = await AnisetteServersManager.shared.isOfflineMode', patched)
        self.assertIn('offlineMode: UserDefaults.standard.bool(forKey: "isAnisetteOfflineMode") || serverCatalogOfflineMode', patched)
        self.assertIn("_ = try await AnisetteServersManager.shared.syncWithRemote()", patched)
        self.assertNotIn("try? await AnisetteServersManager.shared.syncWithRemote()", patched)
        self.assertNotIn("catch OperationError.unknownUDID", patched)
        self.assertIn("V3_AUTH_ATTEMPT_SESSION_PRESERVATION_V1", patched)
        self.assertIn("!self.v3AuthenticatedDuringThisOperation", patched)
        self.assertEqual(service_patch.patch_sign_in_operation(patched), patched)

    def test_signin_operation_patch_fails_closed_on_private_anchor_drift(self):
        fixture = (ROOT / "tests/fixtures/v3_signin_operation_patch_anchors.swift").read_text(encoding="utf-8")
        drifted = fixture.replace("private func getAnisetteData()", "func getAnisetteData()", 1)
        with self.assertRaises(SystemExit):
            service_patch.patch_sign_in_operation(drifted)

    def test_silent_authentication_can_fall_back_to_current_apple_id(self):
        runtime = (ROOT / "scripts/templates/v3_headless_runtime.swift").read_text(encoding="utf-8")
        self.assertIn("let currentAppleID = AuthManager.shared.currentAppleID?", runtime)
        self.assertIn("resolvedAppleID = currentAppleID", runtime)
        self.assertIn("AuthManager.shared.session = session", runtime)

    def test_anisette_remote_sync_policy_executes_all_mode_paths(self):
        swiftc = shutil.which("swiftc")
        if not swiftc:
            self.skipTest("Swift compiler unavailable; policy harness runs in CI")
        primitives = (ROOT / "scripts/templates/v3_behavioral_primitives.swift").read_text(encoding="utf-8")
        start = primitives.index("enum V3AuthAnisetteRemoteSyncPolicy {")
        end = primitives.index("\nenum V3AuthTerminalFailureActionPolicy", start)
        policy = primitives[start:end]
        harness = """
@main struct AnisettePolicyHarness {
    static func main() {
        precondition(V3AuthAnisetteRemoteSyncPolicy.shouldSyncRemote(
            useOnDeviceAnisette: false, offlineMode: false, activeServerCount: 0))
        precondition(!V3AuthAnisetteRemoteSyncPolicy.shouldSyncRemote(
            useOnDeviceAnisette: false, offlineMode: false, activeServerCount: 2))
        precondition(!V3AuthAnisetteRemoteSyncPolicy.shouldSyncRemote(
            useOnDeviceAnisette: true, offlineMode: false, activeServerCount: 0))
        precondition(!V3AuthAnisetteRemoteSyncPolicy.shouldSyncRemote(
            useOnDeviceAnisette: false, offlineMode: true, activeServerCount: 0))
        print("V3_AUTH_ANISETTE_SYNC_POLICY_PASS")
    }
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "policy.swift"
            executable = Path(temporary) / "policy"
            source.write_text(policy + "\n" + harness, encoding="utf-8")
            compiled = subprocess.run([swiftc, "-parse-as-library", str(source), "-o", str(executable)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("V3_AUTH_ANISETTE_SYNC_POLICY_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
