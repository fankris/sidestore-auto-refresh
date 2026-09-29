#!/usr/bin/env python3
"""Normalize GSA X-MMe-Client-Info to avoid Apple edge 503 errors."""
from __future__ import annotations
from pathlib import Path
import sys

MARKER = "V3_GSA_AKD_CLIENT_INFO_V1"
AUTH = Path("Sources/DeveloperPortal/Authentication.swift")

HELPER = r'''// V3_GSA_AKD_CLIENT_INFO_V1: normalize client token to avoid Apple GSA 503s.
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
        raise SystemExit(f"patch_sidesign_gsa_client_info: {label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)

def patch(root: Path) -> None:
    path = root / AUTH
    if not path.is_file():
        raise SystemExit(f"patch_sidesign_gsa_client_info: {path} not found")
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return

    text = replace_once(
        text,
        "public extension DeveloperPortal {",
        HELPER + "\npublic extension DeveloperPortal {",
        "insert client identity helper"
    )

    if '"X-MMe-Client-Info": anisetteData.deviceDescription,' in text:
        text = replace_once(
            text,
            '"X-MMe-Client-Info": anisetteData.deviceDescription,',
            '"X-MMe-Client-Info": v3GsaClientInfo(anisetteData.deviceDescription),',
            "initial auth header (deviceDescription)"
        )
    elif '"X-MMe-Client-Info": anisetteData.clientInfo,' in text:
        text = replace_once(
            text,
            '"X-MMe-Client-Info": anisetteData.clientInfo,',
            '"X-MMe-Client-Info": v3GsaClientInfo(anisetteData.clientInfo),',
            "initial auth header (clientInfo)"
        )

    if '"X-MMe-Client-Info": context.anisetteData.deviceDescription,' in text:
        text = replace_once(
            text,
            '"X-MMe-Client-Info": context.anisetteData.deviceDescription,',
            '"X-MMe-Client-Info": v3GsaClientInfo(context.anisetteData.deviceDescription),',
            "grand slam header (deviceDescription)"
        )
    elif '"X-MMe-Client-Info": a.clientInfo,' in text:
        text = replace_once(
            text,
            '"X-MMe-Client-Info": a.clientInfo,',
            '"X-MMe-Client-Info": v3GsaClientInfo(a.clientInfo),',
            "grand slam header (clientInfo)"
        )

    path.write_text(text, encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_sidesign_gsa_client_info.py <sidesign-root>")
    patch(Path(sys.argv[1]).resolve())
    print("SideSign GSA client identity normalized successfully")
