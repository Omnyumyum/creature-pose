"""네 발 동물 몸 마스크를 만들어 내는 합성기 (2026-11-17). 정답 관절을 아는 마스크를 끝없이 만든다.

왜: 사람이 고르는 정답은 300장에 111장(15분)이라 수십만 장을 모을 수 없다. 학습 입력이 그림이 아니라 몸 마스크(흰 덩어리)라서,
옆모습 네 발 동물의 덩어리를 여러 꼴로 그려 내면 그 자체가 학습 정답이 된다. 관절은 그릴 때 쓴 자리에서 나오므로 틀릴 수 없다.

한 장 = 몸통(둥근 네모, 등이 솟거나 꺼짐, 혹) + 다리(앞 · 뒤 각각 1~2개, 굵기 · 길이 · 기울기 · 무릎 꺾임 · 발) + 목 · 머리(짧은 목 ~ 기린 목, 큰 얼굴, 귀)
+ 꼬리(없음 · 짧음 · 위로 · 뒤로 · 아래로 늘어짐 · 굵은 꼬리) + 헷갈리는 것(코끼리 코처럼 아래로 늘어진 것, 갈기). 일부는 속이 빈 선 그림으로.
머리는 늘 오른쪽으로 그린다(좌우 뒤집기는 학습 때 늘리기가 한다).

관절 약속은 서비스 규칙(drawtale-ai quadruped.py find_joints)과 같게 놓는다 (tools/export_train.py · tools/body_rule.py 와 같은 약속).
  - 다리 뿌리 = 다리 가로 자리, 배 선 높이.  무릎 = 뿌리와 발의 한가운데.  발 = 다리 끝
  - 다리 번호: 몸 가운데 쪽이 right(1). 한쪽에 하나만 그렸으면 두 칸을 겹친다
  - 엉덩이 · 어깨 · 목: 다리 뿌리와 마스크에서 계산 (배 선에서 등까지의 15% · 55% · 65%)
  - 꼬리: 뿌리 · 가운데 · 끝. 없으면 셋 다 엉덩이에

    python train/synth_quad.py [장 수=24]   → work/synth_look.jpg (눈으로 보기)
"""

import math
import sys
from pathlib import Path

import cv2
import numpy as np

ORDER = ["hip", "torso", "neck",
         "right_hip_b", "right_knee_b", "right_foot_b", "left_hip_b", "left_knee_b", "left_foot_b",
         "right_hip_f", "right_knee_f", "right_foot_f", "left_hip_f", "left_knee_f", "left_foot_f",
         "tail", "tail_mid", "tail_tip"]
S = 448          # 그리는 칸


def _curve(p0, p1, p2, n: int = 16) -> np.ndarray:  # noqa: ANN001
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * np.array(p0) + 2 * (1 - t) * t * np.array(p1) + t ** 2 * np.array(p2)


def _line(m: np.ndarray, pts, w: float) -> None:  # noqa: ANN001
    cv2.polylines(m, [np.round(np.array(pts) * 4).astype(np.int32)], False, 255, max(1, int(round(w))), cv2.LINE_AA, shift=2)


def generate(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """(마스크 bool SxS, 관절 18x2). 머리는 오른쪽"""
    u = rng.uniform
    m = np.zeros((S, S), np.uint8)
    cx, cy = S / 2 + u(-15, 15), S / 2 + u(-30, 10)
    L = u(110, 210)                                   # 몸 길이
    a, b = L / 2, u(0.22, 0.55) * L / 2               # 몸 반지름
    n = u(2.0, 5.0)                                   # 2 = 타원, 클수록 네모
    bend = u(-0.25, 0.25) * b                         # 등이 솟음(-) · 꺼짐(+)
    t = np.linspace(0, 2 * math.pi, 72, endpoint=False)
    bx = a * np.sign(np.cos(t)) * np.abs(np.cos(t)) ** (2 / n)
    by = b * np.sign(np.sin(t)) * np.abs(np.sin(t)) ** (2 / n) + bend * ((bx / a) ** 2 - 0.5)
    wob = np.convolve(np.r_[rng.normal(0, 0.03 * L, 72)] * 1.0, np.ones(7) / 7, mode="same")      # 손으로 그린 듯 느리게 출렁이게
    body = np.c_[cx + bx + wob, cy + by + np.roll(wob, 9)]
    cv2.fillPoly(m, [np.round(body).astype(np.int32)], 255)
    if rng.random() < 0.12:                           # 혹 (낙타)
        for k in range(int(rng.integers(1, 3))):
            hx = cx + u(-0.5, 0.4) * a
            cv2.ellipse(m, (int(hx), int(cy - b * 0.9)), (int(u(0.12, 0.25) * L), int(u(0.15, 0.4) * L)), 0, 180, 360, 255, -1)

    # 목 · 머리
    big = rng.random() < 0.15                         # 얼굴이 몸만큼 큰 그림
    nl = (u(0.05, 0.35) if rng.random() < 0.7 else u(0.35, 1.0)) * L
    ang = math.radians(u(-85, 20))                    # 0 = 앞으로, -90 = 위로
    n0 = np.array([cx + a * u(0.6, 0.9), cy - b * u(0.2, 0.7)])
    hc = n0 + nl * np.array([math.cos(ang), math.sin(ang)])
    hr = (u(0.3, 0.45) if big else u(0.1, 0.24)) * L
    _line(m, [n0, hc], u(0.5, 1.3) * hr * (0.6 if nl > 0.35 * L else 1.2))
    cv2.ellipse(m, (int(hc[0]), int(hc[1])), (int(hr * u(0.9, 1.4)), int(hr * u(0.7, 1.0))), u(-30, 30), 0, 360, 255, -1)
    if rng.random() < 0.6:                            # 귀 · 뿔
        for dx in (-0.4, 0.3)[: int(rng.integers(1, 3))]:
            e = hc + np.array([dx * hr, -hr * 0.7])
            cv2.fillPoly(m, [np.round([e + [-hr * 0.25, 0], e + [hr * 0.25, 0], e + [u(-0.2, 0.2) * hr, -hr * u(0.4, 1.0)]]).astype(np.int32)], 255)
    if rng.random() < 0.08:                           # 갈기
        cv2.circle(m, (int(hc[0] - hr * 0.3), int(hc[1])), int(hr * u(1.2, 1.6)), 255, -1)

    # 다리. 배 선 = 다리 사이에서 몸 아래쪽이 가장 낮은 높이
    belly = float(np.max(body[:, 1]))
    ll = u(0.2, 0.7) * L
    tl = u(4, max(5, 0.13 * L))
    xb, xf = cx - a * u(0.5, 0.82), cx + a * u(0.45, 0.8)
    kind = rng.random()
    counts = (2, 2) if kind < 0.55 else (1, 1) if kind < 0.8 else ((1, 2) if rng.random() < 0.5 else (2, 1))
    ground = belly + ll
    legs = {}
    for side, x0, cnt in (("b", xb, counts[0]), ("f", xf, counts[1])):
        gap = u(0.1, 0.32) * a if cnt == 2 else 0.0
        xs = [x0 - gap / 2, x0 + gap / 2] if cnt == 2 else [x0]
        got = []
        for x in xs:
            lean = math.radians(u(-18, 18))
            length = ll * u(0.85, 1.1)
            foot = np.array([x + math.sin(lean) * length, belly + math.cos(lean) * length])
            top_in = np.array([x, belly - b * u(0.3, 0.9)])                    # 몸 안에서 시작
            pts = [top_in, [x, belly]]
            if rng.random() < 0.3:                                              # 무릎 꺾임
                pts.append([(x + foot[0]) / 2 + u(-0.12, 0.12) * length, (belly + foot[1]) / 2])
            pts.append(foot)
            _line(m, pts, tl * u(0.8, 1.2))
            if rng.random() < 0.3:                                              # 발
                _line(m, [foot, foot + [u(0.5, 1.5) * tl, 0]], tl * u(0.6, 1.0))
            got.append((np.array([x, belly]), foot))
        # 몸 가운데 쪽이 1: 뒷다리는 머리(오른쪽)에 가까운 것, 앞다리는 꼬리(왼쪽)에 가까운 것
        got.sort(key=lambda g: g[0][0], reverse=(side == "b"))
        legs[side] = [got[0], got[-1]]
    if rng.random() < 0.1:                            # 헷갈리는 것: 머리에서 아래로 늘어진 코 (다리가 아니다)
        end = np.array([hc[0] + u(0.0, 0.8) * hr, min(ground, hc[1] + u(0.8, 2.5) * hr)])
        _line(m, _curve(hc + [hr * 0.6, 0], [hc[0] + hr * 1.6, (hc[1] + end[1]) / 2], end), tl * u(0.7, 1.2))

    # 꼬리
    tail = None
    kind = rng.random()
    if kind > 0.3:
        r0 = np.array([cx - a * u(0.9, 1.0), cy - b * u(-0.2, 0.5)])
        tlen = u(0.15, 0.9) * L
        if kind < 0.5:      # 아래로 늘어짐 (뒷다리 옆: 규칙이 다리로 잘못 세는 꼴)
            tip = np.array([r0[0] - u(0.02, 0.3) * tlen, min(ground - u(0, 0.2) * ll, r0[1] + tlen)])
            ctrl = [r0[0] - u(0.1, 0.5) * tlen, r0[1] + u(-0.1, 0.3) * tlen]
        elif kind < 0.75:   # 위로
            tip = r0 + [-u(0.2, 0.7) * tlen, -u(0.4, 1.0) * tlen]
            ctrl = [r0[0] - u(0.3, 0.9) * tlen, r0[1] + u(-0.2, 0.2) * tlen]
        else:               # 뒤로
            tip = r0 + [-tlen, u(-0.3, 0.3) * tlen]
            ctrl = [r0[0] - tlen / 2, r0[1] + u(-0.4, 0.4) * tlen]
        c = _curve(r0, ctrl, tip)
        _line(m, c, u(3, 7) if rng.random() < 0.8 else u(0.08, 0.2) * L)        # 가는 꼬리 · 굵은 꼬리
        tail = (c[1], c[len(c) // 2], c[-1])

    mask = m > 127
    if rng.random() < 0.15:                           # 속이 빈 선 그림
        k = int(u(4, 9))
        inner = cv2.erode(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
        mask = mask & ~(inner > 0)

    j = {}
    for side in "bf":
        for name, (top, foot) in zip(("right", "left"), legs[side]):
            j[f"{name}_hip_{side}"], j[f"{name}_foot_{side}"] = top, foot
            j[f"{name}_knee_{side}"] = (top + foot) / 2
    # 몸통 세 점: tools/body_rule.py 와 같은 식 (머리는 오른쪽)
    mx_b = float(np.mean([g[0][0] for g in legs["b"]]))
    mx_f = float(np.mean([g[0][0] for g in legs["f"]]))
    span = abs(mx_f - mx_b)
    first = float(np.where(mask.any(axis=1))[0][0])

    def at(x: float, up: float) -> np.ndarray:
        col = mask[:, min(max(int(round(x)), 0), S - 1)]
        top = float(np.argmax(col)) if col.any() else first
        return np.array([x, belly - max(belly - top, 0.0) * up])
    j["hip"], j["torso"], j["neck"] = at(mx_b + span * 0.25, 0.15), at(mx_f, 0.55), at(mx_f + span * 0.08, 0.65)
    for k, p in zip(("tail", "tail_mid", "tail_tip"), tail if tail is not None else (j["hip"],) * 3):
        j[k] = np.array(p, float)
    return mask, np.array([j[k] for k in ORDER], float)


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    rng = np.random.default_rng(1117)
    cols = 6
    sheet = np.full((-(-count // cols) * 300, cols * 300, 3), 255, np.uint8)
    for i in range(count):
        mask, pts = generate(rng)
        im = cv2.cvtColor(mask.astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)
        for k, (x, y) in zip(ORDER, pts):
            c = (50, 40, 210) if k.endswith("_b") else (220, 90, 40) if k.endswith("_f") else (200, 60, 150) if k.startswith("tail") else (60, 170, 0)
            cv2.circle(im, (int(x), int(y)), 3 if "knee" in k or k == "tail_mid" else 6, c, -1)
        sheet[(i // cols) * 300:(i // cols) * 300 + 300, (i % cols) * 300:(i % cols) * 300 + 300] = cv2.resize(im, (300, 300), interpolation=cv2.INTER_AREA)
    out = Path(__file__).resolve().parent.parent / "work/synth_look.jpg"
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(out)
