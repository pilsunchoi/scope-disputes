"""무역위원회 누리집에서 반덤핑조사 사건의 목록과 상세(조사번호, 대상국, 재심 종류, 진행 일정)를 받는다.

4단계(무역위원회 사건 연결)의 첫 스크립트다. "무역구제조사 종결"(menuId 12)과 "무역구제조사 진행"(menuId 11)
메뉴의 반덤핑조사 목록을 모두 넘겨 받고, 사건마다 상세 화면을 저장한다. 이미 받은 상세는 다시 받지 않는다.
진행 중인 사건도 받는 것은 최종판정 뒤 부령이 공포되었어도 누리집에는 아직 진행으로 남은 사건이 있기 때문이다.

    python scripts/12_collect_ktc_cases.py

산출:
    data/ktc-cases.csv                    사건 단위 (조사번호, 건명, 품목, 대상국, 재심 종류, 조사개시·예비·최종판정일 등, 문서 목록)
    data/raw/ktc/<masterId>.html          사건 상세 화면 원문
"""
import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ktc"
OUT = ROOT / "data" / "ktc-cases.csv"

BASE = "https://www.ktc.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)"}
PAUSE = 0.5
AD = "10100001"          # 조사유형: 반덤핑조사
STEP = "11000005"        # 누리집 스크립트가 늘 보내는 값. 진행·종결의 구분은 menuId가 한다
MENUS = {"12": "종결", "11": "진행"}


def list_page(menu, i):
    r = requests.post(BASE + "/investArticle.do", headers=UA, timeout=60,
                      data={"menuId": menu, "pageIndex": i, "process_step_code": STEP, "invstg_type_code": AD})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    for tr in soup.select("tbody tr"):
        a = tr.find("a", href=re.compile(r"viewInvest"))
        if not a:
            continue
        td = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        rows.append({"master_id": re.search(r"viewInvest\('(\d+)'", a["href"])[1], "menu": menu,
                     "status": MENUS[menu], "title": td[0], "case_no": td[1], "product": td[2],
                     "initiation_date": td[3].replace(".", "-")})
    return rows


def detail(master_id, menu):
    path = RAW / f"{master_id}.html"
    if not (path.exists() and path.stat().st_size > 1000):
        r = requests.post(BASE + "/viewInvest.do", headers=UA, timeout=60,
                          data={"menuId": menu, "masterId": master_id, "invstg_type_code": AD})
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
        time.sleep(PAUSE)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    out = {}
    for th in soup.find_all("th"):
        td = th.find_next_sibling("td")
        if td:
            out[th.get_text(strip=True)] = " ".join(td.get_text(" ", strip=True).split())
    # 진행일정 표: 진행단계 | 진행일
    steps = {}
    for tr in soup.find_all("tr"):
        c = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) == 2 and re.match(r"\d{4}-\d\d-\d\d$", c[1]):
            steps.setdefault(c[0], c[1])
    # 게시된 문서 제목(질의서, 조사대상물품범위안내서, 최종보고서 등)
    docs = sorted({" ".join(td.get_text(" ", strip=True).split()) for td in soup.find_all("td")
                   if re.match(r"^\[[^\]]+\]", td.get_text(strip=True))})
    return out, steps, docs


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for menu in MENUS:
        seen, i = set(), 1
        while True:
            page = [r for r in list_page(menu, i) if r["master_id"] not in seen]
            if not page:
                break
            seen |= {r["master_id"] for r in page}
            rows += page
            i += 1
            time.sleep(PAUSE)
        print(f"  {MENUS[menu]} 목록 {i - 1}쪽, 사건 {len(seen)}건")

    step_names = set()
    for r in rows:
        info, steps, docs = detail(r["master_id"], r.pop("menu"))
        r["case_no"] = info.get("조사번호", r["case_no"])
        r["countries"] = info.get("대상국", "")
        r["review_type"] = info.get("재심종류", "")
        r["steps"] = steps
        r["docs"] = " | ".join(docs)
        step_names |= set(steps)

    cols = ["master_id", "status", "case_no", "title", "product", "countries", "review_type", "initiation_date",
            "prelim_date", "final_date", "hearing_date", "steps_all", "docs"]
    for r in rows:
        s = r.pop("steps")
        r["prelim_date"] = next((v for k, v in s.items() if "예비" in k), "")
        r["final_date"] = next((v for k, v in s.items() if "최종" in k), "")
        r["hearing_date"] = next((v for k, v in s.items() if "공청회" in k), "")
        r["steps_all"] = "; ".join(f"{k} {v}" for k, v in s.items())
    rows.sort(key=lambda r: (r["initiation_date"], r["case_no"]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["review_type"] or "(빈칸)"] = by.get(r["review_type"] or "(빈칸)", 0) + 1
    print(f"사건 {len(rows)}건 -> {OUT.relative_to(ROOT)}", by)
    print("  진행단계 이름:", sorted(step_names))
    print(f"  최종판정일이 있는 사건 {sum(bool(r['final_date']) for r in rows)}건")


if __name__ == "__main__":
    main()
