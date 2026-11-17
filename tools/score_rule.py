"""네 발 시험 세트에서 관절 예측을 사람이 표시한 정답과 견준다 (2026-11-17).

정답: data/testset/quadruped/labels.json (표시 도구가 저장, 「시험에 씀」 이 켜진 그림만 쓴다)
예측 두 가지를 잰다.
  그대로   auto.json           그림을 받은 그대로 규칙에 넣은 결과 (서비스에서 어른이 아무것도 안 고친 경우)
  세워서   auto_upright.json   사람이 정한 각도 · 머리 쪽을 알려 주고 규칙을 다시 돌린 결과 (--rerun 으로 만든다, 로컬 AI 서버 필요)

재는 법: 관절마다 정답과의 거리 / 몸 크기. 몸 크기는 보이는 정답 관절을 감싼 상자의 대각선.
거리가 몸 크기의 10% · 20% 안이면 맞은 것으로 센다(PCK@0.1 · @0.2). 안 보임으로 표시한 관절과 머리(규칙에 없음)는 뺀다.
다리는 같은 쪽(앞 · 뒤) 두 개의 번호가 바뀌어도 그림으로는 같으므로, 둘을 바꿔 본 쪽이 더 가까우면 그쪽으로 센다.

    python tools/score_rule.py [--rerun]   → 화면에 표, out/score_rule.json
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "data/testset/quadruped"
OUT = ROOT / "out"

GROUPS = {
    "몸통": ["hip", "torso", "neck"],
    "앞다리": ["right_hip_f", "right_knee_f", "right_foot_f", "left_hip_f", "left_knee_f", "left_foot_f"],
    "뒷다리": ["right_hip_b", "right_knee_b", "right_foot_b", "left_hip_b", "left_knee_b", "left_foot_b"],
    "꼬리": ["tail", "tail_mid", "tail_tip"],
}
PAIRS = [("_f", ["hip", "knee", "foot"]), ("_b", ["hip", "knee", "foot"])]


def load(name: str) -> dict:
    p = SET / name
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def rerun(labels: dict) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from label_server import redraft
    out = {}
    for name, rec in labels.items():
        if not rec.get("use"):
            continue
        r = redraft(name, float(rec.get("rotate") or 0), rec.get("facing") or None)
        out[name] = {"found": bool(r.get("found")), "message": r.get("message"), "joints": r.get("joints") or {}}
        print(" ", name, "찾음" if out[name]["found"] else "못 찾음 또는 기본 뼈대", flush=True)
    json.dump(out, open(SET / "auto_upright.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


def errors(gt: dict, pred: dict) -> dict:
    """관절 이름 → 거리 / 몸 크기. 정답에서 보이는 관절만"""
    vis = {k: v for k, v in gt.items() if k != "head" and (len(v) < 3 or v[2])}
    xs, ys = [v[0] for v in vis.values()], [v[1] for v in vis.values()]
    size = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0

    def d(g: str, p: str) -> float:
        return math.hypot(gt[g][0] - pred[p][0], gt[g][1] - pred[p][1]) / size if p in pred else 9.0

    e = {k: d(k, k) for k in vis}
    for suf, parts in PAIRS:        # 다리 번호 바꿔 보기
        a = [f"right_{p}{suf}" for p in parts]
        b = [f"left_{p}{suf}" for p in parts]
        keep = [k for k in a + b if k in vis]
        if not keep:
            continue
        swap = dict(zip(a + b, b + a))
        if sum(d(k, swap[k]) for k in keep) < sum(e[k] for k in keep):
            for k in keep:
                e[k] = d(k, swap[k])
    return e


def main() -> None:
    labels = load("labels.json")
    used = {n: r for n, r in labels.items() if r.get("use")}
    preds = {"그대로": load("auto.json")}
    if "--rerun" in sys.argv:
        print("각도 · 머리 쪽을 알려 주고 규칙 다시 돌리기")
        rerun(labels)
    if (SET / "auto_upright.json").exists():
        preds["세워서"] = load("auto_upright.json")

    result = {}
    for cond, pred in preds.items():
        rows = {n: errors(r["joints"], pred.get(n, {}).get("joints", {})) for n, r in used.items()}
        found = {n: bool(pred.get(n, {}).get("found")) for n in used}

        def pck(names: list, keys: list | None, t: float) -> tuple:
            es = [e for n in names for k, e in rows[n].items() if keys is None or k in keys]
            return (sum(e <= t for e in es) / len(es) if es else float("nan")), len(es)

        def line(title: str, names: list) -> dict:
            if not names:
                return {}
            a, n = pck(names, None, 0.1)
            b, _ = pck(names, None, 0.2)
            print(f"  {title:<22} 그림 {len(names):>2}  관절 {n:>3}  PCK@0.1 {a:5.1%}  @0.2 {b:5.1%}")
            return {"images": len(names), "joints": n, "pck10": round(a, 4), "pck20": round(b, 4)}

        print(f"\n[{cond}] 규칙이 관절을 찾았다고 한 그림 {sum(found.values())}/{len(used)}")
        res = {"found": sum(found.values()), "images": len(used), "by": {}}
        res["by"]["전체"] = line("전체", list(used))
        res["by"]["찾았다고 한 그림만"] = line("찾았다고 한 그림만", [n for n in used if found[n]])
        res["by"]["못 찾은 그림만"] = line("못 찾은 그림만", [n for n in used if not found[n]])
        for src, title in (("kids", "아이 그림"), ("qr", "공개 낙서"), ("own", "직접 그린 것"), ("synth", "합성")):
            res["by"][title] = line(title, [n for n in used if n.startswith(src + "_")])
        res["by"]["실제 그림(합성 빼고)"] = line("실제 그림(합성 빼고)", [n for n in used if not n.startswith("synth_")])
        print("  부위별 (전체 그림)")
        res["parts"] = {}
        for g, keys in GROUPS.items():
            a, n = pck(list(used), keys, 0.1)
            b, _ = pck(list(used), keys, 0.2)
            print(f"    {g:<6} 관절 {n:>3}  PCK@0.1 {a:5.1%}  @0.2 {b:5.1%}")
            res["parts"][g] = {"joints": n, "pck10": round(a, 4), "pck20": round(b, 4)}
        res["per_image"] = {n: {"found": found[n], "pck20": round(sum(e <= 0.2 for e in rows[n].values()) / len(rows[n]), 3),
                                "mean_err": round(sum(min(e, 1.0) for e in rows[n].values()) / len(rows[n]), 3)} for n in used}
        result[cond] = res

    if len(result) == 2:
        print("\n그림별 PCK@0.2 (그대로 → 세워서)")
        for n in used:
            a, b = result["그대로"]["per_image"][n], result["세워서"]["per_image"][n]
            r = labels[n]
            print(f"  {n:<13} {a['pck20']:5.0%} → {b['pck20']:5.0%}   {'찾음' if b['found'] else '못 찾음':<5} {r.get('kind') or '':<10} 각도 {r.get('rotate') or 0}")
    OUT.mkdir(exist_ok=True)
    json.dump(result, open(OUT / "score_rule.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
