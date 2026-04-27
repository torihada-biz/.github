#!/usr/bin/env bash
# apply-update-readme.sh
#
# torihada-biz org の全リポジトリに update-readme wrapper ワークフローを一括配信する。
# gh CLI が認証済みであること（gh auth login）が前提。
#
# 使用方法:
#   bash apply-update-readme.sh             # 実際に配信
#   bash apply-update-readme.sh --dry-run   # dry-run（変更せずに対象リポジトリを確認）

set -euo pipefail

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
ORG="torihada-biz"
WORKFLOW_PATH=".github/workflows/update-readme.yml"
# このスクリプトと同じディレクトリにある workflow-templates を参照
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../workflow-templates/update-readme.yml"
COMMIT_MESSAGE="ci: add update-readme wrapper workflow"
BRANCH="add-update-readme-workflow"

# ---------------------------------------------------------------------------
# 引数解析
# ---------------------------------------------------------------------------
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "[ERROR] 不明な引数: $arg" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# 前提チェック
# ---------------------------------------------------------------------------
if ! command -v gh &>/dev/null; then
  echo "[ERROR] gh CLI がインストールされていません。https://cli.github.com/ からインストールしてください。" >&2
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "[ERROR] gh CLI が認証されていません。'gh auth login' を実行してください。" >&2
  exit 1
fi

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "[ERROR] テンプレートファイルが見つかりません: ${TEMPLATE_FILE}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# wrapper ワークフローの内容を読み込む
# ---------------------------------------------------------------------------
WORKFLOW_CONTENT=$(cat "${TEMPLATE_FILE}")

# ---------------------------------------------------------------------------
# リポジトリ一覧を取得（アーカイブ済みを除外）
# ---------------------------------------------------------------------------
echo "[INFO] ${ORG} のリポジトリ一覧を取得中..."
REPOS=$(gh repo list "${ORG}" --limit 100 --json name,isArchived \
  | python3 -c "
import json, sys
repos = json.load(sys.stdin)
active = [r['name'] for r in repos if not r['isArchived']]
print('\n'.join(active))
")

TOTAL=$(echo "${REPOS}" | wc -l | tr -d ' ')
echo "[INFO] アクティブなリポジトリ数: ${TOTAL}"

if [[ "${DRY_RUN}" == "true" ]]; then
  echo ""
  echo "=== [DRY-RUN] 配信対象リポジトリ一覧 ==="
  echo "${REPOS}"
  echo ""
  echo "[DRY-RUN] 上記 ${TOTAL} リポジトリに '${WORKFLOW_PATH}' を配信する予定です。"
  echo "[DRY-RUN] 実際に配信するには --dry-run を外して再実行してください。"
  echo ""
  echo "[NOTE] .github リポジトリは wrapper 不要のためスキップされます。"
  exit 0
fi

# ---------------------------------------------------------------------------
# 各リポジトリに wrapper を配信
# ---------------------------------------------------------------------------
SUCCESS=0
SKIP=0
FAIL=0

while IFS= read -r REPO_NAME; do
  # .github リポジトリ自体はスキップ（Composite Action の本体なので wrapper 不要）
  if [[ "${REPO_NAME}" == ".github" ]]; then
    echo "[SKIP] ${REPO_NAME} — Composite Action 本体のためスキップ"
    ((SKIP++)) || true
    continue
  fi

  echo -n "[INFO] ${ORG}/${REPO_NAME} に配信中... "

  # ファイルの存在確認
  EXISTING_SHA=$(gh api "repos/${ORG}/${REPO_NAME}/contents/${WORKFLOW_PATH}" \
    --jq '.sha' 2>/dev/null || echo "")

  # Base64 エンコード（macOS と Linux 両対応）
  if base64 --version 2>&1 | grep -q "GNU"; then
    CONTENT_B64=$(echo "${WORKFLOW_CONTENT}" | base64 -w 0)
  else
    CONTENT_B64=$(echo "${WORKFLOW_CONTENT}" | base64)
  fi

  # PUT でファイルを作成または更新
  if [[ -n "${EXISTING_SHA}" ]]; then
    # 既存ファイルを更新
    gh api "repos/${ORG}/${REPO_NAME}/contents/${WORKFLOW_PATH}" \
      -X PUT \
      -f message="${COMMIT_MESSAGE}" \
      -f content="${CONTENT_B64}" \
      -f sha="${EXISTING_SHA}" \
      --silent && echo "更新済み" || { echo "FAILED"; ((FAIL++)) || true; continue; }
  else
    # 新規作成
    gh api "repos/${ORG}/${REPO_NAME}/contents/${WORKFLOW_PATH}" \
      -X PUT \
      -f message="${COMMIT_MESSAGE}" \
      -f content="${CONTENT_B64}" \
      --silent && echo "作成済み" || { echo "FAILED"; ((FAIL++)) || true; continue; }
  fi

  ((SUCCESS++)) || true
done <<< "${REPOS}"

# ---------------------------------------------------------------------------
# 結果サマリー
# ---------------------------------------------------------------------------
echo ""
echo "=== 配信結果 ==="
echo "  成功: ${SUCCESS}"
echo "  スキップ: ${SKIP}"
echo "  失敗: ${FAIL}"
echo ""
if [[ "${FAIL}" -gt 0 ]]; then
  echo "[WARN] 失敗したリポジトリがあります。手動で確認してください。"
  exit 1
fi
echo "[INFO] 完了。各リポジトリの Settings > Actions > General > Workflow permissions を「Read and write」に設定してください。"
echo "       詳細手順: docs/INSTALL.md を参照"
