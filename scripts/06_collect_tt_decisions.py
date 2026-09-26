"""조세심판원 심판결정례 가운데 덤핑방지관세 사건의 목록과 결정문 전문을 받는다.

2단계(분쟁 사건 수집)의 조세심판원 몫이다. 관세 세목에서 "덤핑방지관세"로 검색한 결과 전부를 받는다.
결정문 전문은 누리집의 인쇄용 화면(xmlPrintViewer)에서 읽는다. 이미 받은 전문은 다시 받지 않는다.

    python scripts/06_collect_tt_decisions.py

산출:
    data/disputes-tt.csv                 결정 단위 목록 (청구번호, 결정일, 결과, 제목, 요지, 관련법령, 전문 길이)
    data/raw/tt/<청구번호>.html           결정문 인쇄 화면 원문
    data/raw/tt/<청구번호>.txt            전문 텍스트
"""
import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "tt"
OUT = ROOT / "data" / "disputes-tt.csv"

BASE = "https://www.tt.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)"}
PAUSE = 0.5
QUERY = "덤핑방지관세"
PAGE = 30


def search_page(start):
    data = {
        "rdSection": "02", "listCount": str(PAGE), "startCnt": str(start), "selectViewCnt": str(PAGE),
        "searchType": "basic", "collections": "out_judge", "taxDivs": "basic", "txtKeyword": QUERY,
        "taxClassify": "02", "taxCategory": "00", "decisionClassify": "S500",
    }
    r = requests.post(BASE + "/mUser/dem/searchDemList.do", data=data, headers=UA, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    total = re.search(r"총\s*([\d,]+)\s*건", soup.get_text(" "))
    rows = []
    for li in soup.select("li.result-box"):
        a = li.find("a", onclick=re.compile(r"dem_no="))
        if not a:
            continue
        dem_no = re.search(r"dem_no=(\d+)", a["onclick"])[1]
        info = li.get_text(" ", strip=True)
        rows.append({
            "claim_no": re.search(r"청구번호\s*(\S+)", info)[1],
            "decision_date": re.search(r"결정일\s*(\d{4}\.\d\d\.\d\d)", info)[1].replace(".", "-"),
            "outcome": li.select_one(".label-decision").get_text(strip=True),
            "title": " ".join(a.get_text(" ", strip=True).split()),
            "dem_no": dem_no,
        })
    return rows, int(total[1].replace(",", "")) if total else 0


def fetch_text(row):
    html_path = RAW / f"{row['claim_no']}.html"
    if not (html_path.exists() and html_path.stat().st_size > 1000):
        r = requests.get(BASE + "/mUser/common/xmlPrintViewer.do",
                         params={"dem_no": row["dem_no"], "db": "s", "out": "print"}, headers=UA, timeout=60)
        r.raise_for_status()
        html_path.write_text(r.text, encoding="utf-8")
        time.sleep(PAUSE)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [" ".join(l.split()) for l in soup.get_text("\n").split("\n")]
    text = "\n".join(l for l in lines if l)
    text = text.replace("xmlViewer\n", "", 1)
    html_path.with_suffix(".txt").write_text(text, encoding="utf-8")
    return text


def section(text, name):
    """[결정요지], [관련법령] 같은 머리 칸의 내용. 다음 [칸]이나 구분선 앞까지다."""
    lines = text.split("\n")
    key = re.compile(r"^\[\s*" + r"\s*".join(name) + r"\s*\]")
    for i, l in enumerate(lines):
        if key.match(l):
            out = [key.sub("", l).strip()]
            for l2 in lines[i + 1:]:
                if l2.startswith("[") or re.match(r"^-{10,}", l2):
                    break
                out.append(l2)
            return " ".join(" ".join(out).split())
    return ""


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    rows, start = [], 0
    while True:
        page, total = search_page(start)
        rows += page
        print(f"  목록 {start + 1}쪽: {len(page)}건 (총 {total}건)")
        start += 1
        time.sleep(PAUSE)
        if not page or len(rows) >= total:
            break

    for r in rows:
        text = fetch_text(r)
        r["summary"] = section(text, "결정요지")
        r["related_law"] = section(text, "관련법령")
        r["text_chars"] = len(text)
        r["text_file"] = f"data/raw/tt/{r['claim_no']}.txt"

    cols = ["claim_no", "decision_date", "outcome", "title", "summary", "related_law", "dem_no", "text_chars", "text_file"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"결정 {len(rows)}건 -> {OUT.relative_to(ROOT)}")
    short = [r["claim_no"] for r in rows if r["text_chars"] < 2000]
    print(f"  전문이 2,000자 미만인 결정 {len(short)}건", *short)


if __name__ == "__main__":
    main()
