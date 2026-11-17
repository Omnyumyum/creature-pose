"""몸통 세 점(엉덩이 · 어깨 · 목)을 다리 자리에서 계산한다 (2026-11-17, 사용자 결정: 규칙 자리로 통일).

사람이 놓는 자리와 서비스 규칙의 자리가 달라(100장 시험: 사람은 엉덩이를 더 위 · 꼬리 쪽, 어깨를 더 아래에 놓음) 정답이 흔들렸다.
그래서 몸통 세 점은 사람이 놓지 않고, 사람이 맞춘 다리 뿌리(「다리 위」 점)와 몸 마스크에서
drawtale-ai runtime/ai_server/quadruped.py find_joints 와 같은 식으로 놓는다.

  배 선 belly  = 보이는 다리 뿌리들의 높이 가운데 값          (규칙: 다리 구간의 맨 윗줄)
  뒤 bx · 앞 fx = 뒷다리 · 앞다리 뿌리의 가로 평균, span = |fx - bx|, 머리 쪽 = 앞다리가 있는 쪽
  엉덩이 = (bx + 머리 쪽으로 span 의 25%,  배 선에서 등까지의 15% 위)
  어깨   = (fx,                           배 선에서 등까지의 55% 위)
  목     = (fx + 머리 쪽으로 span 의 8%,   배 선에서 등까지의 65% 위)
  등 = 그 세로줄에서 마스크가 처음 나오는 높이

마스크는 로컬 AI 서버 분석이 만든 오린 그림(cutout)의 투명도. 그림을 바로 세운 각도로 돌려 분석하므로 모든 계산은 세운 화면 좌표에서 하고
원본 좌표로 되돌린다. 마스크는 <묶음>/masks/ 에 남겨 다시 쓴다(data/ 아래라 커밋되지 않는다).
"""

import io
import math
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from build_testset import analyze

BODY = ("hip", "torso", "neck")


def rotated(src: Path, deg: float) -> Image.Image:
    im = Image.open(src).convert("RGB")
    return im.rotate(-deg, expand=True, fillcolor="white", resample=Image.BICUBIC) if deg % 360 else im   # PIL 은 반시계가 양수


def mask_path(folder: Path, name: str, deg: float) -> Path:
    return folder / "masks" / f"{Path(name).stem}_r{int(round(deg)) % 360}.png"


def analyze_upright(folder: Path, name: str, deg: float, facing: str | None = None) -> tuple[dict | None, tuple[int, int]]:
    """그림을 세워 분석하고 마스크를 남긴다. (분석 결과, 세운 그림 크기)"""
    rot = rotated(folder / Path(name).name, deg)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "upright.png"
        rot.save(tmp)
        r = analyze(tmp, facing, cutout=True)
    if r and r.get("_cutout"):
        alpha = np.array(Image.open(io.BytesIO(r.pop("_cutout"))).convert("RGBA"))[..., 3]
        (folder / "masks").mkdir(exist_ok=True)
        Image.fromarray(((alpha > 127) * 255).astype(np.uint8)).save(mask_path(folder, name, deg))
    return r, rot.size


def get_mask(folder: Path, name: str, deg: float) -> np.ndarray | None:
    p = mask_path(folder, name, deg)
    if not p.exists():
        analyze_upright(folder, name, deg)
    return np.array(Image.open(p)) > 127 if p.exists() else None


def body_points(folder: Path, name: str, deg: float, joints: dict) -> dict | None:
    """joints: 원본 좌표 {이름: [x, y, 보임]}. 몸통 세 점을 원본 좌표로 돌려준다. 앞 · 뒤 다리가 한쪽이라도 없으면 None"""
    mask = get_mask(folder, name, deg)
    if mask is None or not mask.any():
        return None
    w, h = Image.open(folder / Path(name).name).size
    H, W = mask.shape
    th = math.radians(deg)
    co, si = math.cos(th), math.sin(th)

    def up(p: list) -> tuple[float, float]:
        dx, dy = p[0] - w / 2, p[1] - h / 2
        return W / 2 + dx * co - dy * si, H / 2 + dx * si + dy * co

    def down(x: float, y: float) -> list:
        dx, dy = x - W / 2, y - H / 2
        return [round(min(max(w / 2 + dx * co + dy * si, 0), w)), round(min(max(h / 2 - dx * si + dy * co, 0), h))]

    tops = {s: [up(joints[k]) for k in (f"right_hip_{s}", f"left_hip_{s}") if k in joints and (len(joints[k]) < 3 or joints[k][2])]
            for s in "bf"}
    if not tops["b"] or not tops["f"]:
        return None
    belly = float(np.median([y for s in "bf" for _, y in tops[s]]))
    bx, fx = float(np.mean([x for x, _ in tops["b"]])), float(np.mean([x for x, _ in tops["f"]]))
    toward, span = (1 if fx >= bx else -1), abs(fx - bx)
    first = float(np.where(mask.any(axis=1))[0][0])

    def at(x: float, up_by: float) -> list:
        col = mask[:, min(max(int(round(x)), 0), W - 1)]
        top = float(np.argmax(col)) if col.any() else first
        return down(x, belly - max(belly - top, 0.0) * up_by)

    return {"hip": at(bx + toward * span * 0.25, 0.15), "torso": at(fx, 0.55), "neck": at(fx + toward * span * 0.08, 0.65)}
