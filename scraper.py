#!/usr/bin/env python3
"""
AJOCCシクロクロス ラップタイムスクレイパー v4
1回の実行で最大 BATCH_SIZE 件の新規大会を処理する。
毎日実行することで全データを少しずつ蓄積する。
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
REQUEST_INTERVAL = 1.0   # サーバー負荷軽減
BATCH_SIZE = 30          # 1回の実行で処理する最大大会数（約3〜5分で完了）

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


class MeetPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meet_links = {}
        self._in_a = False
        self._current_href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if re.search(r"/meet/[A-Z0-9]+-\d+-\d+", href):
                self._current_href = href
                self._in_a = True
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            text = "".join(self._buf).strip()
            m = re.search(r"/meet/([A-Z0-9]+-\d+-\d+)", self._current_href)
            if m:
                mid = m.group(1)
                if mid not in self.meet_links:
                    self.meet_links[mid] = {
                        "id": mid,
                        "url": f"{BASE_URL}/meet/{mid}",
                        "name": text,
                    }
            self._in_a = False
            self._current_href = None
            self._buf = []

    def handle_data(self, data):
        if self._in_a:
            self._buf.append(data)


class MeetDetailParser(HTMLParser):
    def __init__(self, meet_name=""):
        super().__init__()
        self.races = []
        self.meet_name = meet_name
        self._in_a = False
        self._current_href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if re.search(r"/race/\d+", href):
                self._current_href = href
                self._in_a = True
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            text = "".join(self._buf).strip()
            m = re.search(r"/race/(\d+)", self._current_href)
            if m:
                rid = m.group(1)
                self.races.append({
                    "id": rid,
                    "url": f"{BASE_URL}/race/{rid}",
                    "category": text,
                    "meetName": self.meet_name,
                })
            self._in_a = False
            self._current_href = None
            self._buf = []

    def handle_data(self, data):
        if self._in_a:
            self._buf.append(data)


class LaptimeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.ec_name = ""
        self.thead_rows = []
        self.tbody_rows = []
        self._in_title_elem = False
        self._in_ec_name = False
        self._in_table = False
        self._in_thead = False
        self._in_tbody = False
        self._in_row = False
        self._in_cell = False
        self._cell_buf = []
        self._current_row = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if attrs_dict.get("id") == "js__page_title":
            self._in_title_elem = True
        if attrs_dict.get("id") == "ec_name":
            self._in_ec_name = True
        if "table__laptime" in attrs_dict.get("class", ""):
            self._in_table = True
        if self._in_table:
            if tag == "thead":
                self._in_thead = True; self._in_tbody = False
            elif tag == "tbody":
                self._in_tbody = True; self._in_thead = False
            elif tag == "tr" and (self._in_thead or self._in_tbody):
                self._in_row = True; self._current_row = []
            elif tag in ("th", "td") and self._in_row:
                self._in_cell = True; self._cell_buf = []

    def handle_endtag(self, tag):
        if tag == "table" and self._in_table:
            self._in_table = self._in_thead = self._in_tbody = False
        if self._in_table:
            if tag == "tr" and self._in_row:
                self._in_row = False
                if self._in_thead: self.thead_rows.append(self._current_row)
                elif self._in_tbody: self.tbody_rows.append(self._current_row)
                self._current_row = []
            elif tag in ("th", "td") and self._in_cell:
                self._in_cell = False
                self._current_row.append("".join(self._cell_buf).strip())
                self._cell_buf = []

    def handle_data(self, data):
        if self._in_title_elem:
            self.title += data; self._in_title_elem = False
        if self._in_ec_name:
            self.ec_name += data; self._in_ec_name = False
        if self._in_cell:
            t = data.strip()
            if t: self._cell_buf.append(t)


def parse_race_page(html, race_id, category_hint="", meet_name=""):
    parser = LaptimeParser()
    parser.feed(html)
    if not parser.tbody_rows:
        return None
    title_full = (parser.title or "").strip()
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", title_full)
    date_str = date_match.group(0) if date_match else ""
    race_name = title_full.replace(date_str, "").strip() if date_str else title_full
    ec_name = (parser.ec_name or category_hint or "").strip()
    lap_labels = parser.thead_rows[0][2:] if parser.thead_rows and len(parser.thead_rows[0]) > 2 else []
    riders = []
    for row in parser.tbody_rows:
        if len(row) < 2: continue
        riders.append({"pos": row[0], "name": row[1], "lapTimes": [t or None for t in row[2:]]})
    return {
        "id": race_id, "date": date_str, "raceName": race_name,
        "meetName": meet_name, "category": ec_name,
        "lapLabels": lap_labels, "riders": riders,
    }


def load_existing(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updatedAt": "", "races": [], "fetchedMeets": []}


def main():
    print("=== AJOCCラップタイムスクレイパー v4 開始 ===")
    existing = load_existing(OUTPUT_FILE)
    existing_race_ids = {r["id"] for r in existing.get("races", [])}
    fetched_meets = set(existing.get("fetchedMeets", []))
    print(f"既存レース数: {len(existing_race_ids)}, 取得済み大会数: {len(fetched_meets)}")

    # 1. /meet から大会一覧を取得
    print(f"\n[1] 大会一覧取得: {MEET_URL}")
    meet_html = fetch(MEET_URL)
    if not meet_html:
        print("  取得失敗。終了。"); sys.exit(1)

    mp = MeetPageParser()
    mp.feed(meet_html)
    all_meets = mp.meet_links
    print(f"  大会数: {len(all_meets)}")

    # 未取得の大会だけ処理（新しい順に BATCH_SIZE 件）
    new_meets = [m for mid, m in all_meets.items() if mid not in fetched_meets]
    batch = new_meets[:BATCH_SIZE]
    print(f"  未取得大会数: {len(new_meets)}, 今回処理: {len(batch)} 件")

    # 2. 各大会ページからレース一覧→ラップタイムを取得
    new_race_data = []
    newly_fetched_meets = []

    for meet in batch:
        time.sleep(REQUEST_INTERVAL)
        print(f"  大会: {meet['name']}")
        detail_html = fetch(meet["url"])
        if not detail_html:
            continue

        dp = MeetDetailParser(meet_name=meet["name"])
        dp.feed(detail_html)

        for stub in dp.races:
            if stub["id"] in existing_race_ids:
                continue
            time.sleep(REQUEST_INTERVAL)
            race_html = fetch(stub["url"])
            if not race_html:
                continue
            data = parse_race_page(race_html, stub["id"], stub["category"], stub["meetName"])
            if data:
                new_race_data.append(data)
                existing_race_ids.add(stub["id"])
                print(f"    [{stub['id']}] {stub['category']} → {len(data['riders'])}選手")

        newly_fetched_meets.append(meet["id"])

    # 3. 保存
    all_races = existing.get("races", []) + new_race_data
    all_races.sort(key=lambda r: (r.get("date") or "0000-00-00"), reverse=True)

    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "fetchedMeets": list(fetched_meets | set(newly_fetched_meets)),
        "races": all_races,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    remaining = len(new_meets) - len(batch)
    print(f"\n=== 完了: 累計 {len(all_races)} レース保存 / 残り未取得大会: {remaining} ===")
    if remaining > 0:
        print(f"  → 明日以降のスケジュール実行で続きを取得します")


if __name__ == "__main__":
    main()
