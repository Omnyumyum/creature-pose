"""네 발 모델이 어디서 틀리는지 뜯어보기 (2026-11-20). 시험 세트가 있는 노트북에서. 학습 없이 지금 있는 모델로만 한다.

    work/venv/Scripts/python tools/analyze_quad.py v2 v2_s1 v2_s2 v2_s3

  1) 모델마다, 그리고 여러 모델의 히트맵을 평균한 것(묶음)의 점수
  2) 좌우 뒤집어 한 번 더 보고 평균하기(뒤집어 보기)의 점수. 관절 이름이 왼 · 오른이 아니라 뒤집어도 그대로다
  3) 틀린 까닭 가르기: 앞 · 뒤를 맞바꿔 채점하면 맞는 그림(= 머리 쪽을 거꾸로 본 것)이 몇 장인가
  4) 그림별 점수 (낮은 순)
점수는 PCK@0.2 (정답에서 몸 크기의 20% 안에 든 관절 비율), tools/score_rule.py 와 같은 채점.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "train"))
import quad_model as Q  # noqa: E402
from body_rule import get_mask  # noqa: E402
from PIL import Image  # noqa: E402
from score_rule import errors  # noqa: E402

FOLDER = ROOT / "data/testset/quadruped"
ORDER = json.load(open(Q.TRAIN / "labels.json", encoding="utf-8"))["order"]
SWAP = {k: (k[:-2] + ("_f" if k.endswith("_b") else "_b")) if k.endswith(("_b", "_f")) else k for k in ORDER}      # 앞다리 ↔ 뒷다리


def load(tag: str) -> Q.Net:
    sd = torch.load(Q.MODELS / f"quad_{tag}.pth", map_location=Q.DEV, weights_only=True)
    net = Q.Net(len(ORDER), pretrained=False, arch="r50" if sd["up.0.weight"].shape[0] == 2048 else "r18").to(Q.DEV)
    net.load_state_dict(sd)
    return net.eval()


def heat(nets: list, mask: np.ndarray, flip: bool) -> tuple[torch.Tensor, np.ndarray]:
    """마스크 → 평균 히트맵 (1, J, HM, HM), 입력 칸으로 옮기는 행렬"""
    M = Q.base_matrix(mask)
    x = torch.from_numpy(Q.warp(mask, M)[None, None].astype(np.float32)).to(Q.DEV)
    hs = []
    with torch.no_grad():
        for net in nets:
            hs.append(net(x))
            if flip:
                hs.append(torch.flip(net(torch.flip(x, dims=[3])), dims=[3]))
    return torch.stack(hs).mean(0), M


def run(nets: list, flip: bool) -> dict:
    """조건(그대로 · 세워서) → 그림 이름 → 관절 좌표(원본 그림 좌표)"""
    labels = json.load(open(FOLDER / "labels.json", encoding="utf-8"))
    used = {n: r for n, r in labels.items() if r.get("use")}
    out = {}
    for cond in ("그대로", "세워서"):
        pred = {}
        for name, r in used.items():
            deg = float(r.get("rotate") or 0) if cond == "세워서" else 0.0
            mask = get_mask(FOLDER, name, deg)
            if mask is None or not mask.any():
                continue
            w, h = Image.open(FOLDER / name).size
            H, W = mask.shape
            co, si = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            hm, M = heat(nets, mask, flip)
            pts = Q.apply(np.linalg.inv(M), Q.decode(hm)[0].astype(float))
            pred[name] = {k: [w / 2 + (x - W / 2) * co + (y - H / 2) * si, h / 2 - (x - W / 2) * si + (y - H / 2) * co] for k, (x, y) in zip(ORDER, pts)}
        out[cond] = pred
    return out, used


def score(pred: dict, used: dict, names: list | None = None, swap: bool = False) -> float:
    es = []
    for n in names or used:
        p = pred.get(n, {})
        if swap:
            p = {SWAP[k]: v for k, v in p.items()}
        es += list(errors(used[n]["joints"], p).values())
    return sum(e <= 0.2 for e in es) / max(1, len(es))


def main() -> None:
    tags = [a for a in sys.argv[1:] if not a.startswith("--")] or ["v2"]
    nets = {t: load(t) for t in tags}
    rows = [(t, [nets[t]], False) for t in tags]
    rows += [(f"{tags[0]} + 뒤집어 보기", [nets[tags[0]]], True)]
    if len(tags) > 1:
        rows += [(f"묶음 {len(tags)}개", list(nets.values()), False), (f"묶음 {len(tags)}개 + 뒤집어 보기", list(nets.values()), True)]
    print(f"{'':<26} 전체 그대로 / 세워서     실제 그림 그대로 / 세워서")
    keep = {}
    for title, ns, flip in rows:
        pred, used = run(ns, flip)
        real = [n for n in used if not n.startswith("synth_")]
        print(f"{title:<26} {score(pred['그대로'], used):6.1%} / {score(pred['세워서'], used):6.1%}        {score(pred['그대로'], used, real):6.1%} / {score(pred['세워서'], used, real):6.1%}", flush=True)
        keep[title] = pred
    best = rows[-1][0]
    pred = keep[best]
    print(f"\n[{best}] 틀린 까닭 가르기 (세워서)")
    flipped, low = [], []
    for n in used:
        a, b = score(pred["세워서"], used, [n]), score(pred["세워서"], used, [n], swap=True)
        low.append((a, b, n))
        if b > a + 0.25:
            flipped.append(n)
    print(f"  앞 · 뒤를 맞바꾸면 훨씬 잘 맞는 그림(머리 쪽을 거꾸로 봄): {len(flipped)}장 {flipped}")
    fixed = sum(max(a, b) if n in flipped else a for a, b, n in low) / len(low)
    print(f"  그 그림들의 머리 쪽만 바로잡히면 그림 평균 {sum(a for a, _, _ in low) / len(low):.1%} → {fixed:.1%}")
    print("\n  그림별 (세워서, 낮은 순)   점수 / 앞뒤 맞바꾼 점수")
    for a, b, n in sorted(low)[:12]:
        print(f"   {n:<14} {a:5.0%} / {b:5.0%}{'   ← 머리 쪽 거꾸로' if n in flipped else ''}")


if __name__ == "__main__":
    main()
