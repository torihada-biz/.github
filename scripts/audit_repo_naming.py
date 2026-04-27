#!/usr/bin/env python3
"""
audit_repo_naming.py - torihada-biz org リポジトリ命名規則監査スクリプト

機能:
  - torihada-biz 配下の全リポを取得し、命名規則違反を検知する
  - 違反があれば .github リポに集約 Issue を作成（同日 Issue がある場合はコメント追記）
  - --dry-run モードではローカル表示のみ（API 書き込み不要）
  - --apply モードでは KNOWN_RENAMES に登録済みの違反リポを自動リネーム実行

使用例:
  # 実行（Issueを実際に作成）
  python scripts/audit_repo_naming.py

  # ドライラン（Issue 作成しない）
  python scripts/audit_repo_naming.py --dry-run

  # 自動リネーム実行（KNOWN_RENAMES のみ・破壊的操作）
  python scripts/audit_repo_naming.py --apply

  # --apply のドライラン（実際には rename せず実行コマンドを表示）
  python scripts/audit_repo_naming.py --apply --dry-run

  # 組織を指定
  python scripts/audit_repo_naming.py --org my-org --dry-run

Requirements: Python 3.11+ 標準ライブラリのみ / gh CLI (authenticated)
             --apply 使用時は PAT に repo スコープ（rename 権限）が必要
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# scripts/ を sys.path に追加（lib パッケージをインポートするため）
_SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.naming import validate_repos, NamingResult, KNOWN_RENAMES

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_ORG = "torihada-biz"
AUDIT_REPO = ".github"  # Issue 作成先リポジトリ
ISSUE_LABEL = "audit"
REPO_LIMIT = 200

# exclude ファイル（リポルート基準）
EXCLUDE_FILE = Path(__file__).parent.parent / "audit-exclude.txt"


# ---------------------------------------------------------------------------
# gh CLI ラッパー
# ---------------------------------------------------------------------------

def _run_gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """gh コマンドを実行して CompletedProcess を返す。"""
    cmd = ["gh"] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def fetch_repos(org: str) -> list[dict]:
    """org 配下の全リポを JSON で取得する。"""
    result = _run_gh([
        "repo", "list", org,
        "--limit", str(REPO_LIMIT),
        "--json", "name,isArchived,isFork,isTemplate,description,url",
    ])
    return json.loads(result.stdout)


def load_exclude_list() -> set[str]:
    """audit-exclude.txt を読み込んで除外リポ名セットを返す。"""
    if not EXCLUDE_FILE.exists():
        return set()
    lines = EXCLUDE_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


# ---------------------------------------------------------------------------
# Issue 管理
# ---------------------------------------------------------------------------

def _today_str() -> str:
    return date.today().isoformat()  # "YYYY-MM-DD"


def _issue_title() -> str:
    return f"[Audit {_today_str()}] Naming violations detected"


def _build_issue_body(violations: list[NamingResult], org: str) -> str:
    today = _today_str()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"## 命名規則違反レポート — {today}",
        "",
        f"- **組織**: `{org}`",
        f"- **監査日時**: {now}",
        f"- **違反リポ数**: {len(violations)}",
        "",
        "---",
        "",
        "| リポジトリ名 | 違反内容 | 推奨名称（提案） |",
        "| ------------ | -------- | --------------- |",
    ]
    for v in violations:
        lines.append(v.to_markdown_row())

    lines += [
        "",
        "---",
        "",
        "## 対応方法",
        "",
        "リポジトリのリネームは破壊的操作（URL変更、既存リンク切れ）のため **自動実行せず、手動対応** としています。",
        "",
        "対応手順:",
        "1. 上記テーブルの「推奨名称」を参考にリネームを検討する",
        "2. チームに確認後、以下コマンドでリネーム実行:",
        "   ```bash",
        f"   gh repo rename <new-name> --repo {org}/<old-name>",
        "   ```",
        "3. 関連する CI/CD・ドキュメント・リンクを更新する",
        "4. 完了後、このIssueをクローズする",
        "",
        "> このIssueは [daily-audit.yml](../.github/workflows/daily-audit.yml) により毎日 JST 19:00 に自動生成されます。",
        "> 同日内に再実行された場合はコメントで追記されます。",
    ]
    return "\n".join(lines)


def _build_comment_body(violations: list[NamingResult]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"## 再監査結果 — {now}",
        "",
        f"違反リポ数: **{len(violations)}**",
        "",
        "| リポジトリ名 | 違反内容 | 推奨名称（提案） |",
        "| ------------ | -------- | --------------- |",
    ]
    for v in violations:
        lines.append(v.to_markdown_row())
    return "\n".join(lines)


def find_today_issue(org: str, repo: str) -> str | None:
    """
    .github リポに本日付けの Audit Issue があればその番号を返す。
    なければ None。
    """
    title_prefix = f"[Audit {_today_str()}]"
    result = _run_gh([
        "issue", "list",
        "--repo", f"{org}/{repo}",
        "--state", "open",
        "--limit", "50",
        "--json", "number,title",
    ], check=False)
    if result.returncode != 0:
        return None
    issues = json.loads(result.stdout or "[]")
    for issue in issues:
        if issue["title"].startswith(title_prefix):
            return str(issue["number"])
    return None


def create_issue(org: str, repo: str, title: str, body: str) -> str:
    """Issue を作成して URL を返す。"""
    result = _run_gh([
        "issue", "create",
        "--repo", f"{org}/{repo}",
        "--title", title,
        "--body", body,
        "--label", ISSUE_LABEL,
    ], check=False)
    if result.returncode != 0:
        # label が存在しない場合はラベルなしで再試行
        result = _run_gh([
            "issue", "create",
            "--repo", f"{org}/{repo}",
            "--title", title,
            "--body", body,
        ])
    return result.stdout.strip()


def comment_on_issue(org: str, repo: str, number: str, body: str) -> None:
    """既存 Issue にコメントを追記する。"""
    _run_gh([
        "issue", "comment", number,
        "--repo", f"{org}/{repo}",
        "--body", body,
    ])


# ---------------------------------------------------------------------------
# リネーム実行
# ---------------------------------------------------------------------------

def _repo_exists(org: str, repo_name: str) -> bool:
    """指定リポジトリが org 内に存在するか確認する（冪等性チェック用）。"""
    result = _run_gh([
        "repo", "view", f"{org}/{repo_name}",
        "--json", "name",
    ], check=False)
    return result.returncode == 0


def rename_repo(org: str, old_name: str, new_name: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    リポジトリをリネームする。

    Args:
        org: GitHub organization 名
        old_name: 現在のリポジトリ名
        new_name: 新しいリポジトリ名
        dry_run: True の場合は実行コマンドを表示するだけで実際には rename しない

    Returns:
        (success: bool, message: str)
    """
    # 冪等性チェック: 既に new_name が存在する場合はスキップ
    if _repo_exists(org, new_name):
        return True, f"スキップ（既にリネーム済み: `{new_name}` が存在）"

    cmd = ["gh", "repo", "rename", new_name, "--repo", f"{org}/{old_name}", "--yes"]
    cmd_str = " ".join(cmd)

    if dry_run:
        return True, f"[DRY-RUN] 実行予定コマンド: `{cmd_str}`"

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, f"リネーム成功: `{old_name}` → `{new_name}`"
    else:
        error_detail = (result.stderr or result.stdout).strip()
        return False, f"リネーム失敗: {error_detail}"


def _write_step_summary(lines: list[str]) -> None:
    """GITHUB_STEP_SUMMARY ファイルに Markdown を追記する。CI環境外では標準出力のみ。"""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    content = "\n".join(lines) + "\n"
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(content)
    else:
        # ローカル実行時はSTDOUTに出力
        print("\n--- STEP SUMMARY (GITHUB_STEP_SUMMARY 未設定のためSTDOUTに出力) ---")
        print(content)
        print("--- STEP SUMMARY END ---\n")


def _build_summary_issue_body(
    renamed_ok: list[tuple[str, str]],
    renamed_ng: list[tuple[str, str, str]],
    org: str,
) -> str:
    """リネームサマリー Issue の本文を構築する。"""
    today = _today_str()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = len(renamed_ok) + len(renamed_ng)
    lines = [
        f"## リネーム実行サマリー — {today}",
        "",
        f"- **組織**: `{org}`",
        f"- **実行日時**: {now}",
        f"- **実行件数**: {total}（成功: {len(renamed_ok)} / 失敗: {len(renamed_ng)}）",
        "",
        "---",
        "",
    ]
    if renamed_ok:
        lines += [
            "### 成功",
            "",
            "| 旧名称 | 新名称 |",
            "| ------ | ------ |",
        ]
        for old, new in renamed_ok:
            lines.append(f"| `{old}` | `{new}` |")
        lines.append("")
    if renamed_ng:
        lines += [
            "### 失敗",
            "",
            "| 旧名称 | 試みた新名称 | エラー内容 |",
            "| ------ | ------------ | ---------- |",
        ]
        for old, new, err in renamed_ng:
            lines.append(f"| `{old}` | `{new}` | {err} |")
        lines.append("")
    lines += [
        "---",
        "",
        "> **リネーム後の対応が必要:**",
        "> - 既存 clone のリモートURLを更新: `git remote set-url origin <新URL>`",
        "> - CI/CD ワークフロー内のリポ名参照を更新",
        "> - ドキュメント・READMEのリポURLを更新",
        "> - GitHubの自動リダイレクトは **2年間** 有効（旧URLのアクセスは継続可能）",
        "",
        "> このIssueは [daily-audit.yml](../.github/workflows/daily-audit.yml) の `--apply` モードにより自動生成されました。",
    ]
    return "\n".join(lines)


def _summary_issue_title(n: int) -> str:
    return f"[Audit {_today_str()}] Renamed {n} repositories"


def run_apply_mode(
    violations: list[NamingResult],
    org: str,
    dry_run: bool,
) -> None:
    """
    --apply モードのメインロジック。
    - confirmed_rename あり → gh repo rename 実行
    - confirmed_rename なし → Issue 作成（提案のみ）
    """
    to_rename = [v for v in violations if v.confirmed_rename]
    no_rename  = [v for v in violations if not v.confirmed_rename]

    print(f"\n[apply] 確定リネーム可能: {len(to_rename)}件 / 確定不可: {len(no_rename)}件")

    renamed_ok: list[tuple[str, str]] = []
    renamed_ng: list[tuple[str, str, str]] = []
    summary_lines: list[str] = [
        f"## 命名規則 自動リネーム結果 — {_today_str()}",
        "",
        "| 結果 | 旧名称 | 新名称 | 詳細 |",
        "| ---- | ------ | ------ | ---- |",
    ]

    for v in to_rename:
        new_name = v.confirmed_rename  # type: ignore[assignment]
        success, msg = rename_repo(org, v.name, new_name, dry_run=dry_run)
        if success:
            renamed_ok.append((v.name, new_name))
            icon = "DRY" if dry_run else "✅"
            print(f"  [{icon}] {v.name} → {new_name}  {msg}")
            summary_lines.append(f"| {'DRY-RUN' if dry_run else '✅ 成功'} | `{v.name}` | `{new_name}` | {msg} |")
        else:
            renamed_ng.append((v.name, new_name, msg))
            print(f"  [❌] {v.name} → {new_name}  {msg}")
            summary_lines.append(f"| ❌ 失敗 | `{v.name}` | `{new_name}` | {msg} |")

    _write_step_summary(summary_lines)

    # 確定リネーム不可の違反は Issue 作成（提案のみ）
    if no_rename:
        print(f"\n[apply] 確定リネーム不可の違反 {len(no_rename)} 件は Issue を作成します...")
        existing_issue = find_today_issue(org, AUDIT_REPO)
        if existing_issue:
            comment_body = _build_comment_body(no_rename)
            comment_on_issue(org, AUDIT_REPO, existing_issue, comment_body)
            print(f"[apply] コメント追記完了 (Issue #{existing_issue})")
        else:
            title = _issue_title()
            body = _build_issue_body(no_rename, org)
            url = create_issue(org, AUDIT_REPO, title, body)
            print(f"[apply] Issue 作成完了: {url}")

    # リネーム成功分のサマリー Issue 作成（ドライランは除く）
    if renamed_ok and not dry_run:
        print(f"\n[apply] サマリー Issue を作成します（{len(renamed_ok)} 件リネーム完了）...")
        summary_title = _summary_issue_title(len(renamed_ok))
        summary_body = _build_summary_issue_body(renamed_ok, renamed_ng, org)
        url = create_issue(org, AUDIT_REPO, summary_title, summary_body)
        print(f"[apply] サマリー Issue 作成完了: {url}")


# ---------------------------------------------------------------------------
# 出力ヘルパー
# ---------------------------------------------------------------------------

def _print_violations(violations: list[NamingResult]) -> None:
    confirmed = [v for v in violations if v.confirmed_rename]
    unconfirmed = [v for v in violations if not v.confirmed_rename]

    print(f"\n{'='*60}")
    print(f"  命名規則違反 — {len(violations)} 件")
    print(f"  確定リネーム可能: {len(confirmed)}件 / 確定不可: {len(unconfirmed)}件")
    print(f"{'='*60}")
    for v in violations:
        print(f"\n  リポ: {v.name}")
        for e in v.errors:
            print(f"    [違反] {e}")
        if v.confirmed_rename:
            print(f"    [確定リネーム] {v.name} → {v.confirmed_rename}")
        else:
            for s in v.suggestions:
                print(f"    [提案] {s}")
    print(f"\n{'='*60}\n")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="torihada-biz リポジトリ命名規則監査スクリプト"
    )
    parser.add_argument(
        "--org", default=DEFAULT_ORG,
        help=f"対象 GitHub organization (デフォルト: {DEFAULT_ORG})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "通常モード: Issue を作成せずローカル表示のみ。"
            "--apply との組み合わせ: gh repo rename を実行せず、実行予定コマンドのみ表示"
        )
    )
    parser.add_argument(
        "--apply", action="store_true",
        help=(
            "KNOWN_RENAMES に登録済みの違反リポを gh repo rename で自動リネームする（破壊的操作）。"
            "確定リネームがない違反は通常通り Issue を作成する。"
            "--dry-run と併用すると実際のリネームを行わず実行予定コマンドのみ表示する。"
        )
    )
    args = parser.parse_args()

    org: str = args.org
    dry_run: bool = args.dry_run
    apply_mode: bool = args.apply

    print(f"[audit-naming] 組織: {org} のリポジトリを取得中...")
    repos = fetch_repos(org)
    print(f"[audit-naming] 取得完了: {len(repos)} リポジトリ")

    exclude_names = load_exclude_list()
    if exclude_names:
        print(f"[audit-naming] 除外リポ: {', '.join(sorted(exclude_names))}")

    violations = validate_repos(repos, exclude_names=exclude_names)

    if not violations:
        print("[audit-naming] 違反なし。全リポジトリが命名規則に準拠しています。")
        return 0

    _print_violations(violations)

    # --apply モード
    if apply_mode:
        if dry_run:
            print("[audit-naming] --apply --dry-run モード: rename コマンドを表示するだけです（実行しません）。")
        else:
            print("[audit-naming] --apply モード: KNOWN_RENAMES に登録済みのリポを自動リネームします。")
        run_apply_mode(violations, org, dry_run=dry_run)
        return 0

    # 通常モード
    if dry_run:
        print("[audit-naming] --dry-run モード: Issue は作成されません。")
        return 0

    # Issue 作成 or コメント追記
    existing_issue = find_today_issue(org, AUDIT_REPO)
    if existing_issue:
        print(f"[audit-naming] 本日の Issue #{existing_issue} が既に存在します。コメントを追記します。")
        comment_body = _build_comment_body(violations)
        comment_on_issue(org, AUDIT_REPO, existing_issue, comment_body)
        print(f"[audit-naming] コメント追記完了 (Issue #{existing_issue})")
    else:
        print("[audit-naming] 新規 Issue を作成します...")
        title = _issue_title()
        body = _build_issue_body(violations, org)
        url = create_issue(org, AUDIT_REPO, title, body)
        print(f"[audit-naming] Issue 作成完了: {url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
