"""Quick, Draw! 시험 100장 만들기 (2026-11-17): 「머리 쪽만 사람이 누르고 → 규칙 → 틀린 것만 고치기」가 되는지 재는 묶음.

종류 17개에서 「몸 전체 옆모습」 자동 고르기(quad_pseudo/pick_rule.py)를 통과한 그림을 고르게 뽑아 굵은 선으로 그린다.
굵은 선은 quad_pseudo 보고서에서 규칙이 가장 잘 맞은 꼴. 규칙 초안은 여기서 달지 않는다(머리 쪽을 누르면 그때 단다).
Quick, Draw! (Google, CC BY 4.0). 받은 파일 · 그린 그림은 data/ 아래라 커밋되지 않는다.

    work/venv/Scripts/python tools/build_qdset.py [--set qd_300] [장 수=100]   (opencv 가 필요해 work/venv 로 돌린다)
    → data/qd_pilot/*.png, data/qd_pilot/auto.json
그다음 python tools/make_labeler.py --set qd_pilot, python tools/label_server.py --set qd_pilot
"""

import json
import random
import sys
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "quad_pseudo"))

import cv2  # noqa: E402
import features  # noqa: E402
import qd  # noqa: E402
from pick_rule import body_side  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from sets import SETS  # noqa: E402

NAME = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "qd_pilot"
OUT = ROOT / SETS[NAME][0]
URL = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{}.ndjson"
PART = 6_000_000      # 종류마다 파일 앞 6MB 만 (quad_pseudo 와 같게)
SKIP = 3000           # quad_pseudo 가 쓴 앞 3,000장은 건너뛴다(눈 매기기에 쓰인 그림과 겹치지 않게)
# 표시 도구의 동물 종류 이름 (tools/make_labeler.py KINDS)
KIND = {"horse": "말", "cow": "소", "sheep": "양", "pig": "돼지", "dog": "강아지", "cat": "고양이", "elephant": "코끼리",
        "giraffe": "기린", "zebra": ("기타", "얼룩말"), "lion": "호랑이 · 사자", "tiger": "호랑이 · 사자", "camel": ("기타", "낙타"),
        "rhinoceros": ("기타", "코뿔소"), "crocodile": "악어 · 도마뱀", "mouse": "쥐 · 토끼", "raccoon": ("기타", "너구리"),
        "squirrel": ("기타", "다람쥐")}


def fetch(cat: str) -> None:
    f = qd.DATA / f"{cat}.part"
    if f.exists():
        return
    qd.DATA.mkdir(parents=True, exist_ok=True)
    req = request.Request(URL.format(cat), headers={"Range": f"bytes=0-{PART - 1}"})
    f.write_bytes(request.urlopen(req, timeout=120).read())
    print("받음", cat, f.stat().st_size, flush=True)


def main() -> None:
    total = int(sys.argv[-1]) if sys.argv[-1].isdigit() else 100
    used = set()        # 다른 Quick, Draw! 묶음에 이미 들어간 그림은 뺀다
    for folder, _, _ in SETS.values():
        f = ROOT / folder / "auto.json"
        if f.exists() and ROOT / folder != OUT:
            used |= {a.get("key") for a in json.load(open(f, encoding="utf-8")).values()}
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(1117)
    per = -(-total // len(qd.CATS))
    picked = []
    for cat in qd.CATS:
        fetch(cat)
        ds = qd.load(cat, 100000)[SKIP:]
        rng.shuffle(ds)
        got = []
        for d in ds:
            if d["key"] not in used and body_side(features.feats(d)):
                got.append(d)
                if len(got) >= per:
                    break
        picked.append(got)
        print(cat, "고른 수", len(got), flush=True)
    # 종류를 돌아가며 한 장씩, 모두 total 장
    order = [d for row in zip(*picked) for d in row][:total]
    auto = {}
    for d in order:
        name = f"qd_{d['cat']}_{d['key']}.png"
        img, _ = qd.render(d, "thick")
        cv2.imwrite(str(OUT / name), img)
        k = KIND[d["cat"]]
        auto[name] = {"source": "quickdraw", "note": f"Quick, Draw! {d['cat']} (Google, CC BY 4.0)", "width": qd.SIZE, "height": qd.SIZE,
                      "found": False, "message": None, "joints": {}, "cat": d["cat"], "key": d["key"],
                      "kind": k if isinstance(k, str) else k[0], "kind_note": "" if isinstance(k, str) else k[1]}
    json.dump(auto, open(OUT / "auto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("모두", len(auto), "장 →", OUT)


if __name__ == "__main__":
    main()
