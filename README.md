# torihada-biz/.github

torihada-biz organization の共通設定リポジトリです。

## 含まれるファイル

- **CLAUDE.md** — Claude Code が org 内の全リポジトリで自動読み込みする共通ルール（命名規則等）
- **docs/repo-naming-guide.md** — [リポジトリ命名規則ガイド（初心者向け）](docs/repo-naming-guide.md)

## Composite Actions

### update-readme

`actions/update-readme/` — README 自動更新 Composite Action

torihada-biz の全リポジトリで共通利用できる README 自動更新の仕組みです。各リポジトリに wrapper ワークフロー 1 本を置くだけで動作します。

```yaml
# 各リポジトリの .github/workflows/update-readme.yml
- uses: torihada-biz/.github/actions/update-readme@main
```

導入手順: [docs/INSTALL.md](docs/INSTALL.md) を参照してください。

### 一括展開

```bash
bash docs/apply-update-readme.sh --dry-run  # 対象確認
bash docs/apply-update-readme.sh             # 配信実行
```
