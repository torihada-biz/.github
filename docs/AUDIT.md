# リポジトリ監査ガイド（daily-audit）

このドキュメントでは、torihada-biz org の自動監査ワークフロー (`daily-audit.yml`) の運用方法を説明します。

---

## 概要

| 項目 | 内容 |
| ---- | ---- |
| 実行タイミング | 毎日 **JST 19:00**（UTC 10:00） |
| 手動実行 | GitHub Actions の `workflow_dispatch` から可能 |
| 対象 | torihada-biz org 配下の全リポジトリ（除外設定を除く） |
| 除外対象 | `.github` リポ自体 / アーカイブ済み / fork / template |

---

## 監査内容

### 1. 命名規則違反チェック（audit-naming job）

torihada-biz の命名規則（`{種別}-{プロジェクト名}-{チーム}`）に違反するリポジトリを検知します。

**違反検知時の動作:**

- `.github` リポに Issue を作成（タイトル: `[Audit YYYY-MM-DD] Naming violations detected`）
- 同日に既に Issue があればコメントを追記（重複防止）
- **リポジトリの自動リネームは行いません**（破壊的操作のため）

### 2. README 欠如チェック（audit-readme job）

README.md が存在しないリポジトリを検知し、コード解析に基づいてテンプレート README を自動生成します。

**処理フロー:**

1. `gh api repos/{org}/{repo}/contents/README.md` で存在確認
2. README なしのリポを shallow clone（`/tmp` 配下）
3. 言語・依存ファイル・エントリポイント・LICENSE を解析
4. テンプレート README 生成（AUTO マーカー4種を含む）
5. ブランチ `bot/auto-readme-YYYY-MM-DD` にコミット・プッシュ
6. PR 作成（タイトル: `docs: auto-generate README from code analysis`）
7. 同名ブランチが既に存在する場合はスキップ

---

## 必須設定: org シークレット登録

ワークフローは `ORG_AUDIT_TOKEN`（PAT）を使用します。

### 必要スコープ

| スコープ | 理由 |
| -------- | ---- |
| `repo` (full) | 全リポの読み取り・ブランチ作成・PR 作成 |
| `workflow` | ワークフローファイルの操作（任意） |

### 登録手順

1. [https://github.com/settings/tokens/new](https://github.com/settings/tokens/new) で PAT を発行
   - **Token name**: `torihada-biz-audit`
   - **Expiration**: 90日（定期的に更新推奨）
   - **Scopes**: `repo`（full）にチェック
2. 発行されたトークンをコピー
3. 以下の URL から org シークレットに登録:
   **https://github.com/organizations/torihada-biz/settings/secrets/actions**
   - Name: `ORG_AUDIT_TOKEN`
   - Value: コピーしたトークン

---

## 手動実行

GitHub Actions の UI から手動実行できます。

```
GitHub → torihada-biz/.github → Actions → Daily Repository Audit → Run workflow
```

### 入力パラメータ

| パラメータ | 型 | デフォルト | 説明 |
| ---------- | -- | ---------- | ---- |
| `dry_run` | choice | `false` | `true` にすると Issue/PR を作成せずログのみ出力（確認用） |
| `apply_rename` | boolean | `false` | `true` にすると KNOWN_RENAMES 登録済みの違反リポを自動リネーム（破壊的） |
| `apply_readme` | boolean | `false` | `true` にすると README 欠如リポへの PR 作成を実行 |

> **重要**: cron（毎日自動実行）では `apply_rename` / `apply_readme` は常に `false`。  
> **手動実行時のみ** `true` に設定できます。

### 自動リネームの実行手順（workflow_dispatch）

1. `torihada-biz/.github` リポジトリを開く
2. 上部メニューの **Actions** タブをクリック
3. 左サイドバーの **Daily Repository Audit** をクリック
4. 右上の **Run workflow** ボタンをクリック
5. ドロップダウンで以下を設定:
   - `apply_rename` → **チェックを入れる**（true）
   - `apply_readme` → 必要に応じてチェック
6. **Run workflow** ボタンをクリックして実行

実行後、ジョブの Step Summary に以下の形式で結果が出力されます:
- 成功: `✅ {旧名称} → {新名称}`
- 失敗: `❌ {旧名称} → {新名称}` + エラー内容

リネーム完了後、`.github` リポに自動でサマリー Issue が作成されます:  
タイトル形式: `[Audit YYYY-MM-DD] Renamed N repositories`

---

## 命名違反 Issue への対応

Issue に記載された推奨名称を参考に、以下の手順でリネームしてください。

### 自動リネーム（KNOWN_RENAMES 登録済みリポ）

`KNOWN_RENAMES` に登録されているリポジトリは `--apply` モードで自動リネームできます（上記 workflow_dispatch 手順を参照）。

### 手動リネーム

```bash
# リポジトリをリネーム
gh repo rename <新しい名前> --repo torihada-biz/<古い名前>

# 例: pppstudio-lp → lp-pppstudio-biz
gh repo rename lp-pppstudio-biz --repo torihada-biz/pppstudio-lp
```

**リネーム後に必ず行うこと:**

- [ ] 関連する CI/CD ワークフロー内のリポ参照を更新
- [ ] ドキュメント・READMEのリポURLを更新
- [ ] 他リポからの `uses:` 参照を更新
- [ ] Issue をクローズ

### リネーム後の副作用と注意事項

#### GitHubの自動リダイレクト（2年間）

GitHub はリポジトリリネーム後 **2年間** 旧 URL を新 URL へ自動リダイレクトします。

- `https://github.com/torihada-biz/pppstudio-lp` → `https://github.com/torihada-biz/lp-pppstudio-biz` へ自動転送
- クローン済みリポのリモートURLは自動で更新 **されません**（手動更新が必要）
- 2年後に旧URLが無効化されるため、その前に参照を更新してください

#### 既存クローンの更新

```bash
# リネーム後、既存クローンのリモートURLを更新する
git remote set-url origin https://github.com/torihada-biz/<新名称>.git

# 確認
git remote -v
```

#### CI/CD 設定の影響

以下の設定にリポ名が含まれている場合は更新が必要です:

- `.github/workflows/*.yml` 内の `uses:` 参照
  ```yaml
  # 変更前
  uses: torihada-biz/pppstudio-lp/.github/actions/deploy@main
  # 変更後
  uses: torihada-biz/lp-pppstudio-biz/.github/actions/deploy@main
  ```
- `package.json` / `pyproject.toml` などのリポURL参照
- Terraform や Pulumi のインフラコード内のリポ名
- Slack / 外部サービスの Webhook URL（リポ名を含む場合）

#### --apply の PAT 権限要件

`--apply` モードは `gh repo rename` を使用するため、PAT（`ORG_AUDIT_TOKEN`）に **`repo` スコープ（full）** が必要です。

| スコープ | 理由 |
| -------- | ---- |
| `repo` (full) | リポジトリのリネーム権限を含む |

> 既存の `ORG_AUDIT_TOKEN` が `repo` スコープ付きで発行されていれば、追加設定は不要です。

---

## README 自動生成 PR への対応

1. PR の内容をレビューして誤りや不足を手修正する
2. 問題なければ `bot/auto-readme-YYYY-MM-DD` → `main` へマージ
3. マージ後、AUTO マーカーは次回のコード変更時に [update-readme Action](../actions/update-readme/) により自動更新される

### AUTO マーカーの種類

| マーカー | 内容 |
| -------- | ---- |
| `AUTO:BADGES` | GitHub バッジ（CI/CD ステータス等） |
| `AUTO:STRUCTURE` | ディレクトリ構成 |
| `AUTO:SCRIPTS` | npm scripts / Makefile ターゲット等 |
| `AUTO:LAST_UPDATED` | 最終更新日時 |

---

## 除外設定

監査から除外したいリポジトリは `audit-exclude.txt` に記載してください。

```
# audit-exclude.txt
legacy-project        # 命名規則違反を意図的に許容
doc-old-archive-corp  # README 自動生成不要
```

1行1リポジトリ名。`#` で始まる行はコメントとして無視されます。

---

## トラブルシューティング

### ワークフローが失敗する

- `ORG_AUDIT_TOKEN` が登録されているか確認
- PAT の有効期限が切れていないか確認（90日更新推奨）
- `repo` スコープが付与されているか確認

### Issue が重複して作成される

- 同日の Issue は自動的にコメント追記になるため重複しません
- 別日の Issue は新規作成されます（過去の Issue は自動クローズしません）

### README 生成 PR のブランチ名

ブランチ名は `bot/auto-readme-YYYY-MM-DD` です。同日に再実行してもスキップされます（翌日は別ブランチが作成されます）。

---

*このドキュメントは `daily-audit.yml` の運用ガイドです。*
*最終更新: 2026-04-27（自動リネーム機能追加）*
