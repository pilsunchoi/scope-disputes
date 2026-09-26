"""부령 판마다 붙은 별표의 목록을 만들고 PDF를 받아 텍스트를 뽑는다.

별표에는 공급자별 덤핑방지관세율과, 많은 조치에서 부과대상에서 제외되는 물품 목록이 들어 있다.
국가법령정보센터는 별표를 HWP·PDF 파일로만 제공한다(화면 보기도 이미지다). PDF가 있으면 PDF를,
옛 별표처럼 HWP만 있으면 HWP를 받는다. HWP 텍스트는 본문 스트림(BodyText)의 문단 레코드에서 직접 읽는다.
olefile 패키지가 필요하다.

    python scripts/03_collect_annexes.py

입력:
    data/decree-versions.csv, data/raw/decrees/*.html   (01_collect_decrees.py 산출)
산출:
    data/annexes.csv                          별표 단위 목록 (판, 별표 번호·제목, 파일 번호, 받은 여부, 텍스트 길이)
    data/raw/annexes/<lsiSeq>_<bylSeq>.pdf    별표 PDF 원본
    data/raw/annexes/<lsiSeq>_<bylSeq>.hwp    PDF가 없는 별표의 HWP 원본
    data/raw/annexes/<lsiSeq>_<bylSeq>.txt    뽑은 텍스트 (PDF는 pdftotext -raw, HWP는 hwp_text)
"""
import csv
import re
import subprocess
import time
from pathlib import Path

import struct
import zlib

import olefile
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DECREE = ROOT / "data" / "raw" / "decrees"
RAW = ROOT / "data" / "raw" / "annexes"
VERSIONS = ROOT / "data" / "decree-versions.csv"
OUT = ROOT / "data" / "annexes.csv"

BASE = "https://www.law.go.kr/LSW/"
UA = {"User-Agent": "Mozilla/5.0 (research; scope-disputes)"}
PAUSE = 0.5

# 별표 하나의 머리: bylInfoDiv('번호') 링크의 제목, 이어지는 HWP·PDF 다운로드 링크
ENTRY_RE = re.compile(
    r"bylInfoDiv\('(?P<byl>\d+)'\);\"\s*href=\"#AJAX\">\s*(?P<title>\[별[표지][^<]*?)\s*</a>(?P<rest>.*?)</span>",
    re.S,
)
FILE_RE = re.compile(r'flDownload\.do\?gubun=&amp;(?:flExt=\w+&amp;)?flSeq=(\d+)&amp;bylClsCd=\d+"[^>]*>\s*<img alt="(HWP|PDF)')


def annex_entries(html):
    out = {}
    for m in ENTRY_RE.finditer(html):
        byl = m["byl"]
        if byl in out:
            continue
        files = {kind: seq for seq, kind in FILE_RE.findall(m["rest"])}
        title = " ".join(m["title"].split())
        no = re.match(r"\[별[표지]\s*(\d*)\]", title)
        out[byl] = {
            "byl_seq": byl, "annex_no": no[1] if no else "", "annex_title": title,
            "pdf_fl_seq": files.get("PDF", ""), "hwp_fl_seq": files.get("HWP", ""),
        }
    return list(out.values())


MAGIC = {".pdf": b"%PDF", ".hwp": b"\xd0\xcf\x11\xe0"}  # HWP 5.0은 OLE 복합 문서


def download(fl_seq, path):
    if path.exists() and path.stat().st_size > 0:
        return False
    r = requests.get(BASE + "flDownload.do", params={"gubun": "", "flSeq": fl_seq, "bylClsCd": "110201"},
                     headers=UA, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(MAGIC[path.suffix]):
        raise ValueError(f"{path.suffix} 형식이 아닌 응답: flSeq={fl_seq}, {r.headers.get('Content-Type')}")
    path.write_bytes(r.content)
    time.sleep(PAUSE)
    return True


def hwp_text(hwp, txt):
    """HWP 5.0 본문의 문단 텍스트(HWPTAG_PARA_TEXT=67) 레코드를 순서대로 잇는다."""
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    ole = olefile.OleFileIO(str(hwp))
    compressed = struct.unpack("<I", ole.openstream("FileHeader").read()[36:40])[0] & 1
    sections = sorted((e for e in ole.listdir() if e[0] == "BodyText"), key=lambda e: int(e[1][7:]))
    paras = []
    for sec in sections:
        data = ole.openstream(sec).read()
        if compressed:
            data = zlib.decompress(data, -15)
        i = 0
        while i + 4 <= len(data):
            h = struct.unpack("<I", data[i:i + 4])[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                size = struct.unpack("<I", data[i:i + 4])[0]
                i += 4
            if tag == 67:
                paras.append(para_chars(data[i:i + size]))
            i += size
    ole.close()
    text = "\n".join(p for p in paras if p.strip())
    txt.write_text(text, encoding="utf-8", errors="replace")  # 짝 없는 서로게이트 문자가 섞인 문서가 있다
    return text


def para_chars(b):
    """문단 텍스트의 UTF-16 문자열. 제어문자 가운데 0·10·13은 한 글자, 나머지는 여덟 글자 폭이다."""
    out, j = [], 0
    n = len(b) // 2
    while j < n:
        c = struct.unpack("<H", b[2 * j:2 * j + 2])[0]
        if c >= 32:
            out.append(chr(c))
            j += 1
        elif c in (0, 10, 13):
            out.append("\n" if c in (10, 13) else "")
            j += 1
        else:
            j += 8
    return "".join(out)


def pdf_text(pdf, txt):
    if not txt.exists():
        subprocess.run(["pdftotext", "-raw", "-enc", "UTF-8", str(pdf), str(txt)], check=True)
    return txt.read_text(encoding="utf-8", errors="replace")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    versions = list(csv.DictReader(VERSIONS.open(encoding="utf-8-sig")))
    rows, new = [], 0
    for v in versions:
        html = (RAW_DECREE / f"{v['lsi_seq']}_{v['ef_yd']}.html").read_text(encoding="utf-8")
        for e in annex_entries(html):
            row = {"lsi_seq": v["lsi_seq"], "ef_yd": v["ef_yd"], "name": v["name"], **e,
                   "source_file": "", "text_chars": ""}
            if e["pdf_fl_seq"]:
                src = RAW / f"{v['lsi_seq']}_{e['byl_seq']}.pdf"
                new += download(e["pdf_fl_seq"], src)
                text = pdf_text(src, src.with_suffix(".txt"))
            elif e["hwp_fl_seq"]:
                src = RAW / f"{v['lsi_seq']}_{e['byl_seq']}.hwp"
                new += download(e["hwp_fl_seq"], src)
                text = hwp_text(src, src.with_suffix(".txt"))
            else:
                src, text = None, ""
            if src:
                row["source_file"] = src.relative_to(ROOT).as_posix()
                row["text_chars"] = len(text.strip())
            rows.append(row)

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    pdf = [r for r in rows if r["source_file"].endswith(".pdf")]
    hwp = [r for r in rows if r["source_file"].endswith(".hwp")]
    empty = [r for r in rows if r["source_file"] and int(r["text_chars"] or 0) < 50]
    print(f"별표 {len(rows)}개 (판 {len({r['lsi_seq'] for r in rows})}개) -> {OUT.relative_to(ROOT)}")
    print(f"  PDF {len(pdf)}개, HWP {len(hwp)}개, 이번에 새로 받은 것 {new}개")
    print(f"  파일이 없는 것 {len(rows) - len(pdf) - len(hwp)}개")
    print(f"  텍스트가 거의 없는 것 {len(empty)}개", *[r["source_file"] for r in empty])


if __name__ == "__main__":
    main()
