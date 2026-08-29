#!/usr/bin/env python3
"""偵測清大總務處事務組的公車公告新增與修改，並整理成可直接判讀的報告。
   本版只做偵測與通知，不解析時刻表數字（時刻表圖片仍由人工判讀）。"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://affairs.site.nthu.edu.tw/p/403-1165-1065-1.php?Lang=zh-tw"

# 禮貌爬取：表明身分與聯絡方式，讓對方知道是誰在抓、出問題找誰
HEADERS = {"User-Agent": "TsingBusBot/1.0 (student project; s60112jjswork@gmail.com)"}

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state.json"

# #分類規則 //順序即優先序，先命中先算。等級決定 issue 標題怎麼寫
CLASSIFIERS = [
    ("時刻表更新", "需更新資料", re.compile(r"時刻表")),
    ("停駛公告",   "需更新資料", re.compile(r"停駛|停止行駛|停班停課")),
    ("站牌異動",   "建議看一下", re.compile(r"站牌|候車區|臨時|調整")),
    ("加開專車",   "建議看一下", re.compile(r"專車")),
    ("宣導事項",   "僅供參考",   re.compile(r"宣導|意見調查|問卷|秩序")),
]

FOOTER_MARK = "校本部電話"
ROC_DATE = re.compile(r"(1\d{2})(\d{2})(\d{2})")


def roc_to_ad(s):
    m = ROC_DATE.fullmatch(s)
    if not m:
        return None
    y, mo, d = int(m.group(1)) + 1911, m.group(2), m.group(3)
    return f"{y}-{mo}-{d}"


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"seen": {}}


def fetch_list():
    resp = requests.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for a in soup.select('a[href*="/p/406-1165-"]'):
        title = a.get_text(strip=True)
        href = a.get("href", "")
        m = re.search(r"/p/406-1165-(\d+),r1065", href)
        if not title or not m:
            continue
        items.append({
            "id": m.group(1),
            "title": title,
            "url": requests.compat.urljoin(LIST_URL, href),
        })
    return items


def fetch_detail(url):
    """回傳 (內文摘要, PDF檔名清單)。任何失敗都回傳空值，不讓整支程式掛掉。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        pdfs = [
            a.get_text(strip=True)
            for a in soup.select('a[href*="downloadfile"]')
            if a.get_text(strip=True)
        ]

        for tag in soup(["script", "style", "nav", "header"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        if FOOTER_MARK in text:
            text = text.split(FOOTER_MARK)[0]
        lines = [
            ln for ln in text.split("\n")
            if 4 <= len(ln) <= 200 and not ln.startswith("跳到") and "組" != ln[-1:]
        ]
        body = "\n".join(lines[-12:])
        return body[:600], pdfs
    except Exception as e:
        return f"(擷取內文失敗：{e})", []


def classify(title):
    for label, level, pattern in CLASSIFIERS:
        if pattern.search(title):
            return label, level
    return "其他", "僅供參考"


def describe_pdf(name):
    nums = ROC_DATE.findall(name)
    if len(nums) >= 2:
        a = roc_to_ad("".join(nums[0]))
        b = roc_to_ad("".join(nums[1]))
        if a and b:
            return f"{name}  →  適用 {a} 至 {b}"
    elif len(nums) == 1:
        a = roc_to_ad("".join(nums[0]))
        if a:
            return f"{name}  →  日期 {a}"
    return name


def main():
    state = load_state()
    seen = state.get("seen", {})
    first_run = len(seen) == 0

    try:
        items = fetch_list()
    except Exception as e:
        print(f"::error::抓取公告列表失敗：{e}")
        sys.exit(1)

    if not items:
        print("::error::公告列表解析到 0 筆，網站結構可能已變更，請檢查 crawl.py")
        sys.exit(1)

    changed = []
    for it in items:
        body, pdfs = fetch_detail(it["url"])
        time.sleep(1)
        it["body"] = body
        it["pdfs"] = pdfs

        digest = hashlib.sha256(
            (it["title"] + body + "|".join(pdfs)).encode("utf-8")
        ).hexdigest()[:16]
        it["digest"] = digest

        old = seen.get(it["id"])
        if old is None:
            changed.append((it, "新增"))
        elif old.get("digest") != digest:
            changed.append((it, "已修改"))

    if first_run:
        state["seen"] = {
            it["id"]: {"title": it["title"], "digest": it["digest"]} for it in items
        }
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"首次執行，已記錄現有 {len(items)} 則公告，本次不通知")
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("has_new=true\n")
        return

    if not changed:
        print(f"沒有異動（目前已知 {len(seen)} 則）")
        return

    order = {"需更新資料": 0, "建議看一下": 1, "僅供參考": 2}
    changed.sort(key=lambda x: order[classify(x[0]["title"])[1]])

    levels = {classify(it["title"])[1] for it, _ in changed}
    top_level = "需更新資料" if "需更新資料" in levels else (
        "建議看一下" if "建議看一下" in levels else "僅供參考"
    )

    lines = []
    for it, status in changed:
        label, level = classify(it["title"])
        lines.append(f"### [{level}] {label}｜{status}")
        lines.append("")
        lines.append(f"**{it['title']}**")
        lines.append("")
        lines.append(f"{it['url']}")
        lines.append("")
        if it["pdfs"]:
            lines.append("附件：")
            for p in it["pdfs"]:
                lines.append(f"- {describe_pdf(p)}")
            lines.append("")
        if it["body"]:
            lines.append("公告內容：")
            lines.append("")
            lines.append("```")
            lines.append(it["body"])
            lines.append("```")
            lines.append("")
        if level == "需更新資料":
            lines.append("處理方式：開連結看時刻表圖片，更新 `docs/v1/campus.json` 或 "
                         "`nanda.json`（停駛則改 `overrides.json`），"
                         "**並記得一併更新 `manifest.json` 的時間戳記**。")
        elif level == "建議看一下":
            lines.append("處理方式：看內容判斷是否需要在 `docs/v1/notice.json` 放一則公告提醒使用者。")
        else:
            lines.append("處理方式：純宣導，通常不需要任何動作。")
        lines.append("")
        lines.append("---")
        lines.append("")

    report = "\n".join(lines)
    (ROOT / "report.md").write_text(report, encoding="utf-8")
    (ROOT / "issue_title.txt").write_text(
        f"[{top_level}] 公車公告 {len(changed)} 則", encoding="utf-8"
    )
    print(report)

    for it in items:
        seen[it["id"]] = {"title": it["title"], "digest": it["digest"]}
    state["seen"] = seen
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write("has_new=true\n")
        f.write(f"issue_title=[{top_level}] 公車公告 {len(changed)} 則\n")


if __name__ == "__main__":
    main()
