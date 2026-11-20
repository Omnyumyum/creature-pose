"""날개형(새 · 나비 · 잠자리) 몸 마스크를 만들어 내는 합성기 (2026-11-20). 네 발의 synth_quad.py 와 같은 쓰임.

세 가지 꼴을 그린다.
  옆모습 새      몸통(타원) + 머리(앞 위) + 부리 + 꼬리 + 다리 + 등 위로 솟은 날개 0 ~ 2개(대부분 하나). 머리는 늘 오른쪽(뒤집기는 학습 때 늘리기가 한다)
  위에서 본 것   나비 · 잠자리: 세로로 긴 몸 + 위쪽 머리 + 왼쪽 · 오른쪽 날개(한 장 또는 위아래 두 장이 붙은 것) + 더듬이
  앞모습 새      둥근 몸 + 위에 머리 + 양옆으로 든 날개 + 다리

관절 약속은 서비스 규칙(drawtale-ai winged.py find_joints)과 같게 놓는다.
  - body = 몸통 가운데, head = 머리 가운데
  - 날개 뿌리 = 날개가 몸통에 닿는 자리의 가운데, 끝 = 날개 안에서 뿌리로부터 가장 먼 곳, 가운데 = 둘의 한가운데
  - 몸 밖으로 솟은 날개가 없으면(몸 안에 그린 날개) 날개 점 여섯을 모두 몸통에 겹친다
  - **날개형은 날개 하나가 기준이다** (사용자 2026-11-20. 서비스 안내도 「날개는 하나만, 등 위로 크게 솟게」, 형태 정의의 view 는 side).
    그래서 모델이 내는 관절은 다섯: 몸통 · 머리 · 날개 뿌리 · 가운데 · 끝 (ORDER). 서비스에 붙일 때는 날개 1 · 2 에 같은 값을 넣는다(to_service)
  - 날개가 둘 보이는 그림(나비 · 앞모습 새)은 하나만 고른다: 더 긴 날개, 길이가 비슷하면(10% 안) 끝이 더 왼쪽인 것 (pick_one).
    이 고르기는 학습 때 뒤집기 · 돌리기를 한 뒤의 그림에서 한다. 그래야 「비슷하면 왼쪽」이 늘 맞는다.
    그래서 generate 는 후보 둘을 다 돌려준다(관절 8개, CAND 순서)

    python train/synth_wing.py [장 수=24]   → work/synth_wing_look.jpg (눈으로 보기)
"""

import math
import sys
from pathlib import Path

import cv2
import numpy as np

ORDER = ["body", "head", "wing_root", "wing_mid", "wing_tip"]                      # 모델이 내는 관절 (날개 하나)
CAND = ["body", "head", "wing1_root", "wing1_mid", "wing1_tip", "wing2_root", "wing2_mid", "wing2_tip"]   # generate 가 돌려주는 후보 (날개 둘까지)


def pick_one(pts: np.ndarray) -> np.ndarray:
    """후보 8점 → 날개 하나 5점. 더 긴 날개, 비슷하면 끝이 더 왼쪽인 것"""
    a, b = np.hypot(*(pts[4] - pts[2])), np.hypot(*(pts[7] - pts[5]))
    first = (pts[4, 0] <= pts[7, 0]) if abs(a - b) <= 0.1 * max(a, b, 1e-6) else a > b
    return pts[[0, 1, 2, 3, 4]] if first else pts[[0, 1, 5, 6, 7]]


def to_service(pts: np.ndarray) -> dict:
    """5점 → 서비스 관절 이름 8개 (날개 2 는 날개 1 에 겹친다)"""
    j = dict(zip(ORDER, pts))
    return {"body": j["body"], "head": j["head"], **{f"wing{k}_{part}": j[f"wing_{part}"] for k in (1, 2) for part in ("root", "mid", "tip")}}
S = 448


def _poly(m: np.ndarray, pts) -> None:  # noqa: ANN001
    cv2.fillPoly(m, [np.round(np.array(pts, float)).astype(np.int32)], 255)


def _line(m: np.ndarray, pts, w: float) -> None:  # noqa: ANN001
    cv2.polylines(m, [np.round(np.array(pts, float) * 4).astype(np.int32)], False, 255, max(1, int(round(w))), cv2.LINE_AA, shift=2)


def _ell(m: np.ndarray, c, ax, ang: float = 0.0) -> None:  # noqa: ANN001
    cv2.ellipse(m, (int(round(c[0])), int(round(c[1]))), (max(1, int(round(ax[0]))), max(1, int(round(ax[1])))), ang, 0, 360, 255, -1)


def _leaf(base: np.ndarray, tip: np.ndarray, width: float, rng: np.random.Generator, jag: bool) -> np.ndarray:
    """뿌리(base)에서 끝(tip)으로 가는 잎 꼴. width = 가장 넓은 곳의 반 너비. jag 면 뒤쪽 가장자리를 깃처럼 들쭉날쭉하게"""
    d = tip - base
    n = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1.0)
    t = np.linspace(0, 1, 14)
    prof = np.sin(np.pi * t ** rng.uniform(0.6, 1.3)) * width                 # 너비가 불룩한 자리를 흔든다
    a = base + t[:, None] * d + n * prof[:, None] * rng.uniform(0.5, 1.0)
    back = prof * rng.uniform(0.5, 1.0)
    if jag:
        back = back * (1 + 0.45 * (np.arange(14) % 2))
    b = base + t[:, None] * d - n * back[:, None]
    return np.r_[a, b[::-1]]


def _wing_points(wing: np.ndarray, body: np.ndarray):  # noqa: ANN201
    """날개 칸(몸통을 뺀 것)에서 뿌리 · 가운데 · 끝. 몸 밖으로 거의 안 나왔으면 None"""
    only = (wing > 127) & ~(body > 127)
    if only.sum() < 250:
        return None
    near = cv2.dilate((body > 127).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    ty, tx = np.nonzero(only & near)
    yy, xx = np.nonzero(only)
    if not len(tx):
        return None
    root = np.array([tx.mean(), ty.mean()])
    k = int(np.argmax(np.hypot(xx - root[0], yy - root[1])))
    tip = np.array([xx[k], yy[k]], float)
    if np.hypot(*(tip - root)) < 18:
        return None
    return root, (root + tip) / 2, tip


def _side_bird(rng: np.random.Generator):  # noqa: ANN202
    u = rng.uniform
    body, rest, wings = (np.zeros((S, S), np.uint8) for _ in range(3))
    rest_wings = []
    cx, cy = S / 2 + u(-25, 15), S / 2 + u(-5, 45)
    a = u(55, 105)
    b = a * u(0.5, 0.9)
    tilt = u(-25, 12)                                     # 음수 = 머리 쪽이 들림
    _ell(body, (cx, cy), (a, b), tilt)
    co, si = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))

    def on(fx: float, fy: float) -> np.ndarray:           # 몸통 타원 좌표(-1 ~ 1) → 그림 좌표
        return np.array([cx + fx * a * co - fy * b * si, cy + fx * a * si + fy * b * co])

    # 머리 · 목 · 부리
    big = rng.random() < 0.2                              # 병아리처럼 머리가 큰 그림
    hr = b * (u(0.75, 1.0) if big else u(0.38, 0.7))
    reach = u(0.0, 0.25) if rng.random() < 0.75 else u(0.4, 1.3)      # 목 길이 (긴 목: 백조 · 타조)
    ang = math.radians(u(-80, -15))
    n0 = on(u(0.55, 0.85), -u(0.25, 0.6))
    hc = n0 + (hr * 0.7 + reach * a) * np.array([math.cos(ang), math.sin(ang)])
    _line(rest, [n0, hc], hr * (u(0.5, 0.9) if reach > 0.3 else u(1.0, 1.5)))
    _ell(rest, hc, (hr * u(0.95, 1.2), hr * u(0.85, 1.0)), u(-20, 20))
    if rng.random() < 0.85:
        bl = hr * u(0.35, 1.3)
        _poly(rest, [hc + [hr * 0.8, -hr * u(0.15, 0.4)], hc + [hr * 0.8 + bl, hr * u(-0.1, 0.3)], hc + [hr * 0.8, hr * u(0.2, 0.45)]])
    if rng.random() < 0.12:                               # 볏
        _ell(rest, hc + [u(-0.3, 0.2) * hr, -hr], (hr * u(0.3, 0.6), hr * u(0.3, 0.6)))
    # 꼬리
    kind = rng.random()
    if kind > 0.15:
        t0 = on(-0.9, u(-0.2, 0.1))
        tl = a * (u(0.3, 0.9) if kind < 0.85 else u(1.0, 1.8))
        ta = math.radians(u(150, 215))
        end = t0 + tl * np.array([math.cos(ta), math.sin(ta)])
        sp = tl * u(0.15, 0.5)
        _poly(rest, [t0 + [0, -b * 0.25], end + [0, -sp], end + [0, sp], t0 + [0, b * 0.25]])
    # 다리 (가는 선: 날개로 잘못 보면 안 된다)
    for dx in ([], [0.0], [-0.25, 0.25])[int(rng.choice([0, 1, 2], p=[0.2, 0.2, 0.6]))]:
        top = on(dx + u(-0.1, 0.1), 0.7)
        ll = b * u(0.5, 1.6)
        foot = top + [u(-0.15, 0.15) * ll, b * 0.3 + ll]
        w = u(3, 7)
        _line(rest, [top, foot], w)
        if rng.random() < 0.6:
            _line(rest, [foot - [u(0, 8), 0], foot + [u(8, 22), 0]], w)
    # 날개: 몸 안(없음) · 등 위로 하나 · 둘
    kind = rng.random()
    count = 0 if kind < 0.3 else 1 if kind < 0.85 else 2
    if count == 0 and rng.random() < 0.5:                 # 몸 가장자리로 살짝 삐져나온 몸 안 날개: 날개로 세지 않는다
        _ell(rest, on(u(-0.3, 0.1), u(-0.5, 0.2)), (a * u(0.4, 0.6), b * u(0.3, 0.5)), tilt + u(-25, 10))
    for k in range(count):
        base = on(u(-0.35, 0.3) - 0.25 * k, -u(0.55, 0.85))
        wl = a * (u(0.7, 1.4) if rng.random() < 0.7 else u(1.4, 2.2))
        wa = math.radians(u(-150, -70) if rng.random() < 0.85 else u(-70, -30))     # 뒤 위로 · 가끔 앞 위로
        tip = base + wl * np.array([math.cos(wa), math.sin(wa)])
        one = np.zeros((S, S), np.uint8)
        _poly(one, _leaf(base, tip, wl * u(0.18, 0.42), rng, rng.random() < 0.3))
        rest_wings.append(one)
        wings |= one
    return body, rest, rest_wings, np.array([cx, cy]), hc


def _top_view(rng: np.random.Generator):  # noqa: ANN202
    u = rng.uniform
    body, rest = np.zeros((S, S), np.uint8), np.zeros((S, S), np.uint8)
    cx, cy = S / 2 + u(-15, 15), S / 2 + u(-10, 25)
    dragon = rng.random() < 0.35
    bl = u(120, 200) if dragon else u(70, 140)            # 몸 길이
    bw = bl * (u(0.05, 0.09) if dragon else u(0.1, 0.22))
    lean = math.radians(u(-18, 18))
    ax = np.array([math.sin(lean), -math.cos(lean)])      # 머리 쪽
    sd = np.array([-ax[1], ax[0]])                        # 오른쪽
    c = np.array([cx, cy])
    _line(body, [c - ax * bl / 2, c + ax * bl / 2], bw * 2)
    hr = bw * u(1.0, 1.8)
    hc = c + ax * (bl / 2 + hr * u(0.3, 0.9))
    _ell(rest, hc, (hr, hr * u(0.85, 1.1)))
    if rng.random() < 0.6:                                # 더듬이
        for s in (-1, 1):
            _line(rest, [hc, hc + ax * hr * u(1.5, 3.5) + sd * s * hr * u(0.6, 2.2)], u(2, 4))
    wl = bl * (u(0.7, 1.2) if dragon else u(0.6, 1.3))
    pairs = 2 if rng.random() < (0.8 if dragon else 0.55) else 1
    same = rng.random() < 0.8                             # 왼쪽 · 오른쪽을 같은 꼴로 (아이마다 삐뚤게도 그린다)
    spec = None
    out = []
    for s in (-1, 1):
        if spec is None or not same:
            spec = [(u(0.05, 0.35), u(-70, -5) if not dragon else u(-25, 5), u(0.8, 1.15), u(0.3, 0.6) if not dragon else u(0.08, 0.18)),
                    (u(-0.35, 0.0), u(5, 70) if not dragon else u(-5, 30), u(0.5, 1.0), u(0.3, 0.6) if not dragon else u(0.08, 0.18))][:pairs]
            if pairs == 1:
                spec = [(u(-0.1, 0.25), u(-45, 30), u(0.8, 1.15), u(0.3, 0.65) if not dragon else u(0.1, 0.2))]
        one = np.zeros((S, S), np.uint8)
        for along, deg, ln, wd in spec:
            base = c + ax * along * bl + sd * s * bw * 0.6
            d = math.radians(deg)
            dirv = sd * s * math.cos(d) + ax * (-math.sin(d))
            _poly(one, _leaf(base, base + dirv * wl * ln, wl * ln * wd, rng, False))
        out.append(one)
    return body, rest, out, c, hc


def _front_bird(rng: np.random.Generator):  # noqa: ANN202
    u = rng.uniform
    body, rest = np.zeros((S, S), np.uint8), np.zeros((S, S), np.uint8)
    cx, cy = S / 2 + u(-15, 15), S / 2 + u(10, 50)
    a = u(45, 85)
    b = a * u(0.9, 1.5)
    _ell(body, (cx, cy), (a, b))
    hr = a * u(0.5, 0.95)
    hc = np.array([cx + u(-0.1, 0.1) * a, cy - b - hr * u(0.3, 0.8)])
    _ell(rest, hc, (hr, hr * u(0.85, 1.05)))
    if rng.random() < 0.5:
        _poly(rest, [hc + [-hr * 0.25, hr * 0.1], hc + [hr * 0.25, hr * 0.1], hc + [0, hr * u(0.5, 0.9)]])
    for s in (-1, 1):
        if rng.random() < 0.8:
            top = np.array([cx + s * a * u(0.2, 0.5), cy + b * 0.85])
            foot = top + [0, b * u(0.25, 0.7)]
            _line(rest, [top, foot], u(3, 7))
            _line(rest, [foot - [10, 0], foot + [10, 0]], u(3, 6))
    wl, wd, deg, at = a * u(1.0, 2.2), u(0.2, 0.42), u(-65, 25), u(-0.5, 0.1)
    out = []
    for s in (-1, 1):
        if rng.random() < 0.2:
            wl, wd, deg, at = a * u(1.0, 2.2), u(0.2, 0.42), u(-65, 25), u(-0.5, 0.1)
        base = np.array([cx + s * a * 0.75, cy + at * b])
        d = math.radians(deg)
        one = np.zeros((S, S), np.uint8)
        _poly(one, _leaf(base, base + wl * np.array([s * math.cos(d), math.sin(d)]), wl * wd, rng, rng.random() < 0.3))
        out.append(one)
    return body, rest, out, np.array([cx, cy]), hc


def generate(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """(마스크 bool SxS, 후보 관절 8x2: CAND 순서). 날개 하나로 줄이기는 pick_one"""
    kind = rng.random()                                   # 옆모습 새가 기준이라 가장 많이
    body, rest, wings, bc, hc = (_side_bird if kind < 0.7 else _top_view if kind < 0.88 else _front_bird)(rng)
    solid = body | rest                                   # 날개를 뺀 몸 (머리 · 꼬리 · 다리 포함): 날개 뿌리는 여기에 닿는 자리
    found = [p for p in (_wing_points(w, solid) for w in wings) if p is not None]
    found.sort(key=lambda p: p[2][0])                     # 끝이 왼쪽인 것이 wing1
    found = found[:2]
    if not found:
        found = [(bc, bc, bc)]
    if len(found) == 1:
        found = found * 2
    m = solid.copy()
    for w in wings:
        m |= w
    mask = m > 127
    if rng.random() < 0.15:                               # 속이 빈 선 그림
        k = int(rng.uniform(4, 9))
        inner = cv2.erode(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
        mask = mask & ~(inner > 0)
    pts = [bc, hc] + [p for trio in found for p in trio]
    return mask, np.array(pts, float)


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    rng = np.random.default_rng(1120)
    cols = 6
    sheet = np.full((-(-count // cols) * 300, cols * 300, 3), 255, np.uint8)
    for i in range(count):
        mask, pts = generate(rng)
        im = cv2.cvtColor(mask.astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)
        for k, (x, y) in zip(ORDER, pick_one(pts)):
            c = (60, 170, 0) if k == "body" else (0, 140, 255) if k == "head" else (50, 40, 210)
            cv2.circle(im, (int(x), int(y)), 4 if k.endswith("_mid") else 8, c, -1)
        sheet[(i // cols) * 300:(i // cols) * 300 + 300, (i % cols) * 300:(i % cols) * 300 + 300] = cv2.resize(im, (300, 300), interpolation=cv2.INTER_AREA)
    out = Path(__file__).resolve().parent.parent / "work/synth_wing_look.jpg"
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(out)
