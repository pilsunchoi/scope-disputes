"""분쟁 결정을 1단계의 조치(부령)에 연결한다. 3단계 매칭.

키는 결정문이 인용한 부령이다.
  1차 키: 부령 번호(제N호). 종류(기획재정부령 등)와 공포일이 적혀 있으면 함께 맞춘다.
          번호가 여러 판에 걸리면(일괄개정령 등) 제명이 가장 비슷한 판을 고른다.
  1차 키': 번호 없이 제명만 있으면 제명이 같은 조치 가운데 수입기간에 시행 중이던 조치.
인용된 부령이 없는 결정은 보조 키로 찾는다.
  보조 키 1: 쟁점 물품 서술에 조치의 물품명이 들어 있으면 그 조치.
  보조 키 2: 신고·처분 HSK의 앞 네 자리가 한 제명의 조치들의 열거 HSK와 같으면 그 조치.
제명이나 보조 키로 고를 때의 시점은 결정문 처분개요에 적힌 수입기간이다. 수입기간을 읽지 못하면
결정일 이전에 시행된 가장 늦은 조치를 고르고, 방법 칸에 "(결정일 기준)"을 붙여 확인 대상으로 남긴다.
잠정덤핑방지관세 고시는 부령이 아니므로 조치에 연결하지 않고 따로 표시한다.
원문만으로 조치를 특정할 수 있는데 키로 찾지 못한 결정은 data/matching-manual.csv에 근거와 함께 적는다.

    python scripts/11_match_disputes.py

입력:  data/dispute-extract.csv, data/disputes.csv, data/measures.csv, data/decree-texts.csv,
       data/matching-manual.csv
산출:  data/dispute-measure-links.csv   결정 × 조치 연결 (방법, 인용 문구, 점수)
"""
import csv
import difflib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "data" / "dispute-extract.csv"
DISPUTES = ROOT / "data" / "disputes.csv"
MEASURES = ROOT / "data" / "measures.csv"
TEXTS = ROOT / "data" / "decree-texts.csv"
MANUAL = ROOT / "data" / "matching-manual.csv"
OUT = ROOT / "data" / "dispute-measure-links.csv"

KINDS = ["재정경제부령", "기획재정부령", "총리령", "재무부령", "대통령령"]
DATE = r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?"


def norm_name(s):
    s = re.sub(r"관세법\s*제\s*\d+\s*조(?:의\s*규정)?에\s*(?:의한|따른)", "", s)
    s = re.sub(r"\(.*?\)|O+|\s|ㆍ|·|,", "", s)
    s = s.replace("의부과에관한", "부과에관한")
    s = re.sub(r"덤핑방지관세(?:의)?부과(?:에관한)?(?:규칙|규정)?.*$", "", s)
    return re.sub(r"에대한$", "", s)


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def load():
    measures = list(csv.DictReader(MEASURES.open(encoding="utf-8-sig")))
    texts = {t["lsi_seq"]: t for t in csv.DictReader(TEXTS.open(encoding="utf-8-sig"))}
    ver2m = {}
    for m in measures:
        m["key"] = norm_name(m["decree_title"])
        m["goods"] = m["key"][len(norm_name(m["countries"])) + 1:] if m["countries"] else m["key"]  # 대상국을 뗀 물품명
        m["hsk4"] = {h[:4] for h in (m["hsk_listed_first"] + ";" + m["hsk_listed_last"]).split(";") if h}
        for s in m["version_seqs"].split(";"):
            ver2m[s] = m
    return measures, texts, ver2m


def import_period(text):
    """처분개요의 첫 'YYYY.M.D.부터 YYYY.M.D.까지' 또는 'YYYY.M.D. ~ YYYY.M.D.'."""
    m = re.search(DATE + r"\s*(?:부터|[~∼～])\s*" + DATE, text[:6000])
    if not m:
        return None
    g = [int(x) for x in m.groups()]
    return f"{g[0]:04d}-{g[1]:02d}-{g[2]:02d}", f"{g[3]:04d}-{g[4]:02d}-{g[5]:02d}"


def pick(cands, day, period):
    """수입기간과 시행기간이 겹치는 조치들. 기간을 모르면 결정일 이전 가장 늦은 조치 하나."""
    if period:
        start, end = period
        hit = [m for m in cands if m["effective_date"] <= end and
               (not m["sunset_by_validity"] or m["sunset_by_validity"] >= start)]
        if hit:
            return hit, ""
    before = [m for m in cands if m["effective_date"] <= day]
    if before:
        return [max(before, key=lambda m: m["effective_date"])], "(결정일 기준)"
    return [], ""


def match_cited(seg, day, period, measures, texts, ver2m):
    """인용 문구 하나를 조치에 연결한다. [(조치 또는 None, 판 번호, 방법, 점수)]."""
    if re.search(r"고시\s*제", seg):
        return [(None, "", "잠정조치 고시(부령 아님)", "")]
    no = re.search(r"제\s*(\d+)\s*호", seg)
    kind = next((k for k in KINDS if k in seg), None)
    date = re.search(DATE, seg)
    name = norm_name(seg)
    if no:
        cands = [t for t in texts.values() if t["promulgation_no"] == f"제{no[1]}호"
                 and (kind is None or t["kind"] == kind)]
        if date:
            d = f"{int(date[1]):04d}-{int(date[2]):02d}-{int(date[3]):02d}"
            dated = [t for t in cands if d in (t["promulgation_date"], t["effective_date"])]
            same_year = [t for t in cands if t["promulgation_date"][:4] == date[1]]
            cands = dated or same_year or cands
        if cands:
            best = max(cands, key=lambda t: sim(name, norm_name(t["name"])) if name else 0)
            score = sim(name, norm_name(best["name"])) if name else 1.0
            if len(cands) == 1 or score >= 0.5:
                m = ver2m.get(best["lsi_seq"])
                if m:
                    return [(m, best["lsi_seq"], "부령 번호" + ("+공포일" if date else ""), round(score, 2))]
    if name and len(name) >= 3:
        cands = [m for m in measures if sim(name, m["key"]) >= 0.8]
        # 이름이 비슷한 다른 조치(단층 사진플레이트와 더블레이어 등)를 섞지 않도록 가장 비슷한 제명만 남긴다
        top = max((sim(name, m["key"]) for m in cands), default=0)
        cands = [m for m in cands if sim(name, m["key"]) == top]
        hit, flag = pick(cands, day, period)
        return [(m, "", "제명+수입기간" + flag, round(sim(name, m["key"]), 2)) for m in hit]
    return []


def main():
    measures, texts, ver2m = load()
    rows = list(csv.DictReader(EXTRACT.open(encoding="utf-8-sig")))
    text_file = {r["dispute_id"]: r["text_file"] for r in csv.DictReader(DISPUTES.open(encoding="utf-8-sig"))}
    manual = {}
    if MANUAL.exists():
        for m in csv.DictReader(MANUAL.open(encoding="utf-8-sig")):
            manual.setdefault(m["dispute_id"], []).append(m)

    links, summary = [], {}
    for r in rows:
        if r["issue_group"] == "무관":
            continue
        day = r["decision_date"]
        period = import_period((ROOT / text_file[r["dispute_id"]]).read_text(encoding="utf-8"))
        found = []
        for seg in [s.strip() for s in r["cited_decree_titles"].split(";") if s.strip()]:
            for m, seq, method, score in match_cited(seg, day, period, measures, texts, ver2m):
                found.append({"measure_id": m["measure_id"] if m else "", "lsi_seq": seq, "method": method,
                              "score": score, "cited": seg})
        if not any(f["measure_id"] for f in found):
            goods = re.sub(r"\s|ㆍ|·", "", r["disputed_goods"] + r["title"])
            cands = [m for m in measures if len(m["goods"]) >= 3 and m["goods"] in goods]
            hit, flag = pick(cands, day, period)
            method = "보조 키1(물품명)"
            if not hit:
                h4 = set(re.findall(r"(\d{4})\.\d", r["hsk_declared"]))
                cands = [m for m in measures if h4 & m["hsk4"]]
                hit, flag = pick(cands, day, period) if len({c["key"] for c in cands}) == 1 else ([], "")
                method = "보조 키2(HSK)"
            for m in hit:
                found.append({"measure_id": m["measure_id"], "lsi_seq": "", "method": method + flag,
                              "score": "", "cited": ""})
        if not any(f["measure_id"] for f in found):
            for m in manual.get(r["dispute_id"], []):
                found.append({"measure_id": m["measure_id"], "lsi_seq": "", "method": "수작업",
                              "score": "", "cited": m["reason"]})

        seen = set()
        for f in found:
            k = f["measure_id"] or f["method"]
            if k in seen:
                continue
            seen.add(k)
            links.append({"dispute_id": r["dispute_id"], "decision_date": day, "issue_group": r["issue_group"],
                          "import_period": "~".join(period) if period else "", **f})
        status = "연결" if any(f["measure_id"] for f in found) else ("잠정조치만" if found else "미연결")
        summary[r["dispute_id"]] = (status, r["issue_group"])
        if status == "미연결":
            links.append({"dispute_id": r["dispute_id"], "decision_date": day, "issue_group": r["issue_group"],
                          "import_period": "~".join(period) if period else "", "measure_id": "", "lsi_seq": "",
                          "method": "미연결", "score": "", "cited": r["cited_decree_titles"] or r["disputed_goods"][:80]})

    mname = {m["measure_id"]: m["decree_title"] for m in measures}
    for l in links:
        l["measure_title"] = mname.get(l["measure_id"], "")
    cols = ["dispute_id", "decision_date", "issue_group", "import_period", "measure_id", "measure_title", "lsi_seq",
            "method", "score", "cited"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(links)

    n = len(summary)
    ok = [k for k, (s, _) in summary.items() if s == "연결"]
    print(f"대상 결정 {n}건(issue_group 무관 제외) 가운데 조치에 연결 {len(ok)}건 ({len(ok) / n:.0%})"
          f" -> {OUT.relative_to(ROOT)}")
    by = {}
    for l in links:
        if l["measure_id"]:
            key = re.sub(r"\(결정일 기준\)", "", l["method"])
            by[key] = by.get(key, 0) + 1
    print("  연결 방법별 연결 수:", by)
    print("  잠정조치 고시만 인용:", [k for k, (s, _) in summary.items() if s == "잠정조치만"])
    print("  미연결:", [k for k, (s, _) in summary.items() if s == "미연결"])
    print("  결정일 기준으로 고른 연결(확인 대상):", sorted({l["dispute_id"] for l in links if "결정일" in l["method"]}))
    scope = [k for k, (s, g) in summary.items() if g.startswith("조사범위")]
    print(f"  조사범위 결정 {len(scope)}건 가운데 연결 {sum(summary[k][0] == '연결' for k in scope)}건")


if __name__ == "__main__":
    main()
