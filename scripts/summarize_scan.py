#!/usr/bin/env python3
import json
import sys
import os
import argparse
from collections import defaultdict


def parse_top(value: str, total: int) -> int:
    v = value.strip().lower()
    if v == "all":
        return total
    try:
        n = int(v)
    except ValueError:
        print(f"Warning: invalid --top value '{value}', defaulting to 10", file=sys.stderr)
        return min(10, total)
    if n < 1:
        print(f"Warning: --top must be >= 1, got {n}, defaulting to 1", file=sys.stderr)
        return 1
    if n > total:
        return total
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="reports/scan-results.json")
    parser.add_argument("--top", default="10", help='Number of violations to show: "all" or a positive integer')
    args = parser.parse_args()

    if not os.path.exists(args.report):
        print("## Salesforce Code Analyzer 掃描結果\n\n> ⚠️ 掃描報告未產生，請確認 workflow 執行日誌。")
        return

    with open(args.report, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content or content == "null":
        print("## Salesforce Code Analyzer 掃描結果\n\n> ✅ 沒有發現任何問題。")
        return

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print("## Salesforce Code Analyzer 掃描結果\n\n> ⚠️ 無法解析掃描報告。")
        return

    if not data:
        print("## Salesforce Code Analyzer 掃描結果\n\n> ✅ 沒有發現任何問題。")
        return

    severity_labels = {
        1: "🔴 Critical",
        2: "🟠 High",
        3: "🟡 Medium",
        4: "🟢 Low",
    }

    severity_counts = defaultdict(int)
    all_violations = []

    for file_result in data:
        file_name = file_result.get("fileName", "Unknown")
        for v in file_result.get("violations", []):
            sev = v.get("normalizedSeverity") or v.get("severity", 4)
            try:
                sev = int(sev)
            except (ValueError, TypeError):
                sev = 4
            severity_counts[sev] += 1
            all_violations.append({
                "file": os.path.relpath(file_name) if os.path.isabs(file_name) else file_name,
                "line": v.get("line", "-"),
                "severity": sev,
                "rule": v.get("ruleName", "-"),
                "message": v.get("message", "-").replace("\n", " ").strip(),
                "engine": v.get("engine", "-"),
            })

    total = sum(severity_counts.values())
    top_n = parse_top(args.top, total)

    print("## 🔍 Salesforce Code Analyzer 掃描結果\n")
    print(f"**總計 {total} 筆問題**\n")

    print("| 嚴重度 | 數量 |")
    print("|--------|------|")
    for sev in sorted(severity_counts.keys()):
        label = severity_labels.get(sev, f"Level {sev}")
        print(f"| {label} | {severity_counts[sev]} |")

    print()

    all_violations.sort(key=lambda x: (x["severity"], x["file"], x["line"]))
    top = all_violations[:top_n]

    label_suffix = "全部" if top_n == total else f"前 {top_n}"
    print(f"### {label_suffix}筆問題\n")
    print("| 嚴重度 | 檔案 | 行數 | 規則 | 說明 |")
    print("|--------|------|------|------|------|")
    for v in top:
        label = severity_labels.get(v["severity"], f"L{v['severity']}")
        msg = v["message"][:80] + "..." if len(v["message"]) > 80 else v["message"]
        file_short = v["file"].replace("force-app/main/default/", "")
        print(f"| {label} | `{file_short}` | {v['line']} | `{v['rule']}` | {msg} |")

    if top_n < total:
        print(f"\n> 完整報告請下載 Artifacts 中的 `scan-results.html`（共 {total} 筆）")


if __name__ == "__main__":
    main()
