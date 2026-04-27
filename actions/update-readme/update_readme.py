#!/usr/bin/env python3
"""
update_readme.py - README自動更新スクリプト
torihada-biz/.github の Composite Action から呼び出される。

対応マーカー:
  <!-- AUTO:LAST_UPDATED:START --> ... <!-- AUTO:LAST_UPDATED:END -->
  <!-- AUTO:STRUCTURE:START -->    ... <!-- AUTO:STRUCTURE:END -->
  <!-- AUTO:SCRIPTS:START -->      ... <!-- AUTO:SCRIPTS:END -->
  <!-- AUTO:BADGES:START -->       ... <!-- AUTO:BADGES:END -->

Requirements: Python 3.10+ 標準ライブラリのみ
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER_RE = re.compile(
    r"(<!-- AUTO:(?P<key>[A-Z_]+):START -->)"
    r"(?P<body>.*?)"
    r"(<!-- AUTO:(?P=key):END -->)",
    re.DOTALL,
)

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
    ".turbo",
    "coverage",
    ".cache",
}

EXCLUDE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    ".gitkeep",
}


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=15,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def get_last_updated(repo_root: Path) -> str:
    """最終コミット日時 + 短縮SHA を取得"""
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root) or "unknown"
    raw_date = _run(["git", "log", "-1", "--format=%cI"], cwd=repo_root)
    if raw_date:
        try:
            # ISO 8601 → UTC表示（ランナーはUTC）
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            dt_utc = dt.astimezone(timezone.utc)
            date_str = dt_utc.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            date_str = raw_date[:10]
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"Last updated: **{date_str}** (commit: `{sha}`)"


# ---------------------------------------------------------------------------
# Directory tree
# ---------------------------------------------------------------------------

def _build_tree(
    root: Path,
    prefix: str = "",
    depth: int = 2,
    current_depth: int = 0,
) -> list[str]:
    if current_depth >= depth:
        return []

    lines: list[str] = []
    try:
        entries = sorted(
            root.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
    except PermissionError:
        return []

    entries = [
        e for e in entries
        if e.name not in EXCLUDE_DIRS
        and e.name not in EXCLUDE_FILES
        and not e.name.startswith(".")
        or e.name in {".github", ".env.example"}
    ]

    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir() and entry.name not in EXCLUDE_DIRS:
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.extend(
                _build_tree(entry, prefix + extension, depth, current_depth + 1)
            )

    return lines


def get_structure(repo_root: Path, depth: int = 2) -> str:
    """ディレクトリツリーを markdown コードブロックとして返す"""
    tree_lines = _build_tree(repo_root, depth=depth)
    name = repo_root.name
    content = f"{name}/\n" + "\n".join(tree_lines)
    return f"```\n{content}\n```"


# ---------------------------------------------------------------------------
# Scripts section
# ---------------------------------------------------------------------------

def _parse_package_json(repo_root: Path) -> str | None:
    pkg = repo_root / "package.json"
    if not pkg.exists():
        # frontendサブディレクトリも探す
        for sub in ("frontend", "web", "app"):
            candidate = repo_root / sub / "package.json"
            if candidate.exists():
                pkg = candidate
                break
        else:
            return None

    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    scripts = data.get("scripts", {})
    if not scripts:
        return None

    lines = [f"**`package.json` scripts** (`{pkg.relative_to(repo_root)}`):", ""]
    lines.append("| コマンド | 内容 |")
    lines.append("|---------|------|")
    for name, cmd in scripts.items():
        lines.append(f"| `npm run {name}` | `{cmd}` |")
    return "\n".join(lines)


def _parse_pyproject_toml(repo_root: Path) -> str | None:
    """pyproject.toml から [tool.taskipy] or [project.scripts] を抽出"""
    candidates = list(repo_root.rglob("pyproject.toml"))
    # .venv 内を除外
    candidates = [p for p in candidates if ".venv" not in str(p) and "node_modules" not in str(p)]
    if not candidates:
        return None

    results: list[str] = []
    for pyproject in candidates[:2]:  # 最大2ファイルまで
        text = pyproject.read_text(encoding="utf-8")
        rel = pyproject.relative_to(repo_root)

        # [project.scripts] セクション
        match = re.search(r"\[project\.scripts\](.*?)(?=\[|\Z)", text, re.DOTALL)
        if match:
            entries = re.findall(r'(\S+)\s*=\s*"([^"]+)"', match.group(1))
            if entries:
                results.append(f"**`{rel}` scripts:**")
                results.append("")
                results.append("| コマンド | エントリーポイント |")
                results.append("|---------|-----------------|")
                for cmd, entry in entries:
                    results.append(f"| `{cmd}` | `{entry}` |")

        # [tool.taskipy.tasks] セクション（taskipy ユーザー向け）
        match2 = re.search(r"\[tool\.taskipy\.tasks\](.*?)(?=\[|\Z)", text, re.DOTALL)
        if match2:
            entries2 = re.findall(r'(\S+)\s*=\s*"([^"]+)"', match2.group(1))
            if entries2:
                results.append(f"**`{rel}` taskipy tasks:**")
                results.append("")
                for cmd, cmd_str in entries2:
                    results.append(f"- `task {cmd}` → `{cmd_str}`")

    return "\n".join(results) if results else None


def _parse_makefile(repo_root: Path) -> str | None:
    makefile = repo_root / "Makefile"
    if not makefile.exists():
        return None

    text = makefile.read_text(encoding="utf-8")
    # phony ターゲットを抽出（コメント付き）
    targets: list[tuple[str, str]] = []
    lines = text.splitlines()
    prev_comment = ""
    for line in lines:
        comment_match = re.match(r"^##\s*(.+)", line)
        if comment_match:
            prev_comment = comment_match.group(1).strip()
            continue
        target_match = re.match(r"^([a-zA-Z0-9_-]+):\s*(?:[^=]|$)", line)
        if target_match:
            target_name = target_match.group(1)
            if target_name not in {"all", ".PHONY", "Makefile"}:
                targets.append((target_name, prev_comment))
            prev_comment = ""
        else:
            prev_comment = ""

    if not targets:
        return None

    results = ["**`Makefile` targets:**", "", "| ターゲット | 説明 |", "|-----------|------|"]
    for target_name, desc in targets[:20]:  # 最大20件
        results.append(f"| `make {target_name}` | {desc or '-'} |")
    return "\n".join(results)


def get_scripts(repo_root: Path) -> str | None:
    """package.json / pyproject.toml / Makefile からスクリプト一覧を生成"""
    sections: list[str] = []

    npm = _parse_package_json(repo_root)
    if npm:
        sections.append(npm)

    py = _parse_pyproject_toml(repo_root)
    if py:
        sections.append(py)

    mk = _parse_makefile(repo_root)
    if mk:
        sections.append(mk)

    return "\n\n".join(sections) if sections else None


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------

def get_badges(repo_root: Path, repo_slug: str | None = None) -> str:
    """CIバッジ等を生成（GITHUB_REPOSITORY 環境変数またはリモートURLから取得）"""
    slug = repo_slug or os.environ.get("GITHUB_REPOSITORY", "")

    if not slug:
        # git remote から推定
        remote = _run(["git", "remote", "get-url", "origin"], cwd=repo_root)
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
        if m:
            slug = m.group(1)

    if not slug:
        return "_バッジ生成にはGITHUB_REPOSITORY環境変数が必要です_"

    badges: list[str] = []

    # CI バッジ（ci.yml または任意のworkflow）
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.exists():
        workflow_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
        for wf in sorted(workflow_files):
            if wf.stem in {"update-readme", "readme"}:
                continue  # README更新WF自体はスキップ
            badge = (
                f"[![{wf.stem}](https://github.com/{slug}/actions/workflows/{wf.name}/badge.svg)]"
                f"(https://github.com/{slug}/actions/workflows/{wf.name})"
            )
            badges.append(badge)

    # ライセンスバッジ
    license_file = repo_root / "LICENSE"
    if license_file.exists():
        text = license_file.read_text(encoding="utf-8", errors="ignore")[:200]
        if "MIT" in text:
            badges.append(
                f"[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]"
                f"(https://github.com/{slug}/blob/main/LICENSE)"
            )
        elif "Apache" in text:
            badges.append(
                f"[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)]"
                f"(https://github.com/{slug}/blob/main/LICENSE)"
            )

    # 最新リリースバッジ
    badges.append(
        f"[![Release](https://img.shields.io/github/v/release/{slug}?include_prereleases)]"
        f"(https://github.com/{slug}/releases)"
    )

    if not badges:
        return "_バッジ対象のワークフロー / ライセンスが見つかりませんでした_"

    return "  ".join(badges)


# ---------------------------------------------------------------------------
# Core replacement logic
# ---------------------------------------------------------------------------

def build_replacement(key: str, repo_root: Path) -> str | None:
    """
    各マーカーキーに対応する新しい本文を返す。
    None を返すとそのマーカーはスキップ（変更しない）。
    """
    if key == "LAST_UPDATED":
        return get_last_updated(repo_root)

    elif key == "STRUCTURE":
        return get_structure(repo_root)

    elif key == "SCRIPTS":
        return get_scripts(repo_root)

    elif key == "BADGES":
        return get_badges(repo_root)

    return None


def process_readme(
    readme_path: Path,
    repo_root: Path,
    dry_run: bool = False,
) -> tuple[bool, list[str]]:
    """
    README を処理して更新する。
    戻り値: (変更があったか, [更新したセクション名リスト])
    """
    original = readme_path.read_text(encoding="utf-8")
    updated = original
    changed_sections: list[str] = []
    skipped_sections: list[str] = []
    failed_sections: list[str] = []

    def replace_match(m: re.Match) -> str:  # type: ignore[type-arg]
        key = m.group("key")
        old_body = m.group("body")
        start_tag = m.group(1)
        end_tag = m.group(4)

        try:
            new_content = build_replacement(key, repo_root)
        except Exception as exc:  # noqa: BLE001
            failed_sections.append(f"{key} (error: {exc})")
            return m.group(0)  # 変更しない

        if new_content is None:
            skipped_sections.append(key)
            return m.group(0)

        new_body = f"\n{new_content}\n"
        if old_body == new_body:
            skipped_sections.append(f"{key} (no change)")
            return m.group(0)

        changed_sections.append(key)
        return f"{start_tag}{new_body}{end_tag}"

    updated = MARKER_RE.sub(replace_match, updated)
    has_changes = updated != original

    if dry_run:
        print("[dry-run] 変更があるセクション:", changed_sections or "(なし)")
        print("[dry-run] 変更なしセクション:", skipped_sections or "(なし)")
        if failed_sections:
            print("[dry-run] 失敗セクション:", failed_sections)
        if has_changes:
            print("\n--- 差分プレビュー (最初の5行) ---")
            orig_lines = original.splitlines()
            new_lines = updated.splitlines()
            diff_count = 0
            for i, (ol, nl) in enumerate(zip(orig_lines, new_lines)):
                if ol != nl:
                    print(f"  L{i+1} - {ol[:80]!r}")
                    print(f"  L{i+1} + {nl[:80]!r}")
                    diff_count += 1
                    if diff_count >= 5:
                        print("  ... (以下省略)")
                        break
    else:
        if has_changes:
            readme_path.write_text(updated, encoding="utf-8")
            print(f"[update_readme] 更新完了: {readme_path}")
            print(f"  更新セクション: {changed_sections}")
        else:
            print("[update_readme] 変更なし（冪等）")
        if failed_sections:
            print(f"  [WARN] 失敗セクション: {failed_sections}", file=sys.stderr)

    return has_changes, changed_sections


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="README自動更新スクリプト")
    parser.add_argument(
        "--readme",
        default="README.md",
        help="READMEファイルパス（デフォルト: README.md）",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="リポジトリルートディレクトリ（デフォルト: カレント）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="差分のみ表示してファイルを書き換えない",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    readme_path = (repo_root / args.readme).resolve()

    if not readme_path.exists():
        print(f"[ERROR] README が見つかりません: {readme_path}", file=sys.stderr)
        return 1

    has_changes, sections = process_readme(readme_path, repo_root, dry_run=args.dry_run)

    # GitHub Actions の出力変数に書き出す
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"readme_changed={'true' if has_changes else 'false'}\n")
            f.write(f"changed_sections={','.join(sections)}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
