"""Quick, Draw! 시험 100장 결과 세기 (2026-11-17): 「머리 쪽 누르기 → 규칙 초안 → 틀린 것만 고치기」에 드는 시간과 통과 비율.

data/qd_pilot/labels.json (표시 도구가 저장)을 읽는다.
  t_facing  머리 쪽을 누르는 데 걸린 시간 (ms)
  t_fix     고치기 화면에 떠 있던 시간 (ms, 「이 그림 끝」을 누를 때까지)
  draft     머리 쪽을 알려 주고 규칙이 단 초안.  joints = 사람이 고친 최종 정답
「그대로 통과」 = 초안의 모든 관절이 최종 정답에서 몸 크기(보이는 관절을 감싼 상자 대각선)의 3% 안이고, 안 보임으로 바꾼 것도 없음.

    python tools/pilot_report.py [--set qd_pilot]   → 화면, out/pilot_report.json
"""

import json
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score_rule import GROUPS  # noqa: E402
from sets import ROOT, SETS  # noqa: E402

NAME = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "qd_pilot"
SET = ROOT / SETS[NAME][0]
SAME = 0.03
TARGET = 20000      # 모으려는 정답 수


def moves(r: dict) -> dict:
    """관절 이름 → 초안에서 옮긴 거리 / 몸 크기 (안 보임으로 바꾼 관절은 9)"""
    j, d = r["joints"], r.get("draft") or {}
    vis = [v for k, v in j.items() if k != "head" and v[2]]
    if not vis:
        return {}
    size = math.hypot(max(v[0] for v in vis) - min(v[0] for v in vis), max(v[1] for v in vis) - min(v[1] for v in vis)) or 1.0
    return {k: (math.hypot(j[k][0] - d[k][0], j[k][1] - d[k][1]) / size if j[k][2] else 9.0) for k in d if k in j and k != "head"}


def mid(xs: list) -> str:
    return f"가운데 값 {st.median(xs) / 1000:.1f}초 · 평균 {st.mean(xs) / 1000:.1f}초" if xs else "없음"


def main() -> None:
    L = json.load(open(SET / "labels.json", encoding="utf-8"))
    total = len(json.load(open(SET / "auto.json", encoding="utf-8")))
    ans = {n: r for n, r in L.items() if r.get("use") is False or r.get("facing")}
    use = {n: r for n, r in ans.items() if r.get("use") is not False}
    done = {n: r for n, r in use.items() if r.get("done") and r.get("draft")}
    print(f"그림 {total}장 · 머리 쪽 누름 {len(ans)} · 쓸 수 있음 {len(use)} ({len(use) / max(1, len(ans)):.0%}) · 고치기 끝 {len(done)}")
    tf = [r["t_facing"] for r in ans.values() if r.get("t_facing")]
    tx = [r["t_fix"] for r in done.values() if r.get("t_fix")]
    print("머리 쪽 누르기:", mid(tf))
    print("고치기:", mid(tx))
    out = {"images": total, "answered": len(ans), "usable": len(use), "fixed": len(done)}
    if done:
        mv = {n: moves(r) for n, r in done.items()}
        same = [n for n, m in mv.items() if m and max(m.values()) <= SAME]
        few = [n for n, m in mv.items() if m and 0 < sum(v > SAME for v in m.values()) <= 3]
        print(f"초안 그대로 통과 {len(same)}/{len(done)} ({len(same) / len(done):.0%}) · 관절 1~3개만 고침 {len(few)} ({len(few) / len(done):.0%})")
        ts = [done[n]["t_fix"] for n in same if done[n].get("t_fix")]
        tn = [done[n]["t_fix"] for n in done if n not in same and done[n].get("t_fix")]
        print("  그대로 통과한 그림:", mid(ts), "| 고친 그림:", mid(tn))
        print("규칙 초안(머리 쪽 알려 줌)이 최종 정답에서 떨어진 정도")
        parts = {}
        for g, keys in GROUPS.items():
            es = [v for m in mv.values() for k, v in m.items() if k in keys]
            if es:
                parts[g] = {"pck10": round(sum(e <= 0.1 for e in es) / len(es), 4), "pck20": round(sum(e <= 0.2 for e in es) / len(es), 4),
                            "moved": round(sum(e > SAME for e in es) / len(es), 4)}
                print(f"  {g:<6} PCK@0.1 {parts[g]['pck10']:5.1%}  @0.2 {parts[g]['pck20']:5.1%}  고친 관절 {parts[g]['moved']:5.1%}")
        by = {}
        for n, r in done.items():
            by.setdefault(json.load(open(SET / "auto.json", encoding="utf-8"))[n].get("cat", "?"), []).append(n in same)
        print("  종류별 그대로 통과:", " · ".join(f"{c} {sum(v)}/{len(v)}" for c, v in sorted(by.items())))
        if tf and tx:
            rate = len(use) / len(ans)
            hours = (TARGET / rate * st.mean(tf) + TARGET * st.mean(tx)) / 3.6e6
            print(f"정답 {TARGET:,}장 어림: 머리 쪽 {TARGET / rate:,.0f}장 누르기 + {TARGET:,}장 고치기 = 약 {hours:.0f}시간 (평균 시간 기준)")
            out["hours_for_target"] = round(hours, 1)
        out.update({"same": len(same), "few": len(few), "parts": parts,
                    "t_facing_mean_s": round(st.mean(tf) / 1000, 2) if tf else None, "t_fix_mean_s": round(st.mean(tx) / 1000, 2) if tx else None})
    (ROOT / "out").mkdir(exist_ok=True)
    json.dump(out, open(ROOT / "out/pilot_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
