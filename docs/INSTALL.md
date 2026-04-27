# update-readme Composite Action 導入手順

各リポジトリに README 自動更新の仕組みを導入するための手順書です。

---

## 概要

- ロジック本体は `torihada-biz/.github` リポジトリ（このリポジトリ）の `actions/update-readme/` に集約されています
- 各リポジトリには wrapper ワークフロー 1 本（`.github/workflows/update-readme.yml`）を置くだけで動作します
- ロジックの更新は `torihada-biz/.github` への変更 1 回で全リポジトリに自動反映されます

---

## Step 1: Workflow permissions の設定（必須）

GitHub の仕様上、Composite Action 内で `git push` を行うには **Workflow permissions を「Read and write」** に設定する必要があります。

### 設定場所

対象リポジトリの以下のパスで設定してください:

```
https://github.com/torihada-biz/{リポジトリ名}/settings/actions
```

「General」セクション → 「Workflow permissions」→ **「Read and write permissions」** を選択 → 「Save」

> この設定をしないと、README の変更があっても push ステップが `403 Permission denied` で失敗します。

### 一括設定の代替手段

Organization レベルで一括設定することも可能です:

```
https://github.com/organizations/torihada-biz/settings/actions
```

ただし、org レベルで有効にすると全リポジトリに適用されるため、セキュリティポリシーを確認の上で判断してください。

---

## Step 2: wrapper ワークフローの配置

対象リポジトリに `.github/workflows/update-readme.yml` を作成します。

```yaml
name: Update README

on:
  push:
    branches: [main]
  pull_request:
    types: [opened, synchronize, reopened]

concurrency:
  group: readme-update-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.head_ref || github.ref_name }}
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: torihada-biz/.github/actions/update-readme@main
```

これだけです。スクリプトやライブラリのコピーは不要です。

---

## Step 3: README にマーカーを追加

自動更新したいセクションに以下のマーカーを挿入します。

```markdown
## 最終更新

<!-- AUTO:LAST_UPDATED:START -->
<!-- AUTO:LAST_UPDATED:END -->

## ディレクトリ構成

<!-- AUTO:STRUCTURE:START -->
<!-- AUTO:STRUCTURE:END -->

## スクリプト

<!-- AUTO:SCRIPTS:START -->
<!-- AUTO:SCRIPTS:END -->

## CI / バッジ

<!-- AUTO:BADGES:START -->
<!-- AUTO:BADGES:END -->
```

マーカーのない README には何も変更が加わらないため、既存の README に段階的に追加できます。

---

## 対応マーカー一覧

| マーカーキー | 生成内容 |
|------------|--------|
| `LAST_UPDATED` | 最終コミット日時 + 短縮 SHA |
| `STRUCTURE` | ディレクトリツリー（depth: 2）|
| `SCRIPTS` | `package.json` / `pyproject.toml` / `Makefile` のスクリプト一覧 |
| `BADGES` | CI ワークフローバッジ + ライセンスバッジ + リリースバッジ |

---

## inputs（カスタマイズ）

wrapper ワークフローで以下の inputs を渡すことで動作を調整できます。

```yaml
- uses: torihada-biz/.github/actions/update-readme@main
  with:
    python-version: '3.12'
    commit-message: 'chore: update README [skip ci]'
    readme-path: 'docs/README.md'
```

| input | デフォルト値 | 説明 |
|-------|-----------|------|
| `python-version` | `3.11` | Python バージョン |
| `commit-message` | `docs: auto-update README sections [skip ci]` | コミットメッセージ |
| `readme-path` | `README.md` | README ファイルのパス |

---

## 一括展開

`docs/apply-update-readme.sh` を使うと torihada-biz org の全リポジトリに wrapper を一括配信できます。

```bash
# dry-run（変更せずに対象リポジトリを確認）
bash docs/apply-update-readme.sh --dry-run

# 実際に配信
bash docs/apply-update-readme.sh
```

詳細は `apply-update-readme.sh` のコメントを参照してください。

---

## 動作の仕組み

```
push or PR
  └─ wrapper workflow (.github/workflows/update-readme.yml)
       └─ uses: torihada-biz/.github/actions/update-readme@main
            ├─ setup-python@v5
            ├─ update_readme.py を実行
            │    └─ README.md の AUTO マーカーを書き換え
            └─ 変更があれば git commit + git push
                  ├─ push イベント: main ブランチに直接コミット（[skip ci] 付きで無限ループ防止）
                  └─ PR イベント: PR ブランチ（head_ref）に追加コミット
```

commit author は `github-actions[bot]` です。

---

## トラブルシューティング

### `403 Permission denied` でpushが失敗する

Step 1 の Workflow permissions 設定が完了しているか確認してください。

### `Error: Resource not accessible by integration`

`permissions: contents: write` が wrapper ワークフローに記載されているか確認してください。

### README が更新されない

README に `<!-- AUTO:LAST_UPDATED:START -->` などのマーカーが存在するか確認してください。マーカーがない場合は何も更新されません（エラーにはなりません）。

### Composite Action の最新版を即時反映したい

`@main` タグを使用しているため、`torihada-biz/.github` の `main` ブランチへのマージ後、次回のワークフロー実行時に自動的に最新版が使用されます。
