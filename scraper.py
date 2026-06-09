#!/usr/bin/env python3
"""
AJOCCシクロクロス ラップタイムスクレイパー
data.cyclocross.jp/meet からレース一覧を取得し、
各レースページの .table__laptime を解析して races.json を生成する。

GitHub Actions から定期実行されることを想定。
"""

import json
import re
import time
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

BASE_URL = "https://data.cyclocross.jp"
MEET_URL = f"{BASE_URL}/meet"
OUTPUT_FILE = "races.json"
REQUEST_INTERVAL = 1.5  # サーバー負荷軽減のためリクエスト間隔（秒）

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AJOCCLaptimeViewer/1.0; +https://github.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ja,en;q=0.9",
}


def fetch(url: str) -> str:
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=20) as res:
            return res.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        print(f"  HTTP {e.code}: {url}", file=sys.stderr)
        return ""
    except URLError as e:
        print(f"  URL error {e.reason}: {url}", file=sys.stderr)
        return ""


# ---- Meet page parser: レース一覧 ----
class MeetParser(HTMLParser):
    """
    /meet ページから各レースのリンク・名前・日付を抽出する。
    想定HTML構造:
      <a href="/meet/NNN">大会名</a>
    """
    def __init__(self):
        super().__init__()
        self.meets = []       # [{id, name, url}]
        self._in_link = False
        self._current_href = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if re.match(r"^/meet/[A-Z0-9]+-\d+-\d+$", href):
                self._current_href = href
                self._in_link = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_link = False
            self._current_href = None

    def handle_data(self, data):
        if self._in_link and self._current_href:
            text = data.strip()
            if text:
                meet_id = self._current_href.split("/")[-1]
                self.meets.append({
                    "id": meet_id,
                    "name": text,
                    "url": BASE_URL + self._current_href,
                })
                self._in_link = False
                self._current_href = None


# ---- Meet detail page parser: レース（カテゴリ）一覧 ----
class MeetDetailParser(HTMLParser):
    """
    /meet/NNN ページから各レース（カテゴリ）へのリンクを抽出する。
    想定HTML:
      <a href="/race/NNN">カテゴリ名</a>
    """
    def __init__(self):
        super().__init__()
        self.races = []
        self._in_link = False
        self._current_href = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if re.match(r"^/race/\d+$", href):
                self._current_href = href
                self._in_link = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_link = False
            self._current_href = None

    def handle_data(self, data):
        if self._in_link and self._current_href:
            text = data.strip()
            if text:
                race_id = self._current_href.split("/")[-1]
                self.races.append({
                    "id": race_id,
                    "category": text,
                    "url": BASE_URL + self._current_href,
                })
                self._in_link = False
                self._current_href = None


# ---- Race page parser: ラップタイムテーブル ----
class LaptimeParser(HTMLParser):
    """
    /race/NNN ページから以下を抽出する:
    - ページタイトル (#js__page_title)
    - カテゴリ名 (#ec_name)
    - 日付 (ページ内のdateまたはタイトルから推定)
    - .table__laptime のthead/tbody
    """
    def __init__(self):
        super().__init__()
        self.title = ""
        self.ec_name = ""
        self.date_str = ""
        self.thead_rows = []   # [[cell, ...], ...]
        self.tbody_rows = []   # [[cell, ...], ...]

        self._in_title_elem = False
        self._in_ec_name = False
        self._in_table = False
        self._in_thead = False
        self._in_tbody = False
        self._in_row = False
        self._in_cell = False
        self._in_lap_div = False
        self._cell_buf = []
        self._current_row = []
        self._depth = 0
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        id_ = attrs_dict.get("id", "")
        class_ = attrs_dict.get("class", "")

        if id_ == "js__page_title":
            self._in_title_elem = True
        if id_ == "ec_name":
            self._in_ec_name = True

        if "table__laptime" in class_:
            self._in_table = True

        if self._in_table:
            if tag == "thead":
                self._in_thead = True
                self._in_tbody = False
            elif tag == "tbody":
                self._in_tbody = True
                self._in_thead = False
            elif tag == "tr" and (self._in_thead or self._in_tbody):
                self._in_row = True
                self._current_row = []
            elif tag in ("th", "td") and self._in_row:
                self._in_cell = True
                self._cell_buf = []
            elif tag == "div" and self._in_cell:
                self._in_lap_div = True

    def handle_endtag(self, tag):
        if tag == "table" and self._in_table:
            self._in_table = False
            self._in_thead = False
            self._in_tbody = False

        if self._in_table:
            if tag == "tr" and self._in_row:
                self._in_row = False
                if self._in_thead:
                    self.thead_rows.append(self._current_row)
                elif self._in_tbody:
                    self.tbody_rows.append(self._current_row)
                self._current_row = []
            elif tag in ("th", "td") and self._in_cell:
                self._in_cell = False
                self._in_lap_div = False
                self._current_row.append("".join(self._cell_buf).strip())
                self._cell_buf = []
            elif tag == "div" and self._in_lap_div:
                self._in_lap_div = False

    def handle_data(self, data):
        if self._in_title_elem:
            self.title += data
            self._in_title_elem = False
        if self._in_ec_name:
            self.ec_name += data
            self._in_ec_name = False
        if self._in_cell:
            text = data.strip()
            if text:
                self._cell_buf.append(text)


def parse_race_page(html: str, race_id: str, category_hint: str = "") -> dict | None:
    """レースページのHTMLをパースしてデータを返す。ラップタイムがなければ None。"""
    parser = LaptimeParser()
    parser.feed(html)

    if not parser.tbody_rows:
        return None

    # 日付をタイトルから抽出 (例: "2026-03-15 大会名")
    title_full = (parser.title or "").strip()
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", title_full)
    date_str = date_match.group(0) if date_match else ""

    race_name = parser.title.replace(date_str, "").strip() if date_str else parser.title.strip()
    ec_name = (parser.ec_name or category_hint or "").strip()

    # thead から周回ラベルを取得
    lap_labels = []
    if parser.thead_rows:
        header = parser.thead_rows[0]
        # 最初の2列（順位・選手）以降がラップ
        lap_labels = header[2:] if len(header) > 2 else []

    riders = []
    for row in parser.tbody_rows:
        if len(row) < 2:
            continue
        pos = row[0]
        name = row[1]
        lap_times = row[2:] if len(row) > 2 else []
        # 空文字を None に統一
        lap_times = [t if t else None for t in lap_times]
        riders.append({"pos": pos, "name": name, "lapTimes": lap_times})

    return {
        "id": race_id,
        "date": date_str,
        "raceName": race_name,
        "category": ec_name,
        "lapLabels": lap_labels,
        "riders": riders,
    }


def load_existing(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updatedAt": "", "races": []}


def main():
    print("=== AJOCCラップタイムスクレイパー開始 ===")
    existing = load_existing(OUTPUT_FILE)
    existing_ids = {r["id"] for r in existing.get("races", [])}
    print(f"既存レース数: {len(existing_ids)}")

    # 1. /meet からミート一覧を取得
    print(f"\n[1] ミート一覧を取得: {MEET_URL}")
    meet_html = fetch(MEET_URL)
    if not meet_html:
        print("  ミートページの取得に失敗。終了します。")
        sys.exit(1)

    meet_parser = MeetParser()
    meet_parser.feed(meet_html)
    meets = meet_parser.meets
    print(f"  ミート数: {len(meets)}")

    # 2. 各ミートページからレース一覧を取得
    all_race_stubs = []  # [{id, category, url, meet_name}]
    for meet in meets:
        time.sleep(REQUEST_INTERVAL)
        print(f"  取得中: {meet['name']} ({meet['url']})")
        detail_html = fetch(meet["url"])
        if not detail_html:
            continue
        detail_parser = MeetDetailParser()
        detail_parser.feed(detail_html)
        for r in detail_parser.races:
            r["meetName"] = meet["name"]
            all_race_stubs.append(r)

    print(f"\n[2] 合計レース数: {len(all_race_stubs)}")

    # 3. 新規レースのみラップタイムを取得
    new_races = [r for r in all_race_stubs if r["id"] not in existing_ids]
    print(f"  新規レース数: {len(new_races)}")

    new_race_data = []
    for stub in new_races:
        time.sleep(REQUEST_INTERVAL)
        print(f"  解析中: [{stub['id']}] {stub.get('meetName','')} {stub['category']}")
        race_html = fetch(stub["url"])
        if not race_html:
            continue
        data = parse_race_page(race_html, stub["id"], stub["category"])
        if data:
            # meetName を付加
            data["meetName"] = stub.get("meetName", "")
            new_race_data.append(data)
            print(f"    → {len(data['riders'])} 選手, {len(data.get('lapLabels',[]))} 周")
        else:
            print(f"    → ラップタイムなし（スキップ）")

    # 4. 既存データと統合してソート（日付降順）
    all_races = existing.get("races", []) + new_race_data
    all_races.sort(key=lambda r: (r.get("date", "") or "0000-00-00"), reverse=True)

    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "races": all_races,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完了: {len(all_races)} レースを {OUTPUT_FILE} に保存 ===")


if __name__ == "__main__":
    main()
