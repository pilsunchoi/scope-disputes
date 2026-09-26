"""분쟁 결정 목록을 본문 크기가 비슷한 묶음으로 나누어 추출 입력을 만든다.

    python scripts/09_build_extraction_input.py [묶음 수]

입력:  data/disputes.csv   (08_build_dispute_list.py 산출)
산출:  data/extraction/input/batch-<n>.csv
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPUTES = ROOT / "data" / "disputes.csv"
OUT = ROOT / "data" / "extraction" / "input"
COLS = ["dispute_id", "forum", "case_no", "decision_date", "title", "outcome", "text_file", "clip_case_nos",
        "stage0_issue_group", "dumping_mentions"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    rows = list(csv.DictReader(DISPUTES.open(encoding="utf-8-sig")))
    size = lambda r: (ROOT / r["text_file"]).stat().st_size
    bins, load = [[] for _ in range(n)], [0] * n
    for r in sorted(rows, key=size, reverse=True):  # 큰 것부터 가장 가벼운 묶음에
        i = load.index(min(load))
        bins[i].append(r)
        load[i] += size(r)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("batch-*.csv"):
        old.unlink()
    for i, b in enumerate(bins, 1):
        b.sort(key=lambda r: r["dispute_id"])
        with (OUT / f"batch-{i}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(b)
        print(f"batch-{i}: {len(b)}건, {load[i - 1] // 1024}KB")


if __name__ == "__main__":
    main()
