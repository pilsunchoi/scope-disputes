"""받은 부령 본문에서 조사범위 관련 조문을 뽑고, 판을 조치(measure) 단위로 묶는다.

    python scripts/02_parse_decrees.py

입력:
    data/decree-versions.csv, data/raw/decrees/*.html   (01_collect_decrees.py 산출)
    data/annexes.csv, data/raw/annexes/*.txt            (03_collect_annexes.py 산출, 있으면 쓴다)
산출:
    data/decree-texts.csv   판 단위. 부과대상 물품 조문, 제외 문언, 열거 HSK, 공급자 조문, 유효기간, 별표 제목
    data/measures.csv       조치 단위. 제정(또는 전부개정)마다 새 조치로 보고 뒤따르는 개정판을 묶는다

제외 요건의 유형 코딩(규격/가공상태/용도/분류/복합)은 사람이 한다. 이 스크립트는 코딩할 문언을 모을 뿐이다.
"""
import csv
import re
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "decrees"
VERSIONS = ROOT / "data" / "decree-versions.csv"
OUT_TEXT = ROOT / "data" / "decree-texts.csv"
OUT_MEASURE = ROOT / "data" / "measures.csv"
ANNEXES = ROOT / "data" / "annexes.csv"
RAW_ANNEX = ROOT / "data" / "raw" / "annexes"

ART_RE = re.compile(r"^제(\d+)조(?:의(\d+))?\s*\(([^)]*)\)\s*(.*)$")
HSK_RE = re.compile(r"(?<![\d.])(\d{4}(?:\s*[.\-]\s*\d{1,2}(?:\s*[.\-]?\s*\d{2,4})?)?)(?![\d])")
PREFIX_RE = re.compile(r"^관세법\s*제\s*\d+\s*조(?:의\s*규정)?에\s*(?:의한|따른)\s*")


def body_lines(path):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text("\n")
    lines = [" ".join(l.split()) for l in text.split("\n")]
    return [l for l in lines if l]


def split_parts(lines):
    """본문 조문, 부칙, 별표 제목으로 나눈다."""
    arts, addenda, annex = [], [], []
    cur, zone = None, "pre"
    plain = []  # 조문 번호 없이 단락으로 적힌 본문(1990년대 후반 규칙)
    for l in lines:
        if re.match(r"^부\s*칙", l):
            zone = "addenda"
            cur = None
            continue
        if l.startswith("[별표") or l.startswith("[별지"):
            zone = "annex"
            t = re.sub(r"\s+", " ", l)
            if t not in annex:
                annex.append(t)
            continue
        if zone == "annex":
            continue
        if zone == "addenda":
            addenda.append(l)
            continue
        m = ART_RE.match(l)
        if m:
            cur = {"no": m[1] + (f"의{m[2]}" if m[2] else ""), "title": m[3].strip(), "text": m[4].strip()}
            arts.append(cur)
            zone = "body"
        elif cur is not None and zone == "body":
            cur["text"] = (cur["text"] + " " + l).strip()
        elif zone == "pre" and l.startswith("[시행"):
            zone = "head"
        elif zone == "head":
            plain.append(l)
    if not arts and plain:
        arts = [{"no": "0", "title": "본문(조문 없음) 부과대상물품", "text": " ".join(plain)}]
    return arts, addenda, annex


def pick(arts, *keys):
    return [a for a in arts if any(k in a["title"].replace(" ", "") for k in keys)]


def hsk_codes(text):
    # 조문 번호(제51조), 연도, 호수를 HSK로 오인하지 않도록 '품목' '번호' '제....호' 주변만 본다
    out = []
    for seg in re.findall(r"(?:품목|번호|세번|HSK|HS)[^)]*", text):
        for c in HSK_RE.findall(seg):
            c = re.sub(r"\s", "", c)
            if re.match(r"^(19|20)\d\d$", c):
                continue
            out.append(c)
    for c in re.findall(r"제\s*(\d{4}(?:\.\d{2,})?)\s*호", text):
        out.append(c)
    seen = []
    for c in out:
        if c not in seen:
            seen.append(c)
    return seen


def exclusion_text(scope_arts):
    """부과대상 물품 조문 가운데 제외를 말하는 문장과 그 뒤의 각 호."""
    parts = []
    for a in scope_arts:
        t = a["text"]
        if "제외" not in t:
            continue
        i = t.find("다만")
        j = t.find("제외")
        # 문장 경계는 '다. '로 본다. HSK 번호(3920.62)의 마침표에서 자르지 않도록 한다
        start = i if 0 <= i < j else max(0, t.rfind("다. ", 0, j) + 3 if t.rfind("다. ", 0, j) >= 0 else 0)
        parts.append(t[start:].strip())
    return " / ".join(parts)


KEY = r"(?:유효\s*기간|적용\s*시한|적용\s*기한)"


def validity_years(addenda):
    t = " ".join(addenda)
    m = re.search(KEY + r"[^<]{0,80}?(\d+)\s*년간", t)
    return m[1] if m else ""


def validity_start(addenda):
    """'…부터 N년간'의 기산일이 시행일이 아닌 날짜로 적힌 경우(1990년대 규정의 산업피해판정일 등)."""
    t = " ".join(addenda)
    m = re.search(KEY + r"[^<]{0,80}?(?:(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일|\((\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\))\s*부터\s*\d+\s*년간", t)
    if not m:
        return ""
    y, mo, d = [int(x) for x in (m.groups()[:3] if m[1] else m.groups()[3:])]
    return f"{y:04d}-{mo:02d}-{d:02d}"


def validity_until(addenda):
    """적용시한이 'YYYY년 M월 D일까지'로 적힌 경우의 날짜."""
    t = " ".join(addenda)
    m = re.search(KEY + r"[^<]{0,40}?(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일까지", t)
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else ""


def base_name(name):
    n = PREFIX_RE.sub("", name.replace(" ", ""))
    n = n.replace("의부과에관한", "부과에관한").replace("덤핑방지관세부과에관한규칙", "").replace("덤핑방지관세부과에관한규정", "")
    n = re.sub(r"에대한$", "", n)
    return n.replace("ㆍ", "·")


COUNTRY_NAMES = {"노르웨이", "대만", "독일", "러시아", "말레이시아", "말레이지아", "미국", "베트남", "불가리아", "사우디아라비아",
                 "스웨덴", "스페인", "싱가포르", "싱가폴", "아랍에미리트연합", "우크라이나", "이집트", "이탈리아", "인도",
                 "인도네시아", "일본", "중국", "캐나다", "태국", "프랑스", "핀란드", "호주", "영국", "네덜란드", "벨기에"}


def countries(bname):
    """제명 앞의 '…산'이 나라 이름들일 때만 대상국으로 본다. '정제인산'의 '산'을 잘라 읽지 않기 위해서다."""
    m = re.match(r"^(.+?)산", bname)
    if not m:
        return ""
    toks = [t for t in re.split(r"[·,]|및", m[1]) if t]
    return m[1] if toks and all(t in COUNTRY_NAMES for t in toks) else ""


def load_annexes():
    """판별 별표. 제외 물품 별표와 그 밖의 별표(세율, 약속대상공급자)로 나눈다."""
    out = {}
    if not ANNEXES.exists():
        return out
    for a in csv.DictReader(ANNEXES.open(encoding="utf-8-sig")):
        txt = RAW_ANNEX / f"{a['lsi_seq']}_{a['byl_seq']}.txt"
        a["text"] = " ".join(txt.read_text(encoding="utf-8").split()) if txt.exists() else ""
        a["is_exclusion"] = "제외" in a["annex_title"]
        out.setdefault(a["lsi_seq"], []).append(a)
    return out


def main():
    versions = list(csv.DictReader(VERSIONS.open(encoding="utf-8-sig")))
    annexes = load_annexes()
    texts = []
    for v in versions:
        path = RAW / f"{v['lsi_seq']}_{v['ef_yd']}.html"
        arts, addenda, annex = split_parts(body_lines(path))
        scope = pick(arts, "부과대상물품", "대상물품", "부과물품")
        supplier = pick(arts, "공급자", "적용대상자", "수출자", "수출국")
        scope_text = " || ".join(f"제{a['no']}조({a['title']}) {a['text']}" for a in scope)
        anx = annexes.get(v["lsi_seq"], [])
        ex_anx = [a for a in anx if a["is_exclusion"]]
        texts.append({
            "lsi_seq": v["lsi_seq"], "ef_yd": v["ef_yd"], "name": v["name"],
            "base_name": base_name(v["name"]),
            "kind": v["kind"], "promulgation_no": v["promulgation_no"],
            "promulgation_date": v["promulgation_date"], "effective_date": v["effective_date"],
            "revision_type": v["revision_type"],
            "n_articles": len(arts),
            "scope_text": scope_text,
            "exclusion_text": exclusion_text(scope),
            "hsk_listed": ";".join(hsk_codes(scope_text)),
            "supplier_text": " || ".join(f"제{a['no']}조({a['title']}) {a['text']}" for a in supplier if a not in scope),
            "validity_years": validity_years(addenda),
            "validity_until": validity_until(addenda),
            "validity_start": validity_start(addenda),
            "addenda_text": " ".join(addenda),
            "annex_titles": " | ".join(annex),
            "annex_mentions_exclusion": "Y" if any("제외" in x for x in annex) else "",
            # 제외 물품 별표의 본문. PDF가 없고 HWP만 있으면 비고 칸에 적는다
            "annex_exclusion_text": " || ".join(a["text"] for a in ex_anx if a["text"]),
            "annex_exclusion_missing": "HWP만 있음" if any(not a["text"] for a in ex_anx) else "",
            "annex_other_text": " || ".join(a["text"] for a in anx if not a["is_exclusion"] and a["text"]),
        })

    with OUT_TEXT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(texts[0].keys()))
        w.writeheader()
        w.writerows(texts)

    # 조치 단위로 묶기: 같은 기본 제명 안에서 제정(또는 폐지 뒤 첫 판)이 새 조치를 연다
    by_name = {}
    for t in texts:
        if t["revision_type"] == "일괄개정":
            continue  # 여러 부령을 고치는 개정령. 대상 부령의 타법개정 판으로 이미 들어 있다
        by_name.setdefault(t["base_name"], []).append(t)
    measures = []
    for bname, vs in by_name.items():
        vs.sort(key=lambda t: (t["effective_date"], int(t["lsi_seq"])))
        cur = None
        for t in vs:
            if t["revision_type"] == "폐지":
                if cur:
                    cur["repealed_date"] = t["effective_date"]
                    cur["versions"].append(t)
                continue
            if cur is None or t["revision_type"] == "제정":
                cur = {"first": t, "versions": [t], "repealed_date": ""}
                measures.append(cur)
            else:
                cur["versions"].append(t)

    rows = []
    for i, m in enumerate(sorted(measures, key=lambda m: (m["first"]["effective_date"], m["first"]["base_name"])), 1):
        f0 = m["first"]
        live = [v for v in m["versions"] if v["revision_type"] != "폐지"]
        last = live[-1]
        years = f0["validity_years"]
        start = date.fromisoformat(f0["validity_start"] or f0["effective_date"])
        sunset = f0["validity_until"]
        if years and not sunset:
            try:
                sunset = start.replace(year=start.year + int(years)).isoformat()
            except ValueError:
                sunset = start.replace(year=start.year + int(years), day=28).isoformat()
        rows.append({
            "measure_id": f"M{i:03d}",
            "base_name": f0["base_name"],
            "decree_title": f0["name"],
            "countries": countries(f0["base_name"]),
            "decree_kind": f0["kind"],
            "decree_no": f0["promulgation_no"],
            "enacted_date": f0["promulgation_date"],
            "effective_date": f0["effective_date"],
            "validity_years": years,
            "validity_note": "" if (years or f0["validity_until"]) else "부칙에 유효기간 없음",
            "sunset_by_validity": sunset,
            "repealed_date": m["repealed_date"],
            "n_versions": len(m["versions"]),
            "version_seqs": ";".join(v["lsi_seq"] for v in m["versions"]),
            "hsk_listed_first": f0["hsk_listed"],
            "hsk_listed_last": last["hsk_listed"],
            "has_exclusion_in_body": "Y" if any(v["exclusion_text"] for v in live) else "",
            "annex_mentions_exclusion": "Y" if any(v["annex_mentions_exclusion"] for v in live) else "",
            "scope_text_first": f0["scope_text"],
            "exclusion_text_first": f0["exclusion_text"],
            "exclusion_text_last": last["exclusion_text"],
            "annex_exclusion_text_last": last["annex_exclusion_text"],
            "annex_exclusion_missing": last["annex_exclusion_missing"],
        })

    with OUT_MEASURE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    no_scope = [t["name"] for t in texts if not t["scope_text"] and t["revision_type"] not in ("폐지", "일괄개정")]
    print(f"판 {len(texts)}개 -> {OUT_TEXT.relative_to(ROOT)}")
    print(f"조치 {len(rows)}개 -> {OUT_MEASURE.relative_to(ROOT)}")
    print(f"  본문에 제외 문언이 있는 조치 {sum(r['has_exclusion_in_body'] == 'Y' for r in rows)}개")
    print(f"  별표 제목에 제외가 들어간 조치 {sum(r['annex_mentions_exclusion'] == 'Y' for r in rows)}개"
          f" (별표 텍스트 확보 {sum(bool(r['annex_exclusion_text_last']) for r in rows)}개,"
          f" HWP만 있어 미확보 {sum(bool(r['annex_exclusion_missing']) for r in rows)}개)")
    print(f"  본문이나 별표 어디에도 제외 요건이 없는 조치"
          f" {sum(not r['has_exclusion_in_body'] and r['annex_mentions_exclusion'] != 'Y' for r in rows)}개")
    print(f"  유효기간을 읽지 못한 조치 {sum(not r['sunset_by_validity'] for r in rows)}개")
    print(f"  부과대상 물품 조문을 찾지 못한 판 {len(no_scope)}개")
    for n in no_scope:
        print("    ", n)


if __name__ == "__main__":
    main()
