#!/usr/bin/env python3
"""Classify GSA HTTP 429 responses before parsing response bodies."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

PIN = "a731c0d5a9a6617c7b385ae493e07ffb7f81cd5d"
MARKER = "V3_GSA_HTTP_429_CLASSIFICATION_V1"
AUTH = Path("Sources/DeveloperPortal/Authentication.swift")

HELPER = r'''// V3_GSA_HTTP_429_CLASSIFICATION_V1: status-only handling avoids parsing rate-limit HTML as plist.
private func v3ThrowIfGsaRateLimited(_ statusCode: Int) throws {
    guard statusCode == HTTPStatusCodes.tooManyRequests else { return }
    throw DeveloperPortalError.tooManyAttempts(cause: "HTTP 429 Too Many Requests")
}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"patch_sidesign_gsa_rate_limit: {label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def function_body(text: str, name: str) -> str:
    signature = f"func {name}("
    start = text.find(signature)
    if start < 0 or text.find(signature, start + len(signature)) >= 0:
        raise SystemExit(f"patch_sidesign_gsa_rate_limit: expected one function {name}")
    next_function = text.find("\n    private func ", start + len(signature))
    if next_function < 0:
        next_function = text.find("\n    func ", start + len(signature))
    return text[start:next_function if next_function >= 0 else len(text)]


def verify_text(text: str) -> None:
    if text.count(MARKER) != 1:
        raise SystemExit("patch_sidesign_gsa_rate_limit: helper marker missing or duplicated")
    if text.count("try v3ThrowIfGsaRateLimited(statusCode)") != 3:
        raise SystemExit("patch_sidesign_gsa_rate_limit: expected exactly three status checks")

    checks = {
        "sendAuthenticationRequest": "guard !data.isEmpty else {",
        "sendTrustedDevice2FACodeRequest": "try throwIfXMLUIErrorAlert(in: data, statusCode: statusCode, actionName: \"sendTrustedDevice2FACodeRequest\")",
        "sendPhone2FACodeRequest": "try throwIfXMLUIErrorAlert(in: data, statusCode: statusCode, actionName: \"sendPhone2FACodeRequest\")",
    }
    for name, later_handler in checks.items():
        body = function_body(text, name)
        rate_check = "try v3ThrowIfGsaRateLimited(statusCode)"
        if body.count(rate_check) != 1:
            raise SystemExit(f"patch_sidesign_gsa_rate_limit: HTTP 429 check missing from {name}")
        if body.index(rate_check) > body.index(later_handler):
            raise SystemExit(f"patch_sidesign_gsa_rate_limit: HTTP 429 check is too late in {name}")


def verify_pin(root: Path) -> None:
    try:
        actual = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("patch_sidesign_gsa_rate_limit: cannot verify pinned SideSign source") from error
    if actual != PIN:
        raise SystemExit(f"patch_sidesign_gsa_rate_limit: expected SideSign {PIN}, got {actual}")


def patch(root: Path, *, enforce_pin: bool = True) -> None:
    if enforce_pin:
        verify_pin(root)
    path = root / AUTH
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        verify_text(text)
        return

    text = replace_once(
        text,
        "public extension DeveloperPortal {",
        HELPER + "\npublic extension DeveloperPortal {",
        "insert HTTP 429 mapper",
    )
    text = replace_once(
        text,
        "        let statusCode = httpResponse?.statusCode ?? 0\n\n        guard !data.isEmpty else {",
        "        let statusCode = httpResponse?.statusCode ?? 0\n        try v3ThrowIfGsaRateLimited(statusCode)\n\n        guard !data.isEmpty else {",
        "initial GSA response status",
    )
    text = replace_once(
        text,
        '        let statusCode = httpResponse?.safeStatusCode ?? 0\n'
        '        try throwIfXMLUIErrorAlert(in: data, statusCode: statusCode, actionName: "sendTrustedDevice2FACodeRequest")',
        '        let statusCode = httpResponse?.safeStatusCode ?? 0\n'
        '        try v3ThrowIfGsaRateLimited(statusCode)\n'
        '        try throwIfXMLUIErrorAlert(in: data, statusCode: statusCode, actionName: "sendTrustedDevice2FACodeRequest")',
        "trusted-device 2FA response status",
    )
    text = replace_once(
        text,
        "        let statusCode = httpResponse?.safeStatusCode ?? 0\n\n        let rawStr = prettyJSONString(from: data)",
        "        let statusCode = httpResponse?.safeStatusCode ?? 0\n"
        "        try v3ThrowIfGsaRateLimited(statusCode)\n\n"
        "        let rawStr = prettyJSONString(from: data)",
        "SMS/voice 2FA response status",
    )
    path.write_text(text, encoding="utf-8")
    verify_text(path.read_text(encoding="utf-8"))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_sidesign_gsa_rate_limit.py <pinned-sidesign-root>")
    patch(Path(sys.argv[1]).resolve())
    print("GSA HTTP 429 mapped to a rate-limit error before body parsing")


if __name__ == "__main__":
    main()
