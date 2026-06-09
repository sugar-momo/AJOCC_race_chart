#!/usr/bin/env python3
"""
AJOCCシクロクロス ラップタイムスクレイパー v3
デバッグ: /meet ページ内の全 href を出力して構造を確認する
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
REQUEST_INTERVAL = 1.5

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


class AllLinkParser(HTMLParser):
    """ページ内の全 href を収集する"""
    def __init__(self):
        super().__init__()
        self.all_hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href:
                self.all_hrefs.append(href)


class MeetPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.race_links = {}
        self.meet_links = {}
        self._in_a = False
        self._current_href = None
        self._current_type = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            # /race/数字 または 完全URL
            if re.search(r"/race/\d+", href):
                self._current_href = href
                self._current_type = "race"
                self._in_a = True
                self._buf = []
            # /meet/英数字-数字-数字 または 完全URL
            elif re.search(r"/meet/[A-Z0-9]+-\d+-\d+", href):
                self._current_href = href
                self._current_type = "meet"
                self._in_a = True
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            text = "".join(self._buf).strip()
            href = self._current_href
            if self._current_type == "race":
                # IDとURLを正規化
                m = re.search(r"/race/(\d+)", href)
                if m:
                    rid = m.group(1)
                    url = f"{BASE_URL}/race/{rid}"
                    if rid not in self.race_links:
                        self.race_links[rid] = {"id": rid, "url": url, "label": text}
            elif self._current_type == "meet":
                m = re.search(r"/meet/([A-Z0-9]+-\d+-\d+)", href)
                if m:
                    mid = m.group(1)
                    url = f"{BASE_URL}/meet/{mid}"
                    if mid not in self.meet_links:
                        self.meet_links[mid] = {"id": mid, "url": url, "name": text}
            self._in_a = False
            self._current_href = None
            self._current_type = None
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
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
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
            text = data.strip()
            if text: self._cell_buf.append(text)


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
        lap_times = [t if t else None for t in row[2:]]
        riders.append({"pos": row[0], "name": row[1], "lapTimes": lap_times})
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
        return {"updatedAt": "", "races": []}


def main():
    print("=== AJOCCラップタイムスクレイパー v3 開始 ===")
    existing = load_existing(OUTPUT_FILE)
    existing_ids = {r["id"] for r in existing.get("races", [])}
    print(f"既存レース数: {len(existing_ids)}")

    # 1. /meet ページを取得
    print(f"\n[1] /meet ページを取得: {MEET_URL}")
    meet_html = fetch(MEET_URL)
    if not meet_html:
        print("  取得失敗。終了。"); sys.exit(1)
    print(f"  取得HTML長: {len(meet_html)} bytes")

    # デバッグ: 全hrefのうち /meet/ か /race/ を含むものを先頭30件表示
    link_parser = AllLinkParser()
    link_parser.feed(meet_html)
    meet_race_hrefs = [h for h in link_parser.all_hrefs if "/meet/" in h or "/race/" in h]
    print(f"\n  [DEBUG] /meet/ or /race/ を含むリンク（先頭30件）:")
    for h in meet_race_hrefs[:30]:
        print(f"    {h}")

    # 本番パース
    meet_page_parser = MeetPageParser()
    meet_page_parser.feed(meet_html)
    direct_races = meet_page_parser.race_links
    meet_links = meet_page_parser.meet_links

    print(f"\n  /race リンク数: {len(direct_races)}")
    print(f"  /meet/XXX-NNN-NNN リンク数: {len(meet_links)}")

    # 2. /meet/XXX-NNN-NNN を辿る
    all_race_stubs = {}
    for rid, r in direct_races.items():
        all_race_stubs[rid] = {"id": rid, "url": r["url"], "category": r["label"], "meetName": ""}

    for mid, meet in meet_links.items():
        time.sleep(REQUEST_INTERVAL)
        print(f"  ミート取得: {meet['name']} ({meet['url']})")
        detail_html = fetch(meet["url"])
        if not detail_html:
            continue
        dp = MeetDetailParser(meet_name=meet["name"])
        dp.feed(detail_html)
        for r in dp.races:
            if r["id"] not in all_race_stubs:
                all_race_stubs[r["id"]] = r
        print(f"    → {len(dp.races)} レース")

    print(f"\n[2] 合計ユニークレース数: {len(all_race_stubs)}")

    new_stubs = [r for r in all_race_stubs.values() if r["id"] not in existing_ids]
    print(f"  新規レース数: {len(new_stubs)}")

    new_race_data = []
    for stub in new_stubs:
        time.sleep(REQUEST_INTERVAL)
        print(f"  解析中: [{stub['id']}] {stub.get('meetName','')} {stub.get('category','')}")
        race_html = fetch(stub["url"])
        if not race_html:
            continue
        data = parse_race_page(race_html, stub["id"], stub.get("category",""), stub.get("meetName",""))
        if data:
            new_race_data.append(data)
            print(f"    → {len(data['riders'])} 選手, {len(data.get('lapLabels',[]))} 周")
        else:
            print(f"    → ラップタイムなし（スキップ）")

    all_races = existing.get("races", []) + new_race_data
    all_races.sort(key=lambda r: (r.get("date") or "0000-00-00"), reverse=True)

    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "races": all_races,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完了: {len(all_races)} レースを {OUTPUT_FILE} に保存 ===")


if __name__ == "__main__":
    main()
