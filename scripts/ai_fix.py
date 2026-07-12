#!/usr/bin/env python3
"""
AI Fix Script — reads scan-results.json, calls an OpenAI-compatible chat
completions API to fix Critical Apex violations, writes fixes back to
source files, tracks token usage.

Usage:
  python3 scripts/ai_fix.py --json reports/scan-results.json --batch 10 --severity 1
  python3 scripts/ai_fix.py --summary reports/ai-fix-summary.json   # print fix summary
  python3 scripts/ai_fix.py --pr-body reports/ai-fix-summary.json   # print PR body

Configure via env vars:
  AI_API_KEY   (required) API key for your provider
  AI_BASE_URL  (optional) OpenAI-compatible base URL, e.g. https://integrate.api.nvidia.com/v1
  AI_MODEL     (optional) model name, defaults to DEFAULT_MODEL below
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"


def parse_batch(value: str, total: int) -> int:
    v = value.strip().lower()
    if v == "all":
        return total
    try:
        n = int(v)
    except ValueError:
        print(f"Warning: invalid --batch value '{value}', defaulting to 10", file=sys.stderr)
        return min(10, total)
    if n < 1:
        print(f"Warning: --batch must be >= 1, got {n}, using 1", file=sys.stderr)
        return 1
    return min(n, total)


def strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def call_model(api_key: str, base_url: str, model: str, system: str, user: str) -> tuple[str, dict]:
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key)
    content_parts = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        top_p=0.7,
        max_tokens=1024,
        stream=True,
    )

    for chunk in completion:
        if hasattr(chunk, "usage") and chunk.usage:
            usage = {
                "prompt_tokens": chunk.usage.prompt_tokens or 0,
                "completion_tokens": chunk.usage.completion_tokens or 0,
                "total_tokens": chunk.usage.total_tokens or 0,
            }
        if chunk.choices and chunk.choices[0].delta.content is not None:
            content_parts.append(chunk.choices[0].delta.content)

    return "".join(content_parts), usage


def build_prompt_line(filename: str, line_no: int, rule: str, message: str, line_content: str) -> tuple[str, str]:
    system = (
        "You are a Salesforce Apex expert and static analysis specialist. "
        "Fix the PMD rule violation in the provided Apex code line. "
        "Return ONLY the fixed replacement lines (raw Apex, no explanation, no markdown, no code fences). "
        "Preserve indentation. The fix may span multiple lines if needed."
    )
    user = (
        f"File: {filename}\n"
        f"Line {line_no}: [{rule}] {message}\n\n"
        f"Code to fix:\n{line_content}"
    )
    return system, user


def print_summary(summary_path: str) -> None:
    if not os.path.exists(summary_path):
        print("## 🤖 AI Fix 摘要\n\n> 摘要檔案不存在。")
        return
    with open(summary_path, "r") as f:
        data = json.load(f)
    tokens = data.get("tokens", {})
    print("## 🤖 AI Fix 摘要\n")
    print(f"- **修復違規數**：{data.get('total_violations', 0)} 筆")
    print(f"- **修復檔案數**：{data.get('total_files', 0)} 個")
    print(f"- **跳過檔案數**：{len(data.get('skipped', []))} 個")
    print()
    print("### Token 消耗")
    print("| 類型 | 數量 |")
    print("|------|------|")
    print(f"| Prompt | {tokens.get('prompt_tokens', 0):,} |")
    print(f"| Completion | {tokens.get('completion_tokens', 0):,} |")
    print(f"| **Total** | **{tokens.get('total_tokens', 0):,}** |")


def pr_body(summary_path: str) -> str:
    if not os.path.exists(summary_path):
        return "## AI Auto-Fix: Critical Violations\n\nNo summary available."
    with open(summary_path, "r") as f:
        data = json.load(f)
    tokens = data.get("tokens", {})
    fixed = data.get("fixed", [])
    skipped = data.get("skipped", [])
    lines = [
        "## AI Auto-Fix: Critical Violations\n",
        f"Fixed **{data.get('total_violations', 0)}** violations across **{data.get('total_files', 0)}** files.\n",
        "| File | Line | Rule |",
        "|------|------|------|",
    ]
    for item in fixed:
        short = item["file"].replace("force-app/main/default/", "")
        for v in item["violations"]:
            lines.append(f"| `{short}` | {v['line']} | `{v['rule']}` |")
    if skipped:
        lines.append("\n### Skipped (API error or empty response)")
        for item in skipped:
            lines.append(f"- `{item['file']}`: {item.get('reason', 'unknown')}")
    lines.append("\n### Token 消耗")
    lines.append("| 類型 | 數量 |")
    lines.append("|------|------|")
    lines.append(f"| Prompt | {tokens.get('prompt_tokens', 0):,} |")
    lines.append(f"| Completion | {tokens.get('completion_tokens', 0):,} |")
    lines.append(f"| **Total** | **{tokens.get('total_tokens', 0):,}** |")
    lines.append(
        "\n> Generated by AI Fix workflow. "
        "Please review all changes carefully before merging."
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="reports/scan-results.json", dest="json_path")
    parser.add_argument("--batch", default="10")
    parser.add_argument("--severity", type=int, default=1)
    parser.add_argument("--summary", default=None, dest="summary_path",
                        help="Print fix summary from summary JSON and exit")
    parser.add_argument("--pr-body", default=None, dest="pr_body_path",
                        help="Print PR body from summary JSON and exit")
    args = parser.parse_args()

    if args.summary_path is not None:
        print_summary(args.summary_path)
        return

    if args.pr_body_path is not None:
        print(pr_body(args.pr_body_path))
        return

    api_key = os.environ.get("AI_API_KEY", "")
    if not api_key:
        print("Error: AI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    base_url = os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("AI_MODEL", DEFAULT_MODEL)

    if not os.path.exists(args.json_path):
        print(f"Error: scan report not found at {args.json_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.json_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw or raw == "null":
        print("No violations found in scan report. Nothing to fix.")
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("Error: could not parse scan report JSON.", file=sys.stderr)
        sys.exit(1)

    all_violations = []
    for file_result in data:
        file_name = file_result.get("fileName", "")
        for v in file_result.get("violations", []):
            sev = v.get("normalizedSeverity") or v.get("severity", 4)
            try:
                sev = int(sev)
            except (ValueError, TypeError):
                sev = 4
            if sev == args.severity:
                all_violations.append({
                    "file": file_name,
                    "line": v.get("line", "-"),
                    "rule": v.get("ruleName", "-"),
                    "message": v.get("message", "-").replace("\n", " ").strip(),
                    "engine": v.get("engine", "-"),
                })

    if not all_violations:
        print(f"No severity-{args.severity} violations found. Nothing to fix.")
        return

    all_violations.sort(key=lambda x: (x["file"], x["line"]))
    batch_n = parse_batch(args.batch, len(all_violations))
    selected = all_violations[:batch_n]

    print(f"Found {len(all_violations)} Critical violations. Processing {batch_n}.")

    by_file: dict[str, list] = defaultdict(list)
    for v in selected:
        by_file[v["file"]].append(v)

    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    summary = {"fixed": [], "skipped": [], "total_violations": 0, "total_files": 0, "tokens": total_tokens}

    for file_path, violations in by_file.items():
        if not os.path.exists(file_path):
            print(f"  Skip (file not found): {file_path}")
            summary["skipped"].append({"file": file_path, "reason": "file not found", "violations": violations})
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            file_lines = f.readlines()

        print(f"  Fixing {len(violations)} violation(s) in {file_path} ...")

        # process violations in reverse line order so earlier splices don't shift later indices
        sorted_violations = sorted(violations, key=lambda v: v["line"], reverse=True)
        fixed_violations = []
        skipped_violations = []

        for v in sorted_violations:
            line_idx = int(v["line"]) - 1
            if line_idx < 0 or line_idx >= len(file_lines):
                skipped_violations.append({**v, "reason": f"line {v['line']} out of range"})
                continue

            line_content = file_lines[line_idx].rstrip("\n")
            try:
                system, user = build_prompt_line(file_path, v["line"], v["rule"], v["message"], line_content)
                response, usage = call_model(api_key, base_url, model, system, user)
                for k in total_tokens:
                    total_tokens[k] += usage.get(k, 0)
                fixed_text = strip_fences(response)
            except Exception as e:
                print(f"    Error for line {v['line']} [{v['rule']}]: {e}", file=sys.stderr)
                skipped_violations.append({**v, "reason": str(e)})
                continue

            if not fixed_text:
                print(f"    Empty response for line {v['line']} [{v['rule']}], skipping.")
                skipped_violations.append({**v, "reason": "empty response"})
                continue

            # splice: replace the single flagged line with the returned lines
            replacement = [l + "\n" for l in fixed_text.splitlines()]
            file_lines[line_idx:line_idx + 1] = replacement
            fixed_violations.append(v)
            print(f"    Fixed line {v['line']} [{v['rule']}]")

        if fixed_violations:
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(file_lines)
            summary["fixed"].append({"file": file_path, "violations": fixed_violations})
            summary["total_violations"] += len(fixed_violations)
            print(f"  Done: {file_path} ({len(fixed_violations)} fixed)")

        if skipped_violations:
            summary["skipped"].append({"file": file_path, "reason": "partial failure", "violations": skipped_violations})

    summary["total_files"] = len(summary["fixed"])
    summary["tokens"] = total_tokens

    os.makedirs("reports", exist_ok=True)
    with open("reports/ai-fix-summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary: fixed {summary['total_violations']} violations in {summary['total_files']} files.")
    print(f"Tokens used: {total_tokens['total_tokens']:,} (prompt: {total_tokens['prompt_tokens']:,}, completion: {total_tokens['completion_tokens']:,})")
    if summary["skipped"]:
        print(f"Skipped: {len(summary['skipped'])} file(s). See reports/ai-fix-summary.json for details.")


if __name__ == "__main__":
    main()
