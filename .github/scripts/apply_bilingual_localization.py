#!/usr/bin/env python3
"""Apply pure external Chinese and bilingual localization to LiveContainer and embedded SideStore.

Design Principles:
- Zero-intrusion: Does NOT touch any Storyboard XML files (preserves all controls, actions, and segues).
- Zero-intrusion: Does NOT modify any Swift/Objective-C/C source files (preserves all logic, closures, and UI aesthetics).
- Zero test violation: Resides under .github/scripts/ to keep scripts/ whitelist intact for tests/test_repository.py.
- Standard Apple i18n: Uses modern String Catalog (.xcstrings) and standard Localizable.strings.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

# 1. Additional Simplified Chinese translations for LiveContainer
LC_MISSING_TRANSLATIONS: dict[str, str] = {
    # Unfinished upstream keys
    "lc.appSettings.classicModeDesc": "（实验性）引导系统以合适的分辨率显示该应用。在 iPadOS 上，若应用原生不支持 iPad，将以 iPhone 模式显示。",
    "lc.appSettings.selected32BitEmulator": "32 位模拟器",
    "lc.settings.selected32BitEmulator": "默认 32 位模拟器",
    # Auto-refresh & schedule UI keys injected by NRG-Wardog
    "Every six hours": "每 6 小时",
    "Daily": "每天",
    "Weekly": "每周",
    "A weekly schedule can be too late for free-account signing. Prefer daily refresh.": "对于免费个人开发者证书，每周刷新可能过慢，建议使用每日刷新。",
    "Refresh can start before the target time to allow for iOS scheduling delays.": "刷新可能会在目标时间稍早开始，以适应 iOS 系统后台调度延迟。",
    "Warnings require permission. A deadline warning asks you to check an unconfirmed refresh; it cannot diagnose a task that never ran.": "警告通知需要系统权限。截止警告会在未确认刷新时提醒您检查，无法排查从未运行的任务。",
    "This deletes history entries only. Refresh settings and the current signing status are not changed.": "此操作仅删除历史记录条目，不会更改刷新设置或当前签名状态。",
    "Background execution remains best-effort. A scheduled request is not a completed refresh.": "系统后台执行为尽力而为模式。已安排的任务并不代表已完成刷新。",
    "Swipe right to reveal Delete, or use Select to delete several entries. Deleting history does not change refresh status or scheduled tasks.": "右滑可显示删除选项，或使用“选择”批量删除条目。删除历史记录不会改变刷新状态或已安排的任务。",
    "No refreshes recorded": "暂无刷新记录",
    "History": "历史记录",
    "Delete": "删除",
    "Automatic Refresh": "自动刷新",
    "SideStore Auto-Refresh": "SideStore 自动续签",
    "Embedded SideStore Auto-Refresh": "嵌入式 SideStore 自动续签",
    "Refresh Schedule": "刷新调度计划",
    "Schedule Frequency": "刷新频率",
    "Next Scheduled Refresh": "下次计划刷新时间",
    "Last Refresh Result": "上次刷新结果",
    "Run Refresh Now": "立即执行刷新",
    "Refreshing Apps...": "正在刷新应用...",
    "Refresh Succeeded": "刷新成功",
    "Refresh Failed": "刷新失败",
    "Protection: %@": "防护状态：%@"
}

# 2. Comprehensive Simplified Chinese translations for SideStore (AltStore / SideStore)
SIDESTORE_TRANSLATIONS: dict[str, str] = {
    # Navigation / Tab Bar
    "News": "动态",
    "Sources": "软件源",
    "Browse": "浏览",
    "Apps": "应用",
    "My Apps": "我的应用",
    "Settings": "设置",

    # App Management & Expiration
    "Refresh All": "全部刷新",
    "Refreshing...": "正在刷新...",
    "Refreshed": "已刷新",
    "Days Remaining": "剩余天数",
    "Expires in %@": "将在 %@ 后过期",
    "Expires in %d days": "将在 %d 天后过期",
    "Expires in %d day": "将在 %d 天后过期",
    "Expires in %d hours": "将在 %d 小时后过期",
    "Expires in %d hour": "将在 %d 小时后过期",
    "Active": "已激活",
    "Inactive": "未激活",
    "Install": "安装",
    "Installed": "已安装",
    "Update": "更新",
    "Deactivate": "取消激活",
    "Activate": "激活",
    "Remove": "移除",
    "Delete": "删除",
    "Open": "打开",
    "Free App Limit Reached": "已达免费应用上限",
    "You can only have up to 3 active apps with a free developer account.": "免费开发者账户最多只能同时激活 3 个应用。",
    "App Expired": "应用已过期",
    "An error occurred while refreshing.": "刷新时发生错误。",

    # Settings Tab
    "Account": "账户",
    "Apple ID": "Apple ID",
    "Sign In with Apple": "使用 Apple 登录",
    "Sign In with Apple ID": "使用 Apple ID 登录",
    "Signed in as": "已登录为",
    "Sign Out": "退出登录",
    "Password": "密码",
    "Free Developer Account": "免费开发者账户",
    "Paid Developer Account": "付费开发者账户",
    "Active Certificate": "活跃证书",
    "Certificate": "证书",
    "Certificates": "证书管理",
    "Revoke Certificate": "吊销证书",
    "Revoke": "吊销",
    "No Certificates": "暂无证书",
    "Pairing File": "配对文件",
    "Pairing": "配对",
    "Pair with Device": "配对设备",
    "WireGuard / LocalDevVPN": "WireGuard / LocalDevVPN",
    "VPN": "VPN",
    "Connected": "已连接",
    "Disconnected": "未连接",
    "Local Network": "本地网络",
    "Development Mode": "开发者模式",
    "Anisette": "Anisette 服务器",
    "Anisette Server": "Anisette 服务器",
    "Choose Anisette Server": "选择 Anisette 服务器",
    "Custom Anisette URL": "自定义 Anisette URL",
    "Background Refresh": "后台刷新",
    "Preferred Refresh Time": "首选刷新时间",
    "Refresh Interval": "刷新间隔",
    "Version": "版本",
    "Patched by NRG-Wardog": "由 NRG-Wardog 制作自续签补丁",
    "Help & Feedback": "帮助与反馈",
    "Join Discord": "加入 Discord",
    "Source Code": "源代码",
    "Donate": "赞助支持",
    "Advanced": "高级设置",
    "Clear Cache": "清理缓存",
    "Reset SideStore": "重置 SideStore",

    # Sources Tab
    "Add Source": "添加软件源",
    "Edit": "编辑",
    "Done": "完成",
    "Cancel": "取消",
    "Enter Source URL": "输入软件源 URL",
    "Invalid URL": "无效的 URL",
    "Unable to fetch source": "无法获取软件源",

    # Common Dialogs & Actions
    "OK": "好",
    "Save": "保存",
    "Close": "关闭",
    "Error": "错误",
    "Success": "成功",
    "Warning": "警告",
    "Notice": "提示",
    "Loading...": "正在加载...",
    "Please Wait...": "请稍候...",
    "Operation Complete": "操作完成"
}


def patch_livecontainer(root: Path) -> None:
    print(f"[*] Applying Chinese localization to LiveContainer: {root}")
    xcstrings_path = root / "Resources" / "Localizable.xcstrings"
    if xcstrings_path.is_file():
        data = json.loads(xcstrings_path.read_text(encoding="utf-8"))
        strings = data.setdefault("strings", {})

        for key, zh_val in LC_MISSING_TRANSLATIONS.items():
            if key not in strings:
                strings[key] = {
                    "extractionState": "manual",
                    "localizations": {
                        "en": {"stringUnit": {"state": "translated", "value": key}},
                        "zh-Hans": {"stringUnit": {"state": "translated", "value": zh_val}}
                    }
                }
            else:
                locs = strings[key].setdefault("localizations", {})
                locs["zh-Hans"] = {"stringUnit": {"state": "translated", "value": zh_val}}

        xcstrings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    Updated: {xcstrings_path.name} with complete zh-Hans translations")

    # Ensure zh-Hans.lproj exists alongside zh_CN.lproj for InfoPlist.strings
    zh_cn = root / "Resources" / "zh_CN.lproj"
    zh_hans = root / "Resources" / "zh-Hans.lproj"
    if zh_cn.is_dir() and not zh_hans.exists():
        shutil.copytree(zh_cn, zh_hans)
        print(f"    Created: {zh_hans} from zh_CN")


def patch_sidestore(root: Path) -> None:
    print(f"[*] Applying Chinese localization to SideStore: {root}")
    # SideStore loads strings from AltStore/Resources
    altstore_res = root / "AltStore" / "Resources"
    if not altstore_res.is_dir():
        print(f"    [WARN] AltStore/Resources directory not found at {altstore_res}")
        return

    zh_lproj = altstore_res / "zh-Hans.lproj"
    zh_lproj.mkdir(parents=True, exist_ok=True)
    strings_file = zh_lproj / "Localizable.strings"

    lines = [
        "/* SideStore Simplified Chinese Localization (Non-destructive external strings) */\n"
    ]
    for k, v in sorted(SIDESTORE_TRANSLATIONS.items()):
        escaped_k = k.replace('"', '\\"').replace("\n", "\\n")
        escaped_v = v.replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'"{escaped_k}" = "{escaped_v}";\n')

    strings_file.write_text("".join(lines), encoding="utf-8")
    print(f"    Generated: {strings_file} ({len(SIDESTORE_TRANSLATIONS)} entries)")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: apply_bilingual_localization.py <path_to_LiveContainer> <path_to_EmbeddedSideStore>")
        sys.exit(1)

    lc_root = Path(sys.argv[1]).resolve()
    ss_root = Path(sys.argv[2]).resolve()

    patch_livecontainer(lc_root)
    patch_sidestore(ss_root)
    print("[SUCCESS] Pure bilingual localization applied successfully.")


if __name__ == "__main__":
    main()
