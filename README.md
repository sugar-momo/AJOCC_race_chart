# AJOCCシクロクロス ラップタイム分析

`data.cyclocross.jp` の全レース結果を自動取得してインタラクティブグラフで表示するサイトです。

## 仕組み

```
GitHub Actions（毎日 JST 9:00 自動実行）
  ↓ data.cyclocross.jp/meet からレース一覧を取得
  ↓ 各レースページの .table__laptime を解析
  ↓ races.json をリポジトリにコミット
      ↓
GitHub Pages（index.html）
  → races.json を読み込んでレース一覧・グラフを表示
```

**新しいレースは翌日自動でサイトに反映されます。手作業は不要。**

## GitHub Pagesへのデプロイ手順

### 1. リポジトリ作成 & プッシュ

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
git push -u origin main
```

### 2. GitHub Pages を有効化

1. GitHubリポジトリ → Settings → Pages
2. Source: `Deploy from a branch`、Branch: `main / (root)`
3. Save

### 3. 初回データ取得を手動実行

1. GitHubリポジトリ → Actions タブ
2. 「レースデータ更新」ワークフロー → 「Run workflow」
3. `races.json` がリポジトリに生成されればOK

数分後に `https://<ユーザー名>.github.io/<リポジトリ名>/` で公開されます。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `index.html` | フロントエンド（GitHub Pagesで公開） |
| `races.json` | スクレイパーが生成するレースデータ（自動更新） |
| `scraper.py` | HTMLスクレイパー（GitHub Actionsが実行） |
| `.github/workflows/update.yml` | 毎日自動実行のワークフロー |
