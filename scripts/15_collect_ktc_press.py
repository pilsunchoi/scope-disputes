"""무역위원회 보도자료 가운데 반덤핑 관련 보도자료의 목록과 첨부 파일을 받아 텍스트를 뽑는다.

보도자료 게시판은 본문을 화면에 싣지 않고 첨부 파일(PDF, HWPX, HWP)로만 제공한다. 제목으로 반덤핑 관련
보도자료를 고르고, 첨부 가운데 PDF를 우선 받는다(없으면 HWPX, HWP). 이미 받은 파일은 다시 받지 않는다.
신청인, 예비·최종판정 결과, 덤핑률과 건의 세율, 가격약속 여부를 사건에 채우는 데 쓴다(추출은 따로 한다).

    python scripts/15_collect_ktc_press.py

산출:  data/ktc-press.csv                     보도자료 단위 목록 (게시번호, 등록일, 제목, 받은 파일, 텍스트 길이)
       data/raw/ktc-press/<bbs_id>.<확장자>, .txt
"""
import csv
import importlib.util
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ktc-press"
OUT = ROOT / "data" / "ktc-press.csv"

BASE = "https://www.ktc.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)"}
PAUSE = 0.7
# 반덤핑 사건 보도자료로 볼 제목. 세이프가드·불공정무역행위·일반 홍보는 뺀다
RELEVANT = re.compile(r"덤핑|종료재심|재심사|가격약속|잠정|부과\s*건의|판정|조사\s*개시")
EXCLUDE = re.compile(r"세이프가드|긴급관세|불공정|지재권|특허|원산지표시|상표|위촉|취임|간담회|설명회|교육|채용")

_spec = importlib.util.spec_from_file_location("guides", ROOT / "scripts" / "14_collect_ktc_scope_guides.py")
guides = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guides)


def list_page(i):
    r = requests.post(BASE + "/reportNewsList.do", headers=UA, timeout=60, data={"menuId": "57", "pageIndex": i})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    for tr in soup.select("tbody tr"):
        a = tr.find("a", href=re.compile(r"boardView\.do[^?]*\?bbs_id="))  # 주소에 세션 id가 끼기도 한다
        if a:
            rows.append({"bbs_id": re.search(r"bbs_id=(\d+)", a["href"])[1],
                         "title": " ".join(a.get_text(" ", strip=True).split())})
    return rows


def view(bbs_id):
    r = requests.get(BASE + "/boardView.do", headers=UA, timeout=60, params={"bbs_id": bbs_id, "menuId": "57"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    date = re.search(r"등록일\s*(\d{4}-\d\d-\d\d)", soup.get_text(" "))
    files = []
    for a in soup.find_all("a", onclick=re.compile(r"fileDownload\('")):
        bid, seq = re.findall(r"'(\d+)'", a["onclick"])[:2]
        files.append({"seq_no": seq, "file_name": " ".join(a.get_text(" ", strip=True).split())})
    time.sleep(PAUSE)
    return (date[1] if date else ""), files


def pick_file(files):
    for ext in (".pdf", ".hwpx", ".hwp"):
        for f in files:
            if f["file_name"].lower().endswith(ext):
                return f, ext
    return None, None


def download(bbs_id, f, ext):
    path = RAW / f"{bbs_id}{ext}"
    if not (path.exists() and path.stat().st_size > 0):
        r = requests.get(BASE + "/boardFileDownload.do", headers=UA, timeout=120,
                         params={"bbs_id": bbs_id, "seq_no": f["seq_no"]})
        r.raise_for_status()
        if len(r.content) < 200 or r.content[:15].lower().startswith(b"<!doctype"):
            raise ValueError(f"파일이 아닌 응답: {path.name}")
        path.write_bytes(r.content)
        time.sleep(PAUSE)
    return path


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    items, i = [], 1
    while True:
        page = list_page(i)
        if not page or (items and page[0]["bbs_id"] in {x["bbs_id"] for x in items}):
            break
        items += page
        i += 1
        time.sleep(PAUSE)
    relevant = [x for x in items if RELEVANT.search(x["title"]) and not EXCLUDE.search(x["title"])]
    print(f"  보도자료 {len(items)}건 가운데 반덤핑 관련 제목 {len(relevant)}건")

    rows = []
    for x in relevant:
        date, files = view(x["bbs_id"])
        f, ext = pick_file(files)
        row = {"bbs_id": x["bbs_id"], "date": date, "title": x["title"], "file_name": f["file_name"] if f else "",
               "file": "", "text_chars": 0, "error": ""}
        if f:
            try:
                path = download(x["bbs_id"], f, ext)
                text = guides.text_of(path)
                row.update({"file": path.relative_to(ROOT).as_posix(), "text_chars": len(text.strip())})
            except Exception as e:
                row["error"] = str(e)[:200]
        rows.append(row)

    rows.sort(key=lambda r: r["date"])
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"보도자료 {len(rows)}건 -> {OUT.relative_to(ROOT)} ({rows[0]['date']}~{rows[-1]['date']})")
    print(f"  첨부 없음 {sum(not r['file_name'] for r in rows)}건, 오류 {sum(bool(r['error']) for r in rows)}건,"
          f" 텍스트 50자 미만 {sum(bool(r['file']) and r['text_chars'] < 50 for r in rows)}건")


if __name__ == "__main__":
    main()
