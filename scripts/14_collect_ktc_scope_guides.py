"""무역위원회 사건별 게시 문서 가운데 조사대상물품(재심사대상물품) 범위 안내서를 받아 텍스트를 뽑는다.

범위 안내서는 무역위원회가 조사를 개시하면서 조사대상물품의 범위와 제외 물품을 설명한 문서다.
부령에 없는 제외 규격이 무역위원회 판정에만 있는 경우(중국산 합판 등) 그 범위의 1차 자료가 된다.
사건 상세 화면(data/raw/ktc/)의 게시 문서 목록에서 제목에 "범위"와 "안내서"(또는 CCN 안내서)가 든 문서를 고르고,
문서 팝업의 첨부 파일을 모두 받는다. 이미 받은 파일은 다시 받지 않는다.

    python scripts/14_collect_ktc_scope_guides.py

입력:  data/ktc-cases.csv, data/raw/ktc/<masterId>.html   (12_collect_ktc_cases.py 산출)
산출:  data/ktc-scope-guides.csv                 파일 단위 목록 (사건, 문서 제목, 파일명, 텍스트 길이)
       data/raw/ktc-scope/<masterId>_<bbsId>_<seq>.<확장자>, .txt
"""
import csv
import importlib.util
import re
import subprocess
import time
import zipfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "ktc-cases.csv"
RAW_CASE = ROOT / "data" / "raw" / "ktc"
RAW = ROOT / "data" / "raw" / "ktc-scope"
OUT = ROOT / "data" / "ktc-scope-guides.csv"

BASE = "https://www.ktc.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)"}
PAUSE = 0.7
GUIDE = re.compile(r"범위.*안내|CCN\s*안내|물품\s*범위")

# HWP 5.0 본문 추출은 별표 수집 스크립트의 것을 그대로 쓴다
_spec = importlib.util.spec_from_file_location("annexes", ROOT / "scripts" / "03_collect_annexes.py")
annexes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(annexes)


def guide_docs(master_id):
    html = (RAW_CASE / f"{master_id}.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=re.compile(r"fnQnaDetailView")):
        title = " ".join(a.get_text(" ", strip=True).split())
        if GUIDE.search(title.replace(" ", "")) or GUIDE.search(title):
            mast, bbs, typ = re.findall(r"'(\d+)'", a["href"])[:3]
            out.append({"invstg_mast_id": mast, "bbs_id": bbs, "bbs_type_code": typ, "doc_title": title})
    return out


def attachments(doc):
    r = requests.get(BASE + "/qnaDetailView.do", headers=UA, timeout=60,
                     params={k: doc[k] for k in ("invstg_mast_id", "bbs_id", "bbs_type_code")})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    names = [td.get_text(" ", strip=True) for td in soup.find_all("td")]
    files = []
    for a in soup.find_all("a", href=re.compile(r"qnaFileDown")):
        mast, bbs, seq = re.findall(r"'(\d+)'", a["href"])[:3]
        # 파일명은 다운로드 링크 앞 칸에 있다
        cell = a.find_parent("td")
        prev = cell.find_previous_sibling("td") if cell else None
        name = prev.get_text(" ", strip=True) if prev else ""
        if not name:
            name = next((n for n in names if re.search(r"\.(hwp|hwpx|pdf|docx?|xlsx?|zip)$", n, re.I)), "")
        files.append({"seq_no": seq, "file_name": name})
    time.sleep(PAUSE)
    return files


def download(doc, f):
    ext = (re.search(r"\.(\w+)$", f["file_name"]) or [None, "bin"])[1].lower()
    path = RAW / f"{doc['invstg_mast_id']}_{doc['bbs_id']}_{f['seq_no']}.{ext}"
    if not (path.exists() and path.stat().st_size > 0):
        r = requests.post(BASE + "/qnaFileDownload.do", headers=UA, timeout=120,
                          data={"invstg_mast_id": doc["invstg_mast_id"], "bbs_id": doc["bbs_id"], "seq_no": f["seq_no"]})
        r.raise_for_status()
        if len(r.content) < 200 or r.content[:15].lower().startswith(b"<!doctype") or r.content[:6] == b"<html>":
            raise ValueError(f"파일이 아닌 응답: {path.name}")
        path.write_bytes(r.content)
        time.sleep(PAUSE)
    return path


def text_of(path):
    txt = path.with_suffix(".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    ext = path.suffix.lower()
    text = ""
    if ext == ".pdf":
        subprocess.run(["pdftotext", "-raw", "-enc", "UTF-8", str(path), str(txt)], check=True)
        return txt.read_text(encoding="utf-8", errors="replace")
    if ext == ".hwp":
        return annexes.hwp_text(path, txt)
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            text += f"[{ws.title}]\n"
            for row in ws.iter_rows(values_only=True):
                cells = [str(v) for v in row if v not in (None, "")]
                if cells:
                    text += " | ".join(cells) + "\n"
    if ext == ".doc":
        # Word 97 이진 문서: 본문 스트림에서 UTF-16 한글·영문 구간만 건진다(서식 정보는 버린다)
        import olefile
        data = olefile.OleFileIO(str(path)).openstream("WordDocument").read()
        runs = re.findall(rb"(?:[\x20-\x7e\r\n\t]\x00|[\x00-\xff][\xac-\xd7]){4,}", data)
        text = "\n".join(r.decode("utf-16le", errors="ignore") for r in runs)
    if ext in (".hwpx", ".docx"):
        with zipfile.ZipFile(path) as z:
            parts = sorted(n for n in z.namelist() if re.match(r"(Contents/section\d+\.xml|word/document\.xml)$", n))
            for n in parts:
                xml = z.read(n).decode("utf-8", errors="replace")
                xml = re.sub(r"</(hp:p|w:p)>", "\n", xml)
                text += re.sub(r"<[^>]+>", "", xml)
    txt.write_text(text, encoding="utf-8")
    return text


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    cases = list(csv.DictReader(CASES.open(encoding="utf-8-sig")))
    rows, n_new = [], 0
    for c in cases:
        for doc in guide_docs(c["master_id"]):
            for f in attachments(doc):
                existed = any(RAW.glob(f"{doc['invstg_mast_id']}_{doc['bbs_id']}_{f['seq_no']}.*"))
                try:
                    path = download(doc, f)
                    text = text_of(path)
                    err = ""
                except Exception as e:  # 한 파일의 실패가 전체를 멈추지 않게 기록만 한다
                    path, text, err = None, "", str(e)[:200]
                n_new += (not existed) and path is not None
                rows.append({"master_id": c["master_id"], "case_no": c["case_no"], "case_title": c["title"],
                             "doc_title": doc["doc_title"], "file_name": f["file_name"],
                             "file": path.relative_to(ROOT).as_posix() if path else "",
                             "text_chars": len(text.strip()), "error": err})
    cols = ["master_id", "case_no", "case_title", "doc_title", "file_name", "file", "text_chars", "error"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"범위 안내서 파일 {len(rows)}개 (사건 {len({r['master_id'] for r in rows})}건), 새로 받은 것 {n_new}개"
          f" -> {OUT.relative_to(ROOT)}")
    print(f"  텍스트를 뽑지 못한 파일 {sum(r['text_chars'] < 50 for r in rows)}개, 오류 {sum(bool(r['error']) for r in rows)}개")
    exts = {}
    for r in rows:
        e = Path(r["file_name"]).suffix.lower() or "(없음)"
        exts[e] = exts.get(e, 0) + 1
    print("  형식:", exts)


if __name__ == "__main__":
    main()
