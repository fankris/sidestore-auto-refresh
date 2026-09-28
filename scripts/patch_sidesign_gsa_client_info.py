#!/usr/bin/env python3
"""Avoid Apple's observed GSA edge block for the Xcode client identity."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

PIN = "a731c0d5a9a6617c7b385ae493e07ffb7f81cd5d"
MARKER = "V3_GSA_AKD_CLIENT_INFO_V1"
AUTH = Path("Sources/DeveloperPortal/Authentication.swift")

HELPER = r'''// V3_GSA_AKD_CLIENT_INFO_V1: normalize the client token implicated in reported GSA 503s.
private func v3GsaClientInfo(_ clientInfo: String) -> String {
    guard let marker = clientInfo.range(of: "com.apple.dt.Xcode") else { return clientInfo }
    let suffix = clientInfo[marker.upperBound...]
    let tokenEnd = suffix.firstIndex(where: { $0 == ")" || $0 == ">" || $0.isWhitespace }) ?? suffix.endIndex
    return String(clientInfo[..<marker.lowerBound]) + "com.apple.akd/1.0" + String(suffix[tokenEnd...])
}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"patch_sidesign_gsa_client_info: {label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def verify_text(text: str) -> None:
    if text.count(MARKER) != 1:
        raise SystemExit("patch_sidesign_gsa_client_info: helper marker missing or duplicated")
    expected = (
        '"X-MMe-Client-Info": v3GsaClientInfo(anisetteData.clientInfo),',
        '"X-MMe-Client-Info": v3GsaClientInfo(a.clientInfo),',
    )
    for anchor in expected:
        if text.count(anchor) != 1:
            raise SystemExit(f"patch_sidesign_gsa_client_info: patched request header missing: {anchor}")
    if '"X-MMe-Client-Info": anisetteData.clientInfo,' in text:
        raise SystemExit("patch_sidesign_gsa_client_info: initial GSA header still uses the raw client identity")
    if '"X-MMe-Client-Info": a.clientInfo,' in text:
        raise SystemExit("patch_sidesign_gsa_client_info: 2FA GSA header still uses the raw client identity")


def verify_pin(root: Path) -> None:
    try:
        actual = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("patch_sidesign_gsa_client_info: cannot verify pinned SideSign source") from error
    if actual != PIN:
        raise SystemExit(f"patch_sidesign_gsa_client_info: expected SideSign {PIN}, got {actual}")


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
        "insert client identity normalizer",
    )
    text = replace_once(
        text,
        '"X-MMe-Client-Info": anisetteData.clientInfo,',
        '"X-MMe-Client-Info": v3GsaClientInfo(anisetteData.clientInfo),',
        "initial GrandSlam authentication header",
    )
    text = replace_once(
        text,
        '"X-MMe-Client-Info": a.clientInfo,',
        '"X-MMe-Client-Info": v3GsaClientInfo(a.clientInfo),',
        "two-factor GrandSlam header",
    )
    path.write_text(text, encoding="utf-8")
    verify_text(path.read_text(encoding="utf-8"))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_sidesign_gsa_client_info.py <pinned-sidesign-root>")
    patch(Path(sys.argv[1]).resolve())
    print("Xcode GSA client identity normalized to akd for initial and 2FA requests")


if __name__ == "__main__":
    main()
