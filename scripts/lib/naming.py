#!/usr/bin/env python3
"""
lib/naming.py - torihada-biz リポジトリ命名規則チェックライブラリ

CLAUDE.md の命名規則と同期して管理する。
変更時は CLAUDE.md 側も合わせること。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 定数 (CLAUDE.md と同期)
# ---------------------------------------------------------------------------

VALID_TYPES: set[str] = {
    "lp",        # ランディングページ
    "web",       # Webアプリ（管理画面・ダッシュボード等）
    "api",       # APIサーバー・バックエンド
    "app",       # モバイル・デスクトップアプリ
    "tool",      # 社内ツール・ユーティリティ
    "bot",       # Bot・自動化スクリプト
    "lib",       # 共通ライブラリ・SDK
    "infra",     # インフラ・IaC・CI/CD
    "doc",       # ドキュメント・ナレッジ
    "video",     # 動画生成・映像系
    "ip",        # IPコンテンツ・キャラクター
    "mvp",       # 検証用プロトタイプ
    "practice",  # 練習・学習用
}

VALID_TEAMS: set[str] = {
    "biz",   # ビジネス・事業部門
    "dev",   # 開発・エンジニアリング
    "ops",   # 社内運用・バックオフィス
    "corp",  # コーポレート・全社共通
}

# リポ名として除外する特殊リポ (system / meta)
EXCLUDE_REPOS: set[str] = {".github"}

# ---------------------------------------------------------------------------
# 確定リネーム推奨マッピング（手動レビュー済み・確実な提案）
# ここに載っているリポは --apply モードで自動リネームされる
# ---------------------------------------------------------------------------

KNOWN_RENAMES: dict[str, str] = {
    "fanme-idol-game":   "ip-fanme-idol-biz",     # fanme内のIPコンテンツ（アイドルゲーム）
    "fanme-bingo-bonus": "ip-fanme-bingo-biz",    # fanme内のIPコンテンツ（ビンゴ）
    "pppstudio-lp":      "lp-pppstudio-biz",      # PPPスタジオのランディングページ
    "goal-tracker":      "tool-goal-tracker-biz", # 目標管理ツール
}

# kebab-case: 小文字英数字とハイフンのみ
_KEBAB_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# ---------------------------------------------------------------------------
# 種別推測ロジック（キーワードマッピング）
# ---------------------------------------------------------------------------

_TYPE_KEYWORD_MAP: list[tuple[str, set[str]]] = [
    ("lp",       {"lp", "landing", "landing-page"}),
    ("web",      {"web", "admin", "dashboard", "ui", "frontend", "portal", "app", "manager"}),
    ("api",      {"api", "backend", "server", "service", "graphql", "grpc", "rest"}),
    ("app",      {"mobile", "ios", "android", "desktop", "native"}),
    ("tool",     {"tool", "tools", "cli", "utility", "utils", "helper", "generator", "uploader", "converter"}),
    ("bot",      {"bot", "slack", "discord", "automation", "auto", "scheduler", "cron"}),
    ("lib",      {"lib", "library", "sdk", "common", "shared", "core", "base"}),
    ("infra",    {"infra", "terraform", "k8s", "kubernetes", "docker", "ci", "cd", "deploy", "gcp", "aws", "azure"}),
    ("doc",      {"doc", "docs", "document", "wiki", "knowledge", "guide", "handbook", "claude", "skills"}),
    ("video",    {"video", "clip", "movie", "reel", "short", "tiktok-video", "youtube"}),
    ("ip",       {"ip", "character", "mascot", "brand", "story", "manga", "anime"}),
    ("mvp",      {"mvp", "prototype", "poc", "demo", "sandbox", "experiment"}),
    ("practice", {"practice", "training", "learn", "learning", "study", "playground", "kata"}),
]

# チーム推測ロジック
_TEAM_KEYWORD_MAP: list[tuple[str, set[str]]] = [
    ("biz",  {"biz", "business", "tolive", "tiksalon", "fanme", "sales", "marketing", "commerce"}),
    ("dev",  {"dev", "development", "engineering", "claude", "skills", "logic", "art"}),
    ("ops",  {"ops", "operation", "operations", "office", "hr", "finance", "admin", "roulette", "obsidian"}),
    ("corp", {"corp", "corporate", "company", "group", "torihada", "all", "common"}),
]


def _suggest_type(name: str) -> str | None:
    """リポ名のキーワードから種別を推測する。"""
    parts = name.lower().split("-")
    parts_set = set(parts)
    for type_val, keywords in _TYPE_KEYWORD_MAP:
        if parts_set & keywords:
            return type_val
    return None


def _suggest_team(name: str) -> str | None:
    """リポ名のキーワードからチームを推測する。"""
    parts = name.lower().split("-")
    parts_set = set(parts)
    for team_val, keywords in _TEAM_KEYWORD_MAP:
        if parts_set & keywords:
            return team_val
    return None


def _has_uppercase(name: str) -> bool:
    return any(c.isupper() for c in name)


def _has_underscore(name: str) -> bool:
    return "_" in name


def _has_japanese(name: str) -> bool:
    """ひらがな・カタカナ・CJK統合漢字を検出する。"""
    return bool(re.search(r"[぀-ヿ㐀-鿿]", name))


# ---------------------------------------------------------------------------
# 検証結果データクラス
# ---------------------------------------------------------------------------

@dataclass
class NamingResult:
    name: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    confirmed_rename: Optional[str] = field(default=None)
    """KNOWN_RENAMES に存在する場合は確定リネーム先名称、なければ None。"""

    def to_markdown_row(self) -> str:
        """Issue本文用のMarkdownテーブル行を返す。"""
        errors_str = " / ".join(self.errors) if self.errors else "-"
        if self.confirmed_rename:
            suggestions_str = f"`{self.confirmed_rename}` ✅確定"
        elif self.suggestions:
            suggestions_str = ", ".join(f"`{s}`" for s in self.suggestions)
        else:
            suggestions_str = "要相談"
        return f"| `{self.name}` | {errors_str} | {suggestions_str} |"


# ---------------------------------------------------------------------------
# メイン検証関数
# ---------------------------------------------------------------------------

def validate_repo_name(name: str) -> NamingResult:
    """
    リポジトリ名を命名規則に従って検証する。

    Args:
        name: リポジトリ名（オーナー部分なし）

    Returns:
        NamingResult: 検証結果
    """
    errors: list[str] = []
    suggestions: list[str] = []

    # 除外リポは常に valid
    if name in EXCLUDE_REPOS:
        return NamingResult(name=name, is_valid=True)

    # 大文字チェック
    if _has_uppercase(name):
        errors.append("大文字混在")

    # アンダースコアチェック
    if _has_underscore(name):
        errors.append("アンダースコア使用")

    # 日本語チェック
    if _has_japanese(name):
        errors.append("日本語混在")

    # kebab-case チェック（大文字/アンダースコア/日本語を除去した後でも確認）
    normalized = name.lower().replace("_", "-")
    if not _KEBAB_PATTERN.match(normalized):
        errors.append("kebab-case 違反（使用可能: 小文字英数字とハイフンのみ）")

    # 3パート構成チェック
    parts = name.lower().split("-")
    if len(parts) < 3:
        errors.append("3パート構成違反（{種別}-{プロジェクト名}-{チーム} が必要）")
        # 3パート未満なら種別/チームチェックをスキップして提案を生成
        sugg_type = _suggest_type(name) or "???"
        sugg_team = _suggest_team(name) or "???"
        project_part = "-".join(parts[:]) if parts else name
        suggestions.append(f"{sugg_type}-{project_part}-{sugg_team}（要確認）")
        confirmed_rename = KNOWN_RENAMES.get(name)
        return NamingResult(
            name=name,
            is_valid=False,
            errors=errors,
            suggestions=suggestions,
            confirmed_rename=confirmed_rename,
        )

    # 種別チェック
    prefix = parts[0]
    suffix = parts[-1]
    project_middle = "-".join(parts[1:-1])

    if prefix not in VALID_TYPES:
        errors.append(f"無効な種別 `{prefix}`（有効: {', '.join(sorted(VALID_TYPES))}）")
        # 種別を推測して提案
        sugg_type = _suggest_type(name)
        if sugg_type:
            suggestions.append(f"`{sugg_type}` を種別として使用: `{sugg_type}-{project_middle}-{suffix}`")
        else:
            suggestions.append("種別の選定が必要: 要相談")

    # チームチェック
    if suffix not in VALID_TEAMS:
        errors.append(f"無効なチーム `{suffix}`（有効: {', '.join(sorted(VALID_TEAMS))}）")
        sugg_team = _suggest_team(name)
        if sugg_team:
            suggestions.append(f"`{sugg_team}` をチームとして使用: `{prefix}-{project_middle}-{sugg_team}`")
        else:
            suggestions.append("チームの選定が必要: 要相談")

    is_valid = len(errors) == 0
    confirmed_rename = KNOWN_RENAMES.get(name)
    return NamingResult(
        name=name,
        is_valid=is_valid,
        errors=errors,
        suggestions=suggestions,
        confirmed_rename=confirmed_rename,
    )


# ---------------------------------------------------------------------------
# バッチ検証
# ---------------------------------------------------------------------------

def validate_repos(
    repos: list[dict],
    exclude_names: set[str] | None = None,
) -> list[NamingResult]:
    """
    リポジトリ一覧を一括検証する。

    Args:
        repos: gh repo list の JSON レスポンスリスト
               各要素: {"name": str, "isArchived": bool, "isFork": bool, "isTemplate": bool}
        exclude_names: 除外するリポジトリ名のセット（audit-exclude.txt から読み込む）

    Returns:
        violations: 違反しているリポのみの NamingResult リスト
    """
    if exclude_names is None:
        exclude_names = set()

    violations: list[NamingResult] = []
    for repo in repos:
        name = repo.get("name", "")
        # 除外対象をスキップ
        if name in EXCLUDE_REPOS:
            continue
        if repo.get("isArchived", False):
            continue
        if repo.get("isFork", False):
            continue
        if repo.get("isTemplate", False):
            continue
        if name in exclude_names:
            continue

        result = validate_repo_name(name)
        if not result.is_valid:
            violations.append(result)

    return violations
