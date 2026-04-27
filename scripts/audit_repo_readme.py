#!/usr/bin/env python3
"""
audit_repo_readme.py - torihada-biz org README 欠如検知 & 自動生成スクリプト

機能:
  - torihada-biz 配下の全リポを取得し、README.md が存在しないリポを特定する
  - コードを shallow clone してコード解析（言語/依存/エントリポイント/LICENSE）
  - テンプレ README を生成し、新規ブランチ (bot/auto-readme-YYYY-MM-DD) にコミット
  - PR を作成する（同名ブランチが既にある場合はスキップ）
  - --dry-run モードではクローン・解析のみ行い、PR は作成しない

使用例:
  python scripts/audit_repo_readme.py --dry-run
  python scripts/audit_repo_readme.py

Requirements: Python 3.11+ 標準ライブラリのみ / gh CLI / git
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

# scripts/ を sys.path に追加
_SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPT_DIR))

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_ORG = "torihada-biz"
REPO_LIMIT = 200
BRANCH_PREFIX = "bot/auto-readme"
PR_TITLE = "docs: auto-generate README from code analysis"

EXCLUDE_FILE = Path(__file__).parent.parent / "audit-exclude.txt"

# 拡張子 → 言語名マッピング
_EXT_LANG_MAP: dict[str, str] = {
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".py": "Python",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".sh": "Shell",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".md": "Markdown",
    ".sql": "SQL",
    ".tf": "Terraform",
    ".dockerfile": "Dockerfile",
}

# 除外ディレクトリ（解析時）
_EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".next", "dist", "build",
    ".turbo", "coverage", "vendor", ".terraform",
}


# ---------------------------------------------------------------------------
# gh CLI ラッパー
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=cwd)


def _run_gh(args: list[str], check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    return _run(["gh"] + args, check=check, cwd=cwd)


def fetch_repos(org: str) -> list[dict]:
    result = _run_gh([
        "repo", "list", org,
        "--limit", str(REPO_LIMIT),
        "--json", "name,isArchived,isFork,isTemplate,description,url,defaultBranchRef",
    ])
    return json.loads(result.stdout)


def load_exclude_list() -> set[str]:
    if not EXCLUDE_FILE.exists():
        return set()
    lines = EXCLUDE_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def has_readme(org: str, repo_name: str) -> bool:
    """gh api でリポに README.md が存在するかチェックする。"""
    result = _run_gh([
        "api", f"repos/{org}/{repo_name}/contents/README.md",
        "--silent",
    ], check=False)
    return result.returncode == 0


def branch_exists_remote(org: str, repo_name: str, branch: str) -> bool:
    """リモートに同名ブランチが既にあるか確認する。"""
    result = _run_gh([
        "api", f"repos/{org}/{repo_name}/branches/{branch}",
        "--silent",
    ], check=False)
    return result.returncode == 0


def pr_exists(org: str, repo_name: str, branch: str) -> bool:
    """同名ブランチのオープン PR が既にあるか確認する。"""
    result = _run_gh([
        "pr", "list",
        "--repo", f"{org}/{repo_name}",
        "--head", branch,
        "--state", "open",
        "--json", "number",
    ], check=False)
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout or "[]")
    return len(data) > 0


# ---------------------------------------------------------------------------
# コード解析
# ---------------------------------------------------------------------------

class RepoAnalysis:
    """shallow clone したリポのコード解析結果。"""

    def __init__(self, repo_path: Path, repo_name: str, description: str):
        self.repo_path = repo_path
        self.repo_name = repo_name
        self.description = description
        self.languages: list[str] = []
        self.dep_files: list[str] = []
        self.entry_points: list[str] = []
        self.license_name: str = "TBD"
        self.setup_hint: str = ""
        self.scripts: dict[str, str] = {}
        self._analyze()

    def _collect_files(self) -> list[Path]:
        """除外ディレクトリを除いた全ファイルリストを返す。"""
        result = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
            for f in files:
                result.append(Path(root) / f)
        return result

    def _analyze(self) -> None:
        all_files = self._collect_files()

        # --- 言語検出（拡張子集計） ---
        ext_counter: Counter[str] = Counter()
        for fp in all_files:
            ext = fp.suffix.lower()
            if ext in _EXT_LANG_MAP:
                ext_counter[ext] += 1

        # Dockerfile は特殊（拡張子なし）
        for fp in all_files:
            if fp.name in ("Dockerfile", "dockerfile"):
                ext_counter[".dockerfile"] += 1

        # 上位5言語（Markdown/YAML/Shell除いた実装言語優先）
        impl_exts = [e for e in ext_counter if e not in (".md", ".yml", ".yaml", ".sh")]
        if impl_exts:
            top = sorted(impl_exts, key=lambda e: ext_counter[e], reverse=True)[:5]
        else:
            top = sorted(ext_counter.keys(), key=lambda e: ext_counter[e], reverse=True)[:3]
        self.languages = [_EXT_LANG_MAP[e] for e in top]

        # --- 依存ファイル検出 ---
        dep_candidates = [
            "package.json", "pyproject.toml", "requirements.txt",
            "Cargo.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle",
            "composer.json", "Pipfile",
        ]
        for dc in dep_candidates:
            if (self.repo_path / dc).exists():
                self.dep_files.append(dc)

        # --- エントリポイント検出 ---
        entry_candidates = [
            "main.py", "app.py", "index.js", "index.ts", "main.ts",
            "src/main.rs", "main.go", "src/index.ts", "src/index.js",
            "src/app.ts", "src/main.ts", "cmd/main.go",
        ]
        for ec in entry_candidates:
            if (self.repo_path / ec).exists():
                self.entry_points.append(ec)

        # --- LICENSE 検出 ---
        for lf in ("LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE"):
            lp = self.repo_path / lf
            if lp.exists():
                content = lp.read_text(encoding="utf-8", errors="ignore")[:500]
                if "MIT" in content:
                    self.license_name = "MIT License"
                elif "Apache" in content:
                    self.license_name = "Apache License 2.0"
                elif "GPL" in content:
                    self.license_name = "GPL"
                elif "BSD" in content:
                    self.license_name = "BSD License"
                else:
                    self.license_name = lf
                break

        # --- セットアップヒント ---
        self.setup_hint = self._build_setup_hint()

        # --- npm scripts ---
        pkg_json = self.repo_path / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                self.scripts = pkg.get("scripts", {})
            except json.JSONDecodeError:
                pass

    def _build_setup_hint(self) -> str:
        hints = []
        if "package.json" in self.dep_files:
            hints.append("```bash\nnpm install\n```")
        if "pyproject.toml" in self.dep_files or "requirements.txt" in self.dep_files:
            hints.append("```bash\npip install -r requirements.txt\n# または\npip install -e .\n```")
        if "Cargo.toml" in self.dep_files:
            hints.append("```bash\ncargo build\n```")
        if "go.mod" in self.dep_files:
            hints.append("```bash\ngo mod download\ngo build ./...\n```")
        if "Gemfile" in self.dep_files:
            hints.append("```bash\nbundle install\n```")
        if not hints:
            hints.append("<!-- セットアップ手順を追記してください -->")
        return "\n\n".join(hints)


# ---------------------------------------------------------------------------
# README テンプレート生成
# ---------------------------------------------------------------------------

def generate_readme(analysis: RepoAnalysis) -> str:
    today = date.today().isoformat()

    # 説明文
    if analysis.description:
        description_line = analysis.description
    else:
        description_line = "<!-- 説明を追記してください -->"

    # 言語スタック
    if analysis.languages:
        tech_stack = "\n".join(f"- {lang}" for lang in analysis.languages)
    else:
        tech_stack = "<!-- 言語・フレームワークを追記してください -->"

    # 依存ファイル補足
    if analysis.dep_files:
        dep_note = f"\n> 依存管理ファイル: {', '.join(f'`{d}`' for d in analysis.dep_files)}"
    else:
        dep_note = ""

    # エントリポイント
    if analysis.entry_points:
        entry_note = f"\n> エントリポイント: {', '.join(f'`{e}`' for e in analysis.entry_points)}"
    else:
        entry_note = ""

    # npm scripts
    if analysis.scripts:
        scripts_content = "\n".join(
            f"- `npm run {k}` — {v}" for k, v in list(analysis.scripts.items())[:10]
        )
    else:
        scripts_content = "<!-- 主要コマンドを追記してください -->"

    readme = f"""# {analysis.repo_name}

> {description_line}

<!-- AUTO:BADGES:START -->
<!-- AUTO:BADGES:END -->

## 技術スタック

{tech_stack}{dep_note}{entry_note}

## ディレクトリ構成

<!-- AUTO:STRUCTURE:START -->
<!-- AUTO:STRUCTURE:END -->

## セットアップ

{analysis.setup_hint}

## 主要コマンド

<!-- AUTO:SCRIPTS:START -->
{scripts_content}
<!-- AUTO:SCRIPTS:END -->

## ライセンス

{analysis.license_name}

---
<!-- AUTO:LAST_UPDATED:START -->
最終更新: {today} （自動生成）
<!-- AUTO:LAST_UPDATED:END -->
"""
    return readme


# ---------------------------------------------------------------------------
# PR 作成フロー
# ---------------------------------------------------------------------------

def _build_pr_body(analysis: RepoAnalysis, branch: str) -> str:
    today = date.today().isoformat()
    lang_list = ", ".join(analysis.languages) if analysis.languages else "不明"
    dep_list = ", ".join(f"`{d}`" for d in analysis.dep_files) if analysis.dep_files else "なし"
    entry_list = ", ".join(f"`{e}`" for e in analysis.entry_points) if analysis.entry_points else "なし"

    return f"""## 概要

このリポジトリには README.md が存在しなかったため、コード解析に基づいてテンプレートを自動生成しました。

## コード解析サマリー

| 項目 | 検出結果 |
| ---- | -------- |
| 主要言語 | {lang_list} |
| 依存管理ファイル | {dep_list} |
| エントリポイント | {entry_list} |
| LICENSE | {analysis.license_name} |

## 含まれる AUTO マーカー

生成された README には以下の AUTO マーカーが含まれています。
[torihada-biz/.github/actions/update-readme](https://github.com/torihada-biz/.github/tree/main/actions/update-readme) Action と連動し、
プッシュ・PR 時に自動更新されます。

- `AUTO:BADGES` — バッジ
- `AUTO:STRUCTURE` — ディレクトリ構成
- `AUTO:SCRIPTS` — 主要コマンド
- `AUTO:LAST_UPDATED` — 最終更新日

## 対応方法

1. このPRをレビューして、不足・誤りを手修正してください
2. 問題なければ `{branch}` → `main` へマージしてください
3. マージ後、AUTO マーカーは次回プッシュ時に自動更新されます

---
> このPRは [daily-audit.yml](https://github.com/torihada-biz/.github/blob/main/.github/workflows/daily-audit.yml) により {today} に自動生成されました。
"""


def process_repo(org: str, repo: dict, dry_run: bool, tmp_base: Path) -> dict:
    """
    1リポジトリの README 生成〜PR 作成を実行する。

    Returns:
        {"name": str, "status": "skipped"|"pr_created"|"dry_run"|"error", "detail": str}
    """
    repo_name = repo["name"]
    description = repo.get("description") or ""
    today = date.today().isoformat()
    branch = f"{BRANCH_PREFIX}-{today}"

    # 同名ブランチ or PR が既にある場合はスキップ
    if not dry_run:
        if branch_exists_remote(org, repo_name, branch):
            return {"name": repo_name, "status": "skipped", "detail": f"ブランチ {branch} が既に存在"}
        if pr_exists(org, repo_name, branch):
            return {"name": repo_name, "status": "skipped", "detail": "同日付け PR が既に存在"}

    # shallow clone
    clone_dir = tmp_base / f"audit-{repo_name}"
    clone_url = f"https://github.com/{org}/{repo_name}.git"
    clone_result = _run(
        ["git", "clone", "--depth", "1", clone_url, str(clone_dir)],
        check=False,
    )
    if clone_result.returncode != 0:
        return {"name": repo_name, "status": "error", "detail": f"clone 失敗: {clone_result.stderr[:200]}"}

    try:
        # コード解析
        analysis = RepoAnalysis(clone_dir, repo_name, description)

        # README 生成
        readme_content = generate_readme(analysis)

        if dry_run:
            print(f"\n[dry-run] {repo_name} の README プレビュー（先頭30行）:")
            print("\n".join(readme_content.splitlines()[:30]))
            print("...")
            return {"name": repo_name, "status": "dry_run", "detail": "dry-run: PR 未作成"}

        # ブランチ作成・コミット・プッシュ
        cwd = str(clone_dir)
        _run(["git", "config", "user.name", "github-actions[bot]"], cwd=cwd)
        _run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=cwd)
        _run(["git", "checkout", "-b", branch], cwd=cwd)

        readme_path = clone_dir / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")

        _run(["git", "add", "README.md"], cwd=cwd)
        _run(["git", "commit", "-m", "docs: auto-generate README from code analysis [skip ci]"], cwd=cwd)

        # push（GH_TOKEN を使用）
        # CI 環境では GITHUB_TOKEN が設定されており、gh auth が通る前提
        push_url = f"https://x-access-token:${'{GH_TOKEN}'}@github.com/{org}/{repo_name}.git"
        # gh auth token で取得したトークンを使う
        token_result = _run(["gh", "auth", "token"], check=False)
        if token_result.returncode == 0:
            token = token_result.stdout.strip()
            push_url = f"https://x-access-token:{token}@github.com/{org}/{repo_name}.git"

        push_result = _run(["git", "push", push_url, f"HEAD:{branch}"], cwd=cwd, check=False)
        if push_result.returncode != 0:
            return {"name": repo_name, "status": "error", "detail": f"push 失敗: {push_result.stderr[:200]}"}

        # PR 作成
        pr_body = _build_pr_body(analysis, branch)
        pr_result = _run_gh([
            "pr", "create",
            "--repo", f"{org}/{repo_name}",
            "--title", PR_TITLE,
            "--body", pr_body,
            "--head", branch,
        ], check=False)
        if pr_result.returncode != 0:
            return {"name": repo_name, "status": "error", "detail": f"PR 作成失敗: {pr_result.stderr[:200]}"}

        pr_url = pr_result.stdout.strip()
        return {"name": repo_name, "status": "pr_created", "detail": pr_url}

    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="torihada-biz org README 欠如検知 & 自動生成スクリプト"
    )
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--dry-run", action="store_true",
                        help="PR を作成せずローカル表示のみ")
    args = parser.parse_args()

    org: str = args.org
    dry_run: bool = args.dry_run

    print(f"[audit-readme] 組織: {org} のリポジトリを取得中...")
    repos = fetch_repos(org)
    print(f"[audit-readme] 取得完了: {len(repos)} リポジトリ")

    exclude_names = load_exclude_list()
    if exclude_names:
        print(f"[audit-readme] 除外リポ: {', '.join(sorted(exclude_names))}")

    # フィルタリング
    target_repos = [
        r for r in repos
        if not r.get("isArchived")
        and not r.get("isFork")
        and not r.get("isTemplate")
        and r["name"] != ".github"
        and r["name"] not in exclude_names
    ]

    # README 欠如チェック
    print(f"[audit-readme] {len(target_repos)} リポジトリの README 存在確認中...")
    missing_readme_repos = []
    for repo in target_repos:
        name = repo["name"]
        if not has_readme(org, name):
            missing_readme_repos.append(repo)
            print(f"  [欠如] {name}")
        else:
            print(f"  [OK  ] {name}")

    if not missing_readme_repos:
        print("[audit-readme] README 欠如リポなし。")
        return 0

    print(f"\n[audit-readme] README 欠如: {len(missing_readme_repos)} リポジトリ")
    for r in missing_readme_repos:
        print(f"  - {r['name']}")

    # 処理実行
    results = []
    with tempfile.TemporaryDirectory(prefix="audit-readme-") as tmp_dir:
        tmp_base = Path(tmp_dir)
        for repo in missing_readme_repos:
            print(f"\n[audit-readme] 処理中: {repo['name']}...")
            result = process_repo(org, repo, dry_run, tmp_base)
            results.append(result)
            status = result["status"]
            detail = result["detail"]
            print(f"  -> {status}: {detail}")

    # サマリー
    print(f"\n{'='*60}")
    print("  実行結果サマリー")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['name']:40s} [{r['status']:12s}] {r['detail']}")
    print(f"{'='*60}\n")

    errors = [r for r in results if r["status"] == "error"]
    if errors:
        print(f"[audit-readme] エラーあり: {len(errors)} 件")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
