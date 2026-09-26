"""1단계의 조치(부령)를 무역위원회 반덤핑조사 사건에 연결한다. 4단계.

조치 하나에 대해 다음을 모두 만족하는 사건 가운데 점수가 가장 높은 것을 고른다.
  물품: 사건의 품목·건명과 조치 제명의 물품명이 비슷하다(유사도, 포함 관계, 괄호 속 약칭).
  대상국: 둘 다 적혀 있으면 한 나라 이상 겹친다.
  시점: 사건의 최종판정일(없으면 조사개시일)이 조치 시행일보다 앞서고, 그 간격이 최종판정일 기준
        24개월, 조사개시일 기준 36개월 안이다.
후보가 여럿이면 물품 유사도에 대상국 구성의 일치도(자카드)를 더하고 시행일까지의 간격을 뺀 점수로 고른다.
사건의 재심 종류(원심, 종료재심사, 중간재심사, 우회덤핑 등)는 건명에서 읽는다.

    python scripts/13_match_ktc.py

입력:  data/measures.csv, data/ktc-cases.csv
산출:  data/measure-ktc-links.csv   조치 × 사건 (점수, 간격, 판단 근거). 연결하지 못한 조치도 한 행씩 남긴다
       data/ktc-cases.csv에 case_type 칸을 더해 다시 쓴다
"""
import csv
import difflib
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEASURES = ROOT / "data" / "measures.csv"
CASES = ROOT / "data" / "ktc-cases.csv"
OUT = ROOT / "data" / "measure-ktc-links.csv"

ALIAS = {"대만": "대만", "중화민국": "대만", "말레이지아": "말레이시아", "말련": "말레이시아", "싱가폴": "싱가포르",
         "인니": "인도네시아", "아랍에미리트연합": "아랍에미리트", "아랍에미리트연방": "아랍에미리트", "UAE": "아랍에미리트",
         "타이": "태국", "이태리": "이탈리아"}
# 무역위원회와 부령이 같은 물품을 다르게 적는 표기. 물품명을 비교하기 전에 앞쪽 표기로 바꾼다
GOODS_ALIAS = [("에이치", "H"), ("시디알", "CD-R"), ("폴리에틸렌테레프탈레이트", "PET"), ("폴리(에틸렌테레프탈레이트)", "PET"),
               ("스테인레스", "스테인리스"), ("스틸", "강"), ("인쇄제판용평면상사진플레이트", "PS인쇄판"),
               ("인쇄제판용평면모양사진플레이트", "PS인쇄판"), ("옵셋인쇄판", "PS인쇄판"), ("폴리비닐알콜", "폴리비닐알코올"),
               ("염화코린", "염화콜린"), ("판유리", "판유리"), ("수산화알미늄", "수산화알루미늄"),
               ("DTY", "연신가공사"), ("POY", "부분연신사"), ("FDY", "완전연신사")]


def case_type(title, review):
    t = title.replace(" ", "")
    if "우회" in t:
        return "우회덤핑"
    if "종료재심" in t or ("재심" in t and "종료" in t):
        return "종료재심사"
    if "제외" in t and ("부과대상" in t or "적용대상" in t):
        return "중간재심사(부과대상 제외)"
    if "중간재심" in t or "상황변동" in t or "변경" in t:
        return "중간재심사"
    if "약속" in t and ("수락" in t or "제의" in t):
        return "가격약속 검토"
    if review == "재심" or "재심" in title:
        return "재심(종류 미상)"
    return "원심"


def norm(s):
    s = re.sub(r"\s|ㆍ|·|,|-", "", s)
    for a, b in GOODS_ALIAS:
        s = s.replace(a, b)
    s = re.sub(r"(덤핑|뎀핑)(수입|사실).*$|에대한.*$|의덤핑.*$", "", s)
    return s


def countries_of(s):
    out = set()
    for tok in re.split(r"[·ㆍ,\s및]+|산$", s):
        tok = ALIAS.get(tok.strip(), tok.strip())
        if tok and len(tok) <= 8:
            out.add(tok)
    return out


def goods_forms(s):
    """물품명의 여러 표기: 전체, 괄호 밖, 괄호 속 약칭."""
    s = norm(s)
    forms = {s, re.sub(r"\(.*?\)", "", s)}
    forms |= set(re.findall(r"\(([^)]+)\)", s))
    return {f for f in forms if len(f) >= 2}


def goods_score(a, b):
    best = 0.0
    for x in goods_forms(a):
        for y in goods_forms(b):
            if len(x) >= 2 and len(y) >= 2 and (x in y or y in x):
                best = max(best, 0.9)
            best = max(best, difflib.SequenceMatcher(None, x, y).ratio())
    return best


def months(a, b):
    a, b = date.fromisoformat(a), date.fromisoformat(b)
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30


def main():
    measures = list(csv.DictReader(MEASURES.open(encoding="utf-8-sig")))
    cases = list(csv.DictReader(CASES.open(encoding="utf-8-sig")))
    for c in cases:
        c["case_type"] = case_type(c["title"], c["review_type"])
        c["cset"] = countries_of(c["countries"].replace(",", "·"))
    with CASES.open("w", encoding="utf-8-sig", newline="") as f:
        cols = [k for k in cases[0] if k != "cset"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(cases)

    links = []
    for m in measures:
        goods = m["base_name"][len(m["countries"]) + 1:] if m["countries"] else m["base_name"]  # "…산"을 뗀 물품명
        mset = countries_of(m["countries"])
        eff = m["effective_date"]
        best = None
        for c in cases:
            g = max(goods_score(goods, c["product"]), goods_score(goods, c["title"]))
            if g < 0.6:
                continue
            if mset and c["cset"] and not (mset & c["cset"]):
                continue
            if c["case_type"] == "가격약속 검토":
                continue  # 조치를 새로 만드는 사건이 아니다
            anchor, limit = (c["final_date"], 24) if c["final_date"] else (c["initiation_date"], 36)
            if not anchor or anchor < "1901" or anchor > eff:
                continue
            gap = months(anchor, eff)
            if gap > limit:
                continue
            # 물품이 같으면 대상국 구성이 더 잘 맞고 시행일에 가까운 사건
            overlap = len(mset & c["cset"]) / len(mset | c["cset"]) if mset and c["cset"] else 0
            score = g + overlap / 10 - gap / 100
            if best is None or score > best[0]:
                best = (score, c, g, gap, anchor == c["final_date"])
        row = {"measure_id": m["measure_id"], "decree_title": m["decree_title"], "effective_date": eff,
               "measure_countries": m["countries"]}
        if best:
            score, c, g, gap, by_final = best
            row.update({"master_id": c["master_id"], "ktc_case_no": c["case_no"], "ktc_title": c["title"],
                        "case_type": c["case_type"], "ktc_countries": c["countries"],
                        "initiation_date": c["initiation_date"], "final_date": c["final_date"],
                        "goods_score": round(g, 2), "gap_months": round(gap, 1),
                        "anchor": "최종판정일" if by_final else "조사개시일",
                        # 최종판정 뒤 부령까지는 보통 몇 달, 조사개시 뒤로는 1년 남짓이다
                        "confidence": "높음" if g >= 0.85 and gap <= (6 if by_final else 18)
                        else ("중간" if g >= 0.7 else "낮음")})
        else:
            row.update({"confidence": "미연결"})
        links.append(row)

    cols = ["measure_id", "decree_title", "effective_date", "measure_countries", "master_id", "ktc_case_no",
            "ktc_title", "case_type", "ktc_countries", "initiation_date", "final_date", "goods_score", "gap_months",
            "anchor", "confidence"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(links)

    ok = [l for l in links if l["confidence"] != "미연결"]
    conf = {}
    for l in links:
        conf[l["confidence"]] = conf.get(l["confidence"], 0) + 1
    print(f"조치 {len(links)}개 가운데 사건에 연결 {len(ok)}개 ({len(ok) / len(links):.0%}) -> {OUT.relative_to(ROOT)}")
    print("  확신도:", conf)
    dup = {}
    for l in ok:
        dup.setdefault(l["master_id"], []).append(l["measure_id"])
    print("  한 사건에 조치 둘 이상이 연결된 경우:", {k: v for k, v in dup.items() if len(v) > 1})
    print("  미연결:", [l["measure_id"] for l in links if l["confidence"] == "미연결"])


if __name__ == "__main__":
    main()
