"""덤핑방지관세 부과 부령의 판(version) 목록과 본문을 국가법령정보센터에서 받는다.

1단계(부령 전수 수집)의 첫 스크립트다. 연혁법령 검색으로 현행과 폐지를 모두 받고,
판마다 본문 HTML을 data/raw/decrees/에 저장한다. 이미 받은 본문은 다시 받지 않는다.

    python scripts/01_collect_decrees.py

산출:
    data/decree-versions.csv      판 단위 목록 (lsiSeq, 시행일, 제명, 법령종류, 공포번호, 공포일, 제정·개정구분)
    data/raw/decrees/<lsiSeq>_<efYd>.html   판별 본문 원문
"""
import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "decrees"
OUT = ROOT / "data" / "decree-versions.csv"

BASE = "https://www.law.go.kr"
LIST_URL = BASE + "/lsScListR.do?menuId=1&subMenuId=17&tabMenuId=93"  # 연혁법령, 법령명 검색
BODY_URL = BASE + "/lsInfoR.do"
QUERIES = ["덤핑방지관세", "부당염매", "덤핑"]
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)"}
PAUSE = 0.5


def ymd(s):
    y, m, d = [int(x) for x in re.findall(r"\d+", s)[:3]]
    return f"{y:04d}-{m:02d}-{d:02d}"


def list_page(query, pg):
    data = {
        "q": query, "outmax": "150", "pg": str(pg), "p7": "0", "p19": "1,3",
        "section": "lawNm", "lsiSeq": "0", "p9": "1,2,3,4",
    }
    r = requests.post(LIST_URL, data=data, headers=UA, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    # 같은 결과가 트리 목록(li)과 표 목록(tr) 두 가지로 실린다. 표 목록의 칸을 읽는다
    for tr in soup.find_all("tr"):
        a = tr.find("a", onclick=lambda x: x and x.startswith("lsViewWideAll("))
        if not a:
            continue
        seq, ef = re.match(r"lsViewWideAll\('(\d+)','(\d+)'", a["onclick"]).groups()
        td = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        # 번호, 제명, 공포일, 법령종류, 공포번호, 시행일, 제정·개정구분, 소관부처
        rows.append({
            "lsi_seq": seq, "ef_yd": ef, "name": " ".join(td[1].split()),
            "kind": td[3], "promulgation_no": td[4],
            "promulgation_date": ymd(td[2]), "effective_date": ymd(td[5]),
            "revision_type": td[6], "ministry": td[7] if len(td) > 7 else "",
        })
    return rows


def collect_list():
    found = {}
    for q in QUERIES:
        pg = 1
        while True:
            rows = list_page(q, pg)
            new = [r for r in rows if r["lsi_seq"] not in found]
            for r in rows:
                found.setdefault(r["lsi_seq"], r)
            print(f"  목록 '{q}' {pg}쪽: {len(rows)}행, 새 판 {len(new)}")
            time.sleep(PAUSE)
            if len(rows) < 150:
                break
            pg += 1
    # 제명에 덤핑방지 또는 부당염매가 없는 것(예: '덤핑' 검색의 잡음)은 뺀다
    keep = {k: v for k, v in found.items() if re.search(r"덤핑방지|부당염매", v["name"])}
    dropped = sorted({v["name"] for k, v in found.items() if k not in keep})
    if dropped:
        print("  제외한 제명:", *dropped, sep="\n    ")
    return sorted(keep.values(), key=lambda r: (r["effective_date"], int(r["lsi_seq"])))


def fetch_body(row):
    path = RAW / f"{row['lsi_seq']}_{row['ef_yd']}.html"
    if path.exists() and path.stat().st_size > 1000:
        return False
    params = {
        "lsiSeq": row["lsi_seq"], "efYd": row["ef_yd"], "chrClsCd": "010202",
        "nwJoYnInfo": "N", "efGubun": "N", "netPrivateYn": "N", "tabMenuId": "93",
    }
    r = requests.get(BODY_URL, params=params, headers=UA, timeout=60)
    r.raise_for_status()
    path.write_text(r.text, encoding="utf-8")
    time.sleep(PAUSE)
    return True


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    print("목록 수집")
    rows = collect_list()
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"판 {len(rows)}개, 제명 {len({r['name'].replace(' ', '') for r in rows})}개 -> {OUT.relative_to(ROOT)}")

    print("본문 수집")
    n = sum(fetch_body(r) for r in rows)
    print(f"새로 받은 본문 {n}개, 저장 위치 {RAW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
