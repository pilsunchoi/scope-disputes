"""보도자료 추출 행을 무역위원회 사건에 붙이고, 사건별로 신청인과 판정 결과를 모은다. 4단계.

보도자료 행 하나(보도자료 × 사건)를 다음 조건의 사건에 붙인다.
  물품: 13_match_ktc.py와 같은 물품명 비교(표기 대응표 포함)로 0.6 이상.
  대상국: 둘 다 적혀 있으면 한 나라 이상 겹친다.
  시점: 단계 날짜나 보도일 가운데 하나가 조사개시일부터 최종판정일 뒤 6개월 사이. 최종판정일이 없으면 개시일부터
        24개월. 게시판 등록일이 보도자료의 실제 날짜보다 늦은 경우가 있어 두 날짜를 모두 본다.
  종류: 행의 case_type이 원심·종료재심사 등으로 적혀 있으면 사건의 종류와 맞는 것을 앞세운다.
후보가 여럿이면 물품 점수, 대상국 일치도, 종류 일치, 보도일과 개시일의 가까움으로 고른다.

    python scripts/16_link_press_to_cases.py [추출 폴더명]

입력:  data/extraction/<폴더, 기본 press-draft>/press-batch-*.csv, data/ktc-cases.csv
산출:  data/ktc-press-rows.csv       보도자료 × 사건 행 (붙은 사건 master_id와 판단 근거)
       data/ktc-case-outcomes.csv    사건 단위 요약 (신청인, 예비·최종판정 결과, 덤핑률, 건의 세율, 가격약속, 근거 보도자료)
"""
import csv
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "ktc-cases.csv"
OUT_ROWS = ROOT / "data" / "ktc-press-rows.csv"
OUT_CASES = ROOT / "data" / "ktc-case-outcomes.csv"

_spec = importlib.util.spec_from_file_location("ktc", ROOT / "scripts" / "13_match_ktc.py")
ktc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ktc)

COLS = ["bbs_id", "press_date", "product", "countries", "case_type", "stage", "stage_date", "determination",
        "petitioners", "dumping_margin", "proposed_duty", "duty_period", "price_undertaking", "scope_note", "note"]


def shift(d, months):
    return (date.fromisoformat(d) + timedelta(days=30 * months)).isoformat()


def main():
    folder = ROOT / "data" / "extraction" / (sys.argv[1] if len(sys.argv) > 1 else "press-draft")
    rows = []
    for f in sorted(folder.glob("press-batch-*.csv")):
        rows += [{c: (r.get(c) or "").strip() for c in COLS} for r in csv.DictReader(f.open(encoding="utf-8-sig"))]
    cases = list(csv.DictReader(CASES.open(encoding="utf-8-sig")))
    for c in cases:
        c["cset"] = ktc.countries_of(c["countries"].replace(",", "·"))
        c["ok_init"] = c["initiation_date"] if c["initiation_date"] > "1901" else ""

    for r in rows:
        days = [d for d in (r["stage_date"], r["press_date"]) if d]
        rset = ktc.countries_of(r["countries"].replace(",", "·"))
        best = None
        for c in cases:
            g = max(ktc.goods_score(r["product"], c["product"]), ktc.goods_score(r["product"], c["title"]))
            if g < 0.6 or not c["ok_init"] or not days:
                continue
            if rset and c["cset"] and not (rset & c["cset"]):
                continue
            end = shift(c["final_date"], 6) if c["final_date"] else shift(c["ok_init"], 24)
            if not any(shift(c["ok_init"], -1) <= d <= end for d in days):
                continue
            overlap = len(rset & c["cset"]) / len(rset | c["cset"]) if rset and c["cset"] else 0
            same_type = 0.2 if r["case_type"] and r["case_type"] != "불명" and r["case_type"] in c["case_type"] else 0
            score = g + overlap / 5 + same_type
            if best is None or score > best[0]:
                best = (score, c, g)
        if best:
            r.update({"master_id": best[1]["master_id"], "ktc_case_no": best[1]["case_no"],
                      "ktc_title": best[1]["title"], "match_score": round(best[0], 2)})
        else:
            r.update({"master_id": "", "ktc_case_no": "", "ktc_title": "", "match_score": ""})

    with OUT_ROWS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS + ["master_id", "ktc_case_no", "ktc_title", "match_score"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["press_date"], r["bbs_id"])))

    by_case = {}
    for r in rows:
        if r["master_id"]:
            by_case.setdefault(r["master_id"], []).append(r)
    out = []
    for c in cases:
        rs = sorted(by_case.get(c["master_id"], []), key=lambda r: r["press_date"])
        if not rs:
            continue
        pet = []
        for r in rs:
            for p in r["petitioners"].split(","):
                p = p.strip()
                if p and p not in pet:
                    pet.append(p)
        stage_rows = lambda key: [r for r in rs if key in r["stage"]]
        prelim, final = stage_rows("예비"), stage_rows("최종") + stage_rows("재심사 판정")
        last = lambda lst, col: next((r[col] for r in reversed(lst) if r[col]), "")
        out.append({
            "master_id": c["master_id"], "case_no": c["case_no"], "title": c["title"], "case_type": c["case_type"],
            "petitioners": ", ".join(pet),
            "prelim_determination": last(prelim, "determination"), "prelim_proposed_duty": last(prelim, "proposed_duty"),
            "final_determination": last(final, "determination"), "final_dumping_margin": last(final, "dumping_margin"),
            "final_proposed_duty": last(final, "proposed_duty"), "duty_period": last(final, "duty_period"),
            "price_undertaking": "Y" if any(r["price_undertaking"] == "Y" for r in rs) else
                                 ("N" if any(r["price_undertaking"] == "N" for r in rs) else "불명"),
            "scope_note": " / ".join(r["scope_note"] for r in rs if r["scope_note"]),
            "press_ids": ";".join(dict.fromkeys(r["bbs_id"] for r in rs)),
        })
    with OUT_CASES.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    n = len(rows)
    linked = sum(bool(r["master_id"]) for r in rows)
    print(f"보도자료 행 {n}개 가운데 사건에 붙은 것 {linked}개 ({linked / n:.0%}) -> {OUT_ROWS.relative_to(ROOT)}")
    print(f"결과가 채워진 사건 {len(out)}건 / 전체 {len(cases)}건 -> {OUT_CASES.relative_to(ROOT)}")
    print(f"  신청인 {sum(bool(o['petitioners']) for o in out)}건, 최종판정 결과 {sum(bool(o['final_determination']) for o in out)}건,"
          f" 예비판정 결과 {sum(bool(o['prelim_determination']) for o in out)}건")
    print("  붙지 못한 행:", [(r["bbs_id"], r["product"][:15], r["press_date"]) for r in rows if not r["master_id"]][:30])


if __name__ == "__main__":
    main()
