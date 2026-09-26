"""조치별 범위 문언을 코딩용 입력으로 묶는다.

조치마다 마지막 유효판(폐지판 제외)의 부과대상 물품 조문, 본문 제외 문언, 제외 물품 별표를 한 레코드로 모은다.
부과대상 조문이 별표를 가리키면 제외 물품 별표가 아닌 별표(세율표 등)도 annex_other_text로 싣는다.
첫 판과 문언이 다르면 첫 판의 조문도 함께 싣는다. 배치로 나누어 코더에게 넘긴다.

    python scripts/04_build_coding_input.py [배치 수]

입력:  data/measures.csv, data/decree-texts.csv   (02_parse_decrees.py 산출)
산출:  data/coding/input/batch-<n>.jsonl
"""
import csv
import re
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEASURES = ROOT / "data" / "measures.csv"
TEXTS = ROOT / "data" / "decree-texts.csv"
OUT = ROOT / "data" / "coding" / "input"


def main():
    n_batch = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    texts = {t["lsi_seq"]: t for t in csv.DictReader(TEXTS.open(encoding="utf-8-sig"))}
    recs = []
    for m in csv.DictReader(MEASURES.open(encoding="utf-8-sig")):
        vs = [texts[s] for s in m["version_seqs"].split(";") if texts[s]["revision_type"] != "폐지"]
        first, last = vs[0], vs[-1]
        rec = {
            "measure_id": m["measure_id"],
            "decree_title": last["name"],
            "effective_date": m["effective_date"],
            "coded_version": {"lsi_seq": last["lsi_seq"], "effective_date": last["effective_date"],
                              "revision_type": last["revision_type"]},
            "scope_text": last["scope_text"],
            "body_exclusion_text": last["exclusion_text"],
            "annex_exclusion_text": last["annex_exclusion_text"],
        }
        # 옛 부령은 부과대상 물품 자체를 "별표에 규정된 것"으로 정하기도 한다. 그 별표(세율표 등)를 함께 싣는다
        # ("별표와 같다"로 세율표를 가리키는 조문은 해당하지 않는다)
        if (re.search(r"별표\s*\d*\s*에(?:서)?\s*(?:규정된|규정하는|기재된|열거된|해당하는|정하는|정한)", last["scope_text"])
                and not last["annex_exclusion_text"] and last["annex_other_text"]):
            rec["annex_other_text"] = last["annex_other_text"]
        if first["scope_text"] != last["scope_text"] or first["annex_exclusion_text"] != last["annex_exclusion_text"]:
            rec["first_version_scope_text"] = first["scope_text"]
            rec["first_version_annex_exclusion_text"] = first["annex_exclusion_text"]
        recs.append(rec)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("batch-*.jsonl"):
        old.unlink()
    size = -(-len(recs) // n_batch)
    for b in range(n_batch):
        part = recs[b * size:(b + 1) * size]
        with (OUT / f"batch-{b + 1}.jsonl").open("w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"batch-{b + 1}: {part[0]['measure_id']}~{part[-1]['measure_id']} ({len(part)}개)")


if __name__ == "__main__":
    main()
