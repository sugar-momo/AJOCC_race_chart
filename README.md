# AJOCCシクロクロス ラップタイム分析

[data.cyclocross.jp](https://data.cyclocross.jp) からダウンロードしたCSVを読み込んでインタラクティブグラフを表示するツールです。

## 機能

- **ラップタイム折れ線グラフ** — 周回ごとのタイムの変化を可視化
- **累積タイムグラフ** — レース全体の経過を比較
- **選手フィルター** — チップをクリックして任意の選手を表示/非表示
- **CSVドラッグ&ドロップ** — ファイルをブラウザ上にドロップするだけで読み込み
- **リザルト表** — 最速ラップをハイライト表示

## GitHub Pagesへのデプロイ手順

### 1. リポジトリ作成

```bash
git init
git add index.html
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/<あなたのユーザー名>/<リポジトリ名>.git
git push -u origin main
```

### 2. GitHub Pages を有効化

1. GitHub のリポジトリページ → **Settings**
2. 左メニュー **Pages**
3. Source を `Deploy from a branch`、Branch を `main / (root)` に設定
4. **Save**

数分後に `https://<ユーザー名>.github.io/<リポジトリ名>/` で公開されます。

## CSVファイルの形式

data.cyclocross.jp の「ラップタイム」CSVをそのままドロップしてください。

```
2026-03-15 レース名 カテゴリ
順位,選手,1周,2周,3周,...
1,選手名,7:56.7,16:24.7,...
DNS,選手名,,,,...
```

## 複数レースの切り替え

ページ右上の「別のCSVを読み込む」ボタンで別のレース結果に切り替えられます。
