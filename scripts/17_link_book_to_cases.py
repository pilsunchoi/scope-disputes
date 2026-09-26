"""'무역위원회 30년의 발자취'(2017) 부록의 사건별 조치내역을 무역위원회 사건에 붙이고,
보도자료에서 모은 결과와 합쳐 사건 단위 요약을 만든다. 4단계.

책의 사건 행 하나를 다음 조건의 사건에 붙인다.
  물품: 13_match_ktc.py와 같은 물품명 비교로 0.6 이상. 대상국: 둘 다 있으면 한 나라 이상 겹친다.
  시점: 책의 조치일이 사건 최종판정일의 앞뒤 4개월 안이거나, 책의 신청일이 사건 조사개시일의 앞 4개월~뒤 1개월 안.
        옛 사건은 누리집에 개시일이 1900-01-01로 적혀 있어 최종판정일을 주로 쓴다.
  종류: 책이 원심·재심을 적었으면 사건의 종류와 맞는 것을 앞세운다.
책은 1987년~2017년 6월 신청분까지 담는다. 보도자료는 2008년 11월 이후를 담는다.
두 자료가 겹치는 사건은 신청인을 합치고, 판정 결과는 보도자료를 앞세운다(더 자세하다).

    python scripts/17_link_book_to_cases.py

입력:  data/ktc-book-cases.csv (책 부록의 구조화), data/ktc-cases.csv, data/ktc-case-outcomes.csv (16 산출)
산출:  data/ktc-book-links.csv     책의 사건 행 × 무역위원회 사건
       data/ktc-case-summary.csv   사건 단위 요약 (신청인, 결과 종류, 최종 결과, 세율, 기간, 가격약속, 출처)
"""
import csv
import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "data" / "ktc-book-cases.csv"
CASES = ROOT / "data" / "ktc-cases.csv"
PRESS = ROOT / "data" / "ktc-case-outcomes.csv"
OUT_LINKS = ROOT / "data" / "ktc-book-links.csv"
OUT = ROOT / "data" / "ktc-case-summary.csv"

_spec = importlib.util.spec_from_file_location("ktc", ROOT / "scripts" / "13_match_ktc.py")
ktc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ktc)


def days(a, b):
    """두 날짜의 간격(일). 책의 오식("200.11.24" 등)처럼 읽을 수 없는 날짜면 None."""
    def d(x):
        x = x + "-15" if len(x) == 7 else x
        return date.fromisoformat(x)
    try:
        return (d(b) - d(a)).days
    except ValueError:
        return None


def main():
    book = list(csv.DictReader(BOOK.open(encoding="utf-8-sig")))
    cases = list(csv.DictReader(CASES.open(encoding="utf-8-sig")))
    for c in cases:
        c["cset"] = ktc.countries_of(c["countries"].replace(",", "·"))
        c["init"] = c["initiation_date"] if c["initiation_date"] > "1901" else ""

    links, used = [], {}
    for b in book:
        bset = ktc.countries_of(b["countries"].replace(",", "·"))
        best = None
        for c in cases:
            g = max(ktc.goods_score(b["product"], c["product"]), ktc.goods_score(b["product"], c["title"]))
            if g < 0.6:
                continue
            if bset and c["cset"] and not (bset & c["cset"]):
                continue
            gf = days(b["outcome_date"], c["final_date"]) if b["outcome_date"] and c["final_date"] else None
            gi = days(b["petition_date"], c["init"]) if b["petition_date"] and c["init"] else None
            ok_final = gf is not None and abs(gf) <= 120
            ok_init = gi is not None and -30 <= gi <= 120
            if not (ok_final or ok_init):
                continue
            kind = b["case_kind"]
            same = 0.2 if (kind.startswith("원심") and c["case_type"] == "원심") or \
                          ("재심" in kind and c["case_type"] != "원심") else 0
            overlap = len(bset & c["cset"]) / len(bset | c["cset"]) if bset and c["cset"] else 0
            score = g + overlap / 5 + same + (0.1 if ok_final and ok_init else 0)
            if best is None or score > best[0]:
                best = (score, c)
        row = {**b, "master_id": "", "ktc_case_no": "", "ktc_title": "", "match_score": ""}
        if best:
            c = best[1]
            row.update({"master_id": c["master_id"], "ktc_case_no": c["case_no"], "ktc_title": c["title"],
                        "match_score": round(best[0], 2)})
            used.setdefault(c["master_id"], []).append(row)
        links.append(row)

    with OUT_LINKS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(links[0].keys()))
        w.writeheader()
        w.writerows(links)

    press = {p["master_id"]: p for p in csv.DictReader(PRESS.open(encoding="utf-8-sig"))}
    out = []
    for c in cases:
        p, bs = press.get(c["master_id"]), used.get(c["master_id"], [])
        if not p and not bs:
            continue
        pet = []
        for s in ([p["petitioners"]] if p else []) + [b["petitioners"] for b in bs]:
            for x in s.split(","):
                x = x.strip()
                if x and x not in pet:
                    pet.append(x)
        b = bs[-1] if bs else {}
        out.append({
            "master_id": c["master_id"], "case_no": c["case_no"], "title": c["title"], "case_type": c["case_type"],
            "petitioners": ", ".join(pet),
            "outcome_type": b.get("outcome_type", ""),
            "final_determination": (p or {}).get("final_determination", ""),
            "prelim_determination": (p or {}).get("prelim_determination", ""),
            "duty_rate": (p or {}).get("final_proposed_duty", "") or b.get("duty_rate", ""),
            "dumping_margin": (p or {}).get("final_dumping_margin", ""),
            "duty_period": (p or {}).get("duty_period", "") or b.get("duty_period", ""),
            "price_undertaking": "Y" if ((p or {}).get("price_undertaking") == "Y" or "가격약속" in b.get("outcome_type", ""))
                                 else (p or {}).get("price_undertaking", "") or ("N" if b else ""),
            "scope_note": (p or {}).get("scope_note", ""),
            "sources": "+".join(s for s, ok in (("보도자료", p), ("30년사", bs)) if ok),
            "press_ids": (p or {}).get("press_ids", ""),
            "book_rows": ";".join(x["book_row"] for x in bs),
        })
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    n = len(links)
    ok = sum(bool(l["master_id"]) for l in links)
    print(f"책의 사건 행 {n}개 가운데 무역위원회 사건에 붙은 것 {ok}개 ({ok / n:.0%}) -> {OUT_LINKS.relative_to(ROOT)}")
    print(f"사건 요약 {len(out)}건 -> {OUT.relative_to(ROOT)}, 신청인 있는 사건 {sum(bool(o['petitioners']) for o in out)}건")
    src = {}
    for o in out:
        src[o["sources"]] = src.get(o["sources"], 0) + 1
    print("  출처별:", src)
    kinds = {}
    for l in links:
        if not l["master_id"]:
            kinds[l["outcome_type"]] = kinds.get(l["outcome_type"], 0) + 1
    print("  붙지 못한 책 행의 결과 종류:", kinds)


if __name__ == "__main__":
    main()
