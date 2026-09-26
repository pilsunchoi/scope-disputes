"""조세심판원과 관세법령정보포털에서 받은 사건을 하나의 결정 목록으로 합친다.

관세법령정보포털(CLIP)의 심판청구는 조세심판원 결정을 처분청 사건번호로 다시 실은 것이다.
결정일이 같은 조세심판원 결정(여럿이면 제목이 가장 비슷한 것)에 대응시킨다. 한 결정에 처분청 사건번호가 여럿 붙기도 한다.
대응이 없는 CLIP 심판청구와 과세전적부심사, 심사청구, 판결은 따로 한 행이 된다.

    python scripts/08_build_dispute_list.py

입력:  data/disputes-tt.csv, data/disputes-clip.csv, data/stage0-tt-dumping-decisions.csv
산출:  data/disputes.csv   결정 단위 (dispute_id, 기관, 대표 번호, 결정일, 제목, 결과, 원문 파일, 0단계 쟁점 분류 등)
"""
import csv
import difflib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TT = ROOT / "data" / "disputes-tt.csv"
CLIP = ROOT / "data" / "disputes-clip.csv"
STAGE0 = ROOT / "data" / "stage0-tt-dumping-decisions.csv"
OUT = ROOT / "data" / "disputes.csv"

FORUM = {"심판청구": "조세심판원", "과세전적부심사": "관세청 과세전적부심사", "심사청구": "관세청 심사청구",
         "이의신청": "세관 이의신청", "판결": "법원"}


def norm(s):
    return re.sub(r"[\s·ㆍ․'‘’\"“”()（）]", "", s)


def main():
    tt = list(csv.DictReader(TT.open(encoding="utf-8-sig")))
    clip = list(csv.DictReader(CLIP.open(encoding="utf-8-sig")))
    stage0 = {r["decision_no"]: r for r in csv.DictReader(STAGE0.open(encoding="utf-8-sig"))}

    rows = []
    for t in tt:
        s0 = stage0.get(t["claim_no"], {})
        rows.append({
            "forum": "조세심판원", "case_no": t["claim_no"], "decision_date": t["decision_date"],
            "title": t["title"], "outcome": t["outcome"], "source": "tt",
            "clip_case_nos": "", "clip_ids": "", "text_file": t["text_file"], "clip_text_files": "",
            "stage0_issue_group": s0.get("issue_group", ""), "dumping_mentions": "",
        })
    tt_rows = {r["case_no"]: r for r in rows}

    unmatched = []
    for c in clip:
        if c["forum"] == "심판청구":
            cands = [r for r in rows if r["source"] == "tt" and r["decision_date"] == c["decision_date"]]
            # 같은 날 결정이 하나면 그것에, 여럿이면 제목이 가장 비슷한 것에 대응시킨다
            # (CLIP은 처분청이 붙인 제목을 쓰므로 조세심판원 제목과 크게 다를 수 있다)
            best = max(cands, key=lambda r: difflib.SequenceMatcher(None, norm(r["title"]), norm(c["title"])).ratio(),
                       default=None)
            if best and (len(cands) == 1 or
                         difflib.SequenceMatcher(None, norm(best["title"]), norm(c["title"])).ratio() > 0.3):
                best["clip_case_nos"] = ";".join(filter(None, [best["clip_case_nos"], c["case_no"]]))
                best["clip_ids"] = ";".join(filter(None, [best["clip_ids"], c["clip_id"]]))
                best["clip_text_files"] = ";".join(filter(None, [best["clip_text_files"], c["text_file"]]))
                continue
        unmatched.append(c)

    for c in unmatched:
        rows.append({
            "forum": FORUM.get(c["forum"], c["forum"]), "case_no": c["case_no"], "decision_date": c["decision_date"],
            "title": c["title"], "outcome": c["outcome"], "source": "clip",
            "clip_case_nos": c["case_no"], "clip_ids": c["clip_id"], "text_file": c["text_file"],
            "clip_text_files": "", "stage0_issue_group": "", "dumping_mentions": c["dumping_mentions"],
        })

    # 조세심판원 결정의 덤핑 언급 횟수도 채운다
    for r in rows:
        if r["source"] == "tt":
            r["dumping_mentions"] = (ROOT / r["text_file"]).read_text(encoding="utf-8").count("덤핑")

    rows.sort(key=lambda r: (r["decision_date"], r["case_no"]))
    for i, r in enumerate(rows, 1):
        r["dispute_id"] = f"D{i:03d}"
    cols = ["dispute_id"] + [k for k in rows[0] if k != "dispute_id"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    by = {}
    for r in rows:
        by[(r["forum"], r["source"])] = by.get((r["forum"], r["source"]), 0) + 1
    print(f"결정 {len(rows)}건 -> {OUT.relative_to(ROOT)}")
    for k, v in sorted(by.items()):
        print(f"  {k[0]} ({k[1]}): {v}")
    print(f"  CLIP 심판청구 가운데 조세심판원 결정에 대응된 것"
          f" {sum(len(r['clip_ids'].split(';')) for r in rows if r['source'] == 'tt' and r['clip_ids'])}건")


if __name__ == "__main__":
    main()
