"""collect.py 결과를 모아 보기 그림과 표로 (2026-11-26).

    work/venv/Scripts/python render_failures/report.py          # out/sheet_{형태}_{쪽}.png + out/flags.json + 표 출력
    work/venv/Scripts/python render_failures/report.py figs     # causes.json 을 읽어 원인별 예시 그림 out/fig_{원인}.png (아이 그림 제외)

그림 한 칸 = [원본 + 찾은 관절] [움직임 지도(장들을 겹친 것)]. 자동 표시(flags)는 후보일 뿐이고, 원인은 사람이 보고 causes.json 에 적는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
EXP = HERE.parent.parent    # collect.py 의 EXP 와 같다 (results.json 의 file 이 이 폴더 기준)
OUT = HERE / "out"
C = 200  # 한 칸

try:
    FONT = ImageFont.truetype("malgun.ttf", 13)
    FONT_B = ImageFont.truetype("malgunbd.ttf", 15)
except OSError:
    FONT = FONT_B = ImageFont.load_default()

COL = {"hip": (60, 160, 70), "body": (60, 160, 70), "head": (230, 150, 20), "tail": (150, 70, 190), "wing": (220, 50, 50)}


def color(name: str) -> tuple:
    for k, v in COL.items():
        if k in name:
            return v
    return (40, 100, 220)


def flags(r: dict) -> list[str]:
    f = []
    if not r.get("ok"):
        return ["분석 실패"]
    if not r.get("joints_found"):
        f.append("기본 뼈대")
    if r.get("render_error"):
        f.append("렌더 실패")
    m = r.get("render")
    if m:
        if m["edge_frames"] > 0:
            f.append("칸 가장자리 닿음")
        if m["area_min"] and m["area_max"] / m["area_min"] > 1.2:
            f.append("넓이 변함")
        if m["move"] < 0.08:
            f.append("거의 안 움직임")
    b, (w, h) = r.get("bbox"), r.get("size", [1, 1])
    if b and (b["right"] - b["left"]) * (b["bottom"] - b["top"]) > 0.9 * w * h and min(w, h) > 400:
        f.append("그림 영역이 사진 전체")
    if r.get("confidence") is not None and r["confidence"] < 0.35:
        f.append("검출 점수 낮음")
    return f


def panel_src(r: dict) -> Image.Image:
    im = Image.open(EXP / r["file"]).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    im = Image.alpha_composite(bg, im).convert("RGB")
    s = C / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))))
    d = ImageDraw.Draw(im)
    b = r.get("bbox")
    if b:
        d.rectangle([b["left"] * s, b["top"] * s, b["right"] * s, b["bottom"] * s], outline=(150, 150, 150))
    for name, x, y in r.get("joints", []):
        d.ellipse([x * s - 3, y * s - 3, x * s + 3, y * s + 3], fill=color(name), outline="white")
    cell = Image.new("RGB", (C, C), "white")
    cell.paste(im, ((C - im.width) // 2, (C - im.height) // 2))
    return cell


def item(key: str, r: dict, label: str | None = None) -> Image.Image:
    im = Image.new("RGB", (2 * C + 6, C + 40), "white")
    im.paste(panel_src(r), (0, 0))
    mv = OUT / r["form"] / f"{key.split('/')[1]}_move.png"
    if mv.exists():
        im.paste(Image.open(mv).convert("RGB").resize((C, C)), (C + 6, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 2 * C + 5, C - 1], outline=(210, 205, 195))
    d.text((2, C + 2), key.split("/")[1][:34], font=FONT, fill=(60, 50, 45))
    d.text((2, C + 20), label if label is not None else " · ".join(flags(r)) or "", font=FONT, fill=(190, 60, 40))
    return im


def sheets(res: dict) -> None:
    per, cols = 20, 4
    for form in sorted({r["form"] for r in res.values()}):
        keys = [k for k in res if res[k]["form"] == form]
        for p in range(0, len(keys), per):
            chunk = keys[p:p + per]
            rows = (len(chunk) + cols - 1) // cols
            W, H = 2 * C + 6, C + 40
            sh = Image.new("RGB", (cols * (W + 10), rows * (H + 8)), "white")
            for i, k in enumerate(chunk):
                sh.paste(item(k, res[k]), ((i % cols) * (W + 10), (i // cols) * (H + 8)))
            sh.save(OUT / f"sheet_{form}_{p // per + 1}.png")


def table(res: dict) -> None:
    fl = {k: flags(r) for k, r in res.items()}
    (OUT / "flags.json").write_text(json.dumps(fl, ensure_ascii=False, indent=1), encoding="utf-8")
    forms = sorted({r["form"] for r in res.values()})
    names = ["분석 실패", "기본 뼈대", "렌더 실패", "칸 가장자리 닿음", "넓이 변함", "거의 안 움직임", "그림 영역이 사진 전체", "검출 점수 낮음"]
    print("형태", "장", *names, "표시 없음", sep=" | ")
    for f in forms:
        ks = [k for k in res if res[k]["form"] == f]
        print(f, len(ks), *[sum(n in fl[k] for k in ks) for n in names], sum(not fl[k] for k in ks), sep=" | ")
    for k, r in res.items():
        if r.get("message") and r["message"] != "Analysis complete" or r.get("render_error") or r.get("error"):
            print(" ", k, "·", r.get("error") or r.get("render_error") or r.get("message"))


def figs(res: dict) -> None:
    causes = json.loads((HERE / "causes.json").read_text(encoding="utf-8"))
    for name, spec in causes["figs"].items():
        keys = [k for k in spec if "kids_" not in k]
        W, H = 2 * C + 6, C + 40
        sh = Image.new("RGB", (len(keys) * (W + 10) - 10, C), "white")
        for i, k in enumerate(keys):
            sh.paste(item(k, res[k], "").crop((0, 0, W, C)), (i * (W + 10), 0))
        sh.save(OUT / f"fig_{name}.png")
        print("fig", name, len(keys))


if __name__ == "__main__":
    res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    if "figs" in sys.argv:
        figs(res)
    else:
        sheets(res)
        table(res)
