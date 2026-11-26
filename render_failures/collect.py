"""비휴머노이드 렌더링 실패 원인 수집 (2026-11-26).

형태별 시험 그림을 로컬 AI 서버(/internal/v1/analyze → /render)에 넣고, 그림마다 어디서 어떻게 어긋나는지 잰다.
결과는 out/results.json. 분류와 모아 보기는 report.py.

    work/venv/Scripts/python render_failures/collect.py            # 전부 (저장소 맨 위에서)
    work/venv/Scripts/python render_failures/collect.py --limit 3  # 형태마다 3장만 (시험)

그림 모음(SETS)은 이미 PC 에 있는 것만 쓴다(data/testset 과, 있으면 옆 폴더 animal-monster · creature-picker 의 그림). 없는 폴더는 건너뛴다. 아이 그림(kids_)도 돌리지만 report.py 가 모아 보기 그림에서는 뺀다.
AI 서버: 환경 변수 AI_URL (기본 http://127.0.0.1:8001)
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
REPO = HERE.parent          # creature-pose
EXP = REPO.parent           # 그 위 실험 폴더 (animal-monster · creature-picker 가 있으면 함께 돌린다)
OUT = HERE / "out"
BASE = os.environ.get("AI_URL", "http://127.0.0.1:8001") + "/internal/v1"
MOTION = "walk"

T = REPO / "data" / "testset"
AM = EXP / "animal-monster"
CP = EXP / "creature-picker" / "drawings"


def pick(folder: Path, *names: str) -> list[Path]:
    return [folder / n for n in names if (folder / n).exists()]


SETS: dict[str, list[Path]] = {
    "quadruped": sorted((T / "quadruped").glob("*.png")) + sorted((AM / "drawings_quad").glob("*.png"))
    + pick(AM / "drawings", "animal_cat.png", "animal_dog.png", "animal_giraffe.png", "real_pig.png", "monster_5legs.png"),
    "winged": sorted((T / "winged").glob("*.png")) + sorted(CP.glob("*.png")) + sorted((CP / "cases").glob("*.png"))
    + pick(AM / "drawings", "animal_bird.png"),
    "chain": pick(AM / "drawings", "snake_coil.png", "snake_line.png", "snake_s.png", "worm.png"),
    "finned": pick(AM / "drawings", "animal_fish.png"),
    "radial": pick(AM / "drawings", "monster_octopus.png", "monster_spiky.png", "monster_eyestalks.png", "monster_blob.png", "monster_2heads.png", "real_garlic.png"),
}


def post(path: str, fields: dict, files: dict | None = None) -> dict:
    b = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fn, data) in (files or {}).items():
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                 "Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(BASE + path, data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return json.load(urllib.request.urlopen(req, timeout=600))


def frames(sheet: Image.Image, cell: int, n: int) -> list[np.ndarray]:
    cols = sheet.width // cell
    return [np.asarray(sheet.crop(((i % cols) * cell, (i // cols) * cell, (i % cols + 1) * cell, (i // cols + 1) * cell))) for i in range(n)]


def measure(fr: list[np.ndarray]) -> dict:
    """프레임들에서 재는 값. 판정은 report.py 가 한다."""
    al = [f[..., 3] > 30 for f in fr]
    area = np.array([a.mean() for a in al])
    first = al[0]
    # 가장자리 닿음: 칸 테두리 2px 띠에 그림이 닿은 프레임 비율
    def edge(a: np.ndarray) -> bool:
        return bool(a[:2].any() or a[-2:].any() or a[:, :2].any() or a[:, -2:].any())
    # 움직임: 첫 장과 달라진 화소 비율의 최대(그림 넓이 대비)
    move = max(float((a ^ first).mean()) for a in al) / max(float(first.mean()), 1e-6)
    ys, xs = np.nonzero(first)
    box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    fill = float(first.mean()) / (((box[2] - box[0] + 1) * (box[3] - box[1] + 1)) / first.size) if box else 0.0
    return {
        "area_first": round(float(area[0]), 4), "area_min": round(float(area.min()), 4), "area_max": round(float(area.max()), 4),
        "edge_frames": round(sum(edge(a) for a in al) / len(al), 2), "move": round(move, 3),
        "box": box, "fill": round(fill, 3),
    }


def overlay(fr: list[np.ndarray]) -> Image.Image:
    cell = fr[0].shape[0]
    acc = np.zeros((cell, cell), float)
    for f in fr:
        acc = np.maximum(acc, (f[..., 3] / 255) * 0.35)
    first = fr[0].astype(float)
    a = first[..., 3:4] / 255
    rgb = np.ones((cell, cell, 3)) * 255 * (1 - acc[..., None]) + np.array([90, 120, 220]) * acc[..., None]
    rgb = rgb * (1 - a) + first[..., :3] * a
    return Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).resize((256, 256))


def run_one(path: Path, form: str, out: Path) -> dict:
    src = Image.open(path)
    res: dict = {"form": form, "file": str(path.relative_to(EXP)).replace("\\", "/"), "size": list(src.size)}
    t = time.time()
    a = post("/analyze", {"form": form}, {"file": (path.name, path.read_bytes())})
    res.update(analyze_s=round(time.time() - t, 1), ok=bool(a.get("success")), joints_found=a.get("joints_found"),
               confidence=a.get("confidence"), message=a.get("message"), bbox=a.get("bbox"),
               n_joints=len(a.get("joints") or []), form_out=a.get("form"))
    if not a.get("success"):
        return res
    res["joints"] = [[j["name"], j["x"], j["y"]] for j in a["joints"]]
    t = time.time()
    r = post("/render", {"request_id": a["request_id"], "joints": json.dumps(a["joints"]), "motion": MOTION, "sprite": "true"})
    res["render_s"] = round(time.time() - t, 1)
    if "sprite" not in r:
        res["render_error"] = r.get("message")
        return res
    sheet = Image.open(io.BytesIO(base64.b64decode(r["sprite"]))).convert("RGBA")
    fr = frames(sheet, r["sprite_cell"], r["sprite_frames"])
    res["render"] = measure(fr)
    res["sprite_box"] = r.get("sprite_box")
    stem = path.stem
    overlay(fr).save(out / f"{stem}_move.png")
    Image.fromarray(fr[0]).resize((256, 256)).save(out / f"{stem}_first.png")
    return res


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    results = {}
    rp = OUT / "results.json"
    if rp.exists() and "--fresh" not in sys.argv:
        results = json.loads(rp.read_text(encoding="utf-8"))
    for form, paths in SETS.items():
        out = OUT / form
        out.mkdir(parents=True, exist_ok=True)
        for p in paths[:limit]:
            key = f"{form}/{p.stem}"
            if key in results and "error" not in results[key]:
                continue
            try:
                results[key] = run_one(p, form, out)
            except Exception as e:  # noqa: BLE001
                results[key] = {"form": form, "file": str(p), "ok": False, "error": str(e)}
            r = results[key]
            print(key, "ok" if r.get("ok") else "FAIL", "관절" if r.get("joints_found") else "기본뼈대", r.get("render_s"), r.get("render_error") or r.get("message") or "", flush=True)
            rp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(results), "장")


if __name__ == "__main__":
    main()
