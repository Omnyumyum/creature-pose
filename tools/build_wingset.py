"""날개형 시험 세트 후보 모으기 (2026-11-20): 새 · 나비 · 잠자리 그림을 data/testset/winged/ 로 모은다. 정답은 tools/wing_labeler.py 에서 표시한다.

후보를 넉넉히 모으고(약 60장), 표시할 때 「못 씀」으로 걸러 20 ~ 30장을 남긴다.
  qd      Quick, Draw! (Google, CC BY 4.0) 의 날개 달린 종류 7개에서 고르게, 굵은 선으로 그림
  own     직접 그린 그림 (experiments/creature-picker/drawings)
  synth   직접 만든 합성 그림 (experiments/head-check/birds: 옆모습 새 경우의 수)
  kids    실제 아이 그림은 여기서 모으지 않는다. 있으면 data/testset/winged/ 에 kids_NN.png 로 넣고 다시 돌리면 목록에 들어간다(로컬만)
그림 · 받은 파일은 data/ 아래라 커밋되지 않는다.

    work/venv/Scripts/python tools/build_wingset.py [종류마다 장 수=7]   → data/testset/winged/*.png, auto.json
"""

import json
import random
import sys
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "quad_pseudo"))

import cv2  # noqa: E402
import qd  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

OUT = ROOT / "data/testset/winged"
EXP = ROOT.parent
URL = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{}.ndjson"
PART = 6_000_000
CATS = {"bird": "새", "duck": "오리", "owl": "부엉이", "parrot": "앵무새", "butterfly": "나비", "mosquito": "모기", "bee": "벌"}      # Quick, Draw! 에 잠자리(dragonfly)는 없다


def fetch(cat: str) -> None:
    f = qd.DATA / f"{cat}.part"
    if f.exists():
        return
    qd.DATA.mkdir(parents=True, exist_ok=True)
    req = request.Request(URL.format(cat), headers={"Range": f"bytes=0-{PART - 1}"})
    f.write_bytes(request.urlopen(req, timeout=120).read())
    print("받음", cat, f.stat().st_size, flush=True)


def prepare(src: Path, dst: Path) -> tuple[int, int]:
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
    im = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB")
    im.thumbnail((1000, 1000))
    im.save(dst)
    return im.size


def main() -> None:
    per = int(sys.argv[-1]) if sys.argv[-1].isdigit() else 7
    OUT.mkdir(parents=True, exist_ok=True)
    auto = {}
    rng = random.Random(1120)
    for cat, kor in CATS.items():
        fetch(cat)
        ds = qd.load(cat, 4000)
        rng.shuffle(ds)
        for d in ds[:per]:
            name = f"qd_{cat}_{d['key']}.png"
            img, _ = qd.render(d, "thick")
            cv2.imwrite(str(OUT / name), img)
            auto[name] = {"source": "quickdraw", "note": f"Quick, Draw! {cat} (Google, CC BY 4.0)", "kind": kor, "width": qd.SIZE, "height": qd.SIZE}
        print(cat, per, flush=True)
    for i, f in enumerate(sorted((EXP / "creature-picker/drawings").glob("*.png"))):
        name = f"own_{i:02d}.png"
        w, h = prepare(f, OUT / name)
        auto[name] = {"source": "own", "note": f"직접 그린 그림 ({f.name})", "kind": "", "width": w, "height": h}
    birds = sorted((EXP / "head-check/birds").glob("*.png"))
    for i, f in enumerate(birds[:: max(1, len(birds) // 6)][:6]):
        name = f"synth_{i:02d}.png"
        w, h = prepare(f, OUT / name)
        auto[name] = {"source": "synth", "note": f"직접 만든 합성 그림 ({f.name})", "kind": "새", "width": w, "height": h}
    for f in sorted(OUT.glob("kids_*.png")):
        w, h = Image.open(f).size
        auto[f.name] = {"source": "kids", "note": "실제 아이 그림, 로컬만", "kind": "", "width": w, "height": h}
    json.dump(auto, open(OUT / "auto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("모두", len(auto), "장 →", OUT)


if __name__ == "__main__":
    main()
