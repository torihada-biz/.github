# torihada-biz 共通ルール

このファイルはtorihada-biz org内の全リポジトリでClaude Codeが自動的に読み込むルールです。

---

## リポジトリ命名規則

### フォーマット（必須）

```
{種別}-{プロジェクト名}-{チーム}
```

**例**: `lp-tolive-biz`, `api-tiklytics-biz`, `tool-csv-uploader-ops`

### 種別（prefix）

| 種別 | 用途 |
|------|------|
| `lp` | ランディングページ |
| `web` | Webアプリ（管理画面・ダッシュボード等） |
| `api` | APIサーバー・バックエンド |
| `app` | モバイル・デスクトップアプリ |
| `tool` | 社内ツール・ユーティリティ |
| `bot` | Bot・自動化スクリプト |
| `lib` | 共通ライブラリ・SDK |
| `infra` | インフラ・IaC・CI/CD |
| `doc` | ドキュメント・ナレッジ |
| `video` | 動画生成・映像系 |
| `ip` | IPコンテンツ・キャラクター |
| `mvp` | 検証用プロトタイプ |
| `practice` | 練習・学習用 |

### チーム（suffix）

| チーム | 対象 |
|--------|------|
| `biz` | ビジネス・事業部門 |
| `dev` | 開発・エンジニアリング |
| `ops` | 社内運用・バックオフィス |
| `corp` | コーポレート・全社共通 |

### ルール

- **小文字ケバブケース**（`kebab-case`）のみ使用する
- **スペース禁止** — 単語区切りはハイフン `-`
- **3パート構成** — `{種別}-{プロジェクト名}-{チーム}` を必ず守る
- **英語のみ** — 日本語・ローマ字は不可
- 同一プロダクトの複数リポは **プロジェクト名を統一** する

### 新規リポ作成時

新しいリポジトリを作成する際は、必ず上記の命名規則に従うこと。
命名に迷った場合は `/repo-naming` スキル（claude-skillsリポに格納）を使用してチェックする。

詳細な命名規則ドキュメント: [doc-claude-skills-dev/repo-naming/github-naming-convention.md](https://github.com/torihada-biz/doc-claude-skills-dev/blob/main/repo-naming/github-naming-convention.md)
