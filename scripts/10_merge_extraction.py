"""묶음별 결정문 추출을 합치고 추출 지침(data/extraction/guide.md)의 값 규칙을 검사한다.

    python scripts/10_merge_extraction.py [추출 폴더명]
    python scripts/10_merge_extraction.py draft       # 묶음별 초벌
    python scripts/10_merge_extraction.py draft-v2    # 정리본(disputes.csv, citations.csv 한 벌)

입력:  data/extraction/<폴더>/disputes*.csv, citations*.csv, data/disputes.csv
산출:  data/dispute-extract.csv   결정 단위 추출 (data/disputes.csv의 목록 칸을 앞에 붙인다)
       data/dispute-citations.csv 원용된 행정기관 회신
"""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPUTES = ROOT / "data" / "disputes.csv"
OUT = ROOT / "data" / "dispute-extract.csv"
OUT_CIT = ROOT / "data" / "dispute-citations.csv"

COLS = ["dispute_id", "decision_group", "dispute_chain", "relevance", "issue_group", "cited_decree_titles", "disputed_goods", "hsk_declared",
        "claimant_argument", "agency_argument", "outcome_raw", "outcome", "taxpayer_win", "reasoning_summary",
        "scope_criteria_used", "ktc_reference", "related_cases", "confidence", "note"]
CIT_COLS = ["dispute_id", "issuing_agency", "document", "reply_date", "cited_by", "reply_position", "adopted", "summary",
            "scope_related", "reply_key"]
ALLOWED = {
    "relevance": {"쟁점", "언급", "무관"},
    "issue_group": {"조사범위", "조사범위 부수", "공급자·세율", "가격약속·과세가격", "불복 적격", "기타", "무관"},
    "outcome": {"인용", "일부인용", "기각", "각하", "재조사"},
    "taxpayer_win": {"Y", "N"},
    "confidence": {"높음", "중간", "낮음"},
}
CIT_ALLOWED = {
    "cited_by": {"청구인", "처분청", "심판기관", "여럿"},
    "reply_position": {"부과대상 포함", "부과대상 제외", "기타"},
    "adopted": {"Y", "N", "불명"},
    "scope_related": {"Y", "N", ""},
}
TYPES = {"규격", "가공상태", "용도", "분류", "제품지정"}


def main():
    folder = ROOT / "data" / "extraction" / (sys.argv[1] if len(sys.argv) > 1 else "draft")
    base = {r["dispute_id"]: r for r in csv.DictReader(DISPUTES.open(encoding="utf-8-sig"))}
    rows, cits = [], []
    for f in sorted(folder.glob("disputes*.csv")):
        rows += [{c: (r.get(c) or "").strip() for c in COLS} for r in csv.DictReader(f.open(encoding="utf-8-sig"))]
    for f in sorted(folder.glob("citations*.csv")):
        cits += [{c: (r.get(c) or "").strip() for c in CIT_COLS} for r in csv.DictReader(f.open(encoding="utf-8-sig"))]

    ids = [r["dispute_id"] for r in rows]
    missing = sorted(set(base) - set(ids))
    dup = [k for k, n in Counter(ids).items() if n > 1]
    problems = []
    for r in rows:
        # 초벌에는 묶음·연쇄 칸이 없다. 없으면 자기 자신을 가리킨다
        r["decision_group"] = r["decision_group"] or r["dispute_id"]
        r["dispute_chain"] = r["dispute_chain"] or r["dispute_id"]
        for g in ("decision_group", "dispute_chain"):
            if r[g] not in base:
                problems.append(f"{r['dispute_id']} {g}={r[g]!r}: 목록에 없는 결정")
        for col, ok in ALLOWED.items():
            if r[col] not in ok:
                problems.append(f"{r['dispute_id']} {col}={r[col]!r}")
        if r["relevance"] != "쟁점" and r["issue_group"] != "무관":
            problems.append(f"{r['dispute_id']} relevance={r['relevance']}인데 issue_group={r['issue_group']}")
        bad = [t for t in r["scope_criteria_used"].split(";") if t.strip() and t.strip() not in TYPES]
        if bad:
            problems.append(f"{r['dispute_id']} scope_criteria_used에 없는 유형 {bad}")
        if (r["outcome"] in ("인용", "일부인용", "재조사")) != (r["taxpayer_win"] == "Y"):
            problems.append(f"{r['dispute_id']} outcome={r['outcome']} taxpayer_win={r['taxpayer_win']}")
    for c in cits:
        for col, ok in CIT_ALLOWED.items():
            if c[col] not in ok:
                problems.append(f"인용 {c['dispute_id']} {col}={c[col]!r}")
        if c["dispute_id"] not in base:
            problems.append(f"인용 {c['dispute_id']}: 목록에 없는 결정")

    lead = ["dispute_id", "forum", "case_no", "decision_date", "title", "clip_case_nos", "stage0_issue_group"]
    out = [{**{k: base[r["dispute_id"]][k] for k in lead}, **r} for r in rows if r["dispute_id"] in base]
    out.sort(key=lambda r: r["dispute_id"])
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=lead + COLS[1:])
        w.writeheader()
        w.writerows(out)
    cits.sort(key=lambda c: (c["dispute_id"], c["reply_date"]))
    with OUT_CIT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CIT_COLS)
        w.writeheader()
        w.writerows(cits)

    print(f"결정 {len(out)}행 -> {OUT.relative_to(ROOT)} (빠진 결정 {len(missing)}, 중복 {len(dup)})", *missing, *dup)
    print(f"회신 {len(cits)}행 -> {OUT_CIT.relative_to(ROOT)}")
    print(f"값 규칙 위반 {len(problems)}건")
    for p in problems:
        print("  ", p)
    for col in ("relevance", "issue_group", "outcome", "confidence"):
        print(f"{col}: {dict(Counter(r[col] for r in out).most_common())}")


if __name__ == "__main__":
    main()
