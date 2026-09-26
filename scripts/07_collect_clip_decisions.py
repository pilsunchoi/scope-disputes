"""관세법령정보포털(CLIP)에서 본문에 "덤핑방지관세"가 나오는 불복 결정과 판결의 목록과 전문을 받는다.

2단계(분쟁 사건 수집)의 관세청 몫이다. CLIP의 결정례 메뉴는 제목으로만 검색되므로 통합검색(본문 검색)을 쓴다.
불복(uls_dsbd)에는 관세청 과세전적부심사·심사청구·이의신청과, 처분청 사건번호로 실린 조세심판원 심판청구가 함께 있다.
소송(uls_suit)은 법원 판결이다. 본문에 검색어가 스치듯 나오는 사건도 섞이므로 덤핑방지관세 사건인지는 따로 가린다.

    python scripts/07_collect_clip_decisions.py

산출:
    data/disputes-clip.csv               사건 단위 목록 (구분, 사건번호, 결정·선고일, 제목, 쟁점분류, 결과, 전문 길이)
    data/raw/clip/<id>.html, <id>.txt    전문 원문과 텍스트 (id는 CLIP 내부 번호)
"""
import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "clip"
OUT = ROOT / "data" / "disputes-clip.csv"

BASE = "https://unipass.customs.go.kr/clip"
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)", "X-Requested-With": "XMLHttpRequest"}
PAUSE = 0.5
QUERY = "덤핑방지관세"
COLLECTIONS = {"uls_dsbd": "불복", "uls_suit": "소송"}


def search(collection):
    found, start = {}, 0
    while True:
        data = {
            "category": "CATE1", "collection": collection, "realCollection": collection, "selectCollection": "",
            "sortOrder": "DESC", "viewCount": "10", "startCount": str(start), "startDate": "", "endDate": "",
            "dateRange": "ALL", "searchRange": "1", "exquery": "", "reQuery": "", "realQuery": "",
            "filterOperation": "", "viewType": "horizontal", "radioSearchrange": "CATE0", "srwr": QUERY,
            "sortField": "RANK", "detailYN": "Y", "isVertical": "Y",
        }
        r = requests.post(BASE + "/infocomn/searchUnfc2.do", data=data, headers=UA, timeout=60)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        new = 0
        for a in soup.select("a.detailLink"):
            url = next((c for c in a.get("class", []) if c.startswith("/clip/")), "")
            m = re.search(r"openULS0105006S\.do\?dsbdIncdNo=(\d+)"
                          r"|openULS0105005S\.do\?suitMtNo=(\d+)&suitDtlSrno=(\d+)&dsadmCstmSrno=(\d+)", url)
            if not m:
                continue  # 품목분류·관세평가 사례 등 다른 메뉴의 링크
            key = m[1] or f"{m[2]}-{m[3]}-{m[4]}"
            if key in found:
                continue
            meta = a.find_next("span").get_text(" ", strip=True) if a.find_next("span") else ""
            found[key] = {"clip_id": key, "collection": COLLECTIONS[collection],
                          "title": " ".join(a.get_text("").split()), "meta": " ".join(meta.split()),
                          "params": dict(re.findall(r"(\w+)=(\w+)", url))}
            new += 1
        time.sleep(PAUSE)
        print(f"  {COLLECTIONS[collection]} {start + 1}~: 새 사건 {new}")
        if new == 0:
            break
        start += 10
    return list(found.values())


def fetch(item):
    html_path = RAW / f"{item['clip_id']}.html"
    if not (html_path.exists() and html_path.stat().st_size > 1000):
        p = item["params"]
        if item["collection"] == "불복":
            r = requests.post(BASE + "/lworsrch/openULS0105002S.do", data={"dsbdIncdNo": p["dsbdIncdNo"]},
                              headers=UA, timeout=60)
        else:
            r = requests.post(BASE + "/lworsrch/openULS0105004S.do",
                              data={k: p[k] for k in ("suitMtNo", "suitDtlSrno", "dsadmCstmSrno")},
                              headers=UA, timeout=60)
        r.raise_for_status()
        html_path.write_text(r.text, encoding="utf-8")
        time.sleep(PAUSE)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [" ".join(l.split()) for l in soup.get_text("\n").split("\n")]
    text = "\n".join(l for l in lines if l).lstrip("﻿")
    html_path.with_suffix(".txt").write_text(text, encoding="utf-8")
    return text


def field(text, name, stop):
    """상세 화면의 '이름' 줄 다음부터 다음 이름 줄 앞까지."""
    m = re.search(r"\n" + name + r"\n(.*?)\n(?:" + "|".join(stop) + r")\n", text, re.S)
    return " ".join(m[1].split()) if m else ""


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    items = []
    for coll in COLLECTIONS:
        items += search(coll)

    rows = []
    for it in items:
        text = fetch(it)
        meta = it["meta"]
        kind = re.search(r"\[(심판청구|심사청구|과세전적부심사|이의신청)\]", meta)
        case_no = re.search(r"\[([^\[\]]+-(?:조심|심사|적부심사|이의)-\d{4}-\d+)\]", meta) or re.search(r"\[([가-힣]+\d{4}[가-힣]+\d+)\]", meta)
        date = re.search(r"(?:결정일자|선고일자):(\d{4}-\d\d-\d\d)", meta)
        if it["collection"] == "불복":
            outcome = field(text, "주문", ["청구경위", "이유"])
        else:
            outcome = field(text, "결과", ["처분청"])
        rows.append({
            "clip_id": it["clip_id"],
            "forum": kind[1] if kind else ("판결" if it["collection"] == "소송" else ""),
            "case_no": case_no[1] if case_no else "",
            "decision_date": date[1] if date else "",
            "title": it["title"],
            "issue_class": (re.search(r"쟁점분류:([^\]]+)\]", meta) or [None, ""])[1],
            "outcome": outcome[:200],
            "dumping_mentions": text.count("덤핑"),
            "text_chars": len(text),
            "text_file": f"data/raw/clip/{it['clip_id']}.txt",
        })

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["forum"]] = by.get(r["forum"], 0) + 1
    print(f"사건 {len(rows)}건 -> {OUT.relative_to(ROOT)}", by)


if __name__ == "__main__":
    main()
