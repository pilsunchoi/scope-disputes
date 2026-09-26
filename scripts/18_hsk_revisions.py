"""부령이 열거한 HSK가 HSK 개정(2012, 2017, 2022)으로 어떻게 되었는지 판정한다. 5단계 HSK 정규화.

연계표는 KCSDB2의 HS10 연계표 작업 산출물을 쓴다(아래 KCSDB2_OUT). 연도별 별표 전문으로 코드의 존재를,
개정별 안분표(dim_hs10_concordance)로 개정 전 코드의 내용이 어느 개정 후 코드로 갔는지를 본다.
그 작업의 한계(연계는 추정이며 안분 비율은 수출액 기준)가 이 판정에도 그대로 따른다. 2007년 이전 개정은
연계표가 없어 다루지 않는다.

조치마다, 개정일(1월 1일)에 시행 중이던 조치에 대해 개정 직전 판의 열거 코드(4·6·10자리)를 하나씩 본다.
  소멸:        개정 후 별표에 그 코드(또는 그 코드로 시작하는 10단위 코드)가 하나도 없다.
  범위 이탈:   열거 코드 아래의 개정 전 10단위 코드 내용 일부가 열거 코드 밖의 개정 후 코드로 옮겨 갔다.
  범위 유입:   열거 코드 밖의 개정 전 코드 내용 일부가 열거 코드 아래의 개정 후 코드로 들어왔다.
  하위 재편:   열거 코드 아래의 10단위 코드가 바뀌었으나 내용이 열거 코드 안에서만 움직였다.
  변동 없음:   위 어느 것도 아니다.
  개정 전 별표에 없음: 열거 코드가 개정 직전 별표에 이미 없다(옛 체계의 코드, 오기 등).
그리고 개정 뒤에 같은 조치의 부령이 열거 HSK를 고쳤는지(판 사이 hsk_listed 변화)를 본다.

    python scripts/18_hsk_revisions.py

입력:  data/measures.csv, data/decree-texts.csv, KCSDB2 연계표 산출물
산출:  data/hsk-revision-codes.csv     조치 × 개정 × 열거 코드 판정
       data/hsk-revision-measures.csv  조치 × 개정 요약 (영향 여부, 부령 정비 여부와 시점)
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KCSDB2_OUT = Path(r"C:\Work\Projects\KCSDB2\analysis\HS10 연계표 구축\outputs")
MEASURES = ROOT / "data" / "measures.csv"
TEXTS = ROOT / "data" / "decree-texts.csv"
OUT_CODES = ROOT / "data" / "hsk-revision-codes.csv"
OUT_MEAS = ROOT / "data" / "hsk-revision-measures.csv"

REVISIONS = {"2012": ("2011", "2013"), "2017": ("2015", "2017"), "2022": ("2021", "2022")}
MIN_W = 0.01  # 안분 가중치가 이보다 작은 이동은 잡음으로 본다


def load_codes(year):
    with (KCSDB2_OUT / f"byeolpyo_{year}.csv").open(encoding="utf-8-sig") as f:
        return {r["code"] for r in csv.DictReader(f) if len(r["code"]) == 10}


def load_concordance():
    conc = defaultdict(lambda: defaultdict(list))
    with (KCSDB2_OUT / "dim_hs10_concordance.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            conc[r["revision"]][r["hs_from"]].append((r["hs_to"], float(r["weight"]), r["relation"]))
    return conc


def norm_code(c):
    d = re.sub(r"\D", "", c)
    return d if len(d) in (4, 6, 8, 10) else ""


def judge(code, pre, post, conc):
    under_pre = {x for x in pre if x.startswith(code)}
    under_post = {x for x in post if x.startswith(code)}
    if not under_pre:
        return "개정 전 별표에 없음", "", ""
    leaving, entering = defaultdict(float), defaultdict(float)
    for x in under_pre:
        for y, w, rel in conc.get(x, []):
            if rel == "moved" and w >= MIN_W and not y.startswith(code):
                leaving[y] += w
    for x, lst in conc.items():
        if x.startswith(code):
            continue
        for y, w, rel in lst:
            if rel == "moved" and w >= MIN_W and y.startswith(code):
                entering[x] += w
    fmt = lambda d: ";".join(f"{k}({v:.2f})" for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:5])
    if not under_post:
        status = "소멸"
    elif leaving and entering:
        status = "범위 이탈·유입"
    elif leaving:
        status = "범위 이탈"
    elif entering:
        status = "범위 유입"
    elif under_pre != under_post:
        status = "하위 재편"
    else:
        status = "변동 없음"
    return status, fmt(leaving), fmt(entering)


def main():
    measures = list(csv.DictReader(MEASURES.open(encoding="utf-8-sig")))
    texts = {t["lsi_seq"]: t for t in csv.DictReader(TEXTS.open(encoding="utf-8-sig"))}
    conc = load_concordance()
    codes = {y: load_codes(y) for pair in REVISIONS.values() for y in pair}

    code_rows, meas_rows = [], []
    for m in measures:
        vs = sorted((texts[s] for s in m["version_seqs"].split(";") if texts[s]["revision_type"] != "폐지"),
                    key=lambda t: t["effective_date"])
        end = min(filter(None, [m["sunset_by_validity"], m["repealed_date"]]), default="9999")
        for rev, (py, qy) in REVISIONS.items():
            day = f"{rev}-01-01"
            if not (m["effective_date"] < day <= end):
                continue
            before = [v for v in vs if v["effective_date"] < day][-1]
            listed = [c for c in dict.fromkeys(norm_code(x) for x in before["hsk_listed"].split(";")) if c]
            statuses = []
            for c in listed:
                st, lv, en = judge(c, codes[py], codes[qy], conc[rev])
                statuses.append(st)
                code_rows.append({"measure_id": m["measure_id"], "decree_title": m["decree_title"], "revision": rev,
                                  "listed_code": c, "status": st, "leaving_to": lv, "entering_from": en})
            after = [v for v in vs if v["effective_date"] >= day]
            upd = next((v for v in after if v["hsk_listed"] != before["hsk_listed"]), None)
            affected = any(s in ("소멸", "범위 이탈", "범위 유입", "범위 이탈·유입") for s in statuses)
            meas_rows.append({
                "measure_id": m["measure_id"], "decree_title": m["decree_title"], "revision": rev,
                "effective_date": m["effective_date"], "measure_end": "" if end == "9999" else end,
                "n_listed": len(listed),
                "n_gone": statuses.count("소멸"),
                "n_moved": sum(s.startswith("범위") for s in statuses),
                "n_not_in_pre": statuses.count("개정 전 별표에 없음"),
                "affected": "Y" if affected else "N",
                "decree_updated": "Y" if upd else "N",
                "updated_date": upd["effective_date"] if upd else "",
                "updated_by": f"{upd['kind']} {upd['promulgation_no']} ({upd['revision_type']})" if upd else "",
                "listed_before": before["hsk_listed"],
                "listed_after": upd["hsk_listed"] if upd else "",
            })

    with OUT_CODES.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(code_rows[0].keys()))
        w.writeheader()
        w.writerows(code_rows)
    with OUT_MEAS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(meas_rows[0].keys()))
        w.writeheader()
        w.writerows(meas_rows)

    print(f"조치 × 개정 {len(meas_rows)}건, 열거 코드 판정 {len(code_rows)}건 -> {OUT_MEAS.relative_to(ROOT)}")
    for rev in REVISIONS:
        rs = [r for r in meas_rows if r["revision"] == rev]
        if not rs:
            continue
        a = [r for r in rs if r["affected"] == "Y"]
        print(f"  {rev}년 개정: 시행 중 조치 {len(rs)}개, 열거 HSK가 영향받은 조치 {len(a)}개"
              f" (그중 부령이 HSK를 고친 조치 {sum(r['decree_updated'] == 'Y' for r in a)}개),"
              f" 영향 없는데 고친 조치 {sum(r['decree_updated'] == 'Y' for r in rs if r['affected'] == 'N')}개")
    st = defaultdict(int)
    for r in code_rows:
        st[r["status"]] += 1
    print("  코드 판정:", dict(st))


if __name__ == "__main__":
    main()
