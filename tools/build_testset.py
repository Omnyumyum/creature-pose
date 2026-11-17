"""네 발 시험 세트 만들기 (2026-11-17): 고른 그림을 data/testset/quadruped/ 로 모으고, 지금 서비스 규칙으로 관절 초안을 단다.

그림은 아이 그림 · 비상업 데이터가 섞여 있어 저장소에 올리지 않는다(data/ 는 git 이 무시). 재기 · 확인용으로만 쓴다.
그림은 방향을 바로잡고 흰 바탕에 올려 긴 변 1000 이하 PNG 로 저장한다. 정답 좌표는 이 PNG 기준이다.
관절 초안은 로컬 AI 서버(AI_URL, 기본 http://127.0.0.1:8001)의 분석(form=quadruped) 결과. 서버가 없으면 초안 없이 그림만 모은다.

    python tools/build_testset.py     → data/testset/quadruped/*.png, data/testset/quadruped/auto.json
그다음 python tools/make_labeler.py  → data/testset/label_quadruped.html (점을 끌어 고치고 JSON 으로 내보내기)
"""

import glob
import json
import os
import uuid
from pathlib import Path
from urllib import request

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/testset/quadruped"
HOME = Path.home()
AI = os.getenv("AI_URL", "http://127.0.0.1:8001") + "/internal/v1"

# (출처 이름, 폴더, 고른 파일 이름 끝부분, 라이선스 메모). 모아 보기를 눈으로 보고 네 발로 선 그림만 골랐다
PICKS = [
    ("kids", HOME / "Downloads/애들그림", ["_02.jpg", "_04.jpg", "_08.jpg", "_09.jpg", "_15.jpg", "_22.jpg"],
     "실제 아이 그림, 로컬만"),
    ("qr", HOME / "Desktop/hankan-story/experiments/quality-review/out/src",
     ["00db4e4ddd.jpg", "029557dd07.jpg", "05996a55c8.jpg", "08175e3136.jpg", "089e91900c.jpg", "0971ac2d89.jpg",
      "09afafe9fe.jpg", "0a6a9db4b5.jpg", "0bd6108af2.jpg", "0bf303d228.jpg", "0d9914ce7d.jpg", "0e6c94439b.jpg",
      "0f818cb5ee.jpg", "cm_c062.jpg", "cm_c069.jpg", "0737f6b4a4.jpg", "0cca355362.jpg"],
     "Meta Amateur Drawings(CC BY-NC) · Wikimedia Commons, 재기용만"),
    ("own", HOME / "Desktop/모델검증용이미지", ["582_08.jpg"], "팀이 그린 그림"),
    ("synth", HOME / "Desktop/hankan-story/experiments/animal-monster/screen_set",
     ["/dog_small_fill.png", "/dog_wide_fill.png", "/dog_wide_left.png", "/dog_wide_line.png", "/giraffe_wide.png",
      "/real_dog_wide.png"], "직접 만든 합성 그림"),
]


def prepare(src: str, dst: Path) -> None:
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
    im = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB")
    im.thumbnail((1000, 1000))
    im.save(dst)


def analyze(path: Path, facing: str | None = None, cutout: bool = False) -> dict | None:
    """facing: 머리 쪽 left · right 를 알려 주면 규칙이 그쪽을 머리로 본다. 없으면 규칙이 추측한다.
    cutout: 분석이 만든 오린 그림(PNG, 투명도 = 몸 마스크)을 결과의 "_cutout" 에 바이트로 붙인다"""
    b = uuid.uuid4().hex
    side = f'--{b}\r\nContent-Disposition: form-data; name="facing"\r\n\r\n{facing}\r\n' if facing in ("left", "right") else ""
    body = (f'--{b}\r\nContent-Disposition: form-data; name="form"\r\n\r\nquadruped\r\n{side}'
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: image/png\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    try:
        req = request.Request(AI + "/analyze", data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
        r = json.loads(request.urlopen(req, timeout=300).read())
        if r.get("request_id"):
            if cutout:
                try:
                    r["_cutout"] = request.urlopen(f"{AI}/sessions/{r['request_id']}/cutout", timeout=60).read()
                except Exception:  # noqa: BLE001
                    pass
            request.urlopen(request.Request(f"{AI}/sessions/{r['request_id']}", method="DELETE"), timeout=60).read()
        return r
    except Exception as e:  # noqa: BLE001
        print("  분석 못 함:", str(e)[:80])
        return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    auto_path = OUT / "auto.json"
    auto = json.load(open(auto_path, encoding="utf-8")) if auto_path.exists() else {}
    for source, folder, ends, note in PICKS:
        files = sorted(glob.glob(str(folder / "*")))
        for k, end in enumerate(ends):
            hit = [f for f in files if f.replace("\\", "/").endswith(end)]
            if not hit:
                print("없음", source, end)
                continue
            name = f"{source}_{k:02d}.png"
            if not (OUT / name).exists():
                prepare(hit[0], OUT / name)
            if name in auto:
                continue
            r = analyze(OUT / name)
            w, h = Image.open(OUT / name).size
            auto[name] = {"source": source, "note": note, "width": w, "height": h,
                          "found": bool(r and r.get("success") and r.get("joints_found")),
                          "message": (r or {}).get("message"),
                          "joints": {j["name"]: [j["x"], j["y"]] for j in (r or {}).get("joints", [])}}
            json.dump(auto, open(auto_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(name, "관절 찾음" if auto[name]["found"] else "못 찾음 또는 기본 뼈대", flush=True)
    print("모두", len(auto), "장")


if __name__ == "__main__":
    main()
