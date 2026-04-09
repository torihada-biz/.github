# GitHub リポジトリ命名規則ガイド

torihada-biz のGitHubリポジトリには命名規則があります。
このガイドでは、ルールの内容と、自動で適用される仕組みを説明します。

---

## そもそもリポジトリとは？

リポジトリ（リポ）は**プロジェクトのフォルダ**のようなものです。
コード、画像、ドキュメントなど、プロジェクトに必要なファイルを全部まとめて管理する場所です。

GitHubは、このリポジトリをチームで共有できるサービスです。

---

## なぜ命名規則が必要？

リポが増えると、こういう問題が起きます：

```
❌ 名前がバラバラだった頃
ToLive-LP          ← 大文字？小文字？
hal-ossan          ← これ何のプロジェクト？
video-commerce-mvp ← どのチームの？
```

```
✅ 命名規則を入れた後
lp-tolive-biz          ← LPだとすぐわかる
ip-hal-ossan-biz       ← IPコンテンツだとわかる
mvp-video-commerce-biz ← MVPで、bizチームだとわかる
```

---

## ルールはシンプル：3つのパーツ

```
{種別}-{プロジェクト名}-{チーム}
```

### 種別（何を作っているか）

| 種別 | 意味 | 例 |
|------|------|-----|
| `lp` | ランディングページ | `lp-tolive-biz` |
| `web` | Webアプリ・管理画面 | `web-tolive-admin-biz` |
| `api` | サーバー側のプログラム | `api-tts-image-biz` |
| `app` | モバイル・デスクトップアプリ | `app-fanme-dax` |
| `tool` | 社内ツール | `tool-team-roulette-ops` |
| `bot` | Bot・自動化 | `bot-creators-post-biz` |
| `lib` | 共通ライブラリ | `lib-auth-common-dev` |
| `infra` | インフラ・CI/CD | `infra-gcp-terraform-ops` |
| `doc` | ドキュメント | `doc-ai-knowhow-biz` |
| `video` | 動画関連 | `video-generator-biz` |
| `ip` | キャラクター・IP | `ip-anamori-biz` |
| `mvp` | 試作品・プロトタイプ | `mvp-video-commerce-biz` |
| `practice` | 練習・学習用 | `practice-logic-art-dev` |

### チーム（誰が使うか）

| チーム | 意味 |
|--------|------|
| `biz` | 事業・ビジネス |
| `dev` | 開発・エンジニアリング |
| `ops` | 社内運用・バックオフィス |
| `corp` | コーポレート・全社共通 |

---

## 何が便利になるの？

- **「LPだけ見たい」** → GitHubで `lp-` と検索すれば全LP一覧が出る
- **「社内ツールだけ見たい」** → `tool-` で検索
- **「新しいリポ名で迷わない」** → ルールに従えば自動的に決まる

---

## やってはいけないこと

| NG | 理由 | 正しい例 |
|----|------|---------|
| `My Project` | スペース禁止 | `web-my-project-biz` |
| `ToLive-LP` | 大文字禁止 | `lp-tolive-biz` |
| `動画ツール` | 日本語禁止 | `video-generator-biz` |
| `tolive` | 種別・チームがない | `lp-tolive-biz` |

---

## Claude Code を使っている人へ（自動適用の仕組み）

torihada-biz では **org共通の CLAUDE.md** という仕組みを導入しています。

### 何が起きるの？

```
torihada-biz/.github/CLAUDE.md
↓
org内のどのリポを Claude Code で開いても、このルールが自動で読み込まれる
↓
新しいリポを作るとき、Claude Code が自動で命名規則に従った名前を提案してくれる
```

### 具体的にどうなるの？

```
あなた：「Toliveの新しいLP用のリポ作りたい」

Claude Code：（CLAUDE.mdのルールを自動で読んでいるので）
           →「lp-tolive-campaign-biz で作成します」
```

**あなたがやることは何もありません。** Claude Code を普通に使うだけで、命名規則が自動適用されます。

### なぜ自動適用できるの？

GitHubには `.github` という特殊なリポジトリがあります。
ここに `CLAUDE.md` を置くと、torihada-biz org内の**全リポジトリ**で Claude Code がそのルールを読み込みます。

```
torihada-biz/.github/CLAUDE.md  ← ここに命名規則が書いてある
  ↓ 自動読み込み
torihada-biz/lp-tolive-biz      ← このリポを開いたとき
torihada-biz/api-tts-image-biz  ← このリポを開いたとき
torihada-biz/（どのリポでも）    ← 全部に適用される
```

---

## Claude Code を使っていない人へ

新しいリポジトリを作成するときは、以下のチェックリストを確認してください：

- [ ] `{種別}-{プロジェクト名}-{チーム}` の形式になっているか
- [ ] すべて小文字のケバブケース（`kebab-case`）か
- [ ] 種別は上の表にあるものを使っているか
- [ ] チームは `biz` / `dev` / `ops` / `corp` のどれかか
- [ ] Description（説明）を設定したか

---

## 困ったら

- 命名規則の詳細ドキュメント → [doc-claude-skills-dev/repo-naming](https://github.com/torihada-biz/doc-claude-skills-dev/tree/main/repo-naming)
- Claude Code を使っている場合 → `/repo-naming` と入力すればチェック・提案してくれます
