"""코더 한 명의 배치별 코딩을 합치고 코드북의 값 규칙을 검사한다.

    python scripts/05_merge_coding.py [코더 폴더명] [산출 파일명]
    python scripts/05_merge_coding.py draft coder-a.csv      # 초벌(Claude) 코딩

입력:  data/coding/<코더 폴더>/batch-*.csv, data/coding/input/batch-*.jsonl
산출:  data/coding/<산출 파일명>
검사:  입력의 모든 조치가 한 번씩 있는지, 값이 코드북 목록 안에 있는지, 요약 유형이 유형 목록과 맞는지
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODING = ROOT / "data" / "coding"

COLS = ["measure_id", "scope_positive_types", "scope_positive_summary", "exclusion_present",
        "exclusion_location", "exclusion_types", "exclusion_summary", "n_exclusion_items", "use_based",
        "changed_across_versions", "evidence_positive", "evidence_exclusion", "confidence", "note"]
TYPES = ["규격", "가공상태", "용도", "분류", "제품지정"]
SUMMARY = set(TYPES) | {"없음", "복합"}
ALLOWED = {
    "exclusion_present": {"Y", "N"},
    "exclusion_location": {"본문", "별표", "둘다", "없음"},
    "use_based": {"Y", "N"},
    "changed_across_versions": {"Y", "N"},
    "confidence": {"높음", "중간", "낮음"},
}


def summary_of(types):
    return "없음" if not types else (types[0] if len(types) == 1 else "복합")


def check(r):
    errs = []
    for col, ok in ALLOWED.items():
        if r[col] not in ok:
            errs.append(f"{col}={r[col]!r}")
    for part in ("scope_positive", "exclusion"):
        types = [t for t in r[f"{part}_types"].split(";") if t]
        bad = [t for t in types if t not in TYPES]
        if bad:
            errs.append(f"{part}_types에 없는 유형 {bad}")
        if r[f"{part}_summary"] not in SUMMARY:
            errs.append(f"{part}_summary={r[f'{part}_summary']!r}")
        elif r[f"{part}_summary"] != summary_of(types):
            errs.append(f"{part}_summary {r[f'{part}_summary']} != 유형 {types}")
    if (r["exclusion_present"] == "N") != (r["exclusion_location"] == "없음"):
        errs.append("exclusion_present와 exclusion_location 불일치")
    if r["exclusion_present"] == "Y" and not r["exclusion_types"]:
        errs.append("제외 있음인데 유형 없음")
    if not r["n_exclusion_items"].isdigit():
        errs.append(f"n_exclusion_items={r['n_exclusion_items']!r}")
    return errs


def main():
    coder = sys.argv[1] if len(sys.argv) > 1 else "draft"
    out = CODING / (sys.argv[2] if len(sys.argv) > 2 else f"{coder}.csv")
    expected = [json.loads(l)["measure_id"] for f in sorted((CODING / "input").glob("batch-*.jsonl"))
                for l in f.open(encoding="utf-8")]
    rows = []
    for f in sorted((CODING / coder).glob("batch-*.csv"), key=lambda p: int(p.stem.split("-")[1])):
        for r in csv.DictReader(f.open(encoding="utf-8-sig")):
            rows.append({c: (r.get(c) or "").strip() for c in COLS})

    ids = [r["measure_id"] for r in rows]
    missing = [m for m in expected if m not in ids]
    dup = [m for m, n in Counter(ids).items() if n > 1]
    problems = {r["measure_id"]: e for r in rows if (e := check(r))}

    rows.sort(key=lambda r: expected.index(r["measure_id"]) if r["measure_id"] in expected else 10**6)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)}행 -> {out.relative_to(ROOT)} (빠진 조치 {len(missing)}, 중복 {len(dup)})")
    for m in missing + dup:
        print("  확인 필요:", m)
    print(f"값 규칙 위반 {len(problems)}행")
    for m, e in problems.items():
        print(f"  {m}: {'; '.join(e)}")
    for col in ("scope_positive_summary", "exclusion_summary", "exclusion_location", "use_based", "confidence"):
        print(f"{col}: {dict(Counter(r[col] for r in rows).most_common())}")


if __name__ == "__main__":
    main()
